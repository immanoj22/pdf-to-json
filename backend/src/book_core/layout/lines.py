"""Visual lines from span-store evidence. Spans keep native order; text is never copied.

Lines are grouped along each span's own writing direction, so rotated, vertical and
right-to-left text are handled by the same geometry. Direction labels come from
Unicode bidirectional classes, never from an assumed script.
"""

import math
import unicodedata
from dataclasses import dataclass, field

import regex
from shapely import STRtree, box

from book_core.extraction.fingerprints import stable_id
from book_core.layout.evidence import locator_cell
from book_core.layout.models import VisualLine
from book_core.model.common import BBox

# Gaps are measured in multiples of the larger font size along the writing direction.
SPLIT_GAP = 2.5
TAB_SPLIT_GAP = 0.5
MERGE_GAP = 1.25
SCRIPT_MIN = 0.45  # a run smaller than this share of its neighbour is no script of it
# A gap of at least STYLE_SPLIT_GAP (larger) font sizes where the size also changes by
# STYLE_RATIO, or of MARKER_SPLIT_GAP before a list marker, separates two lines that share a
# baseline: a folio, label or heading set beside a column's line across a narrow gutter, or
# the first item of the next column. Text changing style mid-line does so across a word
# space (about a third of the size); a script sits close.
STYLE_SPLIT_GAP = 0.75
STYLE_RATIO = 1.2
MARKER_SPLIT_GAP = 1.0
DIRECTION_TOLERANCE = 0.999
# A whole fragment that is one enumerator ("1." "(2)" "a)" "iv."), in any script.
ENUMERATOR = regex.compile(r"^[(\[]?(?:\p{N}{1,3}|\p{L}|[ivxlcdm]{1,6}|[IVXLCDM]{1,6})[.)\]:]?$")
# An enumerator with its punctuation ("1." "2)" "(iv)") is a list marker, never a page locator.
PUNCTUATED = regex.compile(r"^[(\[]?(?:\p{N}{1,3}|\p{L}|[ivxlcdm]{1,6}|[IVXLCDM]{1,6})[.)\]:]$")
# A gutter is a white channel between columns, not a size of gap: a narrow gutter can be
# narrower than a justified word space. A gap between two same-baseline fragments is a gutter
# when, on GUTTER_ROWS or more contiguous rows (its own included), nothing covers the gap's
# middle, text lies on both sides, and the column beside the channel shares the edge its lines
# start from within GUTTER_EDGE font sizes: the starts right of the channel for left-to-right
# text, the ends left of it for right-to-left text (either when the direction is unknown). A
# row whose text covers the middle (a heading across the columns) ends the channel. Words after
# justified spaces never share a start; a common first word can share an end, so the other
# edge is not evidence.
# A list marker is never the left side of a gutter: bullets and enumerators in a hanging indent
# line up like a column but belong with the text that follows them. A gutter is white: small
# ink in the gap on the pair's row (a symbol drawn as vector art or an image, at most
# GUTTER_INK_HEIGHT font sizes tall) means the gap holds content. Taller ink (a column rule, a
# background panel) does not. A piece of locators only (a page number, "(p. 45)", a numeric
# cell) stays with its row: a TOC, index or glossary locator column is read with its entry.
# A list marker opening the next column's item joins neither side across the gutter: the
# earlier text keeps to its column when a gutter separates it from the text the marker opens.
# The test runs between native lines on one baseline and inside a native line at span
# boundaries (an extractor may join two columns' lines across a narrow gutter). Gaps under
# GUTTER_MIN_GAP font sizes (a word space is about a quarter to a third) are never a gutter.
GUTTER_ROWS = 4
GUTTER_EDGE = 0.1
GUTTER_MIN_GAP = 0.5
# A paragraph's first line starts this far in from its column edge (the column still starts
# where the other lines do): rows of indented first lines are rows of the column, not of text
# beyond its edge. Without them a column of indented paragraphs shows too few aligned rows.
FIRST_LINE_INDENT = 2.0
GUTTER_INK_HEIGHT = 3.0
# A column whose first fragment on the pair's row is a list marker, or opens with one (a
# numbered entry: right-aligned enumerators of different widths start at different x), starts
# its other lines at the hanging indent: their starts within HANGING_INDENT font sizes past
# the fragment's start share the column edge too.
HANGING_INDENT = 3.0


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
    lead: str = ""  # the first non-blank character, in native order
    text: str = ""  # the fragment's characters in native order (evidence, never copied out)
    symbolic: bool | None = None  # every glyph from a font its descriptor marks Symbolic
    wordy: bool = False  # holds a letter or decimal digit (not only marks or symbols)

    @property
    def blank(self):
        return not self.baselines

    @property
    def size(self):
        return weighted_median(self.sizes) if self.sizes else 0.0

    @property
    def baseline(self):
        return weighted_median(self.baselines)

    def extend(self, other):
        """Append a later piece of the same native line."""
        self.span_ids.extend(other.span_ids)
        self.along = [min(self.along[0], other.along[0]), max(self.along[1], other.along[1])]
        self.normal = [min(self.normal[0], other.normal[0]), max(self.normal[1], other.normal[1])]
        self.baselines.extend(other.baselines)
        self.sizes.extend(other.sizes)
        self.ends_with_tab = other.ends_with_tab
        self.lead = self.lead or other.lead
        self.text += other.text
        self.wordy = self.wordy or other.wordy
        self.symbolic = bool(self.symbolic and other.symbolic)

    @property
    def marker_only(self):
        """The whole fragment is a list marker: bullet symbols or one enumerator."""
        text = "".join(self.text.split())
        if self.symbolic and 0 < len(text) <= 2:
            return True  # a dingbat glyph, whatever character its font decodes to
        return bool(text) and (all(map(_marker, text)) or bool(ENUMERATOR.match(text)))

    @property
    def opens_item(self):
        """The fragment is a list marker or starts with one ("10.\tSwain…", "• Item")."""
        if self.marker_only:
            return True
        words = self.text.split()
        return bool(words) and (_marker(words[0][0]) or bool(PUNCTUATED.match(words[0])))

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


