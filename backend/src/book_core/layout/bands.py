"""Band segmentation and per-band gutters for one scope.

Free text lines and visual blocks are rasterised into an occupancy mask. Gutter seeds are
empty strips (OpenCV opening) with content on both sides; each seed then extends along its
own strip until something crosses it. Callouts or figures crossing a gutter while text
continues on both sides are insets and do not split the band. Bands are maximal vertical
intervals with one gutter set; without gutters, wide visual blocks form their own bands.
Columns are counted per band and never assumed.

Bands of one scope never overlap: two proposed intervals that overlap by more than half a
font size are one band, keeping only the gutters no member crosses. A gutter separates
lanes only when members lie on both of its sides within the band, so lanes always have
positive width. A lane holding only short locator cells (page references) that sit on the
rows of a neighbouring text lane is part of that lane, not a column of its own.
"""

from dataclasses import dataclass, field
from statistics import median

import cv2
import numpy as np

from book_core.extraction.fingerprints import stable_id
from book_core.layout.evidence import line_text, short_reference
from book_core.layout.models import Band, Gutter, Lane
from book_core.model.common import BBox

SPANNING_SHARE = 0.6


@dataclass
class Element:
    id: str
    bbox: BBox
    kind: str  # "line" or a block kind
    line: object = None
    block: object = None

    @property
    def cy(self):
        return (self.bbox.y0 + self.bbox.y1) / 2

    @property
    def cx(self):
        return (self.bbox.x0 + self.bbox.x1) / 2


@dataclass
class Strip:
    x0: float
    x1: float
    y0: float
    y1: float
    insets: list[str] = field(default_factory=list)


def union(boxes):
    boxes = list(boxes)
    return BBox(
        x0=min(b.x0 for b in boxes),
        y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes),
        y1=max(b.y1 for b in boxes),
    )


class Grid:
    """Point/pixel conversion for one scope at a fixed scale."""

    def __init__(self, scope, scale):
        self.scope, self.scale = scope, scale
        self.width = max(1, int(np.ceil((scope.x1 - scope.x0) * scale)))
        self.height = max(1, int(np.ceil((scope.y1 - scope.y0) * scale)))

    def px(self, x):
        return int(np.clip(round((x - self.scope.x0) * self.scale), 0, self.width - 1))

    def py(self, y):
        return int(np.clip(round((y - self.scope.y0) * self.scale), 0, self.height - 1))

    def x(self, px):
        return self.scope.x0 + px / self.scale

    def y(self, py):
        return self.scope.y0 + py / self.scale

    def fill(self, mask, bbox, value=1):
        x0, y0, x1, y1 = self.px(bbox.x0), self.py(bbox.y0), self.px(bbox.x1), self.py(bbox.y1)
        mask[y0 : max(y0 + 1, y1 + 1), x0 : max(x0 + 1, x1 + 1)] = value


