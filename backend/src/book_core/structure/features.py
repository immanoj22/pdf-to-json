"""Pass 1 of the structure stage: per-unit and per-page evidence (no decision).

For every text unit of a page (Step 9 units, read in their Step 7/8 stream order) this records
style (character-weighted size, weight, slant, colour, family, letter case), extent and position
along the page's own block axis, spacing to the neighbouring units of its stream, sentence
cues, the printed-navigation entries on its lines, a digit-masked repetition key,
the ledger token ordinals it owns (for evaluation) and, for units of several lines, each line's
start and the head and tail of its text (``line_entries``: a unit that holds several entries
of an index or glossary is read line by line by the navigation decision). Positions use each
line's own reading frame (``paragraphs.geometry``), so right-to-left and vertical text are
measured the same way.

The evidence keeps a short normalized text excerpt for matching (navigation titles, repetition);
the structure model itself never stores text.
"""

from __future__ import annotations

import unicodedata
from collections import Counter

import regex

from book_core.paragraphs.geometry import frame
from book_core.paragraphs.lexicon import TOKEN
from book_core.paragraphs.models import TEXT_KINDS
from book_core.reading_order.continuation import beginning, ending

BOLD, ITALIC = 1 << 4, 1 << 1
EXCERPT = 240
LINE_HEAD, LINE_TAIL = 32, 24  # characters of a line kept as entry evidence
_DIGITS = regex.compile(r"\p{N}+")


def span_style(span):
    font = span.font.split("+", 1)[-1]
    lowered = font.casefold()
    return {
        "size": span.size,
        "bold": bool(span.flags & BOLD) or "bold" in lowered or "black" in lowered
        or "heavy" in lowered,
        "italic": bool(span.flags & ITALIC) or "italic" in lowered or "oblique" in lowered,
        "color": span.color,
        "family": font.split("-")[0].split(",")[0].casefold(),
    }  # fmt: skip


def _weighted_median(pairs):
    total = sum(w for _, w in pairs)
    running = 0
    for value, weight in sorted(pairs):
        running += weight
        if running * 2 >= total:
            return value
    return pairs[0][0] if pairs else 0.0


def text_style(store, span_ids):
    """Character-weighted style of a run of spans."""
    weighted, colors, families = [], Counter(), Counter()
    bold = italic = total = upper = cased = 0
    for sid in span_ids:
        span = store.spans[sid]
        chars = len(span.raw_text.strip())
        if not chars:
            continue
        style = span_style(span)
        weighted.append((style["size"], chars))
        colors[style["color"]] += chars
        families[style["family"]] += chars
        bold += chars * style["bold"]
        italic += chars * style["italic"]
        total += chars
        for c in span.text:
            if c.isupper():
                upper += 1
                cased += 1
            elif c.islower():
                cased += 1
    if not total:
        return None
    return {
        "size": round(_weighted_median(weighted), 2),
        "bold": round(bold / total, 3),
        "italic": round(italic / total, 3),
        "color": colors.most_common(1)[0][0],
        "family": families.most_common(1)[0][0],
        "caps": round(upper / cased, 3) if cased else None,
        "chars": total,
    }


def lead_run(store, line):
    """The leading run of a line set in a style that differs from the rest of the line.

    Evidence for a run-in heading ("Causes. The war began..."): returns the run's span ids,
    the end offset in its last span, its style and its last non-space character, or None.
    """
    spans = [store.spans[s] for s in line.span_ids if store.spans[s].raw_text.strip()]
    if len(spans) < 2:
        return None

    def key(span):
        style = span_style(span)
        return style["bold"], style["italic"], round(style["size"] * 4), style["color"]

    first = key(spans[0])
    count = 1
    while count < len(spans) and key(spans[count]) == first:
        count += 1
    if count == len(spans):
        return None
    run, rest = spans[:count], spans[count:]
    text = "".join(s.raw_text for s in run)
    stripped = text.rstrip()
    style = span_style(run[0])
    rest_style = span_style(rest[0])
    return {
        "span_ids": [s.id for s in run],
        "end": len(run[-1].raw_text.rstrip()) or len(run[-1].raw_text),
        "tokens": len(TOKEN.findall(text)),
        "letters": sum(c.isalpha() for c in text),
        "last": unicodedata.normalize("NFKC", stripped[-1:]) if stripped else "",
        "bold": style["bold"],
        "italic": style["italic"],
        "size_ratio": round(style["size"] / max(rest_style["size"], 0.1), 3),
        "rest_bold": rest_style["bold"],
        "rest_italic": rest_style["italic"],
        "color_differs": style["color"] != rest_style["color"],
        "rest_letters": sum(c.isalpha() for s in rest for c in s.raw_text),
    }


_SEPARATOR = regex.compile(r"\S(?:\t| {2,}|\u2002|\u2003)\S")


def line_entries(store, lines, frames, line_ids):
    """[start, head, tail, letters, tokens] of each line of a unit of several lines, in unit
    order (start along the line's own frame; head and tail of its NFKC text)."""
    if len(line_ids) < 2:
        return []
    out = []
    for lid in line_ids:
        raw = "".join(store.spans[s].raw_text for s in lines[lid].span_ids)
        text = " ".join(unicodedata.normalize("NFKC", raw).split())
        out.append([
            round(frames[lid].start, 2), text[:LINE_HEAD], text[-LINE_TAIL:],
            sum(c.isalpha() for c in text), len(TOKEN.findall(text)),
        ])  # fmt: skip
    return out


def repeat_key(text):
    """Casefolded, digit-masked, whitespace-collapsed text (repetition evidence)."""
    return " ".join(_DIGITS.sub("#", text.casefold()).split())


