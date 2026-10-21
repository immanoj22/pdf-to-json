"""Ruling lines and fills from native drawings, and their frame geometry.

A rule is an axis-aligned segment painted by a drawing: a stroked line, the edges of a
stroked rectangle, or a filled rectangle thin enough to read as a line. A fill is a filled
area large enough to be a cell or row background; its edges are also kept as weak rules
(``fill_edge``), because some producers draw a grid only as adjacent coloured cells. Near-
white fills paint background, not structure, and are ignored. Every segment is clipped to
its object's painted box (native paths may extend beyond the visible clip).

Geometry is page coordinates; ``in_frame`` maps rules into a rotated reading frame (frame x
along the text), where a rule keeps its axis relative to the text. Thresholds are in font
units supplied by the caller; nothing names a page, font or book.
"""

from dataclasses import dataclass, replace

from book_core.layout.frames import to_frame, to_frame_point
from book_core.model.common import BBox

THIN = 0.25  # font sizes: a filled rectangle this thin is a rule
MIN_RULE = 0.6  # font sizes: shorter segments are glyph parts, not rules
WHITE = 0.97  # every colour component at least this light paints background


@dataclass(frozen=True)
class Rule:
    axis: str  # "h" (along frame x) or "v"
    at: float  # the constant coordinate
    start: float
    end: float
    width: float
    kind: str  # stroke / thin_fill / fill_edge
    object_id: str
    light: bool = False  # near-white paint (a separator only over a coloured fill)

    @property
    def length(self):
        return self.end - self.start


@dataclass(frozen=True)
class Fill:
    bbox: BBox
    color: tuple
    object_id: str


def _white(color):
    return color is not None and len(color) > 0 and all(c >= WHITE for c in color)


def _clip(a0, a1, lo, hi):
    a0, a1 = min(a0, a1), max(a0, a1)
    return max(a0, lo), min(a1, hi)


def _segment(x0, y0, x1, y1, box, kind, width, oid, font, light):
    """An axis-aligned segment clipped to the object's box, or None."""
    tolerance = 0.5
    if abs(y0 - y1) <= tolerance:
        start, end = _clip(x0, x1, box.x0, box.x1)
        at = (y0 + y1) / 2
        if end - start >= MIN_RULE * font and box.y0 - 1 <= at <= box.y1 + 1:
            return Rule("h", at, start, end, width, kind, oid, light)
    elif abs(x0 - x1) <= tolerance:
        start, end = _clip(y0, y1, box.y0, box.y1)
        at = (x0 + x1) / 2
        if end - start >= MIN_RULE * font and box.x0 - 1 <= at <= box.x1 + 1:
            return Rule("v", at, start, end, width, kind, oid, light)
    return None


def _thin_or_fill(x0, y0, x1, y1, box, color, oid, font, light):
    x0, x1 = _clip(x0, x1, box.x0, box.x1)
    y0, y1 = _clip(y0, y1, box.y0, box.y1)
    w, h = x1 - x0, y1 - y0
    if w <= 0 and h <= 0:
        return [], []
    if h <= THIN * font and w >= MIN_RULE * font:
        return [Rule("h", (y0 + y1) / 2, x0, x1, max(h, 0.1), "thin_fill", oid, light)], []
    if w <= THIN * font and h >= MIN_RULE * font:
        return [Rule("v", (x0 + x1) / 2, y0, y1, max(w, 0.1), "thin_fill", oid, light)], []
    if w < MIN_RULE * font or h < MIN_RULE * font:
        return [], []
    fill = Fill(BBox(x0=x0, y0=y0, x1=x1, y1=y1), tuple(color or ()), oid)
    if light:
        return [], [fill]  # kept only where it lies on a coloured fill (see page_rules)
    edges = [
        Rule("h", y0, x0, x1, 0.0, "fill_edge", oid),
        Rule("h", y1, x0, x1, 0.0, "fill_edge", oid),
        Rule("v", x0, y0, y1, 0.0, "fill_edge", oid),
        Rule("v", x1, y0, y1, 0.0, "fill_edge", oid),
    ]
    return edges, [fill]


def page_rules(objects, font):
    """(rules, fills) of a page's drawings; ``font`` is the page's body font size."""
    rules, fills = [], []
    for obj in objects:
        if obj.kind != "drawing" or obj.bbox is None or not obj.path_items:
            continue
        box = obj.bbox
        stroke = obj.stroke is not None and (obj.stroke_width or 0) >= 0
        light_stroke = _white(obj.stroke)
        light_fill = _white(obj.fill)
        width = obj.stroke_width or 0.0
        points = []
        for item in obj.path_items:
            c = item.coordinates
            if item.operator == "l" and len(c) >= 4:
                points += [(c[0], c[1]), (c[2], c[3])]
                if stroke:
                    found = _segment(*c[:4], box, "stroke", width, obj.id, font, light_stroke)
                    if found:
                        rules.append(found)
            elif item.operator == "re" and len(c) >= 4:
                x0, y0, x1, y1 = c[:4]
                if stroke:
                    for edge in ((x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1),
                                 (x1, y0, x1, y1)):  # fmt: skip
                        found = _segment(*edge, box, "stroke", width, obj.id, font, light_stroke)
                        if found:
                            rules.append(found)
                if obj.fill is not None:
                    more_rules, more_fills = _thin_or_fill(
                        x0, y0, x1, y1, box, obj.fill, obj.id, font, light_fill
                    )
                    rules += more_rules
                    fills += more_fills
            elif len(c) >= 2:
                points += [(c[i], c[i + 1]) for i in range(0, len(c) - 1, 2)]
        if (
            obj.fill is not None
            and points
            and not any(item.operator == "re" for item in obj.path_items)
        ):
            # A filled outline made of lines and curves (rounded cells, bars): its box.
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            more_rules, more_fills = _thin_or_fill(
                min(xs), min(ys), max(xs), max(ys), box, obj.fill, obj.id, font, light_fill
            )
            rules += more_rules
            fills += more_fills
    # A near-white fill paints background, except on a coloured fill: white cells over a
    # coloured table background draw the grid as the gaps between them.
    coloured = [f for f in fills if not _white(f.color)]
    kept = []
    for fill in fills:
        if not _white(fill.color):
            kept.append(fill)
        elif any(_covered(fill.bbox, c.bbox) for c in coloured):
            kept.append(fill)
            b = fill.bbox
            rules += [
                Rule("h", b.y0, b.x0, b.x1, 0.0, "fill_edge", fill.object_id),
                Rule("h", b.y1, b.x0, b.x1, 0.0, "fill_edge", fill.object_id),
                Rule("v", b.x0, b.y0, b.y1, 0.0, "fill_edge", fill.object_id),
                Rule("v", b.x1, b.y0, b.y1, 0.0, "fill_edge", fill.object_id),
            ]
    return _without_panels(rules, kept), kept


