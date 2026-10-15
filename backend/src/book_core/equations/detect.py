"""Equation regions of one page from native evidence; layout-model boxes are support only.

Vector regions: recurring glyph outlines (``glyphs``) joined by proximity, with rule bars
that have the nearest rows of glyphs on both sides (fractions) or just below (overlines).
Boundaries (Step 13b), all relative to the book's text size and line pitch:

- drawing groups: a text-free clip lying close around its marks is one native drawing; its
  marks join, and marks of two different groups never join by proximity;
- operator bars (a minus) and dots (decimal points) join the glyphs beside them on their
  band; parts (a wide radical sign, an overline piece) join the cluster they touch or share
  a group with; none of them starts a cluster;
- glyphs set inside a text line stack only at accent distance and never across two text
  lines; display rows closer than one text line pitch, with no text between, are one display.

Text regions: operator runs (``text``). A vector region and a text run on the same visual
band that touch are one mixed region; a text run never bridges two drawing groups. A region
is inline when text of a visual line shares its band beside it, display otherwise. Where a
region lands is the unit that holds its line (inline), or the unit of the nearest line above
it (display). Lettering lighter than the fill painted right behind it (a logo, a banner) is
not typeset math.

Nothing is dropped or reordered: regions are added evidence over unchanged units; owners
are decided by ``ownership``.
"""

import unicodedata
from collections import Counter, defaultdict

from book_core.equations.glyphs import BAR_MAX_HEIGHT, page_dots, page_glyphs, page_parts
from book_core.equations.models import (
    EquationRegion,
    Host,
    ModelOnlyRegion,
    ModelSupport,
)
from book_core.equations.text import line_runs
from book_core.extraction.fingerprints import stable_id
from book_core.model.common import BBox, SpanRef

# Distances relative to the page's median text size.
JOIN_GAP = 0.9
STACK_GAP = 0.6
BAR_REACH = 1.2
INLINE_REACH = 3.0
BAND_OVERLAP = 0.5
MODEL_OVERLAP = 0.5
BAR_MAX_WIDTH = 40.0
COLOUR_TOLERANCE = 0.06  # per channel, 0-1
ACCENT_GAP = 0.25  # stacking of glyphs set inside a text line (accents, primes)
ROW_SLACK = 0.3  # a fraction bar takes the nearest row above and below it
OVERLINE_REACH = 0.35
OPERATOR_MAX_WIDTH = 2.0  # a loose bar read as an operator sign (minus)
MARK_STACK = 0.4  # bars of one sign stacked (an equals sign drawn as two bars)
CLIP_MARGIN = 1.0  # a drawing group's clip lies this close around its marks
TOUCH = 0.15  # objects this close on both axes touch
REVERSED_CONTRAST = 0.3  # luminance by which reversed lettering exceeds its ground
ROW_GAP = 1.0  # display rows closer than this many text line pitches are one display
DEFAULT_PITCH = 1.2


def _fill(obj):
    return tuple(obj.fill or obj.stroke or ())


def _same_colour(a, b):
    return len(a) == len(b) and all(
        abs(x - y) <= COLOUR_TOLERANCE for x, y in zip(a, b, strict=True)
    )


def _luminance(colour):
    if len(colour) == 3:
        return 0.2126 * colour[0] + 0.7152 * colour[1] + 0.0722 * colour[2]
    if len(colour) == 1:
        return colour[0]
    if len(colour) == 4:  # CMYK
        return (1 - colour[3]) * (1 - (colour[0] + colour[1] + colour[2]) / 3)
    return None


def reversed_out(cluster, paint_order, fills, text_items=()):
    """The cluster is lighter than the filled shape painted right behind it, and no fill of
    that shape's colour on the page holds text of the cluster's colour: lettering reversed out
    of a dark shape (a logo). Math reversed in shaded text areas (table header cells) is set
    among text of its own colour on fills of the same colour. ``fills``: [(paint index,
    object)] of filled drawings; ``text_items``: [(box, colour)] of the page's text spans."""
    box = _union(o.bbox for o in cluster)
    first = min(paint_order.get(o.id, 0) for o in cluster)
    behind = [
        (index, obj)
        for index, obj in fills
        if index < first and obj.bbox is not None and obj.bbox.contains_center(box)
    ]
    if not behind:
        return False
    _, background = max(behind, key=lambda item: item[0])
    ink, ground = _luminance(_fill(cluster[0])), _luminance(_fill(background))
    if ink is None or ground is None or ink <= ground + REVERSED_CONTRAST:
        return False
    grounds = [obj.bbox for _, obj in fills if _same_colour(_fill(obj), _fill(background))]
    return not any(
        _same_colour(_fill(cluster[0]), colour)
        and any(ground_box.contains_center(text_box) for ground_box in grounds)
        for text_box, colour in text_items
    )


