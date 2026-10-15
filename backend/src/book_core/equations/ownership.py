"""Ownership of equation regions: nothing drawn as math is left without an owner.

Every region gets one owner:

- a region with spans (text, mixed) belongs to the text unit whose line holds its spans:
  the text stays text, the equation is recorded beside it, and drawn objects of a mixed
  region are read at their place in that line;
- drawn objects of an inline equation are read inside the text unit of the line beside them,
  before the first character that follows them along the line's own reading direction;
- a display equation is a unit of its own, anchored in a reading-order stream after the
  nearest line above it (or before the nearest line below) in its own column, never by a
  page-wide sort;
- inside a figure: a figure region whose content is only equation evidence is replaced by its
  equations (read where the figure was anchored; its image is not exported); a real figure
  keeps its image and the equations inside it are recorded with the figure as owner.

A display region with nothing to anchor it is kept for review and never read as an equation.
Units, lines, order and text are unchanged: equation units hold drawn objects only.
"""

from collections import Counter, defaultdict

from book_core.equations.detect import char_boxes, range_box
from book_core.equations.models import (
    EquationAnchor,
    EquationOwner,
    EquationUnit,
    FigureConversion,
    FigureMath,
    GlyphOwnership,
    InlinePlace,
)
from book_core.extraction.fingerprints import stable_id
from book_core.model.common import BBox

# Streams whose lines are not read as content: an equation is never anchored to them.
UNREAD_STREAMS = frozenset({"furniture", "artifact", "invisible"})
IN_FIGURE = 0.5  # share of a region's drawn objects inside a figure's objects


def _axis(line):
    """Unit reading direction of a line: its baseline direction, reversed for right-to-left
    text."""
    dx, dy = line.direction
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    dx, dy = dx / length, dy / length
    if line.text_direction == "rtl":
        dx, dy = -dx, -dy
    return dx, dy


def inline_place(line, store, geometry, box, cells=None):
    """Place of drawn objects in a line: before the first character whose centre lies after
    the objects' start along the line's reading direction; after the line's last character
    when none does."""
    dx, dy = _axis(line)
    start = min(x * dx + y * dy for x in (box.x0, box.x1) for y in (box.y0, box.y1))
    last = None
    for sid in line.span_ids:
        span = store.spans[sid]
        for offset in range(len(span.raw_text)):
            cell = range_box(span, offset, offset + 1, geometry.get(sid), (cells or {}).get(sid))
            centre = (cell.x0 + cell.x1) / 2 * dx + (cell.y0 + cell.y1) / 2 * dy
            if centre > start:
                return InlinePlace(line_id=line.id, span_id=sid, offset=offset)
        last = span
    return InlinePlace(line_id=line.id, span_id=last.id, offset=len(last.raw_text))


def _overlap_x(a, b):
    return min(a.x1, b.x1) - max(a.x0, b.x0)


def display_anchor(box, layout, order):
    """(stream id, after line id, position, confidence, reasons) of a display equation:
    after the nearest content line above it in its column, or before the nearest below."""
    lines = {line.id: line for line in layout.lines}
    place = {}
    for stream in order.streams:
        if stream.kind in UNREAD_STREAMS:
            continue
        for index, lid in enumerate(stream.line_ids):
            place[lid] = (stream, index)
    centre = (box.y0 + box.y1) / 2
    column = [
        lines[lid]
        for lid in place
        if lid in lines and not lines[lid].blank and _overlap_x(lines[lid].bbox, box) > 0
    ]
    above = [line for line in column if line.bbox.y1 <= centre]
    below = [line for line in column if line.bbox.y0 >= centre]
    up = max(above, key=lambda line: line.bbox.y1) if above else None
    down = min(below, key=lambda line: line.bbox.y0) if below else None
    if up is not None:
        stream, index = place[up.id]
        if down is not None:
            next_stream, next_index = place[down.id]
            if next_stream.id == stream.id and next_index == index + 1:
                return stream.id, up.id, index, 0.9, ["between consecutive lines of its stream"]
        if down is None or box.y0 - up.bbox.y1 <= down.bbox.y0 - box.y1:
            return stream.id, up.id, index, 0.7, ["after the nearest line above in its column"]
    if down is not None:
        stream, index = place[down.id]
        after = stream.line_ids[index - 1] if index > 0 else None
        return stream.id, after, index - 1, 0.7, ["before the nearest line below in its column"]
    return None


