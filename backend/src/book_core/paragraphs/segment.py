"""Paragraph units over one page's ordered streams (Step 7 order with Step 8 roles).

Each stream is read in its order. Between two consecutive lines a boundary score is built from
evidence; a boundary is placed when it reaches BOUNDARY. All lengths are relative to font
size and line pitch (local region pitch, else the book's pitch for the size):

- vertical gap (baseline advance / pitch), ignored when another stream's lines occupy the gap
  (a float interrupting a paragraph never breaks it);
- first-line indent: a line starting clearly after both of its neighbours in the lane (a local
  bump, so text wrapped around a shape does not count) and after the lane's usual start;
- hanging indent: a line starting clearly before a continuation line above it;
- line-end fill: a short last line, used only in mostly justified regions;
- text: sentence terminal / open end / hyphen of the previous line, case of the next line, a
  colon followed by a gap (a displayed quote or list follows);
- style change against the neighbour, list markers, drop caps, same-row fragments;
- Step 4 region type change (heading, caption, figure, table) and Step 7 lane transitions,
  where columns join only when continuation evidence agrees (``reading_order.continuation``).

Furniture, artifact and invisible lines are units of their own and never part of a paragraph.
Heading-like and list-like lines become their own units, kinds ``heading_candidate`` and
``list_item_candidate``. No heading level, list, figure, table or zone is decided.
"""

from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import median

import regex

from book_core.extraction.fingerprints import stable_id
from book_core.model.common import SpanRef
from book_core.paragraphs.geometry import frame
from book_core.paragraphs.lexicon import (
    HYPHENS,
    SOFT_HYPHEN,
    TOKEN,
    hyphen_evidence,
    pitch_for,
)
from book_core.paragraphs.models import (
    REVIEW_BELOW,
    Boundary,
    HyphenDecision,
    LineJoin,
    ParagraphUnit,
    WordJoin,
)
from book_core.reading_order.continuation import beginning, continuation, ending

BOUNDARY = 0.45
INDENT = 0.8  # font sizes
FILL = 2.5  # font sizes short of the region's line end
ROW = 0.35  # font sizes: same baseline
JUSTIFIED = 0.6  # share of region lines reaching the line end
WINDOW = 6  # lines on each side that decide whether a line sits in a hanging-indent block
LANE_CHANGES = frozenset({"next_lane_in_band", "next_band", "continues_across_column"})
TEXT_STREAMS = frozenset(
    {"main", "sidebar", "callout", "figure", "table", "card", "credit", "note"}
)
OWN_UNIT_STREAMS = {"artifact": "artifact", "invisible": "invisible"}
KIND_OF_REGION = {
    "title_candidate": "heading_candidate",
    "heading_candidate": "heading_candidate",
    "caption_candidate": "caption",
    "figure": "figure_text",
    "table_candidate": "table_text",
}
# List markers: bullets U+2022 U+2023 U+2043 U+204C U+204D U+25AA U+25AB U+25CF U+25E6 U+2219
# U+25A0 U+25A1 and dashes U+2013 U+2014; numbers "1." "1)" "(1)", or a number then a tab,
# a U+2002 or U+2003 space, or two spaces. Single-letter markers ("A." "b)" "(c)")
# are matched separately: they count only with sequence evidence or in a hanging-indent
# block, so an initial ("W. Bush") never splits a paragraph. The colon class includes
# FULLWIDTH COLON U+FF1A.
_LIST_MARKER = regex.compile(
    r"^\s*(?:[•‣⁃⁌⁍▪▫●◦∙■□"
    r"–—*]|\(?\p{N}{1,3}[.)])\s+\S"
    r"|^\s*\p{N}{1,3}(?:\t| | |\s{2,})\s*\S"
)
_LETTER_MARKER = regex.compile(r"^\s*(\()?(\p{L})([.)])\s+\S")
_COLON = regex.compile(r"[:：]\s*$")
BOLD, ITALIC = 1 << 4, 1 << 1


@dataclass
class Line:
    id: str
    line: object
    frame: object
    text: str  # NFKC; evidence only
    region: object
    stream_id: str
    stream_kind: str
    role: str
    style: tuple


