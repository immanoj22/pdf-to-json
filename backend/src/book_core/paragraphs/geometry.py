"""Line geometry in the line's own reading frame: block axis (lines advance) and inline axis.

The inline axis is the writing direction; for right-to-left text the reading start is the
right end, so "indent" always means further from the reading start. The block axis is the
normal to the writing direction; for horizontal text lines advance downward, for vertical
writing lines advance right to left. No script or direction is assumed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    start: float  # inline position where reading begins
    end: float  # inline position where reading ends
    block: float  # baseline position along the block axis
    size: float  # font size


def frame(line) -> Frame:
    dx, dy = line.direction
    norm = math.hypot(dx, dy) or 1.0
    dx, dy = dx / norm, dy / norm
    nx, ny = -dy, dx
    box = line.bbox
    corners = ((box.x0, box.y0), (box.x1, box.y0), (box.x0, box.y1), (box.x1, box.y1))
    along = [x * dx + y * dy for x, y in corners]
    low, high = min(along), max(along)
    if line.text_direction == "rtl":
        start, end = -high, -low
    else:
        start, end = low, high
    bx, by = line.baseline_start
    return Frame(start, end, bx * nx + by * ny, max(line.font_size, 1.0))