def typeset_like(cluster, images, text_colours, paint_order=None, fills=(), text_items=()):
    """Typeset characters of one expression are painted in one colour that the page's own text
    uses, darker than what they are printed on, and are not drawn over a picture; drawn art
    (map symbols, icons, logos) is not. Returns the reason a cluster is not typeset-like, or
    None."""
    colours = [_fill(o) for o in cluster]
    if any(not _same_colour(colours[0], colour) for colour in colours[1:]):
        return "several colours"
    box = _union(o.bbox for o in cluster)
    if any(
        _horizontal_overlap(box, image) > 0 and _vertical_overlap(box, image) > 0
        for image in images
    ):
        return "drawn over an image"
    if not any(_same_colour(colours[0], colour) for colour in text_colours):
        return "colour unused by the page's text"
    if paint_order is not None and reversed_out(cluster, paint_order, fills, text_items):
        return "reversed out of a darker fill"
    return None


def _union(boxes):
    boxes = list(boxes)
    return BBox(
        x0=min(b.x0 for b in boxes),
        y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes),
        y1=max(b.y1 for b in boxes),
    )


def _vertical_overlap(a, b):
    return min(a.y1, b.y1) - max(a.y0, b.y0)


def _horizontal_overlap(a, b):
    return min(a.x1, b.x1) - max(a.x0, b.x0)


def _gap(a, b):
    dx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    dy = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    return dx, dy


def _overlap_share(a, b):
    w, h = _horizontal_overlap(a, b), _vertical_overlap(a, b)
    if w <= 0 or h <= 0:
        return 0.0
    smaller = min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0))
    return w * h / smaller if smaller > 0 else 0.0


class _Sets:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[b] = a


def char_boxes(native, store):
    """{span id: [glyph box per character]} from the rendered glyphs of the page's native
    text objects, for spans whose glyphs match their characters one to one; other spans are
    absent (their ranges fall back to an even share of the span)."""
    glyphs = defaultdict(list)
    for obj in native.objects:
        if obj.kind != "text" or len(obj.source_spans) != 1:
            continue
        for info in obj.render_info:
            glyphs[obj.source_spans[0]].extend(info.glyphs)
    result = {}
    for sid, found in glyphs.items():
        span = store.spans.get(sid)
        if span is None or len(found) != len(span.raw_text):
            continue
        if any(
            chr(g.unicode) != c or g.bbox is None for g, c in zip(found, span.raw_text, strict=True)
        ):
            continue
        result[sid] = [g.bbox for g in found]
    return result


def range_box(span, start, end, frame=None, glyphs=None):
    """Box of a character range of a span: the union of its rendered glyph boxes when
    ``glyphs`` (the span's glyph boxes) is given, else its share of the span's extent along
    the span's own writing direction (characters taken as equally wide)."""
    if glyphs is not None and end > start:
        return _union(glyphs[start:end])
    box, length = span.bbox, max(1, len(span.raw_text))
    a, b = start / length, end / length
    dx, dy = frame.direction if frame is not None else (1.0, 0.0)
    if abs(dx) >= abs(dy):
        x0, x1 = (box.x0, box.x1) if dx >= 0 else (box.x1, box.x0)
        left, right = sorted((x0 + (x1 - x0) * a, x0 + (x1 - x0) * b))
        return BBox(x0=left, y0=box.y0, x1=right, y1=box.y1)
    y0, y1 = (box.y0, box.y1) if dy >= 0 else (box.y1, box.y0)
    top, bottom = sorted((y0 + (y1 - y0) * a, y0 + (y1 - y0) * b))
    return BBox(x0=box.x0, y0=top, x1=box.x1, y1=bottom)


def _text_between(a, b, text_boxes):
    """Text on the shared band lies in the horizontal gap between two boxes."""
    left, right = (a, b) if a.x1 <= b.x0 else (b, a)
    if left.x1 >= right.x0:
        return False
    y0, y1 = max(a.y0, b.y0), min(a.y1, b.y1)
    return any(
        t.x0 >= left.x1 - 0.5 and t.x1 <= right.x0 + 0.5 and min(t.y1, y1) > max(t.y0, y0)
        for t in text_boxes
    )


def beside_others(group, signatures):
    """Glyphs of a group with a glyph of another shape beside them on their band (set side by
    side, as characters are), not nested inside or around each other (as icon parts are)."""
    result = []
    for item in group:
        for other in group:
            if other is item or _vertical_overlap(item.bbox, other.bbox) <= 0:
                continue
            if signatures[other.id] == signatures[item.id]:
                continue
            narrow = min(item.bbox.x1 - item.bbox.x0, other.bbox.x1 - other.bbox.x0)
            if _horizontal_overlap(item.bbox, other.bbox) <= 0.2 * narrow:
                result.append(item)
                break
    return result


