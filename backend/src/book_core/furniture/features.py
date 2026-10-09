"""Per-line evidence for the furniture stage, from one page's Step 4 layout and Step 7 order.

Positions are measured in the page content frame (the TrimBox frame of the ledger) along the
line's own block axis: horizontal lines use the top and bottom edges, rotated or vertical lines
the left and right edges. Nothing here sorts lines into an order or decides a role.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import regex

from book_core.furniture.labels import Label, parse_label

TOKEN = regex.compile(r"[\p{L}\p{M}\p{N}]+")
EDGE_FRACTION = 0.16  # share of the frame extent, from the edge, that may hold furniture
BOLD = 1 << 4
ITALIC = 1 << 1


def masked_key(text: str) -> str:
    """Casefolded NFKC text with whitespace collapsed and every digit masked (Step 6 rule)."""
    text = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    return regex.sub(r"\p{N}", "#", text)


def family(font: str) -> str:
    """Font family without subset tag or weight/style suffix; evidence for style identity only."""
    name = font.split("+", 1)[-1]
    return regex.split(r"[-,]", name, maxsplit=1)[0].casefold()


@dataclass(frozen=True)
class LineFeatures:
    line_id: str
    page: int
    text: str  # NFKC; evidence only, never stored in the model
    key: str
    tokens: int
    bbox: tuple[float, float, float, float]
    font_size: float
    style: tuple  # (family, rounded size, color, bold, italic)
    vertical: bool
    inside_content: bool
    blank: bool
    visible: bool
    edge: str | None  # top | bottom | left | right: the nearest edge on the block axis
    depth: float  # distance from that edge, as a share of the frame extent
    across: float  # centre along the inline axis, as a share of the frame extent (0..1)
    side: str  # start | centre | end of the inline axis (from the line's extent)
    outer_rank: int  # inside-content text lines strictly between the line and its edge
    inward_gap: float | None  # whitespace to the next text line inward, in font sizes
    stream: str  # Step 7 stream kind
    region_type: str
    region_id: str
    region_lines: int
    scope_kind: str
    label: Label | None
    edge_label: tuple[str, Label] | None = None  # (start|end, label) for a label at a line end
    neighbours: dict = field(default_factory=dict)


def _dominant(spans):
    weights = Counter()
    for span in spans:
        weights[span.id] += max(1, len(span.raw_text.strip()))
    return max(spans, key=lambda s: weights[s.id])


def _edge_label(text: str) -> tuple[str, Label] | None:
    """A label separated by whitespace at the start or end of a longer line."""
    parts = text.split()
    if len(parts) < 2:
        return None
    for where, token in (("start", parts[0]), ("end", parts[-1])):
        label = parse_label(token)
        if label is not None and label.kind != "roman":
            return where, label
    return None


def page_features(page, layout, order) -> list[LineFeatures]:
    """Evidence for every visual line of one page (blank and outside-frame lines included)."""
    store = page.store
    frame = page.geometry.content_bbox
    width = max(frame.x1 - frame.x0, 1e-6)
    height = max(frame.y1 - frame.y0, 1e-6)
    stream_of = {lid: s.kind for s in order.streams for lid in s.line_ids}
    region_of = {lid: r for r in layout.regions for lid in r.line_ids}
    scope_kind = {s.id: s.kind for s in layout.scopes}
    texts = {}
    for line in layout.lines:
        texts[line.id] = unicodedata.normalize(
            "NFKC", "".join(store.spans[s].raw_text for s in line.span_ids)
        )
    vertical = {
        line.id: (not line.horizontal and round(line.rotation / 90) % 2 == 1)
        or line.writing_mode == "vertical"
        for line in layout.lines
    }
    textual = [
        line
        for line in layout.lines
        if not line.blank and texts[line.id].strip() and line.inside_content
    ]
    rows = []
    for line in layout.lines:
        text = texts[line.id]
        box = line.bbox
        spans = [store.spans[s] for s in line.span_ids]
        span = _dominant(spans)
        style = (
            family(span.font),
            round(span.size * 2) / 2,
            span.color,
            bool(span.flags & BOLD) or "bold" in span.font.casefold(),
            bool(span.flags & ITALIC) or "italic" in span.font.casefold(),
        )
        is_vertical = vertical[line.id]
        if is_vertical:
            low, high = (box.x0 - frame.x0) / width, (frame.x1 - box.x1) / width
            edges = ("left", "right")
            a0, a1, extent, origin = box.y0, box.y1, height, frame.y0
        else:
            low, high = (box.y0 - frame.y0) / height, (frame.y1 - box.y1) / height
            edges = ("top", "bottom")
            a0, a1, extent, origin = box.x0, box.x1, width, frame.x0
        edge = edges[0] if low <= high else edges[1]
        depth = min(low, high)
        centre = ((a0 + a1) / 2 - origin) / extent
        lo, hi = (a0 - origin) / extent, (a1 - origin) / extent
        side = "start" if hi < 0.5 else "end" if lo > 0.5 else "centre"
        # Lines between this one and its edge, and the whitespace to the next line inward.
        outer, gap = 0, None
        for other in textual:
            if other.id == line.id or vertical[other.id] != is_vertical:
                continue
            ob = other.bbox
            if is_vertical:
                overlap = min(box.y1, ob.y1) - max(box.y0, ob.y0)
                before = (
                    ob.x1 <= (box.x0 + box.x1) / 2
                    if edge == "left"
                    else ob.x0 >= (box.x0 + box.x1) / 2
                )
                distance = box.x0 - ob.x1 if edge == "right" else ob.x0 - box.x1
            else:
                overlap = min(box.x1, ob.x1) - max(box.x0, ob.x0)
                before = (
                    (ob.y0 + ob.y1) / 2 < (box.y0 + box.y1) / 2
                    if edge == "top"
                    else (ob.y0 + ob.y1) / 2 > (box.y0 + box.y1) / 2
                )
                distance = box.y0 - ob.y1 if edge == "bottom" else ob.y0 - box.y1
            if before:
                outer += 1
            elif overlap > -2 * line.font_size and distance > -0.5 * line.font_size:
                value = max(distance, 0.0) / max(line.font_size, 1.0)
                gap = value if gap is None else min(gap, value)
        region = region_of[line.id]
        rows.append(
            LineFeatures(
                line_id=line.id,
                page=layout.page,
                text=text,
                key=masked_key(text),
                tokens=len(TOKEN.findall(text)),
                bbox=(box.x0, box.y0, box.x1, box.y1),
                font_size=line.font_size,
                style=style,
                vertical=is_vertical,
                inside_content=line.inside_content,
                blank=line.blank or not text.strip(),
                visible=line.visible,
                edge=edge,
                depth=depth,
                across=centre,
                side=side,
                outer_rank=outer,
                inward_gap=gap,
                stream=stream_of.get(line.id, "unordered"),
                region_type=region.type,
                region_id=region.id,
                region_lines=len(region.line_ids),
                scope_kind=scope_kind.get(region.scope_id, "page"),
                label=parse_label(text),
                edge_label=_edge_label(text),
            )
        )
    return rows
