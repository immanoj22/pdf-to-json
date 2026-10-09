"""Reading order for one page, built over the Step 4 layout (scopes, bands, lanes, regions, lines).

Rules (no page numbers, coordinates, fonts or book-specific rules; layout-model evidence is
never consulted):

- A scope reads its bands along its stacking axis; rotated scopes are read in their own frame.
- A band reads its lanes in writing-direction order (rtl bands right to left, vertical writing
  right to left); a lane reads its lines along the block axis by baseline. Lines overlapping on
  the block axis form a row, read in the inline direction.
- A callout that forms a band by itself is an in-flow section: its scope is read in place.
  Other callouts, sidebars, figures, tables, cards, notes and credits are floats: separate
  streams, each anchored after the main-flow line where it interrupts. Inside a text lane that
  is its centre on the block axis; a gutter-bridging inset uses the first lane it overlaps in
  writing order; a float lane is read in lane order; a band-level float at its band's end.
- Card lanes are cards: one float per card, in lane order, each read top to bottom.
- Header/footer/page-number candidates go to a furniture stream (kept, not removed); lines
  outside the TrimBox or blank go to an artifact stream; invisible text to an invisible stream.
- Continuation evidence (punctuation, case, hyphenation, optional book vocabulary) types the
  transitions and resolves one ambiguity: whether columns continue across a band that holds
  only floats. Every decision carries confidence and reasons; low confidence is flagged.
"""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field

from book_core.extraction.fingerprints import stable_id
from book_core.model.common import Provenance
from book_core.reading_order.continuation import CONTINUES, continuation
from book_core.reading_order.frames import Frame
from book_core.reading_order.models import (
    PAGE_START,
    REVIEW_BELOW,
    Anchor,
    OrderDecision,
    OrderEdge,
    PageReadingOrder,
    Stream,
)

READING_ORDER_VERSION = "reading-order-1"
ROLE = {
    "title_candidate": "main",
    "heading_candidate": "main",
    "main_text": "main",
    "unknown": "main",
    "caption_candidate": "caption",
    "sidebar": "sidebar",
    "figure": "figure",
    "table_candidate": "table",
    "footnote_candidate": "note",
    "credit_candidate": "credit",
    "header_footer_candidate": "furniture",
    "page_number_candidate": "furniture",
    "artifact_candidate": "artifact",
    "callout": "container",
}
ROW_BASELINE = 0.35
CREDIT_REACH = 4.0  # font sizes from a figure edge (the Step 4 I5 credit rule)
CAPTION_GAP = 2.0  # caption font sizes between a caption and its figure/table
STRADDLE = 0.25
FLOW_MARGIN = 0.4
SUB_LANE_LINES = 5
SUB_LANE_WIDTH = 6.0  # font sizes
SUB_LANE_OVERLAP = 0.5  # vertical overlap of adjacent sub-lanes, of the shorter
SUB_LANE_CROSSING = 0.05  # share of lines that may cross a gutter
PARALLEL_BLOCKS = 3
PARALLEL_SHARE = 0.75  # of the larger block count of two adjacent lanes
BLOCK_GAP = 1.4  # baseline pitches
INSET_REACH = 3.0  # font sizes between an inset and the lane it interrupts


def region_node(region_id):
    return f"region:{region_id}"


def stream_node(stream_id):
    return f"stream:{stream_id}"


@dataclass
class Unit:
    """One item of a scope's reading sequence: a line or a float."""

    line_id: str | None = None
    place: tuple | None = None  # (scope, band, lane) of a line
    role: str = "main"
    float: "Float | None" = None


@dataclass
class Float:
    kind: str
    seed: str
    scope_id: str
    mode: str
    confidence: float
    reasons: list[str]
    units: list[Unit] = field(default_factory=list)
    region_ids: list[str] = field(default_factory=list)


@dataclass
class BandResult:
    band: object
    lanes: list  # [(lane, units)] in reading order
    tail: list  # band-level floats read after the lanes

    def units(self):
        return [u for _, units in self.lanes for u in units] + self.tail

    def main_lanes(self):
        return [(lane, units) for lane, units in self.lanes if _main_lines(units)]


def _main_lines(units):
    return [u.line_id for u in units if u.float is None and u.role == "main"]


def _overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