def _rtl(text):
    kinds = [unicodedata.bidirectional(c) for c in text]
    return sum(k in {"R", "AL"} for k in kinds) > kinds.count("L")


def page_evidence(page, layout, paragraphs, furniture, owners, navigation_entries=()):
    """Evidence of one page.

    ``owners``: visual line id of each retained token ordinal (``evaluation.furniture``
    ``token_lines``); ``navigation_entries``: Step 6 printed entries whose source is this page,
    with resolved ``title`` added by the caller.
    """
    store = page.store
    lines = {line.id: line for line in layout.lines}
    frames = {lid: frame(line) for lid, line in lines.items()}
    region_of = {lid: region for region in layout.regions for lid in region.line_ids}
    ordinals = {}
    for index, lid in enumerate(owners):
        ordinals.setdefault(lid, []).append(index)
    entry_of = {}
    for entry in navigation_entries:
        for source in entry["line_ids"]:
            entry_of[source] = entry["id"]
    text_lines = [lines[lid] for lid in lines if lines[lid].visible and not lines[lid].blank]
    blocks = [frames[line.id].block for line in text_lines] or [0.0]
    low, high = min(blocks), max(blocks)
    extent = max(high - low, 1.0)
    streams = {}
    for unit in paragraphs.units:
        streams.setdefault(unit.stream_id, []).append(unit)
    units = []
    for stream_units in streams.values():
        text_units = [u for u in stream_units if u.kind in TEXT_KINDS]
        for position, unit in enumerate(text_units):
            spans = [sid for lid in unit.line_ids for sid in lines[lid].span_ids]
            style = text_style(store, spans)
            raw = "\n".join(
                "".join(store.spans[s].raw_text for s in lines[lid].span_ids)
                for lid in unit.line_ids
            )
            text = " ".join(unicodedata.normalize("NFKC", raw).split())
            if style is None or not text:
                continue
            first, last = frames[unit.line_ids[0]], frames[unit.line_ids[-1]]
            unit_frames = [frames[lid] for lid in unit.line_ids]
            previous = text_units[position - 1] if position else None
            following = text_units[position + 1] if position + 1 < len(text_units) else None

            def gap(a_id, b_id, size):
                a, b = frames[a_id], frames[b_id]
                return round((b.block - a.block) / max(size, 0.1), 3)

            entries = sorted(
                {entry_of[s] for lid in unit.line_ids for s in lines[lid].source_line_ids
                 if s in entry_of}
            )  # fmt: skip
            units.append({
                "page": layout.page,
                "unit": unit.id,
                "kind": unit.kind,
                "stream": unit.stream_kind,
                "stream_id": unit.stream_id,
                "position": position,
                "stream_units": len(text_units),
                "region": region_of[unit.line_ids[0]].type if unit.line_ids[0] in region_of
                else "unknown",
                "lines": len(unit.line_ids),
                "tokens": len(TOKEN.findall(text)),
                "letters": sum(c.isalpha() for c in text),
                "text": text[:EXCERPT],
                "rtl": _rtl(text),
                "language": unit.language,
                **{k: style[k] for k in ("size", "bold", "italic", "color", "family", "caps")},
                "block": round((first.block - low) / extent, 4),
                "block_end": round((last.block - low) / extent, 4),
                "start": round(min(f.start for f in unit_frames), 2),
                "end": round(max(f.end for f in unit_frames), 2),
                "gap_before": gap(previous.line_ids[-1], unit.line_ids[0], style["size"])
                if previous else None,
                "gap_after": gap(unit.line_ids[-1], following.line_ids[0], style["size"])
                if following else None,
                "previous_kind": previous.kind if previous else None,
                "next_kind": following.kind if following else None,
                "ending": ending(text),
                "beginning": beginning(text),
                "navigation_entries": entries,
                "repeat_key": repeat_key(text)[:120],
                "boundary_reasons": unit.boundary.reasons[:3],
                "lead_run": lead_run(store, lines[unit.line_ids[0]]),
                # A wide space or tab inside the first line (term/definition, number/title).
                "separator": bool(_SEPARATOR.search(raw.split("\n", 1)[0])),
                "review": unit.review_required,
                "line_entries": line_entries(store, lines, frames, unit.line_ids),
                "token_ordinals": [i for lid in unit.line_ids for i in ordinals.get(lid, [])],
            })  # fmt: skip
    # Next/previous sizes in stream order (style contrast with the text that follows).
    by_stream = {}
    for item in units:
        by_stream.setdefault(item["stream_id"], []).append(item)
    for items in by_stream.values():
        items.sort(key=lambda x: x["position"])
        for a, b in zip(items, items[1:], strict=False):
            a["next_size"], a["next_bold"] = b["size"], b["bold"]
            b["previous_size"], b["previous_bold"] = a["size"], a["bold"]
    marker = furniture.marker
    letters = Counter()
    for item in units:
        letters[item["stream"]] += item["letters"]
    return {
        "page": layout.page,
        "label": marker.label,
        "label_kind": marker.kind,
        "label_source": marker.source,
        "label_run": marker.run_index,
        "letters_by_stream": dict(letters),
        "units": units,
        "navigation": [
            {
                k: entry.get(k)
                for k in (
                    "id",
                    "title",
                    "target_label",
                    "level_evidence",
                    "reference_side",
                    "leaders",
                    "font_size",
                    "geometry_only_ambiguous",
                    "confidence",
                    "line_ids",
                )
            }
            for entry in navigation_entries
        ],  # fmt: skip
    }
