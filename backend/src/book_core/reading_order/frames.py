"""Reading frames for ordering: block axis (lines and bands advance) and inline axis.

Rotated scopes are first transformed into their own frame (``layout.frames``), where text runs
along +x. Horizontal writing then advances lines along +y; lanes and items in a row follow the
writing direction (left to right, or right to left for rtl lanes). Vertical writing (ttb) runs
along +y and advances lines and lanes right to left. Nothing here assumes a script.
"""

from dataclasses import dataclass

from book_core.layout.frames import right_angle, to_frame, to_frame_point


@dataclass(frozen=True)
class Frame:
    rotation: float = 0.0
    vertical: bool = False
    rtl: bool = False

    def box(self, bbox):
        return to_frame(bbox, self.rotation) if self.rotation else bbox

    def with_direction(self, rtl):
        return Frame(self.rotation, self.vertical, rtl)

    # Bands of a scope stack along frame y in both writing modes.
    def band_key(self, bbox):
        box = self.box(bbox)
        return (box.y0, box.x0)

    def block_interval(self, bbox):
        box = self.box(bbox)
        return (-box.x1, -box.x0) if self.vertical else (box.y0, box.y1)

    def center_key(self, bbox):
        start, end = self.block_interval(bbox)
        return (start + end) / 2

    def line_key(self, line):
        """Baseline position along the block axis; robust to tall glyphs and drop caps."""
        if self.vertical:
            return self.center_key(line.bbox)
        aligned = right_angle(line.rotation - self.rotation) == 0
        if not aligned:
            return self.center_key(line.bbox)
        if self.rotation:
            start = to_frame_point(*line.baseline_start, self.rotation)
            end = to_frame_point(*line.baseline_end, self.rotation)
        else:
            start, end = line.baseline_start, line.baseline_end
        return (start[1] + end[1]) / 2

    def inline_key(self, bbox):
        box = self.box(bbox)
        if self.vertical:
            return box.y0
        return -box.x1 if self.rtl else box.x0

    def lane_key(self, lane):
        """Lane x positions are already in the scope frame (see ``layout.models.Scope``)."""
        return -lane.x1 if (self.rtl or self.vertical) else lane.x0

    def x_interval(self, bbox):
        box = self.box(bbox)
        return box.x0, box.x1