def drawing_groups(marks, clips, text_boxes, size):
    """{object id: clip id} of marks drawn under a local clip.

    A producer that clips a drawing groups its paths natively. The innermost clip of a mark
    is a drawing group when it holds at least two marks, no text, and lies close around
    them (a page, column or picture clip holds text or reaches far beyond its marks).
    Without such clips every mark is ungrouped and proximity alone decides.
    """
    members = defaultdict(list)
    for mark in marks:
        if mark.clip_ids:
            members[mark.clip_ids[-1]].append(mark)
    result = {}
    for clip_id, held in members.items():
        clip = clips.get(clip_id)
        if clip is None or clip.bbox is None or len(held) < 2:
            continue
        box, around = clip.bbox, _union(m.bbox for m in held)
        margin = CLIP_MARGIN * size
        tight = (
            box.x0 >= around.x0 - margin
            and box.y0 >= around.y0 - margin
            and box.x1 <= around.x1 + margin
            and box.y1 <= around.y1 + margin
        )
        if tight and not any(box.contains_center(t) for t in text_boxes):
            for mark in held:
                result[mark.id] = clip_id
    return result


def _separate(a, b, groups):
    """Two marks of different drawing groups are never joined by proximity."""
    ga, gb = groups.get(a.id), groups.get(b.id)
    return ga is not None and gb is not None and ga != gb


def text_band(box, text_boxes, size):
    """(y0, y1) of the nearby text the box is set beside (its text line), or None."""
    best, share = None, 0.0
    for t in text_boxes:
        overlap = _vertical_overlap(t, box)
        if overlap <= BAND_OVERLAP * min(t.y1 - t.y0, box.y1 - box.y0):
            continue
        if _gap(t, box)[0] <= INLINE_REACH * size and overlap > share:
            best, share = (t.y0, t.y1), overlap
    return best


def beside_text(box, text_boxes, size):
    """Text shares the box's band nearby: the mark is set inside a text line (inline)."""
    return text_band(box, text_boxes, size) is not None


def glyph_groups(glyphs, size, text_boxes, groups=None, inline=None):
    """[[objects]] of glyph outlines joined by proximity, never across text between them.

    With drawing groups (``groups``) the marks of one group join and marks of different
    groups never join; with ``inline`` ({glyph id: band of the text line it is set in})
    inline glyphs stack only at accent distance and never across two text lines, so
    expressions on neighbouring lines stay apart."""
    groups = groups or {}
    inline = inline or {}
    sets = _Sets(len(glyphs))
    first = {}
    for i, a in enumerate(glyphs):
        group = groups.get(a.id)
        if group is not None:
            if group in first:
                sets.join(first[group], i)
            else:
                first[group] = i
        for j in range(i + 1, len(glyphs)):
            b = glyphs[j]
            if _separate(a, b, groups):
                continue
            dx, dy = _gap(a.bbox, b.bbox)
            same_band = _vertical_overlap(a.bbox, b.bbox) > 0
            stacked = _horizontal_overlap(a.bbox, b.bbox) > 0
            line_a, line_b = inline.get(a.id), inline.get(b.id)
            stack_gap = ACCENT_GAP if line_a or line_b else STACK_GAP
            other_lines = bool(line_a and line_b) and min(line_a[1], line_b[1]) <= max(
                line_a[0], line_b[0]
            )
            joined = (same_band and dx <= JOIN_GAP * size) or (
                not other_lines
                and (
                    (stacked and dy <= stack_gap * size)
                    or (dx <= 0.15 * size and dy <= 0.15 * size)
                )
            )
            if joined and not (same_band and _text_between(a.bbox, b.bbox, text_boxes)):
                sets.join(i, j)
    result = defaultdict(list)
    for i, item in enumerate(glyphs):
        result[sets.find(i)].append(item)
    return list(result.values())


def _cluster_groups(cluster, groups):
    return {groups[o.id] for o in cluster if o.id in groups}


def _row(candidates, size):
    """The nearest row of (gap, cluster index) candidates: a fraction's numerator or
    denominator, not a line further away."""
    if not candidates:
        return []
    nearest = min(gap for gap, _ in candidates)
    return sorted({index for gap, index in candidates if gap <= nearest + ROW_SLACK * size})


