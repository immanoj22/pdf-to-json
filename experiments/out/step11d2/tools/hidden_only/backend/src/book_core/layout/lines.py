"""Visual lines from span-store evidence. Spans keep native order; text is never copied.

Lines are grouped along each span's own writing direction, so rotated, vertical and
right-to-left text are handled by the same geometry. Direction labels come from
Unicode bidirectional classes, never from an assumed script.
"""

import math
import unicodedata
from dataclasses import dataclass, field

from shapely import STRtree, box

from book_core.extraction.fingerprints import stable_id
from book_core.layout.models import VisualLine
from book_core.model.common import BBox

# Gaps are measured in multiples of the larger font size along the writing direction.
SPLIT_GAP = 2.5
TAB_SPLIT_GAP = 0.5
MERGE_GAP = 1.25
DIRECTION_TOLERANCE = 0.999


@dataclass
class Fragment:
    span_ids: list[str]
    source_line_ids: list[str]
    direction: tuple[float, float]
    writing_mode: str
    visible: bool
    along: list[float] = field(default_factory=lambda: [math.inf, -math.inf])
    normal: list[float] = field(default_factory=lambda: [math.inf, -math.inf])
    baselines: list[tuple[float, int]] = field(default_factory=list)
    sizes: list[tuple[float, int]] = field(default_factory=list)
    ends_with_tab: bool = False

    @property
    def blank(self):
        return not self.baselines

    @property
    def size(self):
        return weighted_median(self.sizes) if self.sizes else 0.0

    @property
    def baseline(self):
        return weighted_median(self.baselines)

    @property
    def height(self):
        return max(0.0, self.normal[1] - self.normal[0])


def weighted_median(values):
    ordered = sorted(values)
    total = sum(weight for _, weight in ordered)
    running = 0
    for value, weight in ordered:
        running += weight
        if running * 2 >= total:
            return value
    return ordered[-1][0]


def unit(vector):
    x, y = vector
    length = math.hypot(x, y)
    return (1.0, 0.0) if length == 0 else (x / length, y / length)


def project(bbox, direction):
    dx, dy = direction
    nx, ny = -dy, dx
    corners = [(bbox.x0, bbox.y0), (bbox.x1, bbox.y0), (bbox.x0, bbox.y1), (bbox.x1, bbox.y1)]
    along = [x * dx + y * dy for x, y in corners]
    normal = [x * nx + y * ny for x, y in corners]
    return (min(along), max(along)), (min(normal), max(normal))


def text_direction(texts, writing_mode):
    """Strong bidirectional classes decide; unknown stays None."""
    if writing_mode == "vertical":
        return "ttb"
    left = right = 0
    for text in texts:
        for character in text:
            category = unicodedata.bidirectional(character)
            if category == "L":
                left += 1
            elif category in {"R", "AL"}:
                right += 1
    if right > left:
        return "rtl"
    if left:
        return "ltr"
    return None


def visibility(native):
    visible = {}
    for obj in native.objects:
        if obj.kind != "text":
            continue
        visible[obj.id] = not obj.render_info or any(
            info.render_type != 3 and (info.opacity is None or info.opacity > 0)
            for info in obj.render_info
        )
    return visible


def native_fragments(native, invisible_span_ids=()):
    store = native.page.store
    geometry = native.span_geometry
    visible = visibility(native)
    visible.update({sid: False for sid in invisible_span_ids})
    fragments = []
    for line in store.lines:
        current = None
        pending = []
        previous_end = None
        previous_size = None
        for sid in line.span_ids:
            span = store.spans[sid]
            evidence = geometry.get(sid)
            direction = unit(evidence.direction) if evidence else (1.0, 0.0)
            mode = evidence.writing_mode if evidence else "horizontal"
            along, normal = project(span.bbox, direction)
            blank = not span.raw_text.strip()
            if blank:
                (current.span_ids if current else pending).append(sid)
                continue
            size = max(span.size, 0.01)
            gap = None if previous_end is None else along[0] - previous_end
            limit = SPLIT_GAP * max(size, previous_size or size)
            if current is not None and current.ends_with_tab:
                limit = min(limit, TAB_SPLIT_GAP * max(size, previous_size or size))
            if (
                current is None
                or current.direction != direction
                or current.writing_mode != mode
                or current.visible != visible.get(sid, True)
                or (gap is not None and gap > limit)
            ):
                current = Fragment(
                    span_ids=[*pending],
                    source_line_ids=[line.id],
                    direction=direction,
                    writing_mode=mode,
                    visible=visible.get(sid, True),
                )
                pending = []
                fragments.append(current)
            current.span_ids.append(sid)
            current.along = [min(current.along[0], along[0]), max(current.along[1], along[1])]
            current.normal = [min(current.normal[0], normal[0]), max(current.normal[1], normal[1])]
            weight = max(1, len(span.raw_text.strip()))
            if evidence is not None:
                x, y = evidence.origin
                nx, ny = -direction[1], direction[0]
                current.baselines.append((x * nx + y * ny, weight))
            else:
                current.baselines.append((normal[1], weight))
            current.sizes.append((span.size, weight))
            current.ends_with_tab = span.raw_text.endswith("\t")
            previous_end = along[1]
            previous_size = size
        if pending:
            # A native line containing only whitespace remains its own blank evidence line.
            target = current
            if target is None:
                span = store.spans[pending[0]]
                evidence = geometry.get(pending[0])
                direction = unit(evidence.direction) if evidence else (1.0, 0.0)
                along, normal = project(span.bbox, direction)
                target = Fragment(
                    span_ids=[],
                    source_line_ids=[line.id],
                    direction=direction,
                    writing_mode=evidence.writing_mode if evidence else "horizontal",
                    visible=visible.get(pending[0], True),
                    along=list(along),
                    normal=list(normal),
                )
                fragments.append(target)
            target.span_ids.extend(pending)
    return fragments


