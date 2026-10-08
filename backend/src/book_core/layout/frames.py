"""Reading frames for rotated text.

A frame is the page seen along a text direction: frame x runs along the writing direction,
frame y runs across it (the next line). Lines sharing a right-angle rotation are analysed in
their own frame with the same band, lane, table and region rules as horizontal text, then
mapped back to page coordinates. The transform is orthonormal, so distances are preserved.
Only right angles are supported for structure; other angles stay individual lines.
"""

import math

from book_core.model.common import BBox

RIGHT_ANGLE_TOLERANCE = 1.0


def right_angle(rotation):
    """Nearest multiple of 90 degrees within tolerance, else None."""
    nearest = round(rotation / 90.0) * 90 % 360
    difference = abs((rotation - nearest + 180) % 360 - 180)
    return nearest if difference <= RIGHT_ANGLE_TOLERANCE else None


def axes(rotation):
    theta = math.radians(rotation)
    direction = (math.cos(theta), -math.sin(theta))
    normal = (-direction[1], direction[0])
    return direction, normal


def _snap(value):
    return 0.0 if abs(value) < 1e-9 else value


def to_frame_point(x, y, rotation):
    (dx, dy), (nx, ny) = axes(rotation)
    return _snap(x * dx + y * dy), _snap(x * nx + y * ny)


def from_frame_point(fx, fy, rotation):
    (dx, dy), (nx, ny) = axes(rotation)
    return _snap(fx * dx + fy * nx), _snap(fx * dy + fy * ny)


def _box(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))


def to_frame(bbox, rotation):
    corners = [(bbox.x0, bbox.y0), (bbox.x1, bbox.y0), (bbox.x0, bbox.y1), (bbox.x1, bbox.y1)]
    return _box([to_frame_point(x, y, rotation) for x, y in corners])


def from_frame(bbox, rotation):
    corners = [(bbox.x0, bbox.y0), (bbox.x1, bbox.y0), (bbox.x0, bbox.y1), (bbox.x1, bbox.y1)]
    return _box([from_frame_point(x, y, rotation) for x, y in corners])


def frame_line(line, rotation):
    """The same visual line (same id and spans) expressed in the frame's coordinates."""
    start = to_frame_point(*line.baseline_start, rotation)
    end = to_frame_point(*line.baseline_end, rotation)
    return line.model_copy(
        update={
            "bbox": to_frame(line.bbox, rotation),
            "baseline_start": start,
            "baseline_end": end,
            "direction": (1.0, 0.0),
            "rotation": 0.0,
            "writing_mode": "horizontal",
        }
    )


def frame_block(block, rotation):
    update = {"bbox": to_frame(block.bbox, rotation)}
    orientation = block.features.get("orientation")
    if orientation and across_axis(rotation) == "x":
        swapped = "vertical" if orientation == "horizontal" else "horizontal"
        update["features"] = {**block.features, "orientation": swapped}
    return block.model_copy(update=update)


def across_axis(rotation):
    """Page axis that runs across the text (the axis bands stack along) for a frame."""
    return "y" if (rotation or 0) % 180 == 0 else "x"