def _in_prose(region, figure):
    """Drawn objects of an inline equation set in a text line of an ordinary text unit (not
    figure text, not a line the figure links as its own): the text unit reads them even where
    the figure region overlaps that line."""
    if region.presentation != "inline" or region.host.relation != "inside":
        return False
    if region.host.unit_kind == "figure_text":
        return False
    own = {
        line
        for link in (*figure.captions, *figure.credits, *figure.internal_text)
        for line in link.line_ids
    }
    return region.host.line_id not in own


def _drawn_in(region, own_box):
    """The region lies within the extent of the figure's own drawn or raster content."""
    return own_box is not None and own_box.contains_center(region.bbox)


def _figure_anchor(anchor, order):
    """A converted figure's own anchor: after the same line, in the stream holding it."""
    if anchor.after_line_id is None:
        return order.main.id, None, -1, 0.6, ["where the converted figure was anchored"]
    for stream in order.streams:
        if anchor.after_line_id in stream.line_ids:
            position = stream.line_ids.index(anchor.after_line_id)
            return (
                stream.id,
                anchor.after_line_id,
                position,
                0.6,
                ["where the converted figure was anchored"],
            )
    return None


def _figure_of(region, figures):
    """The page figure holding most of the region's drawn objects, if it holds enough."""
    if not region.object_ids:
        return None
    best, share = None, 0.0
    for figure in figures:
        inside = len(set(region.object_ids) & set(figure.object_ids)) / len(region.object_ids)
        if inside > share:
            best, share = figure, inside
    return best if share >= IN_FIGURE else None


def classify_figures(regions, figures, figure_content):
    """{figure id: (converted?, [region], reasons)} for figures holding equation regions.

    ``figure_content(figure)``: the figure's own content beside its equations (a list of
    reasons it is a real figure; empty when its content is only equation evidence)."""
    holding = defaultdict(list)
    for region in regions:
        figure = _figure_of(region, figures)
        if figure is not None:
            holding[figure.id].append(region)
    result = {}
    for figure in figures:
        if figure.id not in holding:
            continue
        reasons = figure_content(figure, holding[figure.id])
        result[figure.id] = (not reasons, holding[figure.id], reasons)
    return result


