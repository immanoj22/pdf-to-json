"""The text of one unit and the spans over it, built from source spans without editing.

A unit's text is its pieces (whole layout lines, or span ranges of lines) in order: each
span range contributes its NFKC text (as the span store holds it); ``"\\n"`` marks every end
of a source line (between layout lines, and inside a layout line that holds spans of several
source lines), while pieces of one source line split over layout lines join as the source
has them. The ledger counts tokens per source line, so the text's tokens are the ledger's.
Excluded ranges (a list marker, hidden spans) contribute nothing and are reported.
Every character keeps its source span (``Segment``), so inline meaning is computed per
source span and merged into runs over the text:

- **bold / italic / bold_italic / small_caps** from the book's learned font table
  (``assembly.fonts``), and italic from glyphs drawn slanted (synthetic italic, per
  character); small caps only from font names (capitals set smaller were measured to be
  labels, not small caps);
- **superscript / subscript** by the baseline rule: a short span (at most 12 characters, two
  words) on an axis-aligned line, set smaller than its line
  (at most 0.85 of the line's size, or carrying the superscript flag) whose baseline is
  raised by at least 0.15 (lowered by at least 0.10) of the line's size, in the line's own
  reading frame; spans inside equation records are left to the math spans;
- **underline** only where a thin horizontal rule is drawn under the span, within the span's
  extent (never wider than the underlined text by more than one font size);
- **link** where a PDF link annotation covers the span;
- **language** (client profile ``review.language_spans``, off by default: measured wrong on
  the printed page) where the unit's language detector found a run in another language, long and
  confident enough (shorter runs keep the paragraph's language), and not mostly capitalised
  words (in scripts with case, names and citations mislead the detector);
- **math** over text-set inline equations, and as an insertion point for drawn inline math.

OCR spans carry no font evidence: no style spans are made for them (never guessed).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from book_core.assembly.fonts import SUPERSCRIPT_FLAG
from book_core.assembly.schema import InlineSpan, LineJoin, LinkTarget, SourceRun, TextContent
from book_core.extraction.fingerprints import stable_id

SMALLER = 0.85
SCRIPT_CHARS = 12
RAISED = 0.15
LOWERED = 0.10
STYLE_KINDS = ("bold", "italic", "small_caps", "superscript", "subscript", "underline")


@dataclass
class Segment:
    """Characters ``[start, end)`` of the text come from ``span`` raw range
    ``[raw_start, raw_end)`` on layout line ``line``."""

    start: int
    end: int
    span: object  # TextSpan
    raw_start: int
    raw_end: int
    line: str


@dataclass
class Built:
    content: TextContent
    segments: list[Segment] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)  # layout lines with text in the unit
    excluded: list[tuple[str, int, int]] = field(default_factory=list)  # (span, start, end)
    line_ends: dict[tuple[str, str], int] = field(default_factory=dict)  # (a, b) -> offset

    def offset_of(self, span_id, raw_offset):
        """Text offset of raw character ``raw_offset`` of ``span_id`` (None if not in text)."""
        for seg in self.segments:
            if seg.span.id == span_id and seg.raw_start <= raw_offset < seg.raw_end:
                prefix = seg.span.raw_text[seg.raw_start : raw_offset]
                return seg.start + len(unicodedata.normalize("NFKC", prefix))
        return None

    def range_of(self, span_id, raw_start=None, raw_end=None):
        """(start, end) text offsets of a span range, or None."""
        found = []
        for seg in self.segments:
            if seg.span.id != span_id:
                continue
            lo = seg.raw_start if raw_start is None else max(seg.raw_start, raw_start)
            hi = seg.raw_end if raw_end is None else min(seg.raw_end, raw_end)
            if lo >= hi:
                continue
            a = seg.start + len(
                unicodedata.normalize("NFKC", seg.span.raw_text[seg.raw_start : lo])
            )
            b = seg.start + len(
                unicodedata.normalize("NFKC", seg.span.raw_text[seg.raw_start : hi])
            )
            found.append((a, b))
        if not found:
            return None
        return min(a for a, _ in found), max(b for _, b in found)


_RANKS = {}


def ordered_spans(store):
    """Source-line sequences carry extraction order; serialized object keys do not."""
    return {sid: store.spans[sid] for line in store.lines for sid in line.span_ids}


def _rank(spans):
    """{span id: extraction position} (the span store keeps extraction order)."""
    key = id(spans)
    if key not in _RANKS or len(_RANKS[key][1]) != len(spans):
        _RANKS.clear()
        _RANKS[key] = (spans, {sid: i for i, sid in enumerate(spans)})
    return _RANKS[key][1]


def _source_grouped(pieces, spans):
    """The pieces unchanged, unless their layout order interleaves source lines (a source
    line's spans not contiguous, as in letter-by-letter rotated labels): then each source
    line's spans are kept together in source order (source lines in order of first
    appearance), each under the layout line where it first appears, so no source line is
    cut into pieces (the ledger reads source lines whole)."""
    sequence = [(lid, ref) for lid, refs in pieces for ref in refs]
    order, seen, closed = [], {}, set()
    interleaved = False
    previous = None
    for lid, ref in sequence:
        line = spans[ref[0]].line_id
        if line != previous:
            if line in closed:
                interleaved = True
            if previous is not None:
                closed.add(previous)
        previous = line
        if line not in seen:
            seen[line] = (lid, [])
            order.append(line)
        seen[line][1].append(ref)
    if not interleaved:
        return pieces
    rank = _rank(spans)
    regrouped = []
    for line in order:
        lid, refs = seen[line]
        refs = sorted(refs, key=lambda r: (rank[r[0]], r[1] or 0))
        if regrouped and regrouped[-1][0] == lid:
            regrouped[-1][1].extend(refs)
        else:
            regrouped.append((lid, list(refs)))
    return regrouped


def source_runs(segments, spans, lines=None):
    """References to existing text slices, in original extraction evidence order."""
    def short(value):
        return value[:16] if len(value) == 64 else stable_id(value)[:16]

    rank = _rank(spans)
    return [SourceRun(page=s.span.page, line=short(s.span.line_id), span=short(s.span.id),
                      position=rank[s.span.id], source_start=s.raw_start,
                      start=s.start, end=s.end)
            for s in segments if s.end > s.start and (lines is None or s.span.line_id in lines)]


def build_text(pieces, spans, exclude=frozenset(), *, source_runs_for=()):
    """``pieces``: [(line id, [(span id, raw start|None, raw end|None)])] in reading order;
    ``spans``: {span id: TextSpan}; ``exclude``: {(span id, raw start, raw end)} or span ids
    (whole span) to leave out. Returns ``Built`` (styles are added by ``decorate``)."""
    pieces = _source_grouped(pieces, spans)
    whole = {e for e in exclude if isinstance(e, str)}
    split_lines = set(source_runs_for) | {spans[s].line_id for s in whole}
    ranges = {}
    for item in exclude:
        if not isinstance(item, str):
            ranges.setdefault(item[0], []).append((item[1], item[2]))
    parts, raw_parts, segments, excluded, lines, ends = [], [], [], [], [], {}
    length, previous, source_line = 0, None, None
    for line_id, refs in pieces:
        line_parts = []
        for span_id, start, end in refs:
            span = spans[span_id]
            lo = 0 if start is None else start
            hi = len(span.raw_text) if end is None else end
            if span_id in whole:
                excluded.append((span_id, lo, hi))
                continue
            cuts = sorted(r for r in ranges.get(span_id, []) if r[0] < hi and r[1] > lo)
            cursor = lo
            for a, b in cuts:
                a, b = max(a, lo), min(b, hi)
                if a > cursor:
                    line_parts.append((span, cursor, a))
                excluded.append((span_id, a, b))
                cursor = max(cursor, b)
            if cursor < hi:
                line_parts.append((span, cursor, hi))
        if not line_parts:
            continue
        if previous is not None and line_parts[0][0].line_id != source_line:
            ends[(previous, line_id)] = length
        for span, a, b in line_parts:
            if source_line is not None and span.line_id != source_line:
                # A source line ends (between layout lines, or inside one layout line that
                # holds spans of several source lines): a token boundary, as in the ledger.
                parts.append("\n")
                raw_parts.append("\n")
                length += 1
            source_line = span.line_id
            raw = span.raw_text[a:b]
            text = unicodedata.normalize("NFKC", raw)
            segments.append(Segment(length, length + len(text), span, a, b, line_id))
            parts.append(text)
            raw_parts.append(raw)
            length += len(text)
        lines.append(line_id)
        previous = line_id
    text, raw = "".join(parts), "".join(raw_parts)
    directions = [s.span.text_direction for s in segments if s.span.text_direction]
    scripts = [s.span.script for s in segments if s.span.script]
    content = TextContent(
        text=text,
        raw=raw if raw != text else None,
        direction=max(directions, key=directions.count) if directions else None,
        script=max(scripts, key=scripts.count) if scripts else None,
        source_runs=source_runs(segments, spans, split_lines),
    )
    return Built(content, segments, lines, excluded, ends)


@dataclass
class LineContext:
    """What the baseline rule needs of one layout line: its dominant size and baseline, and
    the reading-frame normal (baseline coordinates grow downwards along it)."""

    size: float
    baseline: float | None
    normal: tuple[float, float]


def line_context(span_ids, spans, geometry):
    weights = {}
    for sid in span_ids:
        span = spans[sid]
        w = len(span.raw_text.strip())
        if w:
            weights[round(span.size, 2)] = weights.get(round(span.size, 2), 0) + w
    size = max(weights, key=lambda k: (weights[k], k)) if weights else 0.0
    normal = (0.0, 1.0)
    baselines = []
    for sid in span_ids:
        g = geometry.get(sid)
        span = spans[sid]
        if g is None or not span.raw_text.strip():
            continue
        dx, dy = g.direction
        normal = (round(-dy, 6) + 0.0, round(dx, 6) + 0.0)
        if abs(span.size - size) <= 0.05 * max(size, 1):
            baselines.append(g.origin[0] * normal[0] + g.origin[1] * normal[1])
    baseline = sorted(baselines)[len(baselines) // 2] if baselines else None
    return LineContext(size, baseline, normal)


def span_style(span, fonts, line, geometry, in_math):
    """The set of style kinds of one source span (OCR spans: none)."""
    if span.provenance.method != "native" or not span.raw_text.strip():
        return frozenset()
    found = set()
    style = fonts.style(span.font)
    if style is not None:
        if style.bold:
            found.add("bold")
        if style.italic:
            found.add("italic")
        if style.small_caps:
            found.add("small_caps")
    if line is not None and line.size > 0:
        g = geometry.get(span.id)
        smaller = span.size <= SMALLER * line.size or bool(span.flags & SUPERSCRIPT_FLAG)
        # Scripts are short (a footnote marker, "th", an index such as "between") and sit on
        # an axis-aligned line (measured: rotated map labels and whole lines in boxes are not).
        short = len(span.raw_text.strip()) <= SCRIPT_CHARS and len(span.raw_text.split()) <= 2
        aligned = line.normal in {(0.0, 1.0), (0.0, -1.0), (1.0, 0.0), (-1.0, 0.0)}
        if (not in_math and g is not None and line.baseline is not None and smaller and short
                and aligned):  # fmt: skip
            own = g.origin[0] * line.normal[0] + g.origin[1] * line.normal[1]
            shift = line.baseline - own  # positive: raised
            if shift >= RAISED * line.size:
                found.add("superscript")
                found.discard("small_caps")
            elif -shift >= LOWERED * line.size:
                found.add("subscript")
                found.discard("small_caps")
    return frozenset(found)


def _runs(segments, labels):
    """[(label, start, end)] merging consecutive segments with the same label; whitespace-
    only segments between two equal labels join them; runs are trimmed of whitespace."""
    runs = []
    for seg, label in zip(segments, labels, strict=True):
        blank = not seg.span.raw_text[seg.raw_start : seg.raw_end].strip()
        if blank:
            continue
        if runs and runs[-1][0] == label and _gap_blank(segments, runs[-1][2], seg.start):
            runs[-1][2] = seg.end
        else:
            runs.append([label, seg.start, seg.end])
    return [(label, a, b) for label, a, b in runs if label]


def _gap_blank(segments, a, b):
    return all(
        not s.span.raw_text[s.raw_start : s.raw_end].strip()
        for s in segments
        if s.start >= a and s.end <= b
    )


def _trim(text, a, b):
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b


def _mostly_names(text):
    """In a script with case, most words start with a capital (names, citations): the
    language detector reads names, not a phrase in another language."""
    cased = [w for w in text.split() if w[:1].isalpha() and (w[0].isupper() or w[0].islower())]
    return bool(cased) and sum(w[0].isupper() for w in cased) * 2 > len(cased)


def _char_runs(text, labels):
    """[(label, start, end)] of characters with the same label; a whitespace-only gap
    between two runs of one label joins them; runs are trimmed of whitespace."""
    runs = []
    for index, label in enumerate(labels):
        if label is None:
            continue
        if runs and runs[-1][0] == label and not text[runs[-1][2] : index].strip():
            runs[-1][2] = index + 1
        else:
            runs.append([label, index, index + 1])
    out = []
    for label, a, b in runs:
        a, b = _trim(text, a, b)
        if b > a:
            out.append((label, a, b))
    return out


def _mark_labels(built, marks, label_of):
    """Per text character: the label of the source characters a mark covers."""
    labels = [None] * len(built.content.text)
    for seg in built.segments:
        for mark in marks.get(seg.span.id, ()):
            lo, hi = max(mark[0], seg.raw_start), min(mark[1], seg.raw_end)
            if lo >= hi:
                continue
            found = built.range_of(seg.span.id, lo, hi)
            if found:
                for k in range(found[0], found[1]):
                    labels[k] = label_of(mark)
    return labels


def decorate(built, *, fonts, contexts, geometry, links, math_ranges, link_marks=None,
             underline_marks=None, slant_marks=None, unit=None, language=None, run_in=(),
             settings=None):  # fmt: skip
    """Add inline spans and line-join decisions to ``built.content`` (in place) and return it.

    ``contexts``: {line id: LineContext}; ``geometry``: {span id: SpanGeometry};
    ``links``: [(PageLink, target unit id|None)]; ``link_marks``/``underline_marks``:
    {span id: [(raw start, raw end[, link index])]} characters a link covers or a drawn rule
    underlines; ``math_ranges``: [(start, end, equation id, mathml, latex, review)];
    ``unit``: the lists-stage unit (joins, language runs);
    ``language``: the book's primary language; ``run_in``: [(start, end)] of a run-in
    heading; ``settings``: the profile's review settings."""
    content, segments, text = built.content, built.segments, built.content.text
    spans = []
    in_math = [any(a <= s.start and s.end <= b for a, b, *_ in math_ranges) for s in segments]
    styles = []
    for seg, math in zip(segments, in_math, strict=True):
        styles.append(set(span_style(seg.span, fonts, contexts.get(seg.line), geometry, math)))
    # Bold and italic per character: the span's learned font style, and slanted glyphs
    # (synthetic italic) per character.
    slanted = _mark_labels(built, slant_marks or {}, lambda m: True)
    weights = [None] * len(text)
    for seg, found in zip(segments, styles, strict=True):
        if not seg.span.raw_text[seg.raw_start : seg.raw_end].strip():
            continue
        for k in range(seg.start, seg.end):
            bold, italic = "bold" in found, "italic" in found or bool(slanted[k])
            weights[k] = ("bold_italic" if bold and italic else "bold" if bold else
                          "italic" if italic else None)  # fmt: skip
    for kind, a, b in _char_runs(text, weights):
        spans.append(InlineSpan(kind=kind, start=a, end=b))
    for kind in ("small_caps", "superscript", "subscript"):
        for _, a, b in _runs(segments, [kind if kind in s else None for s in styles]):
            a, b = _trim(text, a, b)
            if b > a:
                spans.append(InlineSpan(kind=kind, start=a, end=b))
    for _, a, b in _char_runs(text, _mark_labels(built, underline_marks or {}, lambda m: 1)):
        spans.append(InlineSpan(kind="underline", start=a, end=b))
    # links (characters inside a link annotation's rectangle)
    for index, a, b in _char_runs(text, _mark_labels(built, link_marks or {}, lambda m: m[2])):
        link, target = links[index]
        if link.kind == "uri" or link.kind == "file":
            if link.uri:
                spans.append(InlineSpan(kind="link", start=a, end=b, href=link.uri))
        elif link.target_page is not None:
            spans.append(
                InlineSpan(
                    kind="link",
                    start=a,
                    end=b,
                    target=LinkTarget(page=link.target_page, unit=target),
                )
            )
    # math
    for a, b, equation, mathml, latex, review in math_ranges:
        spans.append(InlineSpan(kind="math", start=a, end=b, equation=equation, mathml=mathml,
                                latex=latex, review_status=review))  # fmt: skip
    for a, b in run_in:
        spans.append(InlineSpan(kind="run_in_heading", start=a, end=b))
    # language
    if unit is not None and settings is not None and settings.language_spans == "on":
        unit_language = unit.language if unit.language != "und" else None
        if (
            unit_language
            and language
            and unit_language != language
            and unit.language_confidence >= settings.language_min_confidence
        ):
            content.language = unit_language
        base = content.language or language
        for run in unit.language_runs:
            found = [built.range_of(r.span_id, r.start, r.end) for r in run.refs]
            found = [f for f in found if f]
            if not found or run.language == base:
                continue
            a, b = _trim(text, min(f[0] for f in found), max(f[1] for f in found))
            letters = sum(c.isalpha() for c in text[a:b])
            words = len(text[a:b].split())
            if (
                letters >= settings.language_min_letters
                and words >= settings.language_min_words
                and run.confidence >= settings.language_min_confidence
                and not _mostly_names(text[a:b])
            ):
                # Measured unreliable on short mixed text (Step 17): always for review.
                spans.append(InlineSpan(kind="language", start=a, end=b, language=run.language,
                                        confidence=round(run.confidence, 4),
                                        review_status="needs_review"))  # fmt: skip
    # joins
    joins = []
    if unit is not None:
        for join in unit.joins:
            at = built.line_ends.get((join.previous_line_id, join.next_line_id))
            if at is None:
                continue
            review = "needs_review" if join.review_required else "ok"
            if join.hyphen is not None:
                ref = join.hyphen.hyphen
                hyphen = built.offset_of(ref.span_id, ref.start or 0)
                if hyphen is None or hyphen >= at:
                    hyphen = None
                joins.append(LineJoin(at=at, decision=join.hyphen.choice, hyphen_at=hyphen,
                                      confidence=round(join.hyphen.confidence, 4),
                                      review_status=review))  # fmt: skip
            elif join.word is not None:
                joins.append(LineJoin(at=at, decision="word",
                                      confidence=round(join.word.confidence, 4),
                                      review_status=review))  # fmt: skip
    content.spans = sorted(spans, key=lambda s: (s.start, s.end, s.kind))
    content.joins = sorted(joins, key=lambda j: j.at)
    return content