def vector_clusters(
    glyphs, bars, signatures, accepted, size, text_boxes=(), dots=(), clips=None, parts=()
):
    """[[objects]] of joined glyphs; a cluster needs at least one accepted outline (recurring
    in the book and often written next to other glyphs). Bars, dots and parts never start
    one."""
    groups = drawing_groups([*glyphs, *bars, *dots, *parts], clips or {}, text_boxes, size)
    bands = {g.id: text_band(g.bbox, text_boxes, size) for g in glyphs}
    inline = {gid: band for gid, band in bands.items() if band is not None}
    clusters = [
        g
        for g in glyph_groups(glyphs, size, text_boxes, groups, inline)
        if any(signatures[x.id] in accepted for x in g)
    ]
    # Bars and dots of a drawing group belong to the cluster of that group.
    by_group = {}
    for index, cluster in enumerate(clusters):
        for group in _cluster_groups(cluster, groups):
            by_group.setdefault(group, index)
    loose_bars, loose_dots = [], []
    for mark in bars:
        index = by_group.get(groups.get(mark.id))
        if index is None:
            loose_bars.append(mark)
        else:
            clusters[index] = clusters[index] + [mark]
    for mark in dots:
        index = by_group.get(groups.get(mark.id))
        if index is None:
            loose_dots.append(mark)
        else:
            clusters[index] = clusters[index] + [mark]
    # Bars join the nearest row(s) they separate (fraction) or cover (overline).
    operators = []
    for bar in loose_bars:
        box = bar.bbox
        if box.x1 - box.x0 > BAR_MAX_WIDTH * size:
            continue
        above, below = [], []
        for index, cluster in enumerate(clusters):
            if any(_separate(bar, item, groups) for item in cluster):
                continue
            for item in cluster:
                if _horizontal_overlap(item.bbox, box) <= 0:
                    continue
                if 0 <= box.y0 - item.bbox.y1 <= BAR_REACH * size:
                    above.append((box.y0 - item.bbox.y1, index))
                elif 0 <= item.bbox.y0 - box.y1 <= BAR_REACH * size:
                    below.append((item.bbox.y0 - box.y1, index))
        nearest_below = min((gap for gap, _ in below), default=None)
        above, below = _row(above, size), _row(below, size)
        thin = box.y1 - box.y0 <= BAR_MAX_HEIGHT * size
        if above and below:
            touched = sorted(set(above) | set(below))
        elif below and not above and thin and nearest_below <= OVERLINE_REACH * size:
            touched = below
        else:
            operators.append(bar)
            continue
        merged = [bar]
        for index in touched:
            merged.extend(clusters[index])
        clusters = [c for i, c in enumerate(clusters) if i not in touched] + [merged]
    # Operator bars (a minus sign) and dots join the cluster(s) beside them on their band.
    marks = [b for b in operators if b.bbox.x1 - b.bbox.x0 <= OPERATOR_MAX_WIDTH * size]
    clusters = _attach_marks(clusters, marks + loose_dots, groups, size, text_boxes)
    clusters = _attach_parts(clusters, parts, groups, size)
    # Fraction parts and their neighbours on the same band join once bars are placed.
    changed = True
    while changed:
        changed = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                gi, gj = _cluster_groups(clusters[i], groups), _cluster_groups(clusters[j], groups)
                if gi and gj and gi != gj:
                    continue
                a, b = _union(o.bbox for o in clusters[i]), _union(o.bbox for o in clusters[j])
                dx, _ = _gap(a, b)
                if (
                    _vertical_overlap(a, b) > 0
                    and dx <= JOIN_GAP * size
                    and not _text_between(a, b, text_boxes)
                ):
                    clusters[i] = clusters[i] + clusters[j]
                    del clusters[j]
                    changed = True
                    break
            if changed:
                break
    return clusters


def _attach_parts(clusters, parts, groups, size):
    """Parts join the cluster of their colour sharing their drawing group, or one they
    touch."""
    remaining = list(parts)
    changed = True
    while changed and remaining:
        changed = False
        for part in list(remaining):
            group = groups.get(part.id)
            for index, cluster in enumerate(clusters):
                if not _same_colour(_fill(part), _fill(cluster[0])):
                    continue
                if group is not None:
                    hit = group in _cluster_groups(cluster, groups)
                else:
                    hit = any(
                        not _separate(part, item, groups)
                        and max(_gap(part.bbox, item.bbox)) <= TOUCH * size
                        for item in cluster
                    )
                if hit:
                    clusters[index] = cluster + [part]
                    remaining.remove(part)
                    changed = True
                    break
    return clusters


def _on_band(mark, item):
    """The mark's centre lies within the vertical extent of a glyph (a minus at the math
    axis, a decimal point on the baseline)."""
    centre = (mark.bbox.y0 + mark.bbox.y1) / 2
    return item.bbox.y0 <= centre <= item.bbox.y1


def _marks_join(x, y, size):
    dx, dy = _gap(x.bbox, y.bbox)
    if _horizontal_overlap(x.bbox, y.bbox) > 0 and dy <= MARK_STACK * size:
        return True
    return _vertical_overlap(x.bbox, y.bbox) > 0 and dx <= JOIN_GAP * size