class PageOrderBuilder:
    def __init__(self, layout, store, vocabulary: Mapping[str, int] | None = None):
        self.layout = layout
        self.store = store
        self.vocabulary = vocabulary
        self.lines = {line.id: line for line in layout.lines}
        self.regions = {region.id: region for region in layout.regions}
        self.region_of = {lid: r for r in layout.regions for lid in r.line_ids}
        self.scopes = {scope.id: scope for scope in layout.scopes}
        self.blocks = {block.id: block for block in layout.blocks}
        self.bands_of = defaultdict(list)
        for band in layout.bands:
            self.bands_of[band.scope_id].append(band)
        self.in_band = defaultdict(list)
        self.loose = defaultdict(list)
        for region in layout.regions:
            if region.band_id is not None:
                self.in_band[region.band_id].append(region)
            else:
                self.loose[region.scope_id].append(region)
        self.callout_scope = self._callout_scopes()
        self.decisions = []
        self.edges = []
        self.placed = {}
        self.page_direction = self._direction([line.id for line in layout.lines])
        self.captions = defaultdict(list)  # target region -> attached caption regions
        self.credits = defaultdict(list)  # figure region -> attached credit regions
        self.attached = set()
        self.card_lanes = {
            (band.id, lane.index)
            for band in layout.bands
            for lane in band.lanes
            if lane.kind == "card"
        }
        self._link_captions()
        self._link_credits()

    # ------------------------------------------------------------------ helpers
    def text(self, line_id):
        return "".join(self.store.spans[s].raw_text for s in self.lines[line_id].span_ids)

    def decide(self, kind, subjects, choice, confidence, reasons, alternatives=(), evidence=None):
        confidence = round(max(0.0, min(1.0, confidence)), 3)
        self.decisions.append(
            OrderDecision(
                kind=kind,
                subject_ids=list(subjects),
                choice=choice,
                alternatives=list(alternatives),
                confidence=confidence,
                reasons=list(reasons),
                evidence=dict(evidence or {}),
                review_required=confidence < REVIEW_BELOW,
            )
        )

    def _callout_scopes(self):
        """Callout region -> the scope it holds (same block box, child of the region's scope)."""
        found = {}
        for scope in self.scopes.values():
            if scope.kind != "callout":
                continue
            block = self.blocks.get(scope.block_id)
            for region in self.regions.values():
                if (
                    region.type == "callout"
                    and region.scope_id == scope.parent_id
                    and block is not None
                    and region.bbox == block.bbox
                    and region.id not in found
                ):
                    found[region.id] = scope.id
                    break
        return found

    def _direction(self, line_ids):
        weights = defaultdict(float)
        for lid in line_ids:
            line = self.lines[lid]
            if line.blank or line.text_direction is None:
                continue
            weights[line.text_direction] += max(1, len(self.text(lid).strip()))
        if not weights:
            return None
        return max(weights, key=weights.get)

    def frame(self, scope, band_regions=None):
        lines = [lid for r in (band_regions or []) for lid in r.line_ids]
        direction = self._direction(lines) if lines else None
        scope_lines = [
            lid for r in self.regions.values() if r.scope_id == scope.id for lid in r.line_ids
        ]
        scope_direction = self._direction(scope_lines)
        vertical = scope_direction == "ttb"
        chosen = direction or scope_direction or self.page_direction
        return Frame(rotation=scope.rotation or 0.0, vertical=vertical, rtl=chosen == "rtl"), (
            direction is not None,
            chosen,
        )

    def role(self, region, lane=None):
        role = ROLE.get(region.type, "main")
        if role == "main" and region.type == "unknown" and region.line_ids:
            if not all(self.lines[lid].visible for lid in region.line_ids):
                return "invisible"
        if role == "caption":
            return "attached" if region.id in self.attached else "main"
        if role == "credit" and region.id in self.attached:
            return "attached"
        return role

    # ------------------------------------------------------------- attachments
    def _font(self, region):
        sizes = sorted(self.lines[lid].font_size for lid in region.line_ids)
        return sizes[len(sizes) // 2] if sizes else 10.0

    def _link_captions(self):
        targets = [r for r in self.regions.values() if r.type in {"figure", "table_candidate"}]
        lane_kind = {
            (band.id, lane.index): lane.kind for band in self.layout.bands for lane in band.lanes
        }
        for caption in self.regions.values():
            if caption.type != "caption_candidate" or not caption.line_ids:
                continue
            if (caption.band_id, caption.lane_index) in self.card_lanes:
                continue
            font = self._font(caption)
            best = None
            for target in targets:
                if target.scope_id != caption.scope_id:
                    continue
                a, b = caption.bbox, target.bbox
                width = min(a.x1 - a.x0, b.x1 - b.x0)
                x_share = _overlap(a.x0, a.x1, b.x0, b.x1) / width if width > 0 else 0
                gap = max(b.y0 - a.y1, a.y0 - b.y1, 0.0)
                if x_share >= 0.5 and gap <= CAPTION_GAP * font:
                    candidate = (gap, 0.8, "caption adjacent above/below with shared extent")
                elif (
                    lane_kind.get((caption.band_id, caption.lane_index)) == "caption"
                    and caption.band_id == target.band_id
                ):
                    side = max(b.x0 - a.x1, a.x0 - b.x1, 0.0)
                    candidate = (side, 0.7, "caption lane beside the figure in the same band")
                else:
                    continue
                if best is None or candidate[0] < best[0]:
                    best = (*candidate, target)
            if best is None:
                self.decide(
                    "caption_link",
                    [caption.id],
                    "not_linked",
                    0.5,
                    ["caption candidate with no adjacent figure/table in its scope; read in place"],
                    ["caption_of"],
                )
                continue
            gap, confidence, reason, target = best
            self.captions[target.id].append(caption)
            self.attached.add(caption.id)
            self.decide("caption_link", [caption.id, target.id], "caption_of", confidence, [reason])
            for lid in caption.line_ids:
                self.edges.append(
                    OrderEdge(
                        source=lid,
                        target=region_node(target.id),
                        kind="caption_of",
                        confidence=confidence,
                        reasons=[reason],
                    )
                )

    def _link_credits(self):
        figures = [r for r in self.regions.values() if r.type == "figure"]
        for credit in self.regions.values():
            if credit.type != "credit_candidate" or not credit.line_ids:
                continue
            reach = CREDIT_REACH * self._font(credit)
            best = None
            for figure in figures:
                a, b = credit.bbox, figure.bbox
                dx = max(b.x0 - a.x1, a.x0 - b.x1, 0.0)
                dy = max(b.y0 - a.y1, a.y0 - b.y1, 0.0)
                distance = max(dx, dy)
                if distance <= reach and (best is None or distance < best[0]):
                    best = (distance, figure)
            if best is None:
                continue
            figure = best[1]
            self.credits[figure.id].append(credit)
            self.attached.add(credit.id)
            reason = f"credit within {CREDIT_REACH:g} font sizes of the figure edge"
            self.decide("credit_link", [credit.id, figure.id], "belongs_to_figure", 0.75, [reason])
            for lid in credit.line_ids:
                self.edges.append(
                    OrderEdge(
                        source=lid,
                        target=region_node(figure.id),
                        kind="belongs_to_figure",
                        confidence=0.75,
                        reasons=[reason],
                    )
                )

    # ---------------------------------------------------------------- content
    def figure_units(self, region, frame, place):
        """Captions above, embedded labels (native order), captions below/beside, credits."""
        units = []
        captions = sorted(self.captions.get(region.id, []), key=lambda c: frame.center_key(c.bbox))
        centre = frame.center_key(region.bbox)
        above = [c for c in captions if frame.center_key(c.bbox) < centre]
        below = [c for c in captions if c not in above]
        kind = "belongs_to_figure" if region.type == "figure" else "belongs_to_table"
        for caption in above:
            units += [Unit(lid, place, "float") for lid in self._rows(caption.line_ids, frame)]
        body = (
            region.line_ids
            if region.type == "figure"
            else self._table_order(region.line_ids, frame)
        )
        for lid in body:
            units.append(Unit(lid, place, "float"))
            reason = (
                "embedded figure text keeps native order"
                if region.type == "figure"
                else ("table lines in row-major cell order (table structure deferred)")
            )
            self.edges.append(
                OrderEdge(
                    source=lid,
                    target=region_node(region.id),
                    kind=kind,
                    confidence=0.8 if region.type == "figure" else 0.6,
                    reasons=[reason],
                )
            )
        for caption in below:
            units += [Unit(lid, place, "float") for lid in self._rows(caption.line_ids, frame)]
        for credit in self.credits.get(region.id, []):
            units += [Unit(lid, place, "float") for lid in credit.line_ids]
        return units

    def _table_order(self, line_ids, frame):
        """Cells (vertically stacked close lines sharing extent) read row-major."""
        lines = sorted(line_ids, key=lambda lid: frame.line_key(self.lines[lid]))
        cells = []
        for lid in lines:
            box = frame.box(self.lines[lid].bbox)
            size = max(self.lines[lid].font_size, 1.0)
            for cell in cells:
                last = frame.box(self.lines[cell[-1]].bbox)
                width = min(box.x1 - box.x0, last.x1 - last.x0)
                share = _overlap(box.x0, box.x1, last.x0, last.x1) / width if width > 0 else 0
                if share >= 0.5 and 0 <= box.y0 - last.y1 <= 0.6 * size:
                    cell.append(lid)
                    break
            else:
                cells.append([lid])
        boxes = [[frame.box(self.lines[lid].bbox) for lid in cell] for cell in cells]
        tops = [min(b.y0 for b in bs) for bs in boxes]
        bottoms = [max(b.y1 for b in bs) for bs in boxes]
        order = sorted(range(len(cells)), key=lambda i: tops[i])
        rows = []
        for i in order:
            for row in rows:
                j = row[0]
                height = min(bottoms[i] - tops[i], bottoms[j] - tops[j])
                if (
                    height > 0
                    and _overlap(tops[i], bottoms[i], tops[j], bottoms[j]) >= 0.5 * height
                ):
                    row.append(i)
                    break
            else:
                rows.append([i])
        result = []
        for row in rows:
            for i in sorted(row, key=lambda k: frame.inline_key(_union(boxes[k]))):
                result.extend(cells[i])
        return result

    def _rows(self, line_ids, frame):
        """Lines along the block axis; lines overlapping on it form a row read inline."""
        ordered = sorted(line_ids, key=lambda lid: frame.line_key(self.lines[lid]))
        result, row = [], []
        for lid in ordered:
            if row and self._same_row(row[0], lid, frame):
                row.append(lid)
                continue
            result.extend(self._row_order(row, frame))
            row = [lid]
        result.extend(self._row_order(row, frame))
        return result

    def _same_row(self, first, other, frame):
        """Lines sharing a baseline (within a fraction of the smaller font size) form a row.

        Baselines, not boxes: a tall quote mark or accent inflates a box but not its baseline.
        """
        a, b = self.lines[first], self.lines[other]
        size = min(a.font_size, b.font_size) or 1.0
        return abs(frame.line_key(a) - frame.line_key(b)) <= ROW_BASELINE * size

    def _row_order(self, row, frame):
        if len(row) > 1:
            self.decide(
                "row",
                row,
                "inline_order",
                0.7,
                ["lines share a baseline; read in the inline direction"],
            )
        return sorted(row, key=lambda lid: frame.inline_key(self.lines[lid].bbox))

    def float_for(self, region, frame, place, mode, confidence, reasons, kind=None):
        role = kind or self.role(region)
        if role in {"figure", "table"}:
            units = self.figure_units(region, frame, place)
        else:
            units = [Unit(lid, place, "float") for lid in self._rows(region.line_ids, frame)]
        return Float(
            kind=role,
            seed=region.id,
            scope_id=region.scope_id,
            mode=mode,
            confidence=confidence,
            reasons=list(reasons),
            units=units,
            region_ids=[region.id]
            + [c.id for c in self.captions.get(region.id, [])]
            + [c.id for c in self.credits.get(region.id, [])],
        )

    def callout_float(self, region, frame, place, lane, mode, confidence, reasons):
        kind = "sidebar" if lane is not None and lane.kind in {"sidebar", "margin"} else "callout"
        scope_id = self.callout_scope.get(region.id)
        units = self.traverse(self.scopes[scope_id], in_float=True) if scope_id else []
        return Float(
            kind=kind,
            seed=region.id,
            scope_id=region.scope_id,
            mode=mode,
            confidence=confidence,
            reasons=list(reasons),
            units=units,
            region_ids=[region.id],
        )

    # -------------------------------------------------------------- traversal
    def traverse(self, scope, in_float=False):
        """Units of one scope in reading order (bands along the stacking axis)."""
        frame, _ = self.frame(scope)
        items = []
        for band in self.bands_of[scope.id]:
            items.append((frame.band_key(band.bbox), "band", band))
        for region in self.loose[scope.id]:
            if self.role(region) in {"artifact", "invisible"} or region.id in self.attached:
                continue
            items.append((frame.band_key(region.bbox), "loose", region))
        for child in self.scopes.values():
            if child.kind == "rotated" and child.parent_id == scope.id:
                items.append((frame.band_key(child.bbox), "scope", child))
        items.sort(key=lambda item: item[0])
        sequence = []  # BandResult or list of units
        for _, kind, item in items:
            if kind == "band":
                sequence.append(self.traverse_band(item, scope, in_float))
            elif kind == "scope":
                sequence.append(self.traverse(item, in_float))
            else:
                sequence.append(self.loose_units(item, scope, frame, in_float))
        if not in_float:
            sequence = self.inset_runs(sequence, frame)
            sequence = self.column_flow(sequence)
        units = []
        for part in sequence:
            units.extend(part.units() if isinstance(part, BandResult) else part)
        return units

    def loose_units(self, region, scope, frame, in_float):
        place = (scope.id, None, None)
        role = self.role(region)
        if in_float:
            if role == "container":
                target = self.callout_scope.get(region.id)
                return self.traverse(self.scopes[target], True) if target else []
            if role in {"figure", "table"}:
                return self.figure_units(region, frame, place)
            return [Unit(lid, place, "float") for lid in self._rows(region.line_ids, frame)]
        if role == "container":
            target = self.callout_scope.get(region.id)
            return self.traverse(self.scopes[target]) if target else []
        if role in {"main", "furniture"}:
            return [Unit(lid, place, role) for lid in self._rows(region.line_ids, frame)]
        reasons = ["region outside any band; read at its position in the scope"]
        return [Unit(float=self.float_for(region, frame, place, "scope", 0.6, reasons))]

    def traverse_band(self, band, scope, in_float):
        regions = self.in_band[band.id]
        frame, (evidence, chosen) = self.frame(scope, regions)
        lanes = sorted(band.lanes, key=frame.lane_key)
        if len(lanes) > 1 and not evidence:
            self.decide(
                "direction",
                [band.id],
                chosen or "ltr",
                0.55,
                ["no direction evidence in the band; scope/page direction used"],
                ["rtl" if chosen != "rtl" else "ltr"],
            )
        by_lane = defaultdict(list)
        unlaned = []
        for region in regions:
            if region.lane_index is None:
                unlaned.append(region)
            else:
                by_lane[region.lane_index].append(region)
        sections = (
            not in_float
            and all(lane.kind == "callout" for lane in lanes)
            and all(r.type == "callout" for r in regions if r.lane_index is not None)
        )
        inserts = defaultdict(list)  # lane index -> extra floats keyed by centre
        tail = []
        for region in unlaned:
            role = self.role(region)
            place = (band.scope_id, band.id, None)
            if role in {"artifact", "invisible", "attached"}:
                continue
            if role == "container":
                target, mode = self._inset_lane(region, lanes, by_lane, frame)
                reasons = ["inset bridging lanes; anchored where it interrupts the first lane"]
                if target is None:
                    reasons = ["callout without a lane; read at the end of its band"]
                    if in_float:
                        tail += self.loose_units(region, self.scopes[band.scope_id], frame, True)
                    else:
                        unit = self.callout_float(region, frame, place, None, "band", 0.6, reasons)
                        tail.append(Unit(float=unit))
                    continue
                inserts[target.index].append((region, mode, reasons))
                continue
            if role in {"main", "furniture", "caption"} or (in_float and role != "container"):
                target = self._best_lane(region, lanes, frame)
                if target is not None:
                    self.decide(
                        "lane_assignment",
                        [region.id],
                        f"lane {target.index}",
                        0.6,
                        ["region has no lane; assigned by horizontal overlap"],
                    )
                    by_lane[target.index].append(region)
                    continue
                if role != "caption":
                    self.decide(
                        "lane_assignment",
                        [region.id],
                        "end_of_band",
                        0.45,
                        ["region overlaps no lane; read at the end of its band"],
                    )
                    unit_role = "float" if in_float else role
                    tail += [
                        Unit(lid, place, unit_role) for lid in self._rows(region.line_ids, frame)
                    ]
                    continue
            if in_float:
                tail += self.loose_units(region, self.scopes[band.scope_id], frame, True)
                continue
            reasons = ["band-level region without a lane; read at the end of its band"]
            tail.append(Unit(float=self.float_for(region, frame, place, "band", 0.7, reasons)))
        result = []
        for lane in lanes:
            lane_regions = by_lane.get(lane.index, [])
            place = (band.scope_id, band.id, lane.index)
            if sections:
                units = []
                for region in sorted(lane_regions, key=lambda r: frame.band_key(r.bbox)):
                    target = self.callout_scope.get(region.id)
                    if target:
                        units += self.traverse(self.scopes[target])
                result.append((lane, units))
                continue
            if (band.id, lane.index) in self.card_lanes and not in_float:
                content = self.lane_units(lane, lane_regions, band, frame, True, [], place)
                card = Float(
                    kind="card",
                    seed=stable_id(band.id, "card", lane.index),
                    scope_id=band.scope_id,
                    mode="band",
                    confidence=0.8,
                    reasons=["card lane: one card, read top to bottom, cards in lane order"],
                    units=content,
                    region_ids=[r.id for r in lane_regions],
                )
                result.append((lane, [Unit(float=card)]))
                continue
            main_ids = [lid for r in lane_regions if self.role(r) == "main" for lid in r.line_ids]
            clusters = [] if in_float else self._sub_lanes(main_ids, frame)
            if len(clusters) > 1:
                result += self._split_lane(
                    lane, lane_regions, band, frame, inserts.get(lane.index, []), clusters
                )
                continue
            units = self.lane_units(
                lane, lane_regions, band, frame, in_float, inserts.get(lane.index, []), place
            )
            result.append((lane, units))
        if not sections and not in_float:
            result = self.parallel_lanes(band, result, frame)
        return BandResult(band, result, tail)

    # ------------------------------------------------- lanes Step 4 left merged or parallel
    def _sub_lanes(self, line_ids, frame):
        """Columns inside one lane, split at whitespace gutters.

        Step 4 can leave several text columns in one lane (for example an index page whose
        gutters it missed). Lines are clustered by their inline extent; a split is kept only if
        the strip is at least one font size wide and crossed by at most SUB_LANE_CROSSING of the
        lines (Step 4 can merge lines across a narrow gutter); every cluster has at least
        SUB_LANE_LINES lines and spans SUB_LANE_WIDTH font sizes; adjacent sub-lanes overlap
        vertically by SUB_LANE_OVERLAP of the shorter one. Lines join the cluster where
        they start; crossing lines are flagged. Clusters are read in writing order.
        """
        if len(line_ids) < 2 * SUB_LANE_LINES or frame.vertical:
            return [line_ids]
        boxes = {lid: frame.box(self.lines[lid].bbox) for lid in line_ids}
        sizes = sorted(self.lines[lid].font_size for lid in line_ids)
        size = sizes[len(sizes) // 2] or 1.0
        left = int(min(b.x0 for b in boxes.values()))
        right = int(max(b.x1 for b in boxes.values())) + 1
        coverage = [0] * (right - left + 1)
        for box in boxes.values():
            for x in range(int(box.x0) - left, int(box.x1) - left + 1):
                coverage[x] += 1
        limit = max(1, int(SUB_LANE_CROSSING * len(line_ids)))
        gutters, run = [], None
        for x, count in enumerate(coverage):
            if count <= limit and 0 < x < len(coverage) - 1:
                run = (run[0], x) if run else (x, x)
                continue
            if run and run[1] - run[0] + 1 >= size:
                gutters.append((run[0] + run[1]) / 2 + left)
            run = None
        while gutters:
            edges = [left, *gutters, right]
            clusters = [[] for _ in gutters] + [[]]
            for lid in line_ids:
                clusters[sum(boxes[lid].x0 >= g for g in gutters)].append(lid)
            invalid = next(
                (
                    i
                    for i, cluster in enumerate(clusters)
                    if len(cluster) < SUB_LANE_LINES
                    or edges[i + 1] - edges[i] < SUB_LANE_WIDTH * size
                ),
                None,
            )
            if invalid is None:
                break
            # A narrow strip (e.g. a hanging indent) is not a gutter: merge with a neighbour.
            gutters.pop(invalid - 1 if invalid > 0 else 0)
        if not gutters:
            return [line_ids]
        # Columns stand side by side; staggered blocks (a collage) are not columns.
        spans = [
            (
                min(frame.block_interval(self.lines[lid].bbox)[0] for lid in cluster),
                max(frame.block_interval(self.lines[lid].bbox)[1] for lid in cluster),
            )
            for cluster in clusters
        ]
        for (a0, a1), (b0, b1) in zip(spans, spans[1:], strict=False):
            if _overlap(a0, a1, b0, b1) < SUB_LANE_OVERLAP * min(a1 - a0, b1 - b0):
                return [line_ids]
        crossing = [
            lid for lid in line_ids if any(boxes[lid].x0 < g < boxes[lid].x1 for g in gutters)
        ]
        if frame.rtl:
            clusters.reverse()
        self.decide(
            "lane_assignment",
            [clusters[0][0]],
            f"{len(clusters)} sub-lanes",
            0.65,
            ["text columns inside one Step 4 lane, split at gutters few lines cross"],
            ["one lane"],
        )
        for lid in crossing:
            self.decide(
                "scope_boundary",
                [lid],
                "assigned_by_start",
                0.4,
                ["line crosses a sub-lane gutter; may merge text of two columns"],
            )
        return clusters

    def parallel_lanes(self, band, lanes, frame):
        """Row-synchronised lanes (e.g. a bilingual glossary) are read block row by block row.

        Blocks are runs of a lane's main lines split at vertical gaps. If every text lane has at
        least PARALLEL_BLOCKS blocks and, for adjacent text lanes, at least PARALLEL_SHARE of the
        larger lane's block starts align (within half a font size), the band is read by block
        start, lanes in writing order within a row. Otherwise lanes are read one after another.
        """
        texts = [(lane, units) for lane, units in lanes if _main_lines(units)]
        if len(texts) < 2:
            return lanes
        blocks = [self._blocks(units, frame) for _, units in texts]
        if any(len(b) < PARALLEL_BLOCKS for b in blocks):
            return lanes
        sizes = sorted(
            self.lines[u.line_id].font_size for _, units in texts for u in units if u.line_id
        )
        tolerance = 0.5 * (sizes[len(sizes) // 2] or 1.0)
        for a, b in zip(blocks, blocks[1:], strict=False):
            starts = [s for s, _ in b]
            aligned = sum(any(abs(s - t) <= tolerance for t in starts) for s, _ in a)
            if aligned < PARALLEL_SHARE * max(len(a), len(b)):
                return lanes
        rows = sorted(
            (
                (start, index, units)
                for index, lane_blocks in enumerate(blocks)
                for start, units in lane_blocks
            ),
            key=lambda item: (item[0], item[1]),
        )
        merged, group = [], []
        for start, index, units in rows:
            if group and start - group[0][0] > tolerance:
                merged += [u for _, _, us in sorted(group, key=lambda g: g[1]) for u in us]
                group = []
            group.append((start, index, units))
        merged += [u for _, _, us in sorted(group, key=lambda g: g[1]) for u in us]
        self.decide(
            "lane_transition",
            [band.id],
            "row_synchronised_lanes",
            0.7,
            ["block starts align across lanes; read block row by block row"],
            ["lane after lane"],
            {"blocks": sum(len(b) for b in blocks)},
        )
        others = [(lane, units) for lane, units in lanes if not _main_lines(units)]
        return [(texts[0][0], merged)] + [(lane, []) for lane, _ in texts[1:]] + others

    def _blocks(self, units, frame):
        """(start key, units) runs split where the baseline gap exceeds the lane's usual pitch."""
        keys = [
            frame.line_key(self.lines[u.line_id]) for u in units if u.line_id and u.float is None
        ]
        steps = sorted(b - a for a, b in zip(keys, keys[1:], strict=False) if b - a > 0)
        pitch = steps[len(steps) // 2] if steps else 0
        blocks, last = [], None
        for unit in units:
            if unit.float is not None or unit.line_id is None:
                if blocks:
                    blocks[-1][1].append(unit)
                else:
                    blocks.append([float("-inf"), [unit]])
                continue
            key = frame.line_key(self.lines[unit.line_id])
            if not blocks or last is None or key - last > BLOCK_GAP * pitch:
                blocks.append([key, [unit]])
            else:
                blocks[-1][1].append(unit)
            last = key
        return [(start, units) for start, units in blocks]

    def _inset_lane(self, region, lanes, by_lane, frame):
        """First text lane in writing order that the inset overlaps or nearly touches."""
        x0, x1 = frame.x_interval(region.bbox)
        texts = [
            lane
            for lane in lanes
            if any(self.role(r) == "main" for r in by_lane.get(lane.index, []))
        ]
        sizes = sorted(
            self.lines[lid].font_size
            for lane in texts
            for r in by_lane[lane.index]
            for lid in r.line_ids
        )
        reach = INSET_REACH * (sizes[len(sizes) // 2] if sizes else 10.0)
        for lane in texts:
            if _overlap(x0, x1, lane.x0, lane.x1) > 0 or max(lane.x0 - x1, x0 - lane.x1) <= reach:
                return lane, "inset"
        return None, None

    def _best_lane(self, region, lanes, frame):
        x0, x1 = frame.x_interval(region.bbox)
        scored = [(_overlap(x0, x1, lane.x0, lane.x1), lane) for lane in lanes]
        scored = [item for item in scored if item[0] > 0]
        return max(scored, key=lambda item: item[0])[1] if scored else None

    def _split_lane(self, lane, regions, band, frame, inserts, clusters):
        """Read each sub-lane as a pseudo-lane; floats join the sub-lane holding their centre."""
        extents = []
        for cluster in clusters:
            boxes = [frame.box(self.lines[lid].bbox) for lid in cluster]
            extents.append((min(b.x0 for b in boxes), max(b.x1 for b in boxes)))

        def home(region):
            x0, x1 = frame.x_interval(region.bbox)
            centre = (x0 + x1) / 2
            return min(
                range(len(extents)),
                key=lambda k: max(extents[k][0] - centre, centre - extents[k][1], 0.0),
            )

        result = []
        for k, cluster in enumerate(clusters):
            pseudo = lane.model_copy(update={"x0": extents[k][0], "x1": extents[k][1]})
            place = (band.scope_id, band.id, (lane.index, k))
            units = self.lane_units(
                pseudo,
                regions,
                band,
                frame,
                False,
                [item for item in inserts if home(item[0]) == k],
                place,
                only=set(cluster),
                accept=lambda region, k=k: home(region) == k,
            )
            result.append((pseudo, units))
        return result

    def lane_units(
        self, lane, regions, band, frame, in_float, inserts, place, only=None, accept=None
    ):
        """Lines by baseline (rows read inline) with floats placed by their centre.

        ``only`` restricts the lines and ``accept`` the floats (sub-lanes of a split lane).
        """
        has_text = any(self.role(r) == "main" for r in regions)
        lines, floats = [], []
        for region in regions:
            role = self.role(region)
            if role in {"artifact", "invisible", "attached"}:
                continue
            if only is not None and role == "main":
                lines += [(lid, role) for lid in region.line_ids if lid in only]
                continue
            if accept is not None and not accept(region):
                continue
            if role == "container":
                target = self.callout_scope.get(region.id)
                if in_float:
                    content = self.traverse(self.scopes[target], True) if target else []
                    floats.append((frame.center_key(region.bbox), content))
                    continue
                mode = "in_lane" if has_text else "lane_order"
                reasons = (
                    ["box inside a text lane; anchored at its centre"]
                    if has_text
                    else ["box occupies its own lane; read in lane order"]
                )
                unit = self.callout_float(region, frame, place, lane, mode, 0.75, reasons)
                floats.append((frame.center_key(region.bbox), [Unit(float=unit)]))
                continue
            if in_float or role in {"main", "furniture"}:
                if in_float and role in {"figure", "table"}:
                    floats.append(
                        (frame.center_key(region.bbox), self.figure_units(region, frame, place))
                    )
                    continue
                unit_role = "float" if in_float else role
                lines += [(lid, unit_role) for lid in region.line_ids]
                continue
            mode = "in_lane" if has_text else "lane_order"
            reasons = (
                [f"{role} inside a text lane; anchored at its centre"]
                if has_text
                else [f"{role} in its own lane; read in lane order"]
            )
            unit = self.float_for(region, frame, place, mode, 0.75 if has_text else 0.7, reasons)
            floats.append((frame.center_key(region.bbox), [Unit(float=unit)]))
        for region, mode, reasons in inserts:
            unit = self.callout_float(region, frame, place, lane, mode, 0.65, reasons)
            floats.append((frame.center_key(region.bbox), [Unit(float=unit)]))
        roles = dict(lines)
        ordered = self._rows(list(roles), frame)
        keyed = [
            (frame.line_key(self.lines[lid]), 0, [Unit(lid, place, roles[lid])]) for lid in ordered
        ]
        # Stable merge: rows keep their order; a float goes before the first line keyed after it.
        floats.sort(key=lambda item: item[0])
        units, f = [], 0
        for key, _, line_units in keyed:
            while f < len(floats) and floats[f][0] < key:
                units += floats[f][1]
                f += 1
            units += line_units
        for _, content in floats[f:]:
            units += content
        return units

    # ------------------------------------------------- column-flow ambiguity
    def inset_runs(self, sequence, frame):
        """Adjacent bands that share one column structure are read as one column flow.

        A run of adjacent bands (gap at most two font sizes) with the same number (at least two)
        of aligned text lanes is read lane by lane across the run. Step 4 splits bands around a
        gutter-bridging inset (an inset never splits a column's text) and where it misses or
        re-finds gutters (sub-lanes count as lanes); no spanning item lies between such bands.
        """
        result, i = [], 0
        while i < len(sequence):
            j = i + 1
            while (
                j < len(sequence)
                and isinstance(sequence[j - 1], BandResult)
                and isinstance(sequence[j], BandResult)
                and self._continuous(sequence[j - 1], sequence[j], frame)
            ):
                j += 1
            run = sequence[i:j]
            if len(run) > 1:
                inset = any(part.band.inset_block_ids for part in run)
                lanes = [part.main_lanes() for part in run]
                merged = []
                for k in range(len(lanes[0])):
                    merged += [u for part in lanes for u in part[k][1]]
                rest = [
                    u
                    for part in run
                    for lane, units in part.lanes
                    if not _main_lines(units)
                    for u in units
                ]
                tail = [u for part in run for u in part.tail]
                self.decide(
                    "column_flow",
                    [part.band.id for part in run],
                    "one_column_flow_around_inset" if inset else "one_column_flow_across_bands",
                    0.75 if inset else 0.6,
                    [
                        "adjacent bands with aligned text lanes split only around an inset"
                        if inset
                        else "adjacent bands with the same aligned columns and no gap"
                    ],
                    ["band_by_band"],
                )
                result.append(merged + rest + tail)
            else:
                result.extend(run)
            i = j
        return result

    def _continuous(self, upper, lower, frame):
        a, b = upper.main_lanes(), lower.main_lanes()
        if len(a) < 2 or len(a) != len(b):
            return False
        if not all(_aligned(x, y) for (x, _), (y, _) in zip(a, b, strict=True)):
            return False
        sizes = [self.lines[u.line_id].font_size for _, units in a + b for u in units if u.line_id]
        size = sorted(sizes)[len(sizes) // 2] if sizes else 10.0
        upper_box, lower_box = frame.box(upper.band.bbox), frame.box(lower.band.bbox)
        if lower_box.y0 - upper_box.y1 > 2 * size:
            return False
        # A rule or banner across the columns between the bands separates two flows.
        width = upper_box.x1 - upper_box.x0
        for block in self.layout.blocks:
            if block.kind not in {"rule", "banner"}:
                continue
            box = frame.box(block.bbox)
            middle = (box.y0 + box.y1) / 2
            share = _overlap(box.x0, box.x1, upper_box.x0, upper_box.x1) / width if width else 0
            if upper_box.y1 - size <= middle <= lower_box.y0 + size and share >= 0.5:
                return False
        return True

    def column_flow(self, sequence):
        """Columns may continue across a band holding only floats; decided on evidence."""
        result = list(sequence)
        i = 0
        while i < len(result):
            first = result[i]
            if not isinstance(first, BandResult) or len(first.main_lanes()) < 2:
                i += 1
                continue
            j = i + 1
            while j < len(result) and self._float_only(result[j]):
                j += 1
            if j == i + 1 or j >= len(result) or not isinstance(result[j], BandResult):
                i += 1
                continue
            second = result[j]
            upper, lower = first.main_lanes(), second.main_lanes()
            if len(upper) != len(lower) or not all(
                _aligned(a, b) for (a, _), (b, _) in zip(upper, lower, strict=True)
            ):
                i += 1
                continue
            end = _main_lines(upper[0][1])[-1]
            across = self._evidence(end, _main_lines(lower[0][1])[0])
            down = self._evidence(end, _main_lines(upper[1][1])[0])
            subjects = [first.band.id, second.band.id]
            difference = round(across.score - down.score, 3)
            evidence = {"across_float_band": across.score, "next_lane_same_band": down.score}
            if across.score >= CONTINUES and difference >= FLOW_MARGIN:
                floats = [u for part in result[i + 1 : j] for u in _units(part)]
                merged = []
                for k, ((_, top), (_, bottom)) in enumerate(zip(upper, lower, strict=True)):
                    merged += top + (floats if k == 0 else []) + bottom
                extra = [u for lane, units in first.lanes if not _main_lines(units) for u in units]
                extra += [
                    u for lane, units in second.lanes if not _main_lines(units) for u in units
                ]
                combined = merged + extra + first.tail + second.tail
                self.decide(
                    "column_flow",
                    subjects,
                    "columns_continue_across_float_band",
                    min(0.85, 0.5 + difference / 2),
                    ["first lane continues below the float band", *across.reasons],
                    ["break_at_float_band"],
                    evidence,
                )
                result[i : j + 1] = [combined]
                i += 1
                continue
            if across.score >= CONTINUES and difference > 0:
                self.decide(
                    "column_flow",
                    subjects,
                    "break_at_float_band",
                    0.5,
                    ["ambiguous: text could continue below the float band", *across.reasons],
                    ["columns_continue_across_float_band"],
                    evidence,
                )
            i = j
        return result

    def _float_only(self, part):
        units = _units(part)
        return bool(units) and all(u.float is not None for u in units)

    def _evidence(self, previous, following):
        return continuation(
            self.text(previous),
            self.text(following),
            previous_type=self.region_of[previous].type,
            following_type=self.region_of[following].type,
            vocabulary=self.vocabulary,
        )

    # ------------------------------------------------------------------ build
    def build(self):
        page_scope = next(s for s in self.layout.scopes if s.kind == "page")
        units = self.traverse(page_scope)
        main, furniture, floats = [], [], []
        place = {}
        for unit in units:
            if unit.float is not None:
                anchor_index = len(main) - 1
                floats.append((anchor_index, unit.float))
                for inner in self._flatten(unit.float.units):
                    place[inner.line_id] = inner.place
                continue
            place[unit.line_id] = unit.place
            (furniture if unit.role == "furniture" else main).append(unit.line_id)
        placed = set(main) | set(furniture)
        for _, item in floats:
            placed.update(u.line_id for u in self._flatten(item.units))
        artifact, invisible, unplaced = [], [], []
        for line in self.layout.lines:
            if line.id in placed:
                continue
            role = self.role(self.region_of[line.id])
            if role == "artifact":
                artifact.append(line.id)
            elif role == "invisible":
                invisible.append(line.id)
            else:
                unplaced.append(line.id)
        for lid in unplaced:
            main.append(lid)
            self.decide(
                "unplaced",
                [lid],
                "appended_to_main_flow",
                0.3,
                ["line not reached by the structural traversal"],
            )
        self._straddles()
        streams = self._streams(main, furniture, artifact, invisible, floats)
        self._sequence_edges(streams, place)
        return streams

    def _flatten(self, units):
        for unit in units:
            if unit.float is not None:
                yield from self._flatten(unit.float.units)
            else:
                yield unit

    def _straddles(self):
        for region in self.regions.values():
            scope = self.scopes.get(region.scope_id)
            if scope is None or scope.kind != "callout":
                continue
            for lid in region.line_ids:
                box = self.lines[lid].bbox
                width = box.x1 - box.x0
                outside = width - _overlap(box.x0, box.x1, scope.bbox.x0, scope.bbox.x1)
                if width > 0 and outside / width > STRADDLE:
                    self.decide(
                        "scope_boundary",
                        [lid, scope.id],
                        "kept_in_scope",
                        0.4,
                        [f"line extends {outside / width:.0%} beyond its box; may merge two texts"],
                    )

    def _streams(self, main, furniture, artifact, invisible, floats):
        layout = self.layout
        sid = lambda *parts: stable_id(layout.source_sha256, layout.page, "stream", *parts)  # noqa: E731
        streams = [
            Stream(
                id=sid("main"),
                kind="main",
                line_ids=main,
                confidence=0.8,
                reasons=["bands along the stacking axis, lanes in writing order"],
            )
        ]
        counts = defaultdict(int)
        merged = []
        for index, item in floats:
            previous = merged[-1] if merged else None
            if (
                previous is not None
                and previous[0] == index
                and previous[1].kind == item.kind
                and item.kind in {"sidebar", "note", "credit"}
                and previous[1].mode == item.mode
            ):
                previous[1].units += item.units
                previous[1].region_ids += item.region_ids
                continue
            merged.append((index, item))
        for index, item in merged:
            after = main[index] if index >= 0 else None
            order = counts[index]
            counts[index] += 1
            lines = [u.line_id for u in self._flatten(item.units)]
            confidence = item.confidence
            stream = Stream(
                id=sid(item.kind, item.seed),
                kind=item.kind,
                line_ids=lines,
                region_ids=item.region_ids,
                scope_id=item.scope_id,
                anchor=Anchor(
                    after_line_id=after,
                    position=index,
                    order=order,
                    mode=item.mode if after is not None else "page_start",
                    confidence=confidence,
                    reasons=item.reasons,
                    review_required=confidence < REVIEW_BELOW,
                ),
                confidence=confidence,
                reasons=item.reasons,
                review_required=confidence < REVIEW_BELOW,
            )
            streams.append(stream)
            self.edges.append(
                OrderEdge(
                    source=stream_node(stream.id),
                    target=after or PAGE_START,
                    kind="anchored_after",
                    confidence=confidence,
                    reasons=item.reasons,
                )
            )
            self.decide(
                "float_anchor",
                [stream.id],
                f"after {after[:12]}" if after else "page_start",
                confidence,
                item.reasons,
            )
        for kind, lines, reason in (
            ("furniture", furniture, "header/footer/page-number candidates, retained"),
            ("artifact", artifact, "outside the explicit TrimBox or blank; extraction order"),
            ("invisible", invisible, "invisible text layer; extraction order; review"),
        ):
            if lines:
                streams.append(
                    Stream(
                        id=sid(kind),
                        kind=kind,
                        line_ids=lines,
                        confidence=0.9 if kind != "invisible" else 0.4,
                        reasons=[reason],
                        review_required=kind == "invisible",
                    )
                )
        return streams

    def _sequence_edges(self, streams, place):
        for stream in streams:
            ids = stream.line_ids
            for previous, following in zip(ids, ids[1:], strict=False):
                self.edges.append(self._edge(stream, previous, following, place))

    def _edge(self, stream, previous, following, place):
        a, b = place.get(previous), place.get(following)
        if stream.kind in {"furniture", "artifact", "invisible"} or a is None or b is None:
            return OrderEdge(
                source=previous,
                target=following,
                kind="next_in_stream",
                confidence=0.8,
                reasons=[f"{stream.kind} stream order"],
            )
        same_region = self.region_of[previous].id == self.region_of[following].id
        if stream.kind in {"figure", "table"} and same_region:
            return OrderEdge(
                source=previous,
                target=following,
                kind="next_in_stream",
                confidence=0.7,
                reasons=[f"{stream.kind} internal order"],
            )
        if a == b:
            return OrderEdge(
                source=previous,
                target=following,
                kind="next_in_lane",
                confidence=0.95,
                reasons=["next line along the lane"],
            )
        evidence = self._evidence(previous, following)
        features = {"score": evidence.score, **evidence.features}
        if a[:2] == b[:2] and a[1] is not None:
            kind, confidence = "next_lane_in_band", 0.85
            if evidence.score >= CONTINUES:
                kind, confidence = "continues_across_column", max(0.85, 0.5 + evidence.score / 2)
            reasons = ["lanes in writing-direction order", *evidence.reasons]
            decision = "lane_transition"
        else:
            kind, confidence = "next_band", 0.9
            reasons = ["bands along the stacking axis", *evidence.reasons]
            decision = "band_transition"
        if evidence.features.get("previous_end") == "hyphen" and evidence.score < CONTINUES:
            confidence = 0.45
            reasons.append("previous line breaks a word but this line does not continue it")
        if stream.kind == "main":
            self.decide(decision, [previous, following], kind, confidence, reasons, [], features)
        return OrderEdge(
            source=previous,
            target=following,
            kind=kind,
            confidence=round(min(1.0, confidence), 3),
            reasons=reasons,
            evidence=features,
        )


def _units(part):
    return part.units() if isinstance(part, BandResult) else part


def _union(boxes):
    from book_core.model.common import BBox

    return BBox(
        x0=min(b.x0 for b in boxes),
        y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes),
        y1=max(b.y1 for b in boxes),
    )


def _aligned(a, b):
    width = min(a.x1 - a.x0, b.x1 - b.x0)
    return width > 0 and _overlap(a.x0, a.x1, b.x0, b.x1) >= 0.7 * width


def build_reading_order(layout, store, vocabulary=None, resolved_device="cpu"):
    """The page's reading order: main flow, anchored floats and side streams."""
    builder = PageOrderBuilder(layout, store, vocabulary)
    streams = builder.build()
    return PageReadingOrder(
        source_sha256=layout.source_sha256,
        page=layout.page,
        order_version=READING_ORDER_VERSION,
        layout_version=layout.layout_version,
        streams=streams,
        edges=builder.edges,
        decisions=builder.decisions,
        provenance=Provenance(
            source_sha256=layout.source_sha256,
            engine="book_core.reading_order",
            engine_version=READING_ORDER_VERSION,
            method="derived",
            resolved_device=resolved_device,
            execution_device="cpu",
        ),
    )