def compatible(a, b):
    if a.blank or b.blank or a.writing_mode != b.writing_mode or a.visible != b.visible:
        return False
    if a.direction[0] * b.direction[0] + a.direction[1] * b.direction[1] < DIRECTION_TOLERANCE:
        return False
    larger = max(a.size, b.size)
    smaller = max(min(a.size, b.size), 0.01)
    overlap = min(a.normal[1], b.normal[1]) - max(a.normal[0], b.normal[0])
    if overlap < 0.5 * max(0.01, min(a.height, b.height)):
        return False
    same_baseline = abs(a.baseline - b.baseline) <= 0.35 * larger
    script_size_shift = smaller / larger <= 0.8
    if not (same_baseline or script_size_shift):
        return False
    gap = max(b.along[0] - a.along[1], a.along[0] - b.along[1])
    if gap > 0 and (
        (a.ends_with_tab and b.along[0] >= a.along[1])
        or (b.ends_with_tab and a.along[0] >= b.along[1])
    ):
        # A tab stop separates fields (running footer and folio); never rejoin across it.
        return False
    return gap <= MERGE_GAP * larger


def build_lines(native, invisible_span_ids=()):
    """Group native line fragments sharing a baseline; native lines may also split at gaps."""
    store = native.page.store
    content = native.page.geometry.content_bbox
    fragments = native_fragments(native, invisible_span_ids)
    order = {sid: i for i, sid in enumerate(sid for line in store.lines for sid in line.span_ids)}
    line_order = {line.id: i for i, line in enumerate(store.lines)}
    parent = list(range(len(fragments)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def bounds(fragment):
        boxes = [store.spans[sid].bbox for sid in fragment.span_ids]
        return box(
            min(b.x0 for b in boxes),
            min(b.y0 for b in boxes),
            max(b.x1 for b in boxes),
            max(b.y1 for b in boxes),
        )

    shapes = [bounds(fragment) for fragment in fragments]
    tree = STRtree(shapes)
    for i, fragment in enumerate(fragments):
        if fragment.blank:
            continue
        reach = MERGE_GAP * max(fragment.size, 0.01)
        for j in tree.query(shapes[i], predicate="dwithin", distance=reach):
            j = int(j)
            if j <= i or not compatible(fragment, fragments[j]):
                continue
            a, b = find(i), find(j)
            if a != b:
                parent[max(a, b)] = min(a, b)
    groups = {}
    for i in range(len(fragments)):
        groups.setdefault(find(i), []).append(fragments[i])
    lines = []
    for members in groups.values():
        span_ids = sorted({sid for member in members for sid in member.span_ids}, key=order.get)
        sources = sorted(
            {source for member in members for source in member.source_line_ids},
            key=line_order.get,
        )
        spans = [store.spans[sid] for sid in span_ids]
        bbox = BBox(
            x0=min(s.bbox.x0 for s in spans),
            y0=min(s.bbox.y0 for s in spans),
            x1=max(s.bbox.x1 for s in spans),
            y1=max(s.bbox.y1 for s in spans),
        )
        textual = [member for member in members if not member.blank]
        dominant = max(textual or members, key=lambda m: sum(w for _, w in m.baselines))
        direction = dominant.direction
        nx, ny = -direction[1], direction[0]
        along = [
            min(m.along[0] for m in members),
            max(m.along[1] for m in members),
        ]
        baseline = dominant.baseline if textual else dominant.normal[1]
        start = (
            along[0] * direction[0] + baseline * nx,
            along[0] * direction[1] + baseline * ny,
        )
        end = (
            along[1] * direction[0] + baseline * nx,
            along[1] * direction[1] + baseline * ny,
        )
        sizes = [pair for member in textual for pair in member.sizes]
        rotation = round(math.degrees(math.atan2(-direction[1], direction[0])) % 360, 3)
        reasons = ["Spans grouped by shared baseline and writing direction"]
        if len(sources) > 1:
            reasons.append("Joins native lines on one baseline")
        members_set = set(span_ids)
        if any(
            not set(store.lines[line_order[source]].span_ids) <= members_set for source in sources
        ):
            reasons.append("Native line split at a large gap or tab stop")
        lines.append(
            VisualLine(
                id=stable_id("visual_line", *sorted(span_ids)),
                span_ids=span_ids,
                source_line_ids=sources,
                bbox=bbox,
                baseline_start=start,
                baseline_end=end,
                direction=direction,
                rotation=0.0 if rotation >= 359.999 else rotation,
                writing_mode=dominant.writing_mode,
                text_direction=text_direction([s.raw_text for s in spans], dominant.writing_mode),
                font_size=weighted_median(sizes) if sizes else 0.0,
                visible=dominant.visible,
                inside_content=content.contains_center(bbox),
                blank=not textual,
                reasons=reasons,
            )
        )
    # Deterministic listing by first native span; this is evidence order, not reading order.
    return sorted(lines, key=lambda line: order[line.span_ids[0]])