def _attach_marks(clusters, marks, groups, size, text_boxes):
    """Marks join each other (stacked bars of one sign, dots of an ellipsis) and the
    clusters beside them on their band; a set of marks touching no cluster is dropped."""
    nodes = [("cluster", c) for c in clusters] + [("mark", [m]) for m in marks]
    sets = _Sets(len(nodes))
    for i in range(len(clusters), len(nodes)):
        mark = nodes[i][1][0]
        for j, (kind, members) in enumerate(nodes):
            if j == i or (kind == "mark" and j < i):
                continue
            for item in members:
                if _separate(mark, item, groups):
                    continue
                if kind == "mark":
                    joined = _marks_join(mark, item, size)
                else:
                    joined = (
                        _on_band(mark, item)
                        and _gap(mark.bbox, item.bbox)[0] <= JOIN_GAP * size
                        and not _text_between(mark.bbox, item.bbox, text_boxes)
                    )
                if joined:
                    sets.join(i, j)
                    break
    merged = defaultdict(list)
    for i in range(len(nodes)):
        merged[sets.find(i)].append(i)
    return [
        [o for i in indexes for o in nodes[i][1]]
        for indexes in merged.values()
        if any(nodes[i][0] == "cluster" for i in indexes)
    ]


def _line_text_boxes(store, lines):
    return [(line, [store.spans[sid].bbox for sid in line.span_ids]) for line in lines]


def presentation(box, store, lines, size, exclude_spans=frozenset()):
    """Inline when a visual line's text shares the band beside the region."""
    for line in lines:
        if not line.horizontal:
            continue
        for sid in line.span_ids:
            if sid in exclude_spans or not store.spans[sid].raw_text.strip():
                continue
            span = store.spans[sid].bbox
            overlap = _vertical_overlap(span, box)
            if overlap <= BAND_OVERLAP * min(span.y1 - span.y0, box.y1 - box.y0):
                continue
            dx, _ = _gap(span, box)
            if dx <= INLINE_REACH * size:
                return "inline", line
    return "display", None


def _host(line, box, units_by_line, lines, regions_by_line, display):
    if line is not None and line.id in units_by_line:
        unit = units_by_line[line.id]
        return Host(
            unit_id=unit.id,
            unit_kind=unit.kind,
            line_id=line.id,
            relation="inside",
            region_type=regions_by_line.get(line.id),
        )
    above = [
        candidate
        for candidate in lines
        if candidate.bbox.y1 <= (box.y0 + box.y1) / 2
        and _horizontal_overlap(candidate.bbox, box) > 0
        and candidate.id in units_by_line
    ]
    if above:
        nearest = max(above, key=lambda c: c.bbox.y1)
        unit = units_by_line[nearest.id]
        return Host(
            unit_id=unit.id,
            unit_kind=unit.kind,
            line_id=nearest.id,
            relation="after",
            region_type=regions_by_line.get(nearest.id),
        )
    below = [c for c in lines if c.bbox.y0 >= (box.y0 + box.y1) / 2 and c.id in units_by_line]
    if below:
        nearest = min(below, key=lambda c: c.bbox.y0)
        unit = units_by_line[nearest.id]
        return Host(
            unit_id=unit.id,
            unit_kind=unit.kind,
            line_id=nearest.id,
            relation="before",
            region_type=regions_by_line.get(nearest.id),
        )
    return Host()


def _support(box, model_boxes):
    support = {}
    labels = set()
    for model, rows in model_boxes.items():
        hit = [label for other, label in rows if _overlap_share(box, other) >= MODEL_OVERLAP]
        support[model] = bool(hit)
        labels.update(hit)
    return ModelSupport(
        heron=support.get("heron", False),
        pp_doclayoutv3=support.get("pp", False),
        labels=sorted(labels),
    )


def _open_end(text):
    """An expression left open at a line end: a trailing operator or unclosed bracket."""
    stripped = text.rstrip()
    if not stripped:
        return False
    if unicodedata.category(stripped[-1]) == "Sm":
        return True
    return sum(stripped.count(c) for c in "([{") > sum(stripped.count(c) for c in ")]}")


def _join_wrapped(drafts, store, lines, units):
    """Join a text run left open at the end of a line with the run opening the unit's next
    line (an inline expression wrapped across lines)."""
    line_text = {
        line.id: "".join(store.spans[sid].raw_text for sid in line.span_ids) for line in lines
    }
    offsets = {}
    for line in lines:
        start = 0
        for sid in line.span_ids:
            offsets[sid] = (line.id, start)
            start += len(store.spans[sid].raw_text)
    following = {}
    for unit in units:
        for previous, current in zip(unit.line_ids, unit.line_ids[1:], strict=False):
            following[previous] = current

    def bounds(draft):
        sid, a, _ = draft["ranges"][0]
        lid, base = offsets[sid]
        last_sid, _, b = draft["ranges"][-1]
        _, last_base = offsets[last_sid]
        return lid, base + a, last_base + b

    changed = True
    while changed:
        changed = False
        texts = [d for d in drafts if d["ranges"] and not d["objects"]]
        for a in texts:
            lid, _, end = bounds(a)
            lid = a["line_ids"][-1]
            text = line_text.get(lid, "")
            if text[end:].strip() or not _open_end(
                "".join(store.spans[s].raw_text[x:y] for s, x, y in a["ranges"])
            ):
                continue
            nxt = following.get(lid)
            for b in texts:
                if b is a or b["line_ids"][0] != nxt:
                    continue
                b_line, b_start, _ = bounds(b)
                if line_text.get(b_line, "")[:b_start].strip():
                    continue
                a["box"] = _union([a["box"], b["box"]])
                a["ranges"] = a["ranges"] + b["ranges"]
                a["line_ids"] = a["line_ids"] + b["line_ids"]
                a["rules"] = sorted(set(a["rules"]) | set(b["rules"]) | {"wrapped_across_lines"})
                a["signals"] = {**b["signals"], **a["signals"], "whole_line": False}
                drafts.remove(b)
                changed = True
                break
            if changed:
                break