def _covered(inner, outer):
    w = min(inner.x1, outer.x1) - max(inner.x0, outer.x0)
    h = min(inner.y1, outer.y1) - max(inner.y0, outer.y0)
    own = (inner.x1 - inner.x0) * (inner.y1 - inner.y0)
    return w > 0 and h > 0 and own > 0 and w * h >= 0.9 * own


def _without_panels(rules, fills):
    """Edges of panel fills dropped: a fill enclosing another drawing's fill is a background
    panel (a box around a table or a sidebar), not a cell. A ring (outer and inner rectangle
    of one drawing) is a cell border, not a panel."""

    def inside(a, b):
        w = min(a.x1, b.x1) - max(a.x0, b.x0)
        h = min(a.y1, b.y1) - max(a.y0, b.y0)
        own = (a.x1 - a.x0) * (a.y1 - a.y0)
        return w > 0 and h > 0 and own > 0 and w * h >= 0.9 * own

    def size(b):
        return (b.x1 - b.x0) * (b.y1 - b.y0)

    panels = {
        f.object_id
        for f in fills
        if any(
            g is not f
            and g.object_id != f.object_id
            and inside(g.bbox, f.bbox)
            and size(g.bbox) < 0.9 * size(f.bbox)
            for g in fills
        )
    }
    return [r for r in rules if not (r.kind == "fill_edge" and r.object_id in panels)]


def in_frame(rules, fills, rotation):
    """Rules and fills expressed in a reading frame (rotation 0 returns them unchanged)."""
    if not rotation:
        return list(rules), list(fills)
    framed = []
    for rule in rules:
        if rule.axis == "h":
            a = to_frame_point(rule.start, rule.at, rotation)
            b = to_frame_point(rule.end, rule.at, rotation)
        else:
            a = to_frame_point(rule.at, rule.start, rotation)
            b = to_frame_point(rule.at, rule.end, rotation)
        if abs(a[1] - b[1]) <= 0.5:
            framed.append(replace(rule, axis="h", at=(a[1] + b[1]) / 2,
                                  start=min(a[0], b[0]), end=max(a[0], b[0])))  # fmt: skip
        else:
            framed.append(replace(rule, axis="v", at=(a[0] + b[0]) / 2,
                                  start=min(a[1], b[1]), end=max(a[1], b[1])))  # fmt: skip
    return framed, [replace(f, bbox=to_frame(f.bbox, rotation)) for f in fills]


def merged(rules, tolerance):
    """Collinear rules of one axis that overlap or nearly touch become one rule: rules are
    clustered by position, then each cluster's intervals are merged along the axis."""
    out = []
    for axis in ("h", "v"):
        pending = sorted((r for r in rules if r.axis == axis), key=lambda r: r.at)
        clusters = []
        for rule in pending:
            if clusters and rule.at - clusters[-1][-1].at <= tolerance:
                clusters[-1].append(rule)
            else:
                clusters.append([rule])
        for cluster in clusters:
            groups = []
            for rule in sorted(cluster, key=lambda r: r.start):
                if groups and rule.start <= max(g.end for g in groups[-1]) + tolerance:
                    groups[-1].append(rule)
                else:
                    groups.append([rule])
            for group in groups:
                strong = [g for g in group if g.kind != "fill_edge"]
                kinds = {g.kind for g in group}
                out.append(
                    Rule(
                        axis,
                        sum(g.at for g in group) / len(group),
                        min(g.start for g in group),
                        max(g.end for g in group),
                        max(g.width for g in group),
                        "stroke" if "stroke" in kinds else ("thin_fill" if strong else "fill_edge"),
                        group[0].object_id,
                        all(g.light for g in group),
                    )
                )
    return out


def freeform(objects):
    """Boxes of drawings that are not axis-aligned rules or rectangles: curves or slanted
    lines (map outlines, diagram strokes, arrows)."""
    found = []
    for obj in objects:
        if obj.kind != "drawing" or obj.bbox is None or not obj.path_items:
            continue
        slanted = 0
        for item in obj.path_items:
            c = item.coordinates
            if item.operator == "c":
                slanted += 1
            elif item.operator == "l" and len(c) >= 4:
                if abs(c[0] - c[2]) > 0.5 and abs(c[1] - c[3]) > 0.5:
                    slanted += 1
        if slanted >= max(2, len(obj.path_items) // 2):
            found.append(obj.bbox)
    return found