def own_page(page, layout, built, figures, native, regions, figure_content, image_of):
    """(owned regions, equation units, conversions, kept figures with math, ownership)."""
    store, number = page.store, page.geometry.page
    lines = {line.id: line for line in layout.lines}
    unit_of_line = {lid: unit for unit in built.units for lid in unit.line_ids}
    geometry = native.span_geometry
    cells = char_boxes(native, store)
    native_index = {obj.id: index for index, obj in enumerate(native.objects)}
    page_figures = [f for f in figures.figures if f.page == number]
    by_id = {f.id: f for f in page_figures}
    decided = classify_figures(regions, page_figures, figure_content)
    figure_of_region = {
        region.id: figure_id for figure_id, (_, held, _) in decided.items() for region in held
    }
    own_boxes = {
        figure_id: figure_content.own_box(by_id[figure_id], held)
        for figure_id, (converted, held, _) in decided.items()
        if not converted
    }
    owned, drafts = [], []
    for region in regions:
        figure_id = figure_of_region.get(region.id)
        converted = figure_id is not None and decided[figure_id][0]
        if region.span_refs:
            line = lines[region.line_ids[0]]
            unit = unit_of_line[line.id]
            place = (
                inline_place(line, store, geometry, _objects_box(region, native), cells)
                if region.object_ids
                else None
            )
            owner = EquationOwner(
                kind="text_unit",
                unit_id=unit.id,
                place=place,
                reasons=["its spans are text of this unit; the equation is recorded beside it"],
            )
        elif (
            figure_id is not None
            and not converted
            and not _in_prose(region, by_id[figure_id])
            and _drawn_in(region, own_boxes.get(figure_id))
        ):
            owner = EquationOwner(
                kind="figure",
                figure_id=figure_id,
                reasons=["drawn in a real figure: the figure image keeps the drawn objects"],
            )
        elif region.presentation == "inline" and region.host.relation == "inside":
            line = lines[region.host.line_id]
            owner = EquationOwner(
                kind="text_unit",
                unit_id=region.host.unit_id,
                place=inline_place(line, store, geometry, region.bbox, cells),
                reasons=["inline: read inside the unit of the line beside it"]
                + (["replaces a figure of equation evidence only"] if converted else [])
                + (
                    ["text-flow math that a real figure's region overlaps"]
                    if figure_id is not None and not converted
                    else []
                ),
            )
        else:
            found = display_anchor(region.bbox, layout, built.order)
            if found is None and converted:
                found = _figure_anchor(by_id[figure_id].anchor, built.order)
            if found is not None and converted:
                found = (*found[:4], [*found[4], "replaces a figure of equation evidence only"])
            if found is None:
                owner = EquationOwner(
                    kind="review", reasons=["display equation with no line to anchor it"]
                )
            else:
                unit_id = stable_id(region.id, "equation_unit")
                owner = EquationOwner(
                    kind="equation_unit",
                    unit_id=unit_id,
                    reasons=["display: a unit of its own in reading order"]
                    + (
                        ["text-flow math that a real figure's region overlaps"]
                        if figure_id is not None and not converted
                        else []
                    ),
                )
                drafts.append((region, unit_id, found, figure_id if converted else None))
        owned.append(region.model_copy(update={"owner": owner}))
    units = _number_units(drafts, built.order, native_index, number)
    conversions, kept = [], []
    for figure_id, (converted, held, reasons) in decided.items():
        figure = by_id[figure_id]
        ids = [r.id for r in held]
        if converted:
            conversions.append(
                FigureConversion(
                    figure_id=figure_id,
                    figure_name=figure.name,
                    image_file=image_of(figure),
                    equation_ids=ids,
                    reasons=["its content is only equation evidence"],
                )
            )
        else:
            ids = [
                r.id for r in owned if r.owner.kind == "figure" and r.owner.figure_id == figure_id
            ]
            if ids:
                kept.append(FigureMath(figure_id=figure_id, equation_ids=ids, reasons=reasons))
    return owned, units, conversions, kept, ownership(owned)


def _objects_box(region, native):
    from book_core.equations.detect import _union

    boxes = [o.bbox for o in native.objects if o.id in set(region.object_ids)]
    return _union(boxes) if boxes else region.bbox


def _number_units(drafts, order, native_index, number):
    stream_rank = {stream.id: index for index, stream in enumerate(order.streams)}
    groups = defaultdict(list)
    for region, unit_id, found, figure_id in drafts:
        groups[(found[0], found[2])].append((region, unit_id, found, figure_id))
    rows = []
    for (stream_id, position), members in groups.items():
        members.sort(key=lambda m: min(native_index.get(o, 0) for o in m[0].object_ids))
        for index, (region, unit_id, found, figure_id) in enumerate(members):
            rows.append(
                (stream_rank[stream_id], position, index, region, unit_id, found, figure_id)
            )
    rows.sort(key=lambda row: row[:3])
    units = []
    for reading_index, (_, position, index, region, unit_id, found, figure_id) in enumerate(
        rows, 1
    ):
        stream_id, after, _, confidence, reasons = found
        units.append(
            EquationUnit(
                id=unit_id,
                page=number,
                equation_id=region.id,
                anchor=EquationAnchor(
                    stream_id=stream_id,
                    after_line_id=after,
                    position=position,
                    order=index,
                    reading_index=reading_index,
                    confidence=confidence,
                    reasons=reasons,
                    review_required=confidence < 0.8,
                ),
                converted_figure_id=figure_id,
            )
        )
    return units


