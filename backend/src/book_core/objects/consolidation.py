"""Geometric paint-run consolidation. No figure or region semantics."""

from collections import defaultdict

from book_core.extraction.fingerprints import stable_id
from book_core.model.common import BBox
from book_core.objects.models import CompoundVisual
from book_core.objects.spatial import SpatialIndex


def consolidate(native):
    page = native.page.geometry
    area = page.width * page.height
    candidates = []
    for obj in native.objects:
        if obj.bbox is None or obj.paint_run is None:
            continue
        size = max(0, obj.bbox.x1 - obj.bbox.x0) * max(0, obj.bbox.y1 - obj.bbox.y0)
        if obj.kind == "shading" or (
            obj.kind == "drawing" and len(obj.path_items) <= 2 and size / area < 0.025
        ):
            candidates.append(obj)
    index = SpatialIndex(candidates)
    parent = list(range(len(candidates)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def style(obj):
        return (
            obj.kind,
            obj.paint_run,
            tuple(obj.fill or ()),
            tuple(obj.stroke or ()),
            obj.fill_opacity,
            obj.stroke_opacity,
            obj.opacity,
            obj.blend_mode,
        )

    # Tolerance scales with the physical page; no fixture coordinates or fixed columns.
    gap = min(page.width, page.height) * 0.0015
    for i, obj in enumerate(candidates):
        for j in index.query(obj.bbox, distance=gap):
            if j <= i or style(obj) != style(candidates[j]):
                continue
            a, b = find(i), find(j)
            if a != b:
                parent[b] = a
    groups = defaultdict(list)
    for i, obj in enumerate(candidates):
        groups[find(i)].append(obj)
    result = []
    for members in groups.values():
        if len(members) < 2:
            continue
        ids = sorted(obj.id for obj in members)
        bounds = BBox(
            x0=min(obj.bbox.x0 for obj in members),
            y0=min(obj.bbox.y0 for obj in members),
            x1=max(obj.bbox.x1 for obj in members),
            y1=max(obj.bbox.y1 for obj in members),
        )
        result.append(
            CompoundVisual(
                id=stable_id("compound", *ids),
                bbox=bounds,
                native_bbox=bounds,
                source_page=page.page,
                member_ids=ids,
                paint_run=members[0].paint_run,
                paint_sequences=sorted({seq for obj in members for seq in obj.paint_sequences}),
                provenance=members[0].provenance.model_copy(update={"method": "derived"}),
                opacity=members[0].opacity,
                fill=members[0].fill,
                stroke=members[0].stroke,
                evidence_notes=[
                    "Adjacent same-style primitives within one uninterrupted paint run"
                ],
            )
        )
    return sorted(result, key=lambda obj: obj.id)
