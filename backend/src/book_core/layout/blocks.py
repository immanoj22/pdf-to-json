"""Layout-shaping visual blocks from Step 3 roles plus native geometry.

Backgrounds never become blocks. Containers become callouts unless they are filled with
figure evidence (figure panels) or are visually transparent inside their parent. Figure
parts and nearby unresolved vector artwork cluster into figure candidates. Every
threshold is relative to the page or font size; no fixture coordinates are used.

Raster seeds are measured on the rendered page with text masked out. Flat margins of a
raster (a fade or an empty border) are not artwork, so a seed covers only its textured
extent; a raster that is flat throughout with text set on it is a backdrop, not a picture.
A placement whose native box lies largely outside the page is a clipped view of a larger
raster (sprite sheets); without clip evidence its visible extent is unknown, so it seeds
nothing. Figures never extend beyond the content frame, and a narrow text-free strip of
artwork running along the content edge is page decoration, not a figure.

Tables come from ruled grids (separate grids that continue one another are merged) and
from aligned numeric cells without rules (`layout.tables`).
"""

from dataclasses import dataclass

import cv2
import numpy as np
import regex
from shapely import STRtree
from shapely import box as shape

from book_core.extraction.fingerprints import stable_id
from book_core.layout.evidence import page_body_style
from book_core.layout.models import VisualBlock
from book_core.layout.tables import aligned_tables, grid_profile, same_grid
from book_core.model.common import BBox

TOKEN = regex.compile(r"[\p{L}\p{M}\p{N}]+")
SEED_ROLES = {"content_image", "figure_part"}
VISUAL_KINDS = {"drawing", "compound", "image", "shading"}
# Rendered-edge fractions (dimensionless) outside text: a row or column of a raster below
# FLAT_EDGES has no visible structure; a whole raster below BACKDROP_EDGES is a flat field.
FLAT_EDGES = 0.01
BACKDROP_EDGES = 0.02
BACKDROP_LINES = 3
OUTSIDE_PAGE_SHARE = 0.10
EDGE_STRIP_WIDTH = 0.10
EDGE_STRIP_HEIGHT = 0.5
EDGE_TOUCH = 0.05


@dataclass
class Cluster:
    members: list
    seeds: int = 0
    filled: int = 0


def area(bbox):
    return max(0.0, bbox.x1 - bbox.x0) * max(0.0, bbox.y1 - bbox.y0)


def to_shape(bbox):
    return shape(bbox.x0, bbox.y0, bbox.x1, bbox.y1)


def union(boxes):
    boxes = list(boxes)
    return BBox(
        x0=min(b.x0 for b in boxes),
        y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes),
        y1=max(b.y1 for b in boxes),
    )


def expand(bbox, margin):
    return BBox(x0=bbox.x0 - margin, y0=bbox.y0 - margin, x1=bbox.x1 + margin, y1=bbox.y1 + margin)


def contains(outer, inner, tolerance=2.0):
    return (
        inner.x0 >= outer.x0 - tolerance
        and inner.y0 >= outer.y0 - tolerance
        and inner.x1 <= outer.x1 + tolerance
        and inner.y1 <= outer.y1 + tolerance
    )


def overlap_area(a, b):
    width = min(a.x1, b.x1) - max(a.x0, b.x0)
    height = min(a.y1, b.y1) - max(a.y0, b.y0)
    return max(0.0, width) * max(0.0, height)


def same_box(a, b, tolerance=2.0):
    return max(abs(a.x0 - b.x0), abs(a.y0 - b.y0), abs(a.x1 - b.x1), abs(a.y1 - b.y1)) <= tolerance


def line_like(obj, page):
    """Thin straight strokes or slim filled bars long enough to separate content."""
    if obj.kind != "drawing" or obj.bbox is None:
        return None
    operators = {item.operator for item in obj.path_items}
    if not operators or not operators <= {"l", "re"}:
        return None
    width, height = obj.bbox.x1 - obj.bbox.x0, obj.bbox.y1 - obj.bbox.y0
    thickness, length = min(width, height), max(width, height)
    if thickness > 2.5 or length < 0.15 * page.width:
        return None
    return "horizontal" if width >= height else "vertical"