def ownership(regions):
    counts = Counter()
    for region in regions:
        n = len(region.object_ids)
        counts["objects"] += n
        counts[region.owner.kind if region.owner is not None else "unowned"] += n
    return GlyphOwnership(
        objects=counts["objects"],
        text_unit=counts["text_unit"],
        equation_unit=counts["equation_unit"],
        figure=counts["figure"],
        review=counts["review"],
        unowned=counts["unowned"],
    )


class FigureContent:
    """``FigureContent(...)(figure, regions)`` for one page: the reasons a figure holding these
    equation regions is a real figure (empty: its content is only equation evidence).

    A real figure has a caption, or drawn or raster content of its own beside the equations'
    objects. A fill painted under an equation (a shaded cell or box behind it, painted
    before it) is its background, not content. Text lines inside the figure region stay units
    of the page either way. ``own_box`` is the extent of that own content: equations inside it
    are drawn in the figure; equations outside it lie in text flow the region overlaps."""

    def __init__(self, page, layout, native):
        self.objects = {o.id: o for o in native.objects}
        self.paint = {o.id: index for index, o in enumerate(native.objects)}

    def _background(self, obj, regions):
        if obj.stroke is not None or obj.fill is None:
            return False
        return any(
            obj.bbox.contains_center(region.bbox)
            and self.paint[obj.id] < min(self.paint.get(o, 0) for o in region.object_ids)
            for region in regions
            if region.object_ids
        )

    def _own(self, figure, regions):
        held = {o for region in regions for o in region.object_ids}
        own = []
        for oid in figure.object_ids:
            if oid in held:
                continue
            obj = self.objects.get(oid)
            if obj is None:
                own.append(("other", None))
            elif obj.kind == "image":
                own.append(("image", obj))
            elif obj.kind == "drawing" and (obj.fill is not None or obj.stroke is not None):
                if obj.bbox is not None and self._background(obj, regions):
                    continue
                own.append(("drawing", obj))
        return own

    def __call__(self, figure, regions):
        reasons = ["it has a caption"] if figure.captions else []
        own = Counter(kind for kind, _ in self._own(figure, regions))
        return reasons + [f"{n} {kind} object(s) of its own" for kind, n in sorted(own.items())]

    def own_box(self, figure, regions):
        boxes = [obj.bbox for _, obj in self._own(figure, regions) if obj is not None and obj.bbox]
        if not boxes:
            return None
        return BBox(
            x0=min(b.x0 for b in boxes),
            y0=min(b.y0 for b in boxes),
            x1=max(b.x1 for b in boxes),
            y1=max(b.y1 for b in boxes),
        )


def final_figures(figures, equations):
    """The page's figures without those converted to equations: reading indexes renumbered,
    credit proposals to converted figures dropped. The figure stage's records stay as they
    are; this is the view written to the final archive."""
    converted = {c.figure_id for c in equations.figure_conversions}
    if not converted:
        return figures
    kept = [f for f in figures.figures if f.id not in converted]
    own = sorted((f for f in kept if f.page == figures.page), key=lambda f: f.anchor.reading_index)
    index = {f.id: i for i, f in enumerate(own, 1)}
    kept = [
        f.model_copy(update={"anchor": f.anchor.model_copy(update={"reading_index": index[f.id]})})
        if f.id in index
        else f
        for f in kept
    ]
    credits = [
        c.model_copy(
            update={"proposed_figure_ids": [i for i in c.proposed_figure_ids if i not in converted]}
        )
        for c in figures.page_credits
    ]
    return figures.model_copy(update={"figures": kept, "page_credits": credits})