def _junction(text_atom, drawn_atom, size):
    """A text part joins a drawn part through an operator or bracket at their junction, or
    by touching it with no space; text with equation evidence of its own always joins."""
    box, character, evidence = text_atom
    if evidence:
        return True
    if character is not None and (
        unicodedata.category(character) in {"Sm", "Pd"} or character in "()[]{}|"
    ):
        return True
    return _gap(box, drawn_atom[0])[0] <= TOUCH * size


def _facing(a, b, size):
    """The nearest (text atom, drawn atom) pair of two drafts that share a band (the text
    atom's band overlaps the drawn atom), or None."""
    best = None
    for x in a["atoms"]:
        for y in b["atoms"]:
            text_atom, drawn_atom = (x, y) if x[1] is not None else (y, x)
            if text_atom[1] is None or drawn_atom[1] is not None:
                continue
            t, d = text_atom[0], drawn_atom[0]
            if _vertical_overlap(t, d) <= BAND_OVERLAP * min(t.y1 - t.y0, d.y1 - d.y0):
                continue
            gap = _gap(t, d)[0]
            if gap <= JOIN_GAP * size and (best is None or gap < best[0]):
                best = (gap, text_atom, drawn_atom)
    return best


def _separated(facing, separators):
    """A list separator of the line (a comma, semicolon or colon before a space) stands
    between the facing text and drawn parts."""
    _, text_atom, drawn_atom = facing
    t, d = text_atom[0], drawn_atom[0]
    left, right = min(t.x1, d.x1), max(t.x0, d.x0)
    return any(
        box.x0 >= left - 0.5 and box.x1 <= right + 0.5 and _vertical_overlap(box, t) > 0
        for box in separators
    )


def _join_mixed(drafts, size, separators=()):
    """Text parts and drawn parts of one expression on one line are one region: they share
    a band and meet through an operator, a bracket or touching (``f(x) =`` before a drawn
    fraction, ``(23 − 12)`` before a drawn bracket). Text runs end at list separators
    (``text``), and a separator between a text part and a drawn part keeps them apart, so a
    separator never joins two expressions."""
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(drafts):
            for j in range(i + 1, len(drafts)):
                b = drafts[j]
                drawn_and_text = (a["objects"] and b["ranges"]) or (a["ranges"] and b["objects"])
                if not drawn_and_text:
                    continue
                facing = _facing(a, b, size)
                if facing is None or not _junction(facing[1], facing[2], size):
                    continue
                if _separated(facing, separators):
                    continue
                a["box"] = _union([a["box"], b["box"]])
                a["objects"] = sorted(set(a["objects"]) | set(b["objects"]))
                a["ranges"] = a["ranges"] + b["ranges"]
                a["line_ids"] = a["line_ids"] + [x for x in b["line_ids"] if x not in a["line_ids"]]
                a["rules"] = sorted(
                    set(a["rules"])
                    | set(b["rules"])
                    | ({"text_part"} if a["part"] or b["part"] else set())
                )
                a["signals"] = {**b["signals"], **a["signals"]}
                a["groups"] = a["groups"] | b["groups"]
                a["atoms"] = a["atoms"] + b["atoms"]
                a["part"] = False
                del drafts[j]
                merged = True
                break
            if merged:
                break


def line_pitches(layout, units):
    """Baseline distances between consecutive horizontal lines of a unit (book statistics
    for the distance at which a display continues on its next row)."""
    lines = {line.id: line for line in layout.lines}
    result = []
    for unit in units:
        for previous, current in zip(unit.line_ids, unit.line_ids[1:], strict=False):
            a, b = lines.get(previous), lines.get(current)
            if a is None or b is None or not (a.horizontal and b.horizontal):
                continue
            distance = b.baseline_start[1] - a.baseline_start[1]
            if distance > 0:
                result.append(distance)
    return result


