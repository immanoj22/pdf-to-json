"""Table regions from combined evidence; tables told apart from look-alikes.

Evidence families (a table needs two of them; one source alone never decides):

- **rules**: a connected network of horizontal and vertical rules (or edges of adjacent
  coloured cells) enclosing at least two cells, or a stack of parallel full-width rules
  (top, header and bottom rules of an unboxed table); a Step 4 ruled table region;
- **alignment**: the text inside forms at least two columns over at least two rows in the
  region's reading frame (``grid.columns_from_text``), or a Step 4 aligned-numeric region;
- **models**: a table box of a learned detector (Heron, PP-DocLayoutV3, Table Transformer)
  covering the region.

Look-alikes are rejected with a reason and kept for review: separate boxes joined by
connectors (graphic organizers), a single axis with ticks (timelines), fill-in rules after
labels (forms), aligned running text (multi-column text) and aligned entries with locators
(indexes and contents). Rotation comes from the lines inside (their right-angle frame).
All distances are in the page's font units.
"""

from collections import Counter
from dataclasses import dataclass, field

from book_core.model.common import BBox
from book_core.tables.rulings import Rule, merged

TOUCH = 0.45  # font sizes: rules this close meet (vertical rules often stop short)
MERGE = 0.3  # font sizes: collinear rules this close are one rule
STACK_OVERLAP = 0.8  # parallel rules sharing this share of the shorter extent stack
MODEL_SCORE = 0.5
MODEL_COVER = 0.5  # a model box supports a region it covers by half of either box
SAME_REGION = 0.5
STACK_RULES = 3  # top, header and bottom rules of an unboxed table
STACK_GAP = 60  # font sizes: rules of one unboxed table are never further apart
ORGANIZER_GAP = 0.6  # font sizes: boxes further apart than this do not share borders


def area(b):
    return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)


def shared(a, b):
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return w * h if w > 0 and h > 0 else 0.0


def union(boxes):
    boxes = list(boxes)
    return BBox(
        x0=min(b.x0 for b in boxes),
        y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes),
        y1=max(b.y1 for b in boxes),
    )


def grow(b, d):
    return BBox(x0=b.x0 - d, y0=b.y0 - d, x1=b.x1 + d, y1=b.y1 + d)


def covers(a, b, share=MODEL_COVER):
    common = shared(a, b)
    return common > 0 and common >= share * min(area(a), area(b))


def rule_box(rules):
    xs, ys = [], []
    for r in rules:
        if r.axis == "h":
            xs += [r.start, r.end]
            ys.append(r.at)
        else:
            ys += [r.start, r.end]
            xs.append(r.at)
    return BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))


def _meets(h, v, t):
    return h.start - t <= v.at <= h.end + t and v.start - t <= h.at <= v.end + t


def _components(items, linked):
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if linked(items[i], items[j]):
                a, b = find(i), find(j)
                if a != b:
                    parent[max(a, b)] = min(a, b)
    groups = {}
    for i, item in enumerate(items):
        groups.setdefault(find(i), []).append(item)
    return list(groups.values())


def _positions(values, tolerance):
    out = []
    for v in sorted(values):
        if not out or v - out[-1] > tolerance:
            out.append(v)
    return out


@dataclass
class Network:
    rules: list[Rule]
    bbox: BBox
    kind: str  # grid / frame / stack
    rows: int  # distinct horizontal positions
    columns: int  # distinct vertical positions
    fill_only: bool = False


def networks(rules, font):
    """Rule networks of a page: grids, single frames and stacks of parallel rules."""
    t = TOUCH * font
    rules = [r for r in merged(rules, MERGE * font) if not r.light]
    found = []

    def linked(a, b):
        # Edges of filled areas meet only edges of other fills: a background panel around
        # a ruled table is not part of its grid.
        if (a.kind == "fill_edge") != (b.kind == "fill_edge"):
            return False
        return a.axis != b.axis and _meets(*(a, b) if a.axis == "h" else (b, a), t)

    for group in _components(rules, linked):
        hs = [r for r in group if r.axis == "h"]
        vs = [r for r in group if r.axis == "v"]
        if not hs or not vs:
            continue
        rows = len(_positions([r.at for r in hs], MERGE * font))
        columns = len(_positions([r.at for r in vs], MERGE * font))
        if rows < 2 or columns < 2:
            continue
        kind = "grid" if rows >= 3 or columns >= 3 else "frame"
        found.append(
            Network(
                group,
                rule_box(group),
                kind,
                rows,
                columns,
                fill_only=all(r.kind == "fill_edge" for r in group),
            )  # fmt: skip
        )
    # Stacks: parallel rules of similar extent, one above another (unboxed tables), in
    # either page axis (a rotated table's rules are vertical on the page).
    grids = list(found)
    in_grids = {id(r) for net in found for r in net.rules}
    for axis in ("h", "v"):
        parallel = [
            r for r in rules if r.axis == axis and r.kind != "fill_edge" and id(r) not in in_grids
        ]

        def stacked(a, b):
            overlap = min(a.end, b.end) - max(a.start, b.start)
            return (
                overlap >= STACK_OVERLAP * max(a.length, b.length)
                and font < abs(a.at - b.at) <= STACK_GAP * font
            )

        for group in _components(parallel, stacked):
            positions = _positions([r.at for r in group], MERGE * font)
            if len(positions) < STACK_RULES:
                continue
            long = max(r.length for r in group)
            if long < 6 * font:
                continue
            box = rule_box(group)
            # Rules around a boxed grid (a panel's edges) do not make an unboxed table.
            if any(n.kind == "grid" and covers(n.bbox, box, 0.9) for n in grids):
                continue
            found.append(Network(group, box, "stack", len(positions), 1))
    return found