def native_fragments(native):
    """Fragments of native lines: split at large gaps and tab stops, and at column gutters."""
    pieces = native_pieces(native)
    gutters = Gutters([piece for line in pieces for piece, _ in line], native.objects)
    fragments = []
    for line in pieces:
        current = None
        for index, (piece, hard) in enumerate(line):
            after = line[index + 1] if index + 1 < len(line) else None
            opens = (  # a marker opening an item a gutter separates from the text before it
                current is not None and piece.marker_only and after is not None
                and not after[1] and gutters.separates(current, after[0])
            )  # fmt: skip
            if current is None or hard or opens or gutters.separates(current, piece):
                current = piece
                fragments.append(current)
            else:
                current.extend(piece)
    return fragments


def native_pieces(native):
    """Per native line, its pieces in native order with whether the cut before each is hard
    (writing direction, mode, visibility, a large gap or a tab stop). Other cuts are at span
    boundaries with a gap of GUTTER_MIN_GAP font sizes or more, and rejoin unless a gutter."""
    store = native.page.store
    geometry = native.span_geometry
    visible = visibility(native)
    lines = []
    for line in store.lines:
        fragments = []
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
            hard = (
                current is None
                or current.direction != direction
                or current.writing_mode != mode
                or current.visible != visible.get(sid, True)
                or (gap is not None and gap > limit)
            )
            if hard or gap >= GUTTER_MIN_GAP * max(size, previous_size or size):
                current = Fragment(
                    span_ids=[*pending],
                    source_line_ids=[line.id],
                    direction=direction,
                    writing_mode=mode,
                    visible=visible.get(sid, True),
                )
                pending = []
                fragments.append((current, hard))
            current.span_ids.append(sid)
            current.lead = current.lead or span.raw_text.strip()[:1]
            current.symbolic = bool(span.symbolic) and current.symbolic is not False
            current.text += span.raw_text
            current.wordy = current.wordy or any(map(_wordy, span.raw_text))
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
                fragments.append((target, True))
            target.span_ids.extend(pending)
        lines.append(fragments)
    return lines


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
    # A script (superscript, subscript, footnote mark) is set at about half to three quarters
    # of its base; a run a fraction of the size (a running head under a display number) is
    # another line that happens to overlap.
    script_size_shift = SCRIPT_MIN <= smaller / larger <= 0.8
    if not (same_baseline or script_size_shift):
        return False
    gap = max(b.along[0] - a.along[1], a.along[0] - b.along[1])
    if gap > 0 and (
        (a.ends_with_tab and b.along[0] >= a.along[1])
        or (b.ends_with_tab and a.along[0] >= b.along[1])
    ):
        # A tab stop separates fields (running footer and folio); never rejoin across it.
        return False
    if (
        gap >= STYLE_SPLIT_GAP * larger
        and larger >= STYLE_RATIO * smaller
        and a.wordy
        and b.wordy  # a bullet or symbol set larger than its text stays with it
    ):
        return False
    # A list marker after a gap of a font size or more opens a line of its own: the first item of
    # another column whose first line shares the baseline (never a word inside a line).
    later = b if b.along[0] >= a.along[1] else a
    if gap >= MARKER_SPLIT_GAP * larger and (
        _marker(later.lead) or (later.symbolic and later.marker_only)
    ):
        return False
    return gap <= MERGE_GAP * larger