def _join_rows(drafts, text_boxes, size, pitch):
    """Rows of one display (a multi-line equation, an aligned derivation) join: display
    rows that overlap horizontally, lie closer than one text line pitch of the book, and
    have no text or other drawing group between them."""
    changed = True
    while changed:
        changed = False
        rows = [d for d in drafts if d["objects"] and not d["ranges"] and not d["inline"]]
        for a in rows:
            for b in rows:
                if a is b or a["box"].y1 > b["box"].y0:
                    continue
                if a["groups"] and b["groups"] and a["groups"] != b["groups"]:
                    continue
                if _horizontal_overlap(a["box"], b["box"]) <= 0:
                    continue
                gap = b["box"].y0 - a["box"].y1
                if gap > ROW_GAP * pitch:
                    continue
                x0, x1 = min(a["box"].x0, b["box"].x0), max(a["box"].x1, b["box"].x1)
                if any(
                    t.y0 >= a["box"].y1 - 0.5
                    and t.y1 <= b["box"].y0 + 0.5
                    and t.x1 > x0
                    and t.x0 < x1
                    for t in text_boxes
                ):
                    continue
                a["box"] = _union([a["box"], b["box"]])
                a["objects"] = sorted(set(a["objects"]) | set(b["objects"]))
                a["rules"] = sorted(set(a["rules"]) | set(b["rules"]) | {"display_rows"})
                a["signals"] = {
                    k: (a["signals"].get(k, 0) + b["signals"].get(k, 0))
                    if isinstance(a["signals"].get(k), int | float)
                    and not isinstance(a["signals"].get(k), bool)
                    else a["signals"].get(k, b["signals"].get(k))
                    for k in {*a["signals"], *b["signals"]}
                }
                a["groups"] = a["groups"] | b["groups"]
                drafts.remove(b)
                changed = True
                break
            if changed:
                break