@dataclass
class Candidate:
    bbox: BBox
    sources: dict[str, float] = field(default_factory=dict)  # source -> strength
    networks: list[Network] = field(default_factory=list)
    model_boxes: dict[str, list] = field(default_factory=dict)
    layout: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def add(self, source, value=1.0):
        self.sources[source] = max(self.sources.get(source, 0.0), value)


def candidates(evidence):
    """Candidate regions from every evidence source, merged where they cover each other."""
    font = evidence.font
    drafts = []
    for net in networks(content_rules(evidence), font):
        if area(net.bbox) <= 0:
            continue
        draft = Candidate(net.bbox, networks=[net])
        draft.add(f"rules_{net.kind}")
        drafts.append(draft)
    for row in evidence.layout_tables:
        draft = Candidate(row["bbox"], layout=[row])
        ruled = not any("without a ruled grid" in r for r in row["reasons"])
        draft.add("layout_ruled" if ruled else "layout_aligned")
        drafts.append(draft)
    for model, boxes in evidence.models.items():
        for bbox, score, label in boxes:
            if score < MODEL_SCORE:
                continue
            draft = Candidate(bbox, model_boxes={model: [(bbox, score, label)]})
            draft.add(f"model_{model}", score)
            drafts.append(draft)
    groups = _components(drafts, lambda a, b: covers(a.bbox, b.bbox, SAME_REGION))
    out = []
    for group in groups:
        merged_draft = Candidate(union(d.bbox for d in group))
        for d in group:
            for source, value in d.sources.items():
                merged_draft.add(source, value)
            merged_draft.networks += d.networks
            merged_draft.layout += d.layout
            for model, boxes in d.model_boxes.items():
                merged_draft.model_boxes.setdefault(model, []).extend(boxes)
        # The region is the geometric extent when rules or layout give one; model boxes
        # alone give it only when nothing else does.
        geometric = [n.bbox for n in merged_draft.networks] + [
            r["bbox"] for r in merged_draft.layout
        ]
        if geometric:
            merged_draft.bbox = union(geometric)
        out.append(merged_draft)
    return out


def content_rules(evidence):
    """Rules lying wholly inside the content area: trim marks, page frames and bleed bands
    reach the content edge or beyond and are page decoration, not table structure."""
    box = evidence.content
    inset = 1.0
    out = []
    for r in evidence.rules:
        if r.axis == "h":
            x0, x1, y0, y1 = r.start, r.end, r.at, r.at
        else:
            x0, x1, y0, y1 = r.at, r.at, r.start, r.end
        if (box.x0 + inset < x0 and x1 < box.x1 - inset
                and box.y0 + inset < y0 and y1 < box.y1 - inset):  # fmt: skip
            out.append(r)
    return out


def text_cells(net, lines, font):
    """(rows, columns) of the network's own cells that hold the centre of a line."""
    hs = _positions([r.at for r in net.rules if r.axis == "h"], MERGE * font)
    vs = _positions([r.at for r in net.rules if r.axis == "v"], MERGE * font)
    found = set()
    for line in lines:
        cx = (line.bbox.x0 + line.bbox.x1) / 2
        cy = (line.bbox.y0 + line.bbox.y1) / 2
        r = sum(y < cy for y in hs)
        c = sum(x < cx for x in vs)
        if 0 < r < len(hs) and 0 < c < len(vs):
            found.add((r, c))
    return len({r for r, _ in found}), len({c for _, c in found})


def frame_rotation(lines):
    """The right-angle reading frame of a region from its lines' characters (None mixed)."""
    votes = Counter()
    for line in lines:
        if line.rotation is not None:
            votes[line.rotation] += max(1, len(line.span_ids))
    if not votes:
        return 0.0
    rotation, count = votes.most_common(1)[0]
    return float(rotation) if count >= 0.6 * sum(votes.values()) else None


def region_lines(evidence, bbox, margin):
    """Content lines whose centre lies inside the region (furniture excluded)."""
    box = grow(bbox, margin)
    return [
        line
        for line in evidence.lines
        if not line.blank and not line.furniture and box.contains_center(line.bbox)
    ]


def organizer(networks_inside, font):
    """Separate closed boxes not sharing borders (and not one grid): a graphic organizer."""
    frames = [n for n in networks_inside if n.kind in {"frame", "grid"}]
    if len(frames) < 2:
        return False
    gap = ORGANIZER_GAP * font
    for i, a in enumerate(frames):
        for b in frames[i + 1 :]:
            if shared(grow(a.bbox, gap), b.bbox) > 0:
                return False  # boxes that touch share a border: one ruled structure
    return True


def timeline(networks_inside, font):
    """One long axis with short perpendicular ticks and no second parallel rule."""
    for net in networks_inside:
        hs = [r for r in net.rules if r.axis == "h"]
        vs = [r for r in net.rules if r.axis == "v"]
        for axis, cross in ((hs, vs), (vs, hs)):
            if len(axis) == 1 and len(cross) >= 3:
                long = axis[0].length
                if all(r.length < 0.25 * long for r in cross):
                    return True
    return False