def sample(raster, scale, bbox):
    """Median colour of a page area in the rendered raster (BGR, 0..255)."""
    height, width = raster.shape[:2]
    x0, y0 = max(0, int(bbox.x0 * scale)), max(0, int(bbox.y0 * scale))
    x1, y1 = min(width, int(np.ceil(bbox.x1 * scale))), min(height, int(np.ceil(bbox.y1 * scale)))
    if x1 <= x0 or y1 <= y0:
        return None
    return np.median(raster[y0:y1, x0:x1].reshape(-1, 3), axis=0)


def ring(raster, scale, bbox, width=3.0):
    pieces = []
    for part in [
        BBox(x0=bbox.x0 - width, y0=bbox.y0 - width, x1=bbox.x1 + width, y1=bbox.y0),
        BBox(x0=bbox.x0 - width, y0=bbox.y1, x1=bbox.x1 + width, y1=bbox.y1 + width),
        BBox(x0=bbox.x0 - width, y0=bbox.y0, x1=bbox.x0, y1=bbox.y1),
        BBox(x0=bbox.x1, y0=bbox.y0, x1=bbox.x1 + width, y1=bbox.y1),
    ]:
        h, w = raster.shape[:2]
        x0, y0 = max(0, int(part.x0 * scale)), max(0, int(part.y0 * scale))
        x1, y1 = min(w, int(np.ceil(part.x1 * scale))), min(h, int(np.ceil(part.y1 * scale)))
        if x1 > x0 and y1 > y0:
            pieces.append(raster[y0:y1, x0:x1].reshape(-1, 3))
    if not pieces:
        return None
    return np.median(np.concatenate(pieces), axis=0)


def clip_to(bbox, frame):
    clipped = BBox(
        x0=max(bbox.x0, frame.x0),
        y0=max(bbox.y0, frame.y0),
        x1=min(bbox.x1, frame.x1),
        y1=min(bbox.y1, frame.y1),
    )
    return clipped if clipped.x1 > clipped.x0 and clipped.y1 > clipped.y0 else None


def text_mask(lines, shape, scale):
    """Rendered-pixel mask of visible text lines, grown by a third of their font size."""
    mask = np.zeros(shape, bool)
    height, width = shape
    for line in lines:
        if line.blank or not line.visible:
            continue
        margin = 0.3 * max(line.font_size, 1.0)
        y0, y1 = int((line.bbox.y0 - margin) * scale), int((line.bbox.y1 + margin) * scale) + 1
        x0, x1 = int((line.bbox.x0 - margin) * scale), int((line.bbox.x1 + margin) * scale) + 1
        mask[max(0, y0) : min(height, y1), max(0, x0) : min(width, x1)] = True
    return mask


def raster_extent(obj, edges, masked, scale, page):
    """(textured extent or None, edge density outside text) of a raster seed."""
    box = clip_to(obj.bbox, BBox(x0=0, y0=0, x1=page.width, y1=page.height))
    if box is None:
        return None, 0.0
    x0, y0 = int(box.x0 * scale), int(box.y0 * scale)
    x1, y1 = int(np.ceil(box.x1 * scale)), int(np.ceil(box.y1 * scale))
    window = edges[y0:y1, x0:x1]
    free = ~masked[y0:y1, x0:x1]
    if window.size == 0 or not free.any():
        return None, 0.0
    density = float(window[free].mean())
    counted = free.sum(axis=1)
    rows = np.where(counted > 0, (window & free).sum(axis=1) / np.maximum(counted, 1), 0.0)
    counted = free.sum(axis=0)
    cols = np.where(counted > 0, (window & free).sum(axis=0) / np.maximum(counted, 1), 0.0)
    rows, cols = np.flatnonzero(rows > FLAT_EDGES), np.flatnonzero(cols > FLAT_EDGES)
    if rows.size == 0 or cols.size == 0:
        return None, density
    extent = BBox(
        x0=box.x0 + cols[0] / scale,
        y0=box.y0 + rows[0] / scale,
        x1=box.x0 + (cols[-1] + 1) / scale,
        y1=box.y0 + (rows[-1] + 1) / scale,
    )
    return extent, density


def outside_page_share(obj, page):
    native = obj.native_bbox or obj.bbox
    total = area(native)
    if total <= 0:
        return 0.0
    inside = clip_to(native, BBox(x0=0, y0=0, x1=page.width, y1=page.height))
    return 1.0 - (area(inside) / total if inside is not None else 0.0)


