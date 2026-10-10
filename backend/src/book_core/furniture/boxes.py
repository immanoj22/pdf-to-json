"""Drawn box/frame evidence for repeated designed boxes (Step 8 decision 4).

A line is in a drawn box when filled vector shapes cover most of its extent, or when it lies
inside a stroked frame. Shapes covering a large share of the page (page backgrounds and
panels) do not count. Native drawings come through the Extractor; nothing is rendered or
guessed, and geometry is relative to the page and the line.
"""

from __future__ import annotations

FILL_COVERAGE = 0.8  # share of the line's width under fills that span its height
MAX_PAGE_SHARE = 0.4  # larger shapes are backgrounds or panels, not boxes
FRAME_MARGIN = 0.5  # font sizes a frame may sit beyond the line


def _shapes(objects, page_area):
    fills, frames = [], []
    for obj in objects:
        box = obj.bbox
        if obj.kind != "drawing" or box is None:
            continue
        area = (box.x1 - box.x0) * (box.y1 - box.y0)
        if area <= 0 or area > MAX_PAGE_SHARE * page_area:
            continue
        if obj.fill is not None and (obj.fill_opacity is None or obj.fill_opacity > 0):
            fills.append(box)
        elif obj.stroke is not None and obj.stroke_width:
            frames.append(box)
    return fills, frames


def _covered(intervals, start, end):
    covered, cursor = 0.0, start
    for a, b in sorted(intervals):
        a, b = max(a, cursor), min(b, end)
        if b > a:
            covered += b - a
            cursor = b
    return covered


def boxed_lines(native_page, rows):
    """Ids of ``rows`` (LineFeatures of one page) that sit in a drawn box or frame."""
    geometry = native_page.page.geometry
    fills, frames = _shapes(native_page.objects, geometry.width * geometry.height)
    result = set()
    for row in rows:
        x0, y0, x1, y1 = row.bbox
        width = x1 - x0
        if width <= 0 or row.blank:
            continue
        spans = [(b.x0, b.x1) for b in fills if b.y0 <= y0 + 1 and b.y1 >= y1 - 1]
        if _covered(spans, x0, x1) >= FILL_COVERAGE * width:
            result.add(row.line_id)
            continue
        margin = FRAME_MARGIN * row.font_size
        if any(
            b.x0 <= x0 + margin
            and b.y0 <= y0 + margin
            and b.x1 >= x1 - margin
            and b.y1 >= y1 - margin
            and (b.x1 - b.x0) > 0
            and (b.y1 - b.y0) > 0.5 * (y1 - y0)
            for b in frames
        ):
            result.add(row.line_id)
    return result