def detect_page(
    page, native, layout, units, recurring, math_fonts, model_boxes, size, config, pitch=None
):
    """(regions, model-only boxes, diagnostics) of one page. ``pitch``: the book's median
    text line pitch (defaults to a relative one)."""
    pitch = pitch or DEFAULT_PITCH * size
    store = page.store
    number = page.geometry.page
    lines = [line for line in layout.lines if line.inside_content and not line.blank]
    text_boxes = [store.spans[sid].bbox for line in lines for sid in line.span_ids]
    glyphs, bars, signatures = page_glyphs(native, size, text_boxes)
    dots = page_dots(native, size, text_boxes)
    parts = page_parts(native, size, text_boxes)
    clips = {o.id: o for o in native.objects if o.kind == "clip"}
    page_groups = drawing_groups([*glyphs, *bars, *dots, *parts], clips, text_boxes, size)
    paint_order = {o.id: index for index, o in enumerate(native.objects)}
    text_items = [
        (span.bbox, tuple(((span.color >> shift) & 255) / 255 for shift in (16, 8, 0)))
        for span in store.spans.values()
        if span.raw_text.strip()
    ]
    fills = [
        (index, o)
        for index, o in enumerate(native.objects)
        if o.kind == "drawing" and o.fill is not None and o.bbox is not None
    ]
    units_by_line = {lid: unit for unit in units for lid in unit.line_ids}
    regions_by_line = {lid: region.type for region in layout.regions for lid in region.line_ids}
    object_region = {oid: region.type for region in layout.regions for oid in region.object_ids}
    images = [o.bbox for o in native.objects if o.kind == "image" and o.bbox is not None]
    text_colours = {
        tuple(((span.color >> shift) & 255) / 255 for shift in (16, 8, 0))
        for span in store.spans.values()
        if span.raw_text.strip()
    }
    drafts, rejected = [], Counter()
    for cluster in vector_clusters(
        glyphs, bars, signatures, recurring, size, text_boxes, dots, clips, parts
    ):
        reason = typeset_like(cluster, images, text_colours, paint_order, fills, text_items)
        if reason is not None:
            rejected[reason] += 1
            continue
        box = _union(o.bbox for o in cluster)
        recurring_share = sum(signatures.get(o.id) in recurring for o in cluster) / len(cluster)
        bar_ids = {b.id for b in bars}
        dot_ids = {d.id for d in dots}
        part_ids = {p.id for p in parts}
        grouped = {o.id: page_groups[o.id] for o in cluster if o.id in page_groups}
        drafts.append(
            {
                "box": box,
                "objects": sorted(o.id for o in cluster),
                "ranges": [],
                "line_ids": [],
                "rules": ["recurring_vector_glyphs"]
                + (["rule_bar"] if any(o.id in bar_ids for o in cluster) else [])
                + (["drawing_group"] if grouped else []),
                "signals": {
                    "glyphs": sum(o.id in signatures for o in cluster),
                    "bars": sum(o.id in bar_ids for o in cluster),
                    "dots": sum(o.id in dot_ids for o in cluster),
                    "parts": sum(o.id in part_ids for o in cluster),
                    "drawing_groups": len(set(grouped.values())),
                    "recurring_share": round(recurring_share, 3),
                    "figure_region": any(object_region.get(o.id) == "figure" for o in cluster),
                },
                "groups": frozenset(grouped.values()),
                "inline": beside_text(box, text_boxes, size),
            }
        )
    _join_rows(drafts, text_boxes, size, pitch)
    geometry = native.span_geometry
    cells = char_boxes(native, store)

    def char_box(sid, offset):
        return range_box(store.spans[sid], offset, offset + 1, geometry.get(sid), cells.get(sid))

    # Text runs follow native text order, so lines of any rotation are read. Runs without
    # evidence of their own are kept as parts that may join a drawn expression.
    for line in lines:
        for run in line_runs(store, line, geometry, math_fonts, attachable=True):
            atoms = [
                (char_box(sid, offset), store.spans[sid].raw_text[offset], bool(run.rules))
                for sid, a, b in run.ranges
                for offset in range(a, b)
                if not store.spans[sid].raw_text[offset].isspace()
            ]
            drafts.append(
                {
                    "box": _union(box for box, _, _ in atoms),
                    "objects": [],
                    "ranges": run.ranges,
                    "line_ids": [line.id],
                    "rules": list(run.rules),
                    "signals": dict(run.signals, whole_line=run.whole_line),
                    "groups": frozenset(),
                    "atoms": atoms,
                    "part": not run.rules,
                }
            )
    by_id = {o.id: o for o in native.objects}
    for draft in drafts:
        if draft["objects"]:
            draft.update(atoms=[(by_id[o].bbox, None, True) for o in draft["objects"]])
            draft.setdefault("part", False)
    separators = [
        char_box(sid, offset)
        for line in lines
        for sid in line.span_ids
        for offset, character in enumerate(store.spans[sid].raw_text)
        if character in ",;:" and store.spans[sid].raw_text[offset + 1 : offset + 2].isspace()
    ]
    _join_mixed(drafts, size, separators)
    # Parts that joined no drawn expression are not equations.
    drafts[:] = [d for d in drafts if not (d["part"] and not d["objects"])]
    # Text runs still open at a line end continue on the unit's next line.
    _join_wrapped(drafts, store, lines, units)
    regions = []
    for draft in drafts:
        box = draft["box"]
        own_spans = frozenset(sid for sid, _, _ in draft["ranges"])
        if draft["ranges"]:
            line = next(item for item in lines if item.id == draft["line_ids"][0])
            kind = "display" if draft["signals"].get("whole_line") else "inline"
            if kind == "display":
                inline, _ = presentation(box, store, lines, size, own_spans)
                kind = "display" if inline == "display" else "inline"
        else:
            kind, line = presentation(box, store, lines, size)
        source = (
            "mixed"
            if draft["objects"] and draft["ranges"]
            else "vector"
            if draft["objects"]
            else "text"
        )
        support = _support(box, model_boxes)
        confidence = 0.55 + 0.1 * (support.heron + support.pp_doclayoutv3)
        if "operator_between_operands" in draft["rules"] or draft["signals"].get("bars"):
            confidence += 0.1
        flags = []
        if draft["signals"].get("figure_region"):
            flags.append("equation objects lie in a layout figure region; review the figure")
        if model_boxes and not (support.heron or support.pp_doclayoutv3):
            flags.append("no layout model finds a formula here")
        regions.append(
            EquationRegion(
                id=stable_id(
                    page.source_sha256,
                    "equation",
                    number,
                    *draft["objects"],
                    *(f"{s}:{a}:{b}" for s, a, b in draft["ranges"]),
                ),
                page=number,
                bbox=box,
                presentation=kind,
                source=source,
                object_ids=draft["objects"],
                span_refs=[SpanRef(span_id=s, start=a, end=b) for s, a, b in draft["ranges"]],
                line_ids=draft["line_ids"],
                signals=draft["signals"],
                rules=sorted(draft["rules"]),
                model_support=support,
                host=_host(line, box, units_by_line, lines, regions_by_line, kind == "display"),
                confidence=round(min(confidence, 0.95), 3),
                review_flags=flags,
            )
        )
    model_only = []
    for model, rows in model_boxes.items():
        for other, label in rows:
            if any(_overlap_share(other, r.bbox) >= MODEL_OVERLAP for r in regions):
                continue
            model_only.append((model, other, label))
    merged_only = []
    for model, box, label in model_only:
        for row in merged_only:
            if _overlap_share(row["box"], box) >= MODEL_OVERLAP:
                row["models"].add(model)
                row["labels"].add(label)
                break
        else:
            merged_only.append({"box": box, "models": {model}, "labels": {label}})
    only = [
        ModelOnlyRegion(
            page=number, bbox=row["box"], models=sorted(row["models"]), labels=sorted(row["labels"])
        )
        for row in merged_only
    ]
    diagnostics = [f"vector glyphs {len(glyphs)}, bars {len(bars)}, regions {len(regions)}"]
    diagnostics += [
        f"vector clusters not typeset-like ({reason}): {count}"
        for reason, count in sorted(rejected.items())
    ]
    return regions, only, diagnostics, signatures