def find_strips(grid, occupied, unit, pitch):
    """Seed strips: empty, at least one unit wide, two line pitches tall, content both sides."""
    empty = (occupied == 0).astype(np.uint8)
    width = max(3, int(round(0.9 * unit * grid.scale)))
    height = max(3, int(round(2.0 * pitch * grid.scale)))
    candidates = cv2.morphologyEx(
        empty, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (width, height))
    )
    tolerance = max(1, int(round(0.6 * pitch * grid.scale)))
    support = cv2.dilate(occupied, np.ones((2 * tolerance + 1, 1), np.uint8))
    left = np.maximum.accumulate(support, axis=1)
    right = np.maximum.accumulate(support[:, ::-1], axis=1)[:, ::-1]
    seeds = (candidates & left & right).astype(np.uint8)
    # Keep only row runs of gutter-like width so wide open areas cannot fuse separate strips.
    widest = max(width + 1, int(0.25 * grid.width))
    for row in np.where(seeds.any(axis=1))[0]:
        values = seeds[row]
        changes = np.flatnonzero(np.diff(np.concatenate(([0], values, [0]))))
        for start, stop in zip(changes[0::2], changes[1::2], strict=True):
            if stop - start > widest:
                values[start:stop] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(seeds, connectivity=4)
    strips = []
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_HEIGHT] < height:
            continue
        x_lo = stats[label, cv2.CC_STAT_LEFT]
        x_hi = x_lo + stats[label, cv2.CC_STAT_WIDTH] - 1
        member = labels == label
        allowance = max(2, int(0.5 * pitch * grid.scale))
        # Core: columns whose longest vertical run is close to the best. Pockets beside short
        # lines join the component but are only a few rows deep, so they drop out.
        runs = {
            x: longest_run(np.flatnonzero(member[:, x]), allowance) for x in range(x_lo, x_hi + 1)
        }
        best_x = max(runs, key=lambda x: runs[x][0])
        limit = 0.9 * runs[best_x][0]
        core0 = core1 = best_x
        while core0 - 1 in runs and runs[core0 - 1][0] >= limit:
            core0 -= 1
        while core1 + 1 in runs and runs[core1 + 1][0] >= limit:
            core1 += 1
        core0, core1 = core0 + 1, core1 - 1
        if core1 - core0 + 1 < max(2, width // 2):
            continue
        rows = np.where(member.any(axis=1))[0]
        inside = np.array([row for row in rows if not occupied[row, core0 : core1 + 1].any()])
        length, top, bottom = longest_run(inside, allowance)
        if length < height:
            continue
        strips.append(Strip(core0, core1, top, bottom))
    return strips


def longest_run(rows, allowance):
    """(length, first, last) of the longest run of rows with gaps no larger than allowance."""
    best, start = (0, -1, -1), None
    for i, row in enumerate(rows):
        if start is None or row - rows[i - 1] > allowance:
            start = row
        if row - start + 1 > best[0]:
            best = (int(row - start + 1), int(start), int(row))
    return best


def extend(strip, text_mask, block_mask, pitch_px):
    """Grow a seed along its own strip until content crosses it or both sides go quiet."""
    x0, x1 = int(strip.x0), int(strip.x1)
    occupied = text_mask | block_mask
    # Any text inside the strip blocks it. A visual block a point wider than the text
    # beside it does not cross the gutter; it must reach the strip's central half.
    margin = max(1, (x1 - x0) // 4)
    blocked = text_mask[:, x0 : x1 + 1].any(axis=1) | block_mask[
        :, x0 + margin : x1 - margin + 1
    ].any(axis=1)
    sides = occupied[:, :x0].any(axis=1) | occupied[:, x1 + 1 :].any(axis=1)
    limit = int(round(1.5 * pitch_px))

    def walk(start, step):
        y, last, quiet = start, start, 0
        while 0 <= y + step < len(blocked) and not blocked[y + step]:
            y += step
            quiet = 0 if sides[y] else quiet + 1
            if quiet > limit:
                break
            if sides[y]:
                last = y
        return last

    strip.y0 = walk(int(strip.y0), -1)
    strip.y1 = walk(int(strip.y1), 1)
    return strip


def merge_overlapping(strips):
    merged = []
    for strip in sorted(strips, key=lambda s: (s.x0, s.y0)):
        for other in merged:
            if (
                min(strip.x1, other.x1) >= max(strip.x0, other.x0)
                and min(strip.y1, other.y1) >= max(strip.y0, other.y0) - 1
            ):
                other.x0, other.x1 = max(other.x0, strip.x0), min(other.x1, strip.x1)
                other.y0, other.y1 = min(other.y0, strip.y0), max(other.y1, strip.y1)
                break
        else:
            merged.append(strip)
    return merged


def bridge_insets(strips, grid, lines, blocks, pitch):
    """Join strips interrupted only by a callout/figure that has text beside it on both sides."""
    changed = True
    while changed:
        changed = False
        ordered = sorted(strips, key=lambda s: s.y0)
        for upper in ordered:
            for lower in ordered:
                if lower is upper or lower.y0 <= upper.y1:
                    continue
                if min(upper.x1, lower.x1) < max(upper.x0, lower.x0):
                    continue
                gx0, gx1 = grid.x(max(upper.x0, lower.x0)), grid.x(min(upper.x1, lower.x1) + 1)
                gy0, gy1 = grid.y(upper.y1), grid.y(lower.y0)
                crossing_lines = [
                    line
                    for line in lines
                    if line.bbox.x0 < gx1
                    and line.bbox.x1 > gx0
                    and line.bbox.y1 > gy0
                    and line.bbox.y0 < gy1
                ]
                crossing = [
                    block
                    for block in blocks
                    if block.kind in {"callout", "figure", "table"}
                    and block.bbox.x0 < gx1
                    and block.bbox.x1 > gx0
                    and block.bbox.y1 > gy0
                    and block.bbox.y0 < gy1
                ]
                if crossing_lines or not crossing:
                    continue
                span = union(block.bbox for block in crossing)
                if span.y0 > gy0 + pitch or span.y1 < gy1 - pitch:
                    continue
                beside = [
                    line
                    for line in lines
                    if span.y0 <= (line.bbox.y0 + line.bbox.y1) / 2 <= span.y1
                ]
                left = sum(line.bbox.x1 <= gx0 + 1 for line in beside)
                right = sum(line.bbox.x0 >= gx1 - 1 for line in beside)
                if left >= 2 and right >= 2:
                    upper.x0, upper.x1 = max(upper.x0, lower.x0), min(upper.x1, lower.x1)
                    upper.y1 = lower.y1
                    upper.insets = sorted({*upper.insets, *lower.insets, *(b.id for b in crossing)})
                    strips.remove(lower)
                    changed = True
                    break
            if changed:
                break
    return strips


def adjacent(index, strip):
    """Elements nearest to the strip on each side, row by row (index map holds id + 1)."""
    left, right = set(), set()
    x0, x1 = int(strip.x0), int(strip.x1)
    for row in range(int(strip.y0), int(strip.y1) + 1):
        before = index[row, :x0]
        found = np.flatnonzero(before)
        if found.size:
            left.add(int(before[found[-1]]) - 1)
        after = index[row, x1 + 1 :]
        found = np.flatnonzero(after)
        if found.size:
            right.add(int(after[found[0]]) - 1)
    return left, right


def ink_fraction(edges, grid, strip_box, rules):
    if edges is None:
        return 0.0
    x0, x1 = grid.px(strip_box.x0), grid.px(strip_box.x1)
    y0, y1 = grid.py(strip_box.y0), grid.py(strip_box.y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    window = edges[y0:y1, x0:x1].astype(bool).copy()
    for rule in rules:
        rx0 = grid.px(rule.bbox.x0 - 1.5) - x0
        rx1 = grid.px(rule.bbox.x1 + 1.5) - x0
        window[:, max(0, rx0) : max(0, rx1 + 1)] = False
    return float(window.mean()) if window.size else 0.0


def segment_scope(
    scope,
    lines,
    blocks,
    edges,
    scale,
    store_sizes,
    frames=(),
    body_ids=frozenset(),
    store=None,
    overlap_tolerance=None,
):
    """Return bands for one scope. `lines` are free horizontal lines owned by the scope."""
    elements = [Element(line.id, line.bbox, "line", line=line) for line in lines]
    elements += [
        Element(block.id, block.bbox, block.kind, block=block)
        for block in blocks
        if block.kind != "rule"
    ]
    if not elements:
        return [], {}, []
    diagnostics = []
    sizes = [line.font_size for line in lines if line.font_size > 0] or store_sizes or [10.0]
    unit = median(sizes)
    heights = [line.bbox.y1 - line.bbox.y0 for line in lines]
    pitch = median(heights) if heights else 1.2 * unit
    grid = Grid(scope.bbox, scale)
    text_mask = np.zeros((grid.height, grid.width), np.uint8)
    block_mask = np.zeros_like(text_mask)
    index = np.zeros((grid.height, grid.width), np.int32)
    # Blocks first, then lines on top: the index map holds element position + 1.
    for position, element in enumerate(elements):
        if element.kind != "line":
            grid.fill(block_mask, element.bbox)
            grid.fill(index, element.bbox, position + 1)
    for position, element in enumerate(elements):
        if element.kind == "line":
            grid.fill(text_mask, element.bbox)
            grid.fill(index, element.bbox, position + 1)
    vertical_rules = []
    for block in blocks:
        if block.kind != "rule":
            continue
        if block.features.get("orientation") == "horizontal":
            # A horizontal rule ends any gutter it crosses, like text would.
            grid.fill(text_mask, block.bbox)
        else:
            vertical_rules.append(block)
    occupied = text_mask | block_mask
    strips = find_strips(grid, occupied, unit, pitch)
    strips = [extend(strip, text_mask, block_mask, pitch * scale) for strip in strips]
    strips = merge_overlapping(strips)
    strips = bridge_insets(strips, grid, lines, blocks, pitch)
    insets = {block_id for strip in strips for block_id in strip.insets}
    gutters = []
    for strip in strips:
        box = BBox(
            x0=grid.x(strip.x0),
            y0=grid.y(strip.y0),
            x1=grid.x(strip.x1 + 1),
            y1=grid.y(strip.y1 + 1),
        )
        sides = adjacent(index, strip)
        counts = []
        for side in sides:
            members = [elements[i] for i in side if 0 <= i < len(elements)]
            usable = [e for e in members if e.id not in insets]
            # Tiny labels beside a picture do not make a text lane.
            text = [e for e in usable if e.kind == "line" and e.bbox.x1 - e.bbox.x0 >= 4 * unit]
            visual = [e for e in usable if e.kind != "line"]
            counts.append((len(text), len(visual), len(members)))
        (left_text, left_visual, left), (right_text, right_visual, right) = counts
        if not (
            (left_text >= 2 or left_visual >= 1)
            and (right_text >= 2 or right_visual >= 1)
            and left_text + right_text >= 2
        ):
            diagnostics.append(
                f"Empty strip at x={box.x0:.1f}-{box.x1:.1f} lacks a text lane on both sides"
            )
            continue
        ink = ink_fraction(edges, grid, box, vertical_rules)
        confidence = 0.9
        reasons = ["Empty strip with content on both sides"]
        if strip.insets:
            reasons.append("Bridged across an inset with text beside it on both sides")
            confidence -= 0.05
        rules = [
            rule.object_ids[0]
            for rule in vertical_rules
            if box.x0 - 2 <= (rule.bbox.x0 + rule.bbox.x1) / 2 <= box.x1 + 2
        ]
        if rules:
            reasons.append("Vertical rule inside the gutter")
        if ink > 0.02:
            confidence -= 0.25
            reasons.append("Rendered ink inside the gutter")
        if min(left, right) < 3:
            confidence -= 0.1
            reasons.append("Few items on one side")
        gutters.append(
            Gutter(
                x0=box.x0,
                x1=box.x1,
                y0=box.y0,
                y1=box.y1,
                inset_block_ids=strip.insets,
                rule_object_ids=rules,
                left_items=left,
                right_items=right,
                ink_fraction=min(1.0, ink),
                confidence=max(0.05, confidence),
                reasons=reasons,
            )
        )
    tolerance = overlap_tolerance if overlap_tolerance is not None else max(1.0, 0.5 * unit)
    texts = {line.id: line_text(line, store) for line in lines} if store is not None else {}
    bands, membership = build_bands(
        scope, elements, gutters, pitch, frames, body_ids, tolerance, texts, diagnostics
    )
    return bands, membership, diagnostics


def crosses(element, gutter, insets):
    """A member that bridges a gutter: a line past both of its edges, or a block over its
    central half. A short line sitting inside the gutter (a centred letter divider) does
    not join the lanes on either side."""
    if element.kind == "line":
        return element.bbox.x0 < gutter.x0 - 0.5 and element.bbox.x1 > gutter.x1 + 0.5
    if element.id in insets or element.kind == "banner":
        return False
    quarter = (gutter.x1 - gutter.x0) / 4
    return element.bbox.x0 < gutter.x1 - quarter and element.bbox.x1 > gutter.x0 + quarter


def merge_gutters(gutters):
    """Gutters overlapping in x describe one strip: keep their common part."""
    result = []
    for gutter in sorted(gutters, key=lambda g: g.x0):
        if result and min(result[-1].x1, gutter.x1) > max(result[-1].x0, gutter.x0):
            previous = result[-1]
            result[-1] = previous.model_copy(
                update={
                    "x0": max(previous.x0, gutter.x0),
                    "x1": min(previous.x1, gutter.x1),
                    "y0": min(previous.y0, gutter.y0),
                    "y1": max(previous.y1, gutter.y1),
                    "inset_block_ids": sorted({*previous.inset_block_ids, *gutter.inset_block_ids}),
                    "rule_object_ids": sorted({*previous.rule_object_ids, *gutter.rule_object_ids}),
                    "left_items": max(previous.left_items, gutter.left_items),
                    "right_items": max(previous.right_items, gutter.right_items),
                    "confidence": min(previous.confidence, gutter.confidence),
                }
            )
        else:
            result.append(gutter)
    return result


def resolve_overlaps(groups, tolerance, insets, diagnostics):
    """Merge band groups whose vertical extents overlap; keep gutters nobody crosses."""
    groups = [(list(members), list(gutters)) for members, gutters in groups if members]
    merged = True
    while merged:
        merged = False
        for i, (a_members, a_gutters) in enumerate(groups):
            a_box = union(e.bbox for e in a_members)
            for j in range(i + 1, len(groups)):
                b_members, b_gutters = groups[j]
                b_box = union(e.bbox for e in b_members)
                overlap = min(a_box.y1, b_box.y1) - max(a_box.y0, b_box.y0)
                if overlap <= tolerance:
                    continue
                members = a_members + b_members
                kept = [
                    g
                    for g in merge_gutters(a_gutters + b_gutters)
                    if not any(crosses(e, g, insets) for e in members)
                ]
                dropped = len(merge_gutters(a_gutters + b_gutters)) - len(kept)
                diagnostics.append(
                    f"Overlapping bands merged ({overlap:.1f}pt); {dropped} crossed gutter(s)"
                    " dropped"
                )
                groups[i] = (members, kept)
                del groups[j]
                merged = True
                break
            if merged:
                break
    return groups


def build_bands(
    scope, elements, gutters, pitch, frames, body_ids, tolerance=1.0, texts=None, diagnostics=None
):
    edges = sorted(
        {scope.bbox.y0, scope.bbox.y1, *(g.y0 for g in gutters), *(g.y1 for g in gutters)}
    )
    slabs = []
    for top, bottom in zip(edges, edges[1:], strict=False):
        middle = (top + bottom) / 2
        active = tuple(sorted(i for i, g in enumerate(gutters) if g.y0 <= middle < g.y1))
        if slabs and slabs[-1][2] == active:
            slabs[-1][1] = bottom
        else:
            slabs.append([top, bottom, active])
    insets = {block_id for g in gutters for block_id in g.inset_block_ids}
    content_x = [e.bbox.x0 for e in elements if e.kind != "banner"]
    content_x1 = [e.bbox.x1 for e in elements if e.kind != "banner"]
    content_width = (max(content_x1) - min(content_x)) if content_x else 1.0
    slab_members = [[] for _ in slabs]
    for e in elements:
        # Clamp so elements protruding beyond the scope still belong to exactly one slab.
        cy = min(max(e.cy, scope.bbox.y0), scope.bbox.y1)
        index = next(
            (i for i, (top, bottom, _) in enumerate(slabs) if top <= cy < bottom),
            len(slabs) - 1,
        )
        slab_members[index].append(e)
    groups = []
    for (_, _, active), members in zip(slabs, slab_members, strict=True):
        if not members:
            continue
        if active:
            groups.append((members, [gutters[i] for i in active]))
            continue
        spanning = [
            e
            for e in members
            if e.kind in {"figure", "callout", "table", "banner"}
            and e.id not in insets
            and (e.bbox.x1 - e.bbox.x0) >= SPANNING_SHARE * content_width
        ]
        # Wide blocks own every element centred within their vertical extent.
        assigned = {}
        for block in spanning:
            for e in members:
                if e.id in assigned or not block.bbox.y0 <= e.cy <= block.bbox.y1:
                    continue
                if (
                    block.kind == "banner"
                    and e.kind == "line"
                    and not (block.bbox.y0 <= e.bbox.y0 and e.bbox.y1 <= block.bbox.y1 + 1)
                ):
                    # Only text printed on the banner belongs to it.
                    continue
                assigned[e.id] = block.id
        clusters = {block.id: [] for block in spanning}
        rest = []
        for e in members:
            if e.id in assigned:
                clusters[assigned[e.id]].append(e)
            else:
                rest.append(e)
        # Absorb elements that overlap or touch a block band vertically (a caption's last line).
        grew = True
        while grew and spanning:
            grew = False
            for e in list(rest):
                for block in spanning:
                    cluster = clusters[block.id]
                    if not cluster or block.kind == "banner":
                        # Banners keep only text printed on them; they do not grow.
                        continue
                    box = union(member.bbox for member in cluster)
                    if e.bbox.y0 <= box.y1 + 0.25 * pitch and e.bbox.y1 >= box.y0 - 0.25 * pitch:
                        cluster.append(e)
                        rest.remove(e)
                        grew = True
                        break
        # Remaining elements split into runs separated by the spanning blocks.
        cuts = sorted((b.bbox.y0, b.bbox.y1) for b in spanning)
        runs = {}
        for e in rest:
            key = sum(e.cy >= cut[1] for cut in cuts)
            runs.setdefault(key, []).append(e)
        for block in spanning:
            cluster = clusters[block.id]
            if block.kind == "banner" and not any(e.kind == "line" for e in cluster):
                # A text-free banner is decoration, not a band; its peers still need one.
                peers = [e for e in cluster if e.id != block.id]
                if peers:
                    groups.append((peers, []))
                continue
            groups.append((cluster, []))
        for run in runs.values():
            if any(e.kind != "banner" for e in run):
                groups.append(([e for e in run if e.kind != "banner"], []))
    diagnostics = diagnostics if diagnostics is not None else []
    groups = resolve_overlaps(groups, tolerance, insets, diagnostics)
    bands = []
    membership = {}
    for members, band_gutters in groups:
        if not members:
            # A spanning block already claimed by an overlapping wider block.
            continue
        bbox = union(e.bbox for e in members)
        band, lanes_of = make_band(
            scope,
            members,
            band_gutters,
            bbox,
            insets,
            pitch,
            frames,
            body_ids,
            texts or {},
            diagnostics,
        )
        bands.append(band)
        membership.update({eid: (band, lane) for eid, lane in lanes_of.items()})
    return bands, membership


def separating(gutters, members, insets):
    """Gutters with non-inset members wholly on both of their sides within the band."""
    kept = []
    for gutter in gutters:
        usable = [e for e in members if e.id not in insets]
        left = any(e.bbox.x1 <= gutter.x0 + 0.5 and e.bbox.x0 < gutter.x0 for e in usable)
        right = any(e.bbox.x0 >= gutter.x1 - 0.5 and e.bbox.x1 > gutter.x1 for e in usable)
        if left and right:
            kept.append(gutter)
    return kept


def locator_gutter(gutters, members, insets, texts):
    """The gutter to drop so a lane of locator cells joins the text lane whose rows it ends."""
    if not texts or not gutters:
        return None
    gutters = sorted(gutters, key=lambda g: g.x0)
    bounds = [-np.inf, *(v for g in gutters for v in (g.x0, g.x1)), np.inf]
    lanes = list(zip(bounds[0::2], bounds[1::2], strict=True))
    lane_lines = [[] for _ in lanes]
    for e in members:
        if e.kind != "line" or e.id in insets or e.id not in texts:
            continue
        index = next((i for i, (x0, x1) in enumerate(lanes) if e.cx < x1 + 0.5), len(lanes) - 1)
        lane_lines[index].append(e)
    for index, items in enumerate(lane_lines):
        if len(items) < 2 or not all(short_reference(texts[e.id]) for e in items):
            continue
        sides = []
        for neighbour, gutter in ((index - 1, index - 1), (index + 1, index)):
            if not 0 <= neighbour < len(lanes):
                continue
            others = [e for e in lane_lines[neighbour] if not short_reference(texts[e.id])]
            rows = sum(
                any(
                    min(e.bbox.y1, o.bbox.y1)
                    > max(e.bbox.y0, o.bbox.y0) - 0.5 * (e.bbox.y1 - e.bbox.y0)
                    for o in others
                )
                for e in items
            )
            if others and rows >= 0.75 * len(items):
                sides.append(gutters[gutter])
        if sides:
            return min(sides, key=lambda g: g.x1 - g.x0)
    return None


def make_band(
    scope, members, gutters, bbox, insets, pitch, frames, body_ids, texts=None, diagnostics=None
):
    gutters = separating(merge_gutters(gutters), members, insets)
    locator = locator_gutter(gutters, members, insets, texts)
    while locator is not None:
        if diagnostics is not None:
            diagnostics.append(
                f"Locator cells beside running text at x={locator.x1:.0f} join that lane"
            )
        gutters = [g for g in gutters if g is not locator]
        locator = locator_gutter(gutters, members, insets, texts)
    bounds = [bbox.x0, *(v for g in gutters for v in (g.x0, g.x1)), bbox.x1]
    lane_edges = list(zip(bounds[0::2], bounds[1::2], strict=True))
    inset_ids = sorted({e.id for e in members if e.id in insets})
    lane_members = [[] for _ in lane_edges]
    lanes_of = {e.id: None for e in members if e.id in inset_ids}
    for e in members:
        if e.id in inset_ids:
            continue
        index = next(
            (i for i, (x0, x1) in enumerate(lane_edges) if e.cx < x1 + 0.5),
            len(lane_edges) - 1,
        )
        lane_members[index].append(e)
    lanes = [
        classify_lane(i, edges, items, lane_members, body_ids, pitch)
        for i, (edges, items) in enumerate(zip(lane_edges, lane_members, strict=True))
    ]
    lanes = refine_lanes(lanes, lane_members)
    framed = framed_lanes(bbox, lanes, frames) if len(lanes) > 1 else []
    if len(framed) >= 2:
        lanes = [
            lane.model_copy(
                update={
                    "kind": "card",
                    "confidence": 0.75,
                    "reasons": [
                        *lane.reasons,
                        "Lane enclosed by its own frame beside framed peers",
                    ],
                }
            )
            if lane.index in framed and lane.kind in {"column", "figure", "unknown", "caption"}
            else lane
            for lane in lanes
        ]
    column_count = sum(lane.kind == "column" for lane in lanes)
    confidences = [g.confidence for g in gutters] + [lane.confidence for lane in lanes]
    confidence = min(confidences) if confidences else 0.85
    reasons = (
        [f"{len(gutters)} gutter(s) separate {len(lanes)} lanes"]
        if gutters
        else ["No gutter: single lane"]
    )
    if inset_ids:
        reasons.append("Inset crosses a gutter without splitting the band")
    review = confidence < 0.7 or any(lane.kind == "unknown" for lane in lanes)
    for lane, items in zip(lanes, lane_members, strict=True):
        lanes_of.update({e.id: lane for e in items})
    band = Band(
        id=stable_id(scope.id, "band", round(bbox.y0, 2), round(bbox.y1, 2), round(bbox.x0, 2)),
        scope_id=scope.id,
        bbox=bbox,
        gutters=gutters,
        lanes=lanes,
        column_count=column_count,
        inset_block_ids=inset_ids,
        confidence=confidence,
        reasons=reasons,
        review_required=review,
    )
    return band, lanes_of


def area(bbox):
    return max(0.0, bbox.x1 - bbox.x0) * max(0.0, bbox.y1 - bbox.y0)


def classify_lane(index, edges, items, all_members, body_ids, pitch):
    x0, x1 = edges
    lines = [e for e in items if e.kind == "line"]
    blocks = [e for e in items if e.kind != "line"]
    block_ids = [e.id for e in blocks]
    if not items:
        return Lane(
            index=index,
            x0=x0,
            x1=x1,
            kind="unknown",
            line_count=0,
            confidence=0.4,
            reasons=["Empty lane between gutters"],
        )
    line_area = sum(area(e.bbox) for e in lines)
    by_kind = {}
    for e in blocks:
        by_kind[e.kind] = by_kind.get(e.kind, 0.0) + area(e.bbox)
    total = line_area + sum(by_kind.values())
    share = {kind: value / max(1e-6, total) for kind, value in by_kind.items()}
    body_lines = sum(e.id in body_ids for e in lines)
    figures = [e for e in blocks if e.kind == "figure"]

    def near_figure(line):
        return any(
            min(line.bbox.x1, f.bbox.x1) > max(line.bbox.x0, f.bbox.x0)
            and max(f.bbox.y0 - line.bbox.y1, line.bbox.y0 - f.bbox.y1) <= 2 * pitch
            for f in figures
        )

    running = [e for e in lines if e.bbox.x1 - e.bbox.x0 >= 0.6 * (x1 - x0) and not near_figure(e)]
    if (body_lines >= 2 or len(running) >= 3) and blocks:
        # Running text continues in this lane around its figure or table.
        return Lane(
            index=index,
            x0=x0,
            x1=x1,
            kind="column",
            line_count=len(lines),
            block_ids=block_ids,
            confidence=0.75,
            reasons=["Body-style text flows around blocks in the lane"],
        )
    if share.get("figure", 0) >= 0.5:
        return Lane(
            index=index,
            x0=x0,
            x1=x1,
            kind="figure",
            line_count=len(lines),
            block_ids=block_ids,
            confidence=0.8,
            reasons=["Figure blocks dominate the lane; not a text column"],
        )
    if share.get("callout", 0) >= 0.6:
        return Lane(
            index=index,
            x0=x0,
            x1=x1,
            kind="callout",
            line_count=len(lines),
            block_ids=block_ids,
            confidence=0.8,
            reasons=["Callout dominates the lane"],
        )
    if share.get("table", 0) >= 0.6:
        return Lane(
            index=index,
            x0=x0,
            x1=x1,
            kind="table",
            line_count=len(lines),
            block_ids=block_ids,
            confidence=0.75,
            reasons=["Table dominates the lane"],
        )
    if share.get("banner", 0) >= 0.6 and not lines:
        return Lane(
            index=index,
            x0=x0,
            x1=x1,
            kind="unknown",
            line_count=0,
            block_ids=block_ids,
            confidence=0.5,
            reasons=["Only banner artwork in the lane"],
        )
    if not lines:
        return Lane(
            index=index,
            x0=x0,
            x1=x1,
            kind="unknown",
            line_count=0,
            block_ids=block_ids,
            confidence=0.5,
            reasons=["No text and no dominant block"],
        )
    # Lines beside a figure in a neighbouring lane, with no blocks of their own: a caption lane.
    neighbours = [
        e
        for j in (index - 1, index + 1)
        if 0 <= j < len(all_members)
        for e in all_members[j]
        if e.kind == "figure"
    ]
    if neighbours and not blocks and len(lines) <= 12:
        lane_box = union(e.bbox for e in lines)
        figure_box = union(e.bbox for e in neighbours)
        gap = max(figure_box.x0 - lane_box.x1, lane_box.x0 - figure_box.x1)
        overlap = min(lane_box.y1, figure_box.y1) - max(lane_box.y0, figure_box.y0)
        if gap <= 4 * pitch and overlap >= 0.5 * (lane_box.y1 - lane_box.y0):
            return Lane(
                index=index,
                x0=x0,
                x1=x1,
                kind="caption",
                line_count=len(lines),
                confidence=0.7,
                reasons=["Short text block beside a figure in the next lane"],
            )
    return Lane(
        index=index,
        x0=x0,
        x1=x1,
        kind="column",
        line_count=len(lines),
        block_ids=block_ids,
        confidence=0.85 if len(lines) >= 3 else 0.7,
        reasons=["Free text lines form a lane"],
    )


def refine_lanes(lanes, lane_members):
    """Callout lanes beside columns are sidebars; narrow few-line lanes are margins."""
    columns = [lane for lane in lanes if lane.kind == "column"]
    widths = [lane.x1 - lane.x0 for lane in columns]
    result = []
    for lane in lanes:
        if lane.kind == "callout" and columns:
            lane = lane.model_copy(
                update={"kind": "sidebar", "reasons": [*lane.reasons, "Beside a text column"]}
            )
        elif (
            lane.kind == "column"
            and len(columns) > 1
            and lane.line_count <= 3
            and (lane.x1 - lane.x0) < 0.35 * max(widths)
        ):
            lane = lane.model_copy(
                update={"kind": "margin", "reasons": [*lane.reasons, "Narrow few-line lane"]}
            )
        result.append(lane)
    return result


def framed_lanes(bbox, lanes, frames):
    """Indices of lanes each enclosed by their own drawn frame (frames sit in the gutters)."""
    framed = []
    height = bbox.y1 - bbox.y0
    for lane in lanes:
        width = lane.x1 - lane.x0
        for frame in frames:
            centre = (frame.x0 + frame.x1) / 2
            if (
                lane.x0 <= centre <= lane.x1
                and 0.6 * width <= frame.x1 - frame.x0 <= 1.3 * width
                and frame.y1 - frame.y0 >= 0.6 * height
                and frame.y0 <= bbox.y0 + 0.4 * height
            ):
                framed.append(lane.index)
                break
    return framed
