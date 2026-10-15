"""Equation regions of one page from native evidence; layout-model boxes are support only.

Vector regions: recurring glyph outlines (``glyphs``) joined by proximity, with rule bars
that have glyphs on both sides (fractions) or glyphs just below (overlines). Text regions:
operator runs (``text``). A vector region and a text run on the same visual band that touch
are one mixed region. A region is inline when text of a visual line shares its band beside
it, display otherwise. Where a region lands is the unit that holds its line (inline), or the
unit of the nearest line above it (display).

Nothing is dropped or reordered: regions are added evidence over unchanged units.
"""

import unicodedata
from collections import Counter, defaultdict

from book_core.equations.glyphs import BAR_MAX_HEIGHT, page_glyphs
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


def _fill(obj):
    return tuple(obj.fill or obj.stroke or ())


def _same_colour(a, b):
    return len(a) == len(b) and all(
        abs(x - y) <= COLOUR_TOLERANCE for x, y in zip(a, b, strict=True)
    )


def typeset_like(cluster, images, text_colours):
    """Typeset characters of one expression are painted in one colour that the page's own text
    uses, and are not drawn over a picture; drawn art (map symbols, icons, logos) is not.
    Returns the reason a cluster is not typeset-like, or None."""
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


def range_box(span, start, end, frame=None):
    """Box of a character range of a span: its share of the span's extent along the span's
    own writing direction (characters are taken as equally wide; no glyph boxes are stored).
    """
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


def glyph_groups(glyphs, size, text_boxes):
    """[[objects]] of glyph outlines joined by proximity, never across text between them."""
    sets = _Sets(len(glyphs))
    for i, a in enumerate(glyphs):
        for j in range(i + 1, len(glyphs)):
            b = glyphs[j]
            dx, dy = _gap(a.bbox, b.bbox)
            same_band = _vertical_overlap(a.bbox, b.bbox) > 0
            stacked = _horizontal_overlap(a.bbox, b.bbox) > 0
            joined = (
                (same_band and dx <= JOIN_GAP * size)
                or (stacked and dy <= STACK_GAP * size)
                or (dx <= 0.15 * size and dy <= 0.15 * size)
            )
            if joined and not (same_band and _text_between(a.bbox, b.bbox, text_boxes)):
                sets.join(i, j)
    groups = defaultdict(list)
    for i, item in enumerate(glyphs):
        groups[sets.find(i)].append(item)
    return list(groups.values())


def vector_clusters(glyphs, bars, signatures, accepted, size, text_boxes=()):
    """[[objects]] of joined glyphs; a cluster needs at least one accepted outline (recurring
    in the book and often written next to other glyphs)."""
    clusters = [
        g
        for g in glyph_groups(glyphs, size, text_boxes)
        if any(signatures[x.id] in accepted for x in g)
    ]
    # Bars join the cluster(s) they separate (fraction) or cover (overline).
    for bar in bars:
        box = bar.bbox
        if box.x1 - box.x0 > BAR_MAX_WIDTH * size:
            continue
        above, below = [], []
        for index, cluster in enumerate(clusters):
            for item in cluster:
                if _horizontal_overlap(item.bbox, box) <= 0:
                    continue
                if 0 <= box.y0 - item.bbox.y1 <= BAR_REACH * size:
                    above.append(index)
                elif 0 <= item.bbox.y0 - box.y1 <= BAR_REACH * size:
                    below.append(index)
        touched = sorted(set(above) | set(below))
        if above and below or (below and not above and box.y1 - box.y0 <= BAR_MAX_HEIGHT * size):
            merged = [bar]
            for index in touched:
                merged.extend(clusters[index])
            clusters = [c for i, c in enumerate(clusters) if i not in touched] + [merged]
    # Fraction parts and their neighbours on the same band join once bars are placed.
    changed = True
    while changed:
        changed = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                a, b = _union(o.bbox for o in clusters[i]), _union(o.bbox for o in clusters[j])
                dx, dy = _gap(a, b)
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


def detect_page(page, native, layout, units, recurring, math_fonts, model_boxes, size, config):
    """(regions, model-only boxes, diagnostics) of one page."""
    store = page.store
    number = page.geometry.page
    lines = [line for line in layout.lines if line.inside_content and not line.blank]
    text_boxes = [store.spans[sid].bbox for line in lines for sid in line.span_ids]
    glyphs, bars, signatures = page_glyphs(native, size, text_boxes)
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
    for cluster in vector_clusters(glyphs, bars, signatures, recurring, size, text_boxes):
        reason = typeset_like(cluster, images, text_colours)
        if reason is not None:
            rejected[reason] += 1
            continue
        box = _union(o.bbox for o in cluster)
        recurring_share = sum(signatures.get(o.id) in recurring for o in cluster) / len(cluster)
        drafts.append(
            {
                "box": box,
                "objects": sorted(o.id for o in cluster),
                "ranges": [],
                "line_ids": [],
                "rules": ["recurring_vector_glyphs"]
                + (["rule_bar"] if any(o.id not in signatures for o in cluster) else []),
                "signals": {
                    "glyphs": sum(o.id in signatures for o in cluster),
                    "bars": sum(o.id not in signatures for o in cluster),
                    "recurring_share": round(recurring_share, 3),
                    "figure_region": any(object_region.get(o.id) == "figure" for o in cluster),
                },
            }
        )
    geometry = native.span_geometry
    # Text runs follow native text order, so lines of any rotation are read.
    for line in lines:
        for run in line_runs(store, line, geometry, math_fonts):
            boxes = [
                range_box(store.spans[sid], a, b, geometry.get(sid)) for sid, a, b in run.ranges
            ]
            drafts.append(
                {
                    "box": _union(boxes),
                    "objects": [],
                    "ranges": run.ranges,
                    "line_ids": [line.id],
                    "rules": list(run.rules),
                    "signals": dict(run.signals, whole_line=run.whole_line),
                }
            )
    _join_wrapped(drafts, store, lines, units)
    # A text run touching a vector region on its band is one mixed region.
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(drafts):
            for j in range(i + 1, len(drafts)):
                b = drafts[j]
                drawn_and_text = (a["objects"] and b["ranges"]) or (a["ranges"] and b["objects"])
                if not drawn_and_text:
                    continue
                dx, _ = _gap(a["box"], b["box"])
                if _vertical_overlap(a["box"], b["box"]) > 0 and dx <= JOIN_GAP * size:
                    a["box"] = _union([a["box"], b["box"]])
                    a["objects"] = sorted(set(a["objects"]) | set(b["objects"]))
                    a["ranges"] = a["ranges"] + b["ranges"]
                    a["line_ids"] = sorted(set(a["line_ids"]) | set(b["line_ids"]))
                    a["rules"] = sorted(set(a["rules"]) | set(b["rules"]))
                    a["signals"] = {**b["signals"], **a["signals"]}
                    del drafts[j]
                    merged = True
                    break
            if merged:
                break
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
