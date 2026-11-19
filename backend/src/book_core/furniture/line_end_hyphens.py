"""A hyphen glyph the PDF draws as its own text object sits at the end of its line.

Some producers (De Gruyter, for one) write the break hyphen of a line as a separate native line.
The layout joins it to the line it touches, but keeps native order, so the hyphen span comes
*first* in the visual line's spans although it is printed at the line's reading end. Read in span
order the line starts with a "bullet" (a false list item) and no line ends in a hyphen (so a word
cut at the line end is never joined: "Analysemo" "dell").

This puts such a span last, judged only by geometry: a span holding nothing but hyphens whose
reading position starts at (or just past) the end of the rest of the line. Spans are never
rewritten or dropped (the span store is untouched; the line keeps the same span ids), a dash at
the line start (a real bullet) is left where it is, and no script or direction is assumed: the
reading end of a right-to-left line is its left side.
"""

from __future__ import annotations

import math

from book_core.layout.lines import project

HYPHENS = frozenset("-‐‑­")  # hyphen-minus, hyphen, non-breaking hyphen, soft hyphen
REACH = 1.0  # the hyphen starts within this many font sizes after the rest of the line
OVERLAP = 0.25  # ... or overlaps its end by at most this many


def _reading_extent(line, span):
    dx, dy = line.direction
    norm = math.hypot(dx, dy) or 1.0
    (low, high), _ = project(span.bbox, (dx / norm, dy / norm))
    return (-high, -low) if line.text_direction == "rtl" else (low, high)


def _is_hyphen(span):
    text = span.raw_text.strip()
    return bool(text) and all(c in HYPHENS for c in text)


def span_order(line, spans):
    """The line's span ids with a detached hyphen moved to the reading end, or None."""
    ids = list(line.span_ids)
    if len(ids) < 2:
        return None
    detached = [s for s in ids if _is_hyphen(spans[s])]
    if not detached or len(detached) == len(ids):
        return None
    rest = [s for s in ids if s not in detached]
    rest_end = max(_reading_extent(line, spans[s])[1] for s in rest)
    size = max(line.font_size, 1.0)
    moved = []
    for s in detached:
        start = _reading_extent(line, spans[s])[0]
        if rest_end - OVERLAP * size <= start <= rest_end + REACH * size:
            moved.append(s)
    if not moved:
        return None
    order = [s for s in ids if s not in moved] + moved
    return order if order != ids else None


def attach_line_end_hyphens(layout, spans):
    """``layout`` with the detached hyphens of its lines last (the same object when none)."""
    lines, changed = [], False
    for line in layout.lines:
        order = span_order(line, spans)
        if order is None:
            lines.append(line)
        else:
            lines.append(line.model_copy(update={"span_ids": order}))
            changed = True
    return layout.model_copy(update={"lines": lines}) if changed else layout