def _style(store, line):
    weights = Counter()
    for sid in line.span_ids:
        span = store.spans[sid]
        bold = bool(span.flags & BOLD) or "bold" in span.font.casefold()
        italic = bool(span.flags & ITALIC) or "italic" in span.font.casefold()
        family = span.font.split("+", 1)[-1].split("-")[0].casefold()
        weights[(family, round(span.size * 2) / 2, bold, italic)] += max(
            1, len(span.raw_text.strip())
        )
    return weights.most_common(1)[0][0] if weights else ("", 0.0, False, False)


def _confidence(score):
    return round(min(0.97, 0.55 + abs(score - BOUNDARY)), 4)


class PageSegmenter:
    def __init__(self, page, layout, furniture, profile, vocabulary, compounds, navigation=None):
        """``navigation``: {native line id: printed navigation entry id} (Step 6 evidence)."""
        self.page, self.layout, self.furniture = page, layout, furniture
        self.profile, self.vocabulary, self.compounds = profile, vocabulary or {}, compounds or {}
        store = page.store
        region_of = {lid: r for r in layout.regions for lid in r.line_ids}
        role_of = {r.line_id: r.role for r in furniture.roles}
        self.order = furniture.order
        by_id = {line.id: line for line in layout.lines}
        self.lines = {}
        for stream in self.order.streams:
            for lid in stream.line_ids:
                line = by_id[lid]
                self.lines[lid] = Line(
                    lid,
                    line,
                    frame(line),
                    unicodedata.normalize(
                        "NFKC", "".join(store.spans[s].raw_text for s in line.span_ids)
                    ),
                    region_of[lid],
                    stream.id,
                    stream.kind,
                    role_of[lid],
                    _style(store, line),
                )
        self.edge_kind = {(e.source, e.target): e.kind for e in self.order.edges}
        self.stats_of = {}
        self.markers = {}  # line id -> reason, for lines that start a list item
        self.entry_of = {}
        for line in layout.lines:
            entries = {(navigation or {}).get(source) for source in line.source_line_ids}
            if len(entries) == 1 and None not in entries:
                self.entry_of[line.id] = entries.pop()

    # ----------------------------------------------------------------- lane-run statistics
    def runs(self, members):
        """Split a stream into lane runs (no lane change) and compute their statistics."""
        runs, current = [], [members[0]]
        for a, b in zip(members, members[1:], strict=False):
            if self.edge_kind.get((a.id, b.id)) in LANE_CHANGES or a.stream_id != b.stream_id:
                runs.append(current)
                current = []
            current.append(b)
        runs.append(current)
        for run in runs:
            stats = self._stats(run)
            for index, line in enumerate(run):
                window = run[max(0, index - WINDOW) : index + WINDOW + 1]
                local = self._stats(window) if len(window) < len(run) else stats
                self.stats_of[line.id] = {**stats, "hanging": stats["hanging"] and local["hanging"]}

    def _stats(self, run):
        frames = [m.frame for m in run if m.text.strip()] or [run[0].frame]
        advances = [
            b.block - a.block
            for a, b in zip(frames, frames[1:], strict=False)
            if abs(a.size - b.size) <= 0.25 and 0.5 * a.size < b.block - a.block < 3 * a.size
        ]
        size = median(f.size for f in frames)
        ends = sorted(f.end for f in frames)
        edge = ends[int(0.9 * (len(ends) - 1))]
        starts = sorted(f.start for f in frames)
        base = starts[int(0.1 * (len(starts) - 1))]
        full = sum(edge - f.end <= size for f in frames) / len(frames)
        # Hanging indent: continuation lines share one indent, and continue each other more
        # often than base lines follow base lines (index and glossary entries).
        level = [(f.start - base) / f.size >= INDENT for f in frames]
        indented = [f.start for f, up in zip(frames, level, strict=True) if up]
        reaches = [(edge - f.end) / f.size < FILL for f in frames]
        # Hanging blocks: a full base line runs on into indented lines, and a short indented
        # line ends an entry before a base line. First-line-indent prose does the opposite: a
        # short base line ends a paragraph before an indented first line.
        hanging_votes = prose_votes = 0
        for i in range(len(frames) - 1):
            if not level[i] and level[i + 1]:
                hanging_votes += reaches[i]
                prose_votes += not reaches[i]
            elif level[i] and not level[i + 1]:
                hanging_votes += not reaches[i]
                prose_votes += reaches[i]
        hanging = (
            len(indented) >= 3
            and len(indented) < len(frames)
            and (max(indented) - min(indented)) / size <= 0.5
            and hanging_votes > prose_votes
        )
        return {
            "pitch": median(advances) if len(advances) >= 3 else pitch_for(self.profile, size),
            "edge": edge,
            "justified": full >= JUSTIFIED and len(frames) >= 3,
            "start": median(starts),
            "base": base,
            "hanging": hanging,
        }

    def list_markers(self, members):
        """Lines of one stream that start a list item.

        Bullets, dashes and numbers always count. A single-letter marker counts only with
        sequence evidence (another marker of the stream has the adjacent letter, in the same
        case and punctuation) or inside a hanging-indent block: a lone initial never does.
        """
        letters = {}
        for line in members:
            if _LIST_MARKER.match(line.text):
                self.markers[line.id] = "next line starts with a list marker"
                continue
            match = _LETTER_MARKER.match(line.text)
            if match:
                letters[line.id] = (bool(match[1]), match[2], match[3])
        signatures = {
            (paren, letter.isupper(), mark, ord(letter.casefold()))
            for paren, letter, mark in letters.values()
        }
        for lid, (paren, letter, mark) in letters.items():
            value = ord(letter.casefold())
            adjacent = any(
                (paren, letter.isupper(), mark, value + step) in signatures for step in (-1, 1)
            )
            if adjacent:
                self.markers[lid] = "next line starts a lettered list item (letter sequence)"
            elif self.stats_of[lid]["hanging"]:
                self.markers[lid] = "next line starts a lettered item of a hanging-indent block"

    # ----------------------------------------------------------------- evidence
    def _same_lane(self, a, b):
        return (
            a is not None
            and b is not None
            and self.edge_kind.get((a.id, b.id)) not in (LANE_CHANGES)
        )

    def _bump(self, prev, cur, nxt):
        """Indent of ``cur`` over its lane neighbours, in font sizes (positive = indented)."""
        refs = []
        if prev is not None and self._same_lane(prev, cur):
            refs.append(prev.frame.start)
        if nxt is not None and self._same_lane(cur, nxt):
            refs.append(nxt.frame.start)
        if not refs:
            refs.append(self.stats_of[cur.id]["start"])
        return (cur.frame.start - max(refs)) / cur.frame.size

    def _occupied(self, a, b):
        """Another stream's line lies between a and b on the block axis and beside them."""
        low, high = sorted((a.frame.block, b.frame.block))
        start = min(a.frame.start, b.frame.start)
        end = max(a.frame.end, b.frame.end)
        for other in self.lines.values():
            if other.stream_id == a.stream_id or not other.text.strip():
                continue
            f = other.frame
            if low + 0.5 * a.frame.size < f.block < high - 0.2 * a.frame.size and not (
                f.end < start or f.start > end
            ):
                return True
        return False

    def decide(self, prev2, a, b, c):
        """(boundary?, score, reasons, evidence, join kind) between consecutive a and b."""
        reasons, evidence = [], {}
        kind_a = KIND_OF_REGION.get(a.region.type, "paragraph")
        kind_b = KIND_OF_REGION.get(b.region.type, "paragraph")
        edge = self.edge_kind.get((a.id, b.id), "next_in_stream")
        evidence["edge"] = edge
        end, start = ending(a.text), beginning(b.text)
        evidence["previous_end"], evidence["next_start"] = end, start
        if b.id in self.markers:
            return True, 0.9, [self.markers[b.id]], evidence, None
        entry_a, entry_b = self.entry_of.get(a.id), self.entry_of.get(b.id)
        if entry_a is not None and entry_b is not None:
            if entry_a != entry_b:
                return True, 0.9, ["separate printed navigation entries"], evidence, None
            return False, -0.6, ["one printed navigation entry"], evidence, "line"
        if kind_a != kind_b or (
            kind_a in {"heading_candidate", "caption", "figure_text", "table_text"}
            and a.region.id != b.region.id
        ):
            reasons.append(f"block type changes ({kind_a} -> {kind_b})")
            return True, 0.95, reasons, evidence, None
        if a.stream_kind in {"figure", "table"} and a.region.id != b.region.id:
            return True, 0.9, ["another figure/table block"], evidence, None
        fa, fb = a.frame, b.frame
        # Drop cap: a large initial beside the first lines.
        if (
            fa.size >= 1.8 * fb.size
            and len(TOKEN.findall(a.text)) <= 1
            and len(a.text.strip()) <= 3
            and abs(fb.block - fa.block) < 2.5 * fa.size
        ):
            evidence["drop_cap"] = True
            return False, -0.6, ["drop cap joins its paragraph"], evidence, "line"
        if abs(fb.block - fa.block) < ROW * fa.size and fb.start > fa.end - 0.5 * fa.size:
            return False, -0.6, ["same row: fragments of one line"], evidence, "row"
        if edge in LANE_CHANGES:
            return self._lane_change(a, b, c, end, start, edge, evidence)
        score = 0.0
        stats = self.stats_of[b.id]
        pitch = stats["pitch"]
        gap = (fb.block - fa.block) / pitch if pitch else 1.0
        evidence["gap_pitches"] = round(gap, 3)
        occupied = gap >= 1.25 and self._occupied(a, b)
        evidence["gap_occupied_by_float"] = occupied
        if _COLON.search(a.text) and gap >= 1.8:
            score += 1.0
            reasons.append("colon followed by a gap: a displayed element follows")
        elif not occupied:
            if gap >= 2.0:
                score += 0.9
                reasons.append(f"large gap ({gap:.2f} pitches)")
            elif gap >= 1.5:
                score += 0.6
                reasons.append(f"gap of {gap:.2f} pitches")
            elif gap >= 1.2:
                score += 0.3
                reasons.append(f"extra space ({gap:.2f} pitches)")
        bump_b = self._bump(a, b, c)
        evidence["indent_fonts"] = round(bump_b, 3)
        lane_start = (fb.start - stats["base"]) / fb.size
        if bump_b >= INDENT and lane_start >= INDENT * 0.5:
            score += 0.5
            reasons.append("first-line indent")
        at_base = (fb.start - stats["base"]) / fb.size < INDENT / 2
        entry_layout = stats["hanging"]
        evidence["hanging_run"] = stats["hanging"]
        if entry_layout:
            if at_base and end != "hyphen":
                score += 0.7
                reasons.append("hanging-indent block: next line starts a new entry")
            elif not at_base:
                score -= 0.3
                reasons.append("hanging-indent block: next line continues the entry")
        else:
            bump_a = self._bump(prev2, a, b)
            if (fa.start - fb.start) / fb.size >= INDENT and bump_a < INDENT:
                score += 0.45
                reasons.append("hanging indent: next line starts before the continuation line")
        short = (stats["edge"] - fa.end) / fa.size
        evidence["previous_short_fonts"] = round(short, 3)
        if short >= FILL and end != "hyphen":
            weight = 0.25 if stats["justified"] else 0.1
            score += weight
            reasons.append("previous line ends short")
        if entry_layout:
            # Entries of a hanging-indent block end and start without sentence cues; only a
            # break hyphen is text evidence there.
            if end == "hyphen":
                score -= 0.6
                reasons.append("previous line ends with a break hyphen")
        else:
            if end == "terminal":
                score += 0.2
                reasons.append("previous line ends a sentence")
            elif end == "open":
                score -= 0.3
                reasons.append("previous line is open")
            elif end == "hyphen":
                score -= 0.6
                reasons.append("previous line ends with a break hyphen")
            if start == "lower":
                score -= 0.4
                reasons.append("next line starts lowercase")
            elif start == "continuing_punctuation":
                score -= 0.3
                reasons.append("next line starts with continuing punctuation")
            elif start in {"upper", "digit"}:
                score += 0.05
                reasons.append("next line starts with a capital or digit")
        if a.style != b.style:
            size_ratio = max(a.style[1], b.style[1]) / max(min(a.style[1], b.style[1]), 0.1)
            if size_ratio >= 1.15 or a.style[0] != b.style[0]:
                score += 0.5
                reasons.append("style changes")
            elif a.style[2:] != b.style[2:]:
                score += 0.15
                reasons.append("weight or slant changes")
        if a.region.id != b.region.id:
            score += 0.1
            reasons.append("another Step 4 block")
        score = round(score, 6)
        evidence["score"] = score
        boundary = score >= BOUNDARY
        return boundary, score, reasons or ["no boundary evidence"], evidence, "line"

    def _lane_change(self, a, b, c, end, start, edge, evidence):
        """Columns or bands: join only when continuation evidence and layout agree."""
        cont = continuation(
            a.text,
            b.text,
            previous_type=a.region.type,
            following_type=b.region.type,
            vocabulary=self.vocabulary,
        )
        bump = self._bump(None, b, c)
        evidence.update(
            {"continuation_score": cont.score, "verdict": cont.verdict,
             "indent_fonts": round(bump, 3)}
        )  # fmt: skip
        reasons = [f"lane transition ({edge})", *cont.reasons]
        if a.style[:2] != b.style[:2]:
            return True, 0.8, [*reasons, "style changes"], evidence, None
        below = (b.frame.block - a.frame.block) / self.stats_of[a.id]["pitch"]
        evidence["next_below_pitches"] = round(below, 3)
        if below > 0.5 and end != "hyphen" and edge != "next_band":
            # A column continues at the top of the next column; text further down is a new
            # row or band of the layout.
            return (
                True,
                0.75,
                [*reasons, "next lane starts below: a new row or band"],
                evidence,
                None,
            )
        if cont.verdict == "continues" and bump < INDENT:
            return False, -0.5, [*reasons, "column continues"], evidence, "column"
        if cont.verdict == "neutral" and end == "open" and bump < INDENT and start != "upper":
            return False, -0.1, [*reasons, "column probably continues"], evidence, "column"
        return True, 0.6 if cont.verdict == "break" else 0.5, reasons, evidence, None

    # ----------------------------------------------------------------- joins
    def hyphen(self, a, b_text):
        """Decision for a hyphen ending line ``a`` before text ``b_text`` (maybe next page)."""
        raw_spans = [self.page.store.spans[s] for s in a.line.span_ids]
        # Last non-space character of the raw line and its span offset.
        for span in reversed(raw_spans):
            stripped = span.raw_text.rstrip()
            if stripped:
                index = len(stripped) - 1
                char = stripped[-1]
                ref_span = span
                break
        else:
            return None
        if char != SOFT_HYPHEN and char not in HYPHENS:
            return None
        ref = SpanRef(span_id=ref_span.id, start=index, end=index + 1)
        left = TOKEN.findall(a.text.rstrip().rstrip(HYPHENS + SOFT_HYPHEN))
        right = TOKEN.findall(b_text)
        if not left or not right:
            return None
        evidence = hyphen_evidence(left[-1], right[0], self.vocabulary, self.compounds)
        if char == SOFT_HYPHEN:
            return HyphenDecision(
                hyphen=ref, choice="soft_join", confidence=0.98,
                reasons=["soft hyphen: discretionary break"], evidence=evidence,
            )  # fmt: skip
        joined, compound = evidence["joined_attested"], evidence["compound_attested"]
        if left[-1][-1:].isdigit() or right[0][:1].isdigit():
            choice, confidence, why = "keep", 0.75, "number at the hyphen"
        elif compound > joined:
            choice = "keep"
            confidence = min(0.95, 0.6 + 0.1 * (compound - joined))
            why = f"hyphenated compound attested {compound}x inside lines vs joined {joined}x"
        elif joined > compound:
            choice = "join"
            confidence = min(0.97, 0.65 + 0.05 * (joined - compound))
            why = f"joined spelling attested {joined}x vs hyphenated {compound}x"
        elif right[0][:1].isupper() and left[-1][:1].isupper():
            choice, confidence, why = "keep", 0.6, "capitalised parts on both sides"
        elif evidence["left_attested"] >= 2 and evidence["right_attested"] >= 2:
            choice, confidence = "keep", 0.6
            why = "neither spelling attested; both parts are words of the book: compound"
        else:
            choice, confidence = "join", 0.6
            why = "neither spelling attested; a part is no word of the book: break hyphen"
        return HyphenDecision(
            hyphen=ref, choice=choice, confidence=round(confidence, 4), reasons=[why],
            evidence=evidence,
        )  # fmt: skip

    def word_join(self, a, b):
        """A word split across lines without a hyphen (strong vocabulary evidence only)."""
        left, right = TOKEN.findall(a.text), TOKEN.findall(b.text)
        if not left or not right or not left[-1].isalpha() or not right[0].isalpha():
            return None
        joined = (left[-1] + right[0]).casefold()
        counts = (
            int(self.vocabulary.get(left[-1].casefold(), 0)),
            int(self.vocabulary.get(right[0].casefold(), 0)),
            int(self.vocabulary.get(joined, 0)),
        )
        if counts[2] >= 3 and counts[0] <= 1 and counts[1] <= 1 and right[0][:1].islower():
            return WordJoin(
                left=SpanRef(span_id=a.line.span_ids[-1]),
                right=SpanRef(span_id=b.line.span_ids[0]),
                confidence=0.7,
                reasons=[
                    f"joined word attested {counts[2]}x; fragments only here",
                ],
                evidence={"left": counts[0], "right": counts[1], "joined": counts[2]},
            )
        return None

    def join(self, a, b, kind, score, reasons):
        hyphen = self.hyphen(a, b.text)
        word = None if hyphen is not None else self.word_join(a, b)
        confidence = _confidence(score)
        return LineJoin(
            previous_line_id=a.id,
            next_line_id=b.id,
            kind=kind,
            confidence=confidence,
            reasons=reasons,
            hyphen=hyphen,
            word=word,
            review_required=confidence < REVIEW_BELOW,
        )

    # ----------------------------------------------------------------- units
    def unit_kind(self, members):
        kinds = Counter(KIND_OF_REGION.get(m.region.type, "paragraph") for m in members)
        kind = kinds.most_common(1)[0][0]
        if kind == "paragraph" and members[0].id in self.markers:
            return "list_item_candidate"
        return kind

    def units(self):
        layout = self.layout
        sid = lambda *parts: stable_id(layout.source_sha256, layout.page, "unit", *parts)  # noqa: E731
        units = []
        for stream in self.order.streams:
            if not stream.line_ids:
                continue
            if stream.kind in OWN_UNIT_STREAMS or stream.kind == "furniture":
                for lid in stream.line_ids:
                    line = self.lines[lid]
                    kind = OWN_UNIT_STREAMS.get(stream.kind)
                    if kind is None:
                        kind = line.role if line.role in {
                            "running_head", "running_foot", "folio", "production_mark"
                        } else "artifact"  # fmt: skip
                    units.append(
                        ParagraphUnit(
                            id=sid(lid),
                            page=layout.page,
                            stream_id=stream.id,
                            stream_kind=stream.kind,
                            kind=kind,
                            line_ids=[lid],
                            boundary=Boundary(
                                confidence=0.95,
                                reasons=[f"{stream.kind} line: never part of a paragraph"],
                            ),
                        )
                    )
                continue
            members = [self.lines[lid] for lid in stream.line_ids]
            self.runs(members)
            self.list_markers(members)
            current, joins, boundary = (
                [members[0]],
                [],
                Boundary(confidence=0.95, reasons=["first line of its stream"]),
            )
            for index in range(1, len(members)):
                a, b = members[index - 1], members[index]
                prev2 = members[index - 2] if index >= 2 else None
                c = members[index + 1] if index + 1 < len(members) else None
                if not b.text.strip() or not a.text.strip():
                    split, score, reasons, evidence, kind = (
                        True, 0.9, ["blank line"], {}, None,
                    )  # fmt: skip
                else:
                    split, score, reasons, evidence, kind = self.decide(prev2, a, b, c)
                if split:
                    units.append(self._unit(sid, stream, current, joins, boundary))
                    confidence = _confidence(score)
                    boundary = Boundary(
                        confidence=confidence,
                        reasons=reasons,
                        evidence=evidence,
                        review_required=confidence < REVIEW_BELOW,
                    )
                    current, joins = [b], []
                else:
                    current.append(b)
                    joins.append(self.join(a, b, kind or "line", score, reasons))
            units.append(self._unit(sid, stream, current, joins, boundary))
        return units

    def _unit(self, sid, stream, members, joins, boundary):
        review = boundary.review_required or any(j.review_required for j in joins)
        return ParagraphUnit(
            id=sid(members[0].id),
            page=self.layout.page,
            stream_id=stream.id,
            stream_kind=stream.kind,
            kind=self.unit_kind(members),
            line_ids=[m.id for m in members],
            boundary=boundary,
            joins=joins,
            review_required=review,
        )


def segment_page(
    page, layout, furniture, profile, vocabulary=None, compounds=None, navigation=None
):
    return PageSegmenter(
        page, layout, furniture, profile, vocabulary, compounds, navigation
    ).units()


def text_streams():
    return TEXT_STREAMS


def stream_units(units):
    by_stream = defaultdict(list)
    for unit in units:
        by_stream[unit.stream_id].append(unit)
    return by_stream