def edge_strip(bbox, content, lines):
    """Narrow, tall, text-free artwork running along the left or right content edge."""
    width, height = content.x1 - content.x0, content.y1 - content.y0
    if bbox.x1 - bbox.x0 > EDGE_STRIP_WIDTH * width:
        return False
    if bbox.y1 - bbox.y0 < EDGE_STRIP_HEIGHT * height:
        return False
    at_edge = (
        bbox.x0 <= content.x0 + EDGE_TOUCH * width or bbox.x1 >= content.x1 - EDGE_TOUCH * width
    )
    carries_text = any(
        not line.blank and line.visible and bbox.contains_center(line.bbox) for line in lines
    )
    return at_edge and not carries_text


def build_blocks(analysis, lines, raster, scale):
    native = analysis.native
    page = native.page.geometry
    content = page.content_bbox
    page_area = page.width * page.height
    objects = {obj.id: obj for obj in analysis.all_objects()}
    roles = {record.object_id: record for record in analysis.asset_ledger.records}
    diagnostics = []
    members = {member for compound in analysis.compounds for member in compound.member_ids}
    sizes = sorted(line.font_size for line in lines if not line.blank and line.font_size > 0)
    typical_size = sizes[len(sizes) // 2] if sizes else 10.0

    def role(oid):
        return roles[oid].role if oid in roles else None

    # Containers, deduplicated where several paints share one box.
    containers = []
    for obj in analysis.all_objects():
        if obj.bbox is None or role(obj.id) != "container":
            continue
        for group in containers:
            if same_box(group["bbox"], obj.bbox):
                group["ids"].append(obj.id)
                break
        else:
            containers.append({"bbox": obj.bbox, "ids": [obj.id]})
    seeds = [
        obj
        for obj in analysis.all_objects()
        if obj.bbox is not None and role(obj.id) in SEED_ROLES and obj.kind in VISUAL_KINDS
    ]
    edges = cv2.Canny(cv2.cvtColor(raster, cv2.COLOR_BGR2GRAY), 80, 160) > 0
    masked = text_mask(lines, edges.shape, scale)
    visible_seeds = []
    for seed in seeds:
        if seed.kind != "image":
            visible_seeds.append(seed)
            continue
        if outside_page_share(seed, page) > OUTSIDE_PAGE_SHARE:
            diagnostics.append(
                f"Image {seed.id[:12]} lies largely outside the page; visible extent unknown,"
                " not a figure seed"
            )
            continue
        extent, density = raster_extent(seed, edges, masked, scale, page)
        over = [
            line
            for line in lines
            if not line.blank and line.visible and seed.bbox.contains_center(line.bbox)
        ]
        if (extent is None or density <= BACKDROP_EDGES) and len(over) >= BACKDROP_LINES:
            diagnostics.append(
                f"Image {seed.id[:12]} is a flat backdrop under {len(over)} text lines;"
                " not a figure seed"
            )
            continue
        if extent is None:
            continue
        if not same_box(extent, seed.bbox, tolerance=1.0):
            diagnostics.append(f"Image {seed.id[:12]} trimmed to its textured extent")
        visible_seeds.append(seed.model_copy(update={"bbox": extent}))
    seeds = visible_seeds
    for group in containers:
        inside = [
            seed
            for seed in seeds
            if group["bbox"].contains_center(seed.bbox) and seed.id not in members
        ]
        figure_area = sum(overlap_area(seed.bbox, group["bbox"]) for seed in inside)
        group["figure_share"] = min(1.0, figure_area / max(1.0, area(group["bbox"])))
        texts = [
            line for line in lines if not line.blank and group["bbox"].contains_center(line.bbox)
        ]
        labels = sum(short_label(line, native.page.store) for line in texts)
        # A figure panel holds artwork with at most short labels, not running text.
        group["panel"] = group["figure_share"] >= 0.15 and labels >= 0.7 * len(texts)
    # Transparency: a container whose fill matches its parent ground is only a frame.
    for group in containers:
        parents = [
            other
            for other in containers
            if other is not group
            and contains(other["bbox"], group["bbox"])
            and area(other["bbox"]) > area(group["bbox"])
        ]
        inner = sample(raster, scale, group["bbox"])
        if parents:
            parent = min(parents, key=lambda other: area(other["bbox"]))
            ground = sample(raster, scale, parent["bbox"])
        else:
            ground = ring(raster, scale, group["bbox"])
        difference = (
            None if inner is None or ground is None else float(np.max(np.abs(inner - ground)) / 255)
        )
        group["ground_difference"] = difference
        group["transparent"] = difference is not None and difference <= 0.04
        if group["transparent"]:
            diagnostics.append(
                f"Container {group['ids'][0][:12]} matches its ground; treated as a frame"
            )

    # Figure clustering: seeds, figure panels and unresolved local artwork as connectors.
    def candidate(obj):
        if obj.bbox is None or obj.kind not in VISUAL_KINDS or obj.id in members:
            return False
        record = roles.get(obj.id)
        if record is None or record.role != "unknown":
            return False
        if area(obj.bbox) / page_area >= 0.05 or not content.contains_center(obj.bbox):
            # Connectors are local artwork; page-scale strokes would chain unrelated content.
            return False
        if obj.bbox.x1 - obj.bbox.x0 > 0.5 * page.width:
            return False
        width = obj.bbox.x1 - obj.bbox.x0
        height = max(0.01, obj.bbox.y1 - obj.bbox.y0)
        if obj.fill is not None and width / page.width > 0.7 and width / height > 5:
            return False
        if line_like(obj, page):
            return False
        overlapping = record.features.get("text_overlap_count") or 0
        # Filled shapes carrying text are label bars or boxes, not artwork connectors.
        return overlapping == 0 if obj.fill is not None else overlapping <= 2

    items = [seed for seed in seeds if seed.id not in members]
    items += [
        {"panel": group} for group in containers if group["panel"] and not group["transparent"]
    ]
    connectors = [obj for obj in analysis.all_objects() if candidate(obj)]
    entries = [*items, *connectors]

    def entry_box(entry):
        return entry["panel"]["bbox"] if isinstance(entry, dict) else entry.bbox

    gap = 0.02 * min(page.width, page.height)
    parent = list(range(len(entries)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    shapes = [to_shape(entry_box(entry)) for entry in entries]
    tree = STRtree(shapes)
    for i in range(len(entries)):
        for j in tree.query(shapes[i], predicate="dwithin", distance=gap):
            j = int(j)
            if j > i:
                a, b = find(i), find(j)
                if a != b:
                    parent[max(a, b)] = min(a, b)
    clusters = {}
    for i, entry in enumerate(entries):
        cluster = clusters.setdefault(find(i), Cluster(members=[]))
        cluster.members.append(entry)
        if i < len(items):
            cluster.seeds += 1
        elif entry.fill is not None:
            cluster.filled += 1
    blocks = []
    figure_boxes = []
    for cluster in clusters.values():
        boxes = [entry_box(entry) for entry in cluster.members]
        bounds = clip_to(union(boxes), content)
        if bounds is None:
            continue
        if edge_strip(bounds, content, lines):
            diagnostics.append(
                f"Narrow text-free artwork along the content edge at x={bounds.x0:.0f}-"
                f"{bounds.x1:.0f} is page decoration, not a figure"
            )
            continue
        ids = sorted(
            oid
            for entry in cluster.members
            for oid in (entry["panel"]["ids"] if isinstance(entry, dict) else [entry.id])
        )
        if cluster.seeds:
            confidence, reasons = 0.82, ["Step 3 figure parts, images or figure panels"]
            if len(cluster.members) > cluster.seeds:
                reasons.append("Adjacent unresolved artwork joined as connectors")
        elif (
            len(cluster.members) >= 4
            and cluster.filled >= 2
            and area(bounds) / page_area >= 0.002
            and min(bounds.x1 - bounds.x0, bounds.y1 - bounds.y0) >= 2 * typical_size
        ):
            confidence = 0.72
            reasons = ["Cluster of unresolved filled vector primitives without body text"]
        else:
            continue
        figure_boxes.append(bounds)
        blocks.append(
            VisualBlock(
                id=stable_id("figure", *ids),
                kind="figure",
                bbox=bounds,
                object_ids=ids,
                confidence=confidence,
                reasons=reasons,
                features={"members": len(ids), "seeds": cluster.seeds},
            )
        )
    # Merge figures whose boxes overlap; one visual unit must not split its labels.
    merged = True
    while merged:
        merged = False
        for i, first in enumerate(blocks):
            for second in blocks[i + 1 :]:
                if overlap_area(first.bbox, second.bbox) > 0:
                    ids = sorted({*first.object_ids, *second.object_ids})
                    combined = first.model_copy(
                        update={
                            "id": stable_id("figure", *ids),
                            "bbox": union([first.bbox, second.bbox]),
                            "object_ids": ids,
                            "confidence": max(first.confidence, second.confidence),
                            "reasons": sorted({*first.reasons, *second.reasons}),
                        }
                    )
                    blocks = [b for b in blocks if b not in (first, second)] + [combined]
                    merged = True
                    break
            if merged:
                break

    # Tables: unresolved ruled grids with several text lines in their cells.
    fragments = []
    for obj in analysis.all_objects():
        if obj.bbox is None or role(obj.id) != "unknown" or obj.id in members:
            continue
        if not contains(content, obj.bbox) or area(obj.bbox) / page_area >= 0.3:
            # Crop/registration frames and page-size outlines are not tables.
            continue
        if any(contains(b.bbox, obj.bbox) for b in blocks if b.kind == "figure"):
            continue
        parts = [objects[m] for m in obj.member_ids] if obj.kind == "compound" else [obj]
        horizontal = vertical = 0
        for part in parts:
            for item in part.path_items:
                c = item.coordinates
                if item.operator == "l" and len(c) >= 4:
                    if abs(c[1] - c[3]) < 0.5 and abs(c[0] - c[2]) >= 8:
                        horizontal += 1
                    elif abs(c[0] - c[2]) < 0.5 and abs(c[1] - c[3]) >= 8:
                        vertical += 1
                elif item.operator == "re":
                    horizontal += 2
                    vertical += 2
        inside = [
            line
            for line in lines
            if not line.blank and expand(obj.bbox, 2).contains_center(line.bbox)
        ]
        if horizontal >= 3 and vertical >= 2 and len(inside) >= 3:
            blocks.append(
                VisualBlock(
                    id=stable_id("table", obj.id),
                    kind="table",
                    bbox=obj.bbox,
                    object_ids=[obj.id],
                    confidence=0.74,
                    reasons=["Ruled grid of horizontal and vertical strokes around text lines"],
                    features={"horizontal_rules": horizontal, "vertical_rules": vertical},
                )
            )
        elif horizontal >= 1 and vertical >= 2 and inside:
            # Too few rules to stand alone (a header strip); it may continue a table.
            fragments.append(
                VisualBlock(
                    id=stable_id("table", obj.id),
                    kind="table",
                    bbox=obj.bbox,
                    object_ids=[obj.id],
                    confidence=0.74,
                    reasons=["Ruled grid fragment continuing a table"],
                    features={"horizontal_rules": horizontal, "vertical_rules": vertical},
                )
            )
    blocks = merge_grids(blocks, objects, typical_size, fragments)
    figures = [b for b in blocks if b.kind == "figure"]
    ruled = [b for b in blocks if b.kind == "table"]
    candidates = [
        line
        for line in lines
        if line.horizontal
        and not line.blank
        and line.visible
        and line.inside_content
        and not any(contains(f.bbox, line.bbox) for f in figures)
        and not any(contains(t.bbox, line.bbox) for t in ruled)
    ]
    body = page_body_style(lines, native.page.store)
    blocks += aligned_blocks(aligned_tables(candidates, native.page.store, body))
    for group in containers:
        if group["transparent"]:
            continue
        if group["panel"] or any(contains(f.bbox, group["bbox"]) for f in figures):
            continue
        if any(contains(t.bbox, group["bbox"]) for t in blocks if t.kind == "table"):
            continue
        blocks.append(
            VisualBlock(
                id=stable_id("callout", *sorted(group["ids"])),
                kind="callout",
                bbox=group["bbox"],
                object_ids=sorted(group["ids"]),
                confidence=0.85,
                reasons=["Step 3 container: filled box distinct from its ground behind text"],
                features={"ground_difference": group["ground_difference"]},
            )
        )
    for obj in analysis.all_objects():
        if obj.bbox is None or obj.kind != "drawing" or role(obj.id) == "background":
            continue
        if any(contains(b.bbox, obj.bbox) for b in blocks if b.kind in {"figure", "table"}):
            continue
        width = obj.bbox.x1 - obj.bbox.x0
        height = max(0.01, obj.bbox.y1 - obj.bbox.y0)
        # Zero-thickness strokes have no area; test intersection by extent instead.
        if (
            obj.bbox.x1 < content.x0
            or obj.bbox.x0 > content.x1
            or obj.bbox.y1 < content.y0
            or obj.bbox.y0 > content.y1
        ):
            continue
        clipped = BBox(
            x0=max(obj.bbox.x0, content.x0),
            y0=max(obj.bbox.y0, content.y0),
            x1=min(obj.bbox.x1, content.x1),
            y1=min(obj.bbox.y1, content.y1),
        )
        orientation = line_like(obj, page)
        if orientation and content.contains_center(obj.bbox):
            blocks.append(
                VisualBlock(
                    id=stable_id("rule", obj.id),
                    kind="rule",
                    bbox=obj.bbox,
                    object_ids=[obj.id],
                    confidence=0.8,
                    reasons=[f"Thin {orientation} rule"],
                    features={"orientation": orientation},
                )
            )
        elif (
            role(obj.id) == "unknown"
            and obj.fill is not None
            and width / page.width > 0.7
            and width / height > 5
        ):
            blocks.append(
                VisualBlock(
                    id=stable_id("banner", obj.id),
                    kind="banner",
                    bbox=clipped,
                    object_ids=[obj.id],
                    confidence=0.7,
                    reasons=["Broad filled band across the page; obstacle only, never a region"],
                )
            )
    return sorted(blocks, key=lambda b: (b.kind, b.id)), diagnostics


def aligned_blocks(found):
    blocks = []
    for table in found:
        x0, y0, x1, y1 = table.bbox
        blocks.append(
            VisualBlock(
                id=stable_id("table", "aligned", *sorted(table.line_ids)),
                kind="table",
                bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                confidence=0.7,
                reasons=table.reasons,
                features={
                    "rows": table.rows,
                    "columns": table.columns,
                    "numeric_columns": table.numeric_columns,
                    "ruled": False,
                },
            )
        )
    return blocks


def merge_grids(blocks, objects, font_unit, fragments=()):
    """Ruled grids sharing column rules within a row height of each other are one table.

    Fragments (ruled strips too sparse to be tables alone) join a table they continue and
    are otherwise dropped.
    """
    tables = [b for b in blocks if b.kind == "table"]
    others = [b for b in blocks if b.kind != "table"]
    pending = list(fragments)

    def profile(block):
        verticals, horizontals = [], []
        for oid in block.object_ids:
            v, h = grid_profile(objects[oid], objects)
            verticals += v
            horizontals += h
        return sorted(verticals), sorted(horizontals)

    merged = True
    while merged:
        merged = False
        for i, first in enumerate(tables):
            for second in tables[i + 1 :]:
                if not same_grid(
                    first.bbox, profile(first), second.bbox, profile(second), font_unit
                ):
                    continue
                ids = sorted({*first.object_ids, *second.object_ids})
                combined = first.model_copy(
                    update={
                        "id": stable_id("table", *ids),
                        "bbox": union([first.bbox, second.bbox]),
                        "object_ids": ids,
                        "reasons": sorted(
                            {
                                *first.reasons,
                                *second.reasons,
                                "Grids sharing column rules within one row height are one table",
                            }
                        ),
                        "features": {
                            "horizontal_rules": first.features.get("horizontal_rules", 0)
                            + second.features.get("horizontal_rules", 0),
                            "vertical_rules": first.features.get("vertical_rules", 0)
                            + second.features.get("vertical_rules", 0),
                            "grids": first.features.get("grids", 1)
                            + second.features.get("grids", 1),
                        },
                    }
                )
                tables = [t for t in tables if t not in (first, second)] + [combined]
                merged = True
                break
            if merged:
                break
        if merged:
            continue
        for fragment in pending:
            host = next(
                (
                    t
                    for t in tables
                    # A fragment continues a table beside it; a frame around a table does not.
                    if not contains(fragment.bbox, t.bbox)
                    and same_grid(t.bbox, profile(t), fragment.bbox, profile(fragment), font_unit)
                ),
                None,
            )
            if host is not None:
                pending.remove(fragment)
                tables = [t for t in tables if t is not host] + [host]
                tables[-1] = host.model_copy(
                    update={
                        "id": stable_id("table", *sorted({*host.object_ids, *fragment.object_ids})),
                        "bbox": union([host.bbox, fragment.bbox]),
                        "object_ids": sorted({*host.object_ids, *fragment.object_ids}),
                        "reasons": sorted(
                            {
                                *host.reasons,
                                "Grids sharing column rules within one row height are one table",
                            }
                        ),
                    }
                )
                merged = True
                break
    return others + tables


def short_label(line, store):
    text = "".join(store.spans[sid].raw_text for sid in line.span_ids).strip()
    return len(text) <= 30 and len(TOKEN.findall(text)) <= 4