class Gutters:
    """Answers whether the gap between two same-baseline fragments is a column gutter."""

    def __init__(self, fragments, objects=()):
        self.objects, self.ink = objects, None
        self.by_direction = {}
        for fragment in fragments:
            if not fragment.blank:
                self.by_direction.setdefault(fragment.direction, []).append(fragment)
        for members in self.by_direction.values():
            members.sort(key=lambda f: f.baseline)
        self.position = {
            id(f): i for members in self.by_direction.values() for i, f in enumerate(members)
        }

    def separates(self, a, b):
        left, right = (a, b) if a.along[1] <= b.along[0] else (b, a)
        low, high = left.along[1], right.along[0]
        size = max(left.size, right.size, 0.01)
        if high - low < GUTTER_MIN_GAP * size or left.marker_only:
            return False
        if any(locator_cell(f.text.strip()) and not PUNCTUATED.match("".join(f.text.split()))
               for f in (left, right)):  # fmt: skip
            return False
        middle, tolerance = (low + high) / 2, GUTTER_EDGE * size
        reach = high + (HANGING_INDENT if right.opens_item else FIRST_LINE_INDENT) * size
        members = self.by_direction[left.direction]
        ends, starts, sides = [], [], [0, 0]
        start = self.position[id(left)]
        for step in (-1, 1):  # outwards from the pair until text covers the channel
            index = start
            while 0 <= index < len(members):
                fragment = members[index]
                index += step
                if fragment.along[0] < middle < fragment.along[1]:
                    break
                row = round(fragment.baseline / (0.35 * size))
                if fragment.along[1] <= middle:
                    sides[0] += 1
                    if low - tolerance <= fragment.along[1]:
                        ends.append((fragment.along[1], row))
                else:
                    sides[1] += 1
                    if fragment.along[0] <= reach:
                        starts.append((fragment.along[0], row))
        if min(sides) < GUTTER_ROWS:
            return False
        reading = text_direction([left.text, right.text], left.writing_mode)
        aligned = (reading != "rtl" and _edge_rows(starts, tolerance) >= GUTTER_ROWS) or (
            reading != "ltr" and _edge_rows(ends, tolerance) >= GUTTER_ROWS
        )
        return aligned and not self.inked(left, right, low, high, size)

    def inked(self, left, right, low, high, size):
        """Small non-text ink inside the gap on the pair's row."""
        if self.ink is None:
            drawn = [o.bbox for o in self.objects if not o.is_text and o.bbox is not None]
            self.ink = (drawn, STRtree([box(b.x0, b.y0, b.x1, b.y1) for b in drawn]))
        drawn, tree = self.ink
        if not drawn:
            return False
        direction = left.direction
        nx, ny = -direction[1], direction[0]
        bottom = min(left.normal[0], right.normal[0])
        top = max(left.normal[1], right.normal[1])
        corners = [
            (a * direction[0] + n * nx, a * direction[1] + n * ny)
            for a in (low, high)
            for n in (bottom, top)
        ]
        xs, ys = [x for x, _ in corners], [y for _, y in corners]
        for index in tree.query(box(min(xs), min(ys), max(xs), max(ys))):
            along, normal = project(drawn[int(index)], direction)
            inside = min(along[1], high) - max(along[0], low) > 0
            if inside and normal[1] - normal[0] <= GUTTER_INK_HEIGHT * size:
                return True
        return False


def _edge_rows(edges, tolerance):
    """The most distinct rows whose edges agree within the tolerance."""
    best = 0
    for edge, _ in edges:
        best = max(best, len({row for value, row in edges if abs(value - edge) <= tolerance}))
    return best


def _wordy(character):
    category = unicodedata.category(character)
    return category[0] == "L" or category == "Nd"


def _marker(character):
    """A list bullet: a symbol, a private-use or unmapped symbol-font glyph, a dot standing in
    for a bullet, or a dash."""
    if not character:
        return False
    return unicodedata.category(character) in {"So", "Co", "Cc"} or character in "•‣⁃▪▫●◦∙·■□–—*"


def build_lines(native):
    """Group native line fragments sharing a baseline; native lines may also split at gaps."""
    store = native.page.store
    content = native.page.geometry.content_bbox
    fragments = native_fragments(native)
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
    gutters = Gutters(fragments, native.objects)
    # ``compatible`` bounds a merge gap by the larger of the pair's sizes, so candidates are
    # searched at the page's largest size: a small marker beside larger text is still found.
    largest = max((f.size for f in fragments if not f.blank), default=0.01)

    def follower(index):
        """The fragment a marker introduces: the nearest compatible one after it."""
        marker = fragments[index]
        reach = MERGE_GAP * max(largest, 0.01)
        after = [int(k) for k in tree.query(shapes[index], predicate="dwithin", distance=reach)
                 if int(k) != index and fragments[int(k)].along[0] >= marker.along[1]
                 and compatible(marker, fragments[int(k)])]  # fmt: skip
        return min(after, key=lambda k: fragments[k].along[0], default=None)

    def bridges(i, j):
        """A marker after text, opening an item that a gutter separates from that text."""
        a, b = fragments[i], fragments[j]
        earlier, later = (i, j) if a.along[1] <= b.along[0] else (j, i)
        if not fragments[later].marker_only:
            return False
        item = follower(later)
        return item is not None and gutters.separates(fragments[earlier], fragments[item])

    for i, fragment in enumerate(fragments):
        if fragment.blank:
            continue
        reach = MERGE_GAP * max(largest, 0.01)
        for j in tree.query(shapes[i], predicate="dwithin", distance=reach):
            j = int(j)
            if j <= i or not compatible(fragment, fragments[j]):
                continue
            if gutters.separates(fragment, fragments[j]) or bridges(i, j):
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
