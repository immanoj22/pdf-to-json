"""Compare layout proposals with reviewed band/column gold. No combined accuracy score.

Bands match by vertical overlap within the same scope. Certain gold bands must match exactly
one found band with the same column count; found bands that match no gold band are extra
unless they overlap an explicitly uncertain gold band. Region agreement is reported only.
"""

from book_core.model.common import BBox

BAND_IOU = 0.5
SCOPE_IOU = 0.8


def box(values):
    return (
        values
        if isinstance(values, BBox)
        else BBox(x0=values[0], y0=values[1], x1=values[2], y1=values[3])
    )


def area(b):
    return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)


def iou(a, b):
    inter = area(
        BBox(
            x0=max(a.x0, b.x0),
            y0=max(a.y0, b.y0),
            x1=max(max(a.x0, b.x0), min(a.x1, b.x1)),
            y1=max(max(a.y0, b.y0), min(a.y1, b.y1)),
        )
    )
    union = area(a) + area(b) - inter
    return inter / union if union > 0 else 0.0


def y_iou(a0, a1, b0, b1):
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    return inter / union if union > 0 else 0.0


def map_scopes(layout, gold):
    """Gold scope id -> found scope id (page scope, or the callout with the closest box)."""
    page = next(scope.id for scope in layout.scopes if scope.kind == "page")
    mapping = {}
    for scope in gold["scopes"]:
        if scope["kind"] == "page":
            mapping[scope["id"]] = page
            continue
        target = box(scope["bbox"])
        candidates = [
            (iou(found.bbox, target), found.id)
            for found in layout.scopes
            if found.kind == "callout"
        ]
        best = max(candidates, default=(0.0, None))
        mapping[scope["id"]] = best[1] if best[0] >= SCOPE_IOU else None
    return mapping


def evaluate(layout, gold):
    scopes = map_scopes(layout, gold)
    annotated = {found for found in scopes.values() if found is not None}
    found_bands = [band for band in layout.bands if band.scope_id in annotated]
    used = set()
    bands = []
    for item in gold["bands"]:
        scope = scopes.get(item["scope"])
        candidates = sorted(
            (
                (y_iou(item["y0"], item["y1"], band.bbox.y0, band.bbox.y1), band)
                for band in found_bands
                if band.scope_id == scope
            ),
            key=lambda pair: -pair[0],
        )
        overlap, match = candidates[0] if candidates else (0.0, None)
        matched = match is not None and overlap >= BAND_IOU
        if matched:
            used.add(match.id)
        bands.append(
            {
                "id": item["id"],
                "scope": item["scope"],
                "uncertain": item["uncertain"],
                "expected_y": [item["y0"], item["y1"]],
                "expected_columns": item["columns"],
                "expected_lanes": item["lanes"],
                "found_y": [round(match.bbox.y0, 1), round(match.bbox.y1, 1)] if matched else None,
                "found_columns": match.column_count if matched else None,
                "found_lanes": [lane.kind for lane in match.lanes] if matched else None,
                "found_confidence": round(match.confidence, 3) if matched else None,
                "y_iou": round(overlap, 3),
                "band_matched": matched,
                "columns_match": matched and match.column_count == item["columns"],
            }
        )
    uncertain = [b for b in gold["bands"] if b["uncertain"]]
    extra = []
    for band in found_bands:
        if band.id in used:
            continue
        excused = any(
            scopes.get(item["scope"]) == band.scope_id
            and y_iou(item["y0"], item["y1"], band.bbox.y0, band.bbox.y1) > 0
            for item in uncertain
        )
        extra.append(
            {
                "y": [round(band.bbox.y0, 1), round(band.bbox.y1, 1)],
                "columns": band.column_count,
                "excused_by_uncertain_gold": excused,
            }
        )
    regions = []
    for item in gold["regions"]:
        target = box(item["bbox"])
        expanded = BBox(x0=target.x0 - 2, y0=target.y0 - 2, x1=target.x1 + 2, y1=target.y1 + 2)
        weights = {}
        for region in layout.regions:
            size = max(area(region.bbox), 1.0)
            inside = area(
                BBox(
                    x0=max(region.bbox.x0, expanded.x0),
                    y0=max(region.bbox.y0, expanded.y0),
                    x1=max(max(region.bbox.x0, expanded.x0), min(region.bbox.x1, expanded.x1)),
                    y1=max(max(region.bbox.y0, expanded.y0), min(region.bbox.y1, expanded.y1)),
                )
            )
            if area(region.bbox) == 0:
                cx, cy = (
                    (region.bbox.x0 + region.bbox.x1) / 2,
                    (region.bbox.y0 + region.bbox.y1) / 2,
                )
                inside = (
                    size
                    if expanded.x0 <= cx <= expanded.x1 and expanded.y0 <= cy <= expanded.y1
                    else 0
                )
            if inside >= 0.5 * size:
                weights[region.type] = weights.get(region.type, 0.0) + size
        found = max(weights, key=weights.get) if weights else None
        # A container region with children inside it is judged by its own best-fitting box.
        closest = max(layout.regions, key=lambda region: iou(region.bbox, target), default=None)
        if closest is not None and iou(closest.bbox, target) >= 0.6:
            found = closest.type
        regions.append(
            {
                "expected": item["type"],
                "found": found,
                "agree": found == item["type"],
                "uncertain": item["uncertain"],
                "note": item["note"],
            }
        )
    certain = [b for b in bands if not b["uncertain"]]
    certain_regions = [r for r in regions if not r["uncertain"]]
    return {
        "fixture": gold["fixture"],
        "human_approved": gold["human_approved"],
        "bands_expected": len(gold["bands"]),
        "bands_expected_certain": len(certain),
        "bands_found_in_annotated_scopes": len(found_bands),
        "certain_bands_matched": sum(b["band_matched"] for b in certain),
        "certain_column_counts_matched": sum(b["columns_match"] for b in certain),
        "unexcused_extra_bands": sum(not e["excused_by_uncertain_gold"] for e in extra),
        "regions_certain": len(certain_regions),
        "regions_agree_certain": sum(r["agree"] for r in certain_regions),
        "regions_uncertain": len(regions) - len(certain_regions),
        "unannotated_scope_bands": sum(band.scope_id not in annotated for band in layout.bands),
        "bands": bands,
        "extra_bands": extra,
        "regions": regions,
    }


def passes(result):
    return (
        result["certain_bands_matched"] == result["bands_expected_certain"]
        and result["certain_column_counts_matched"] == result["bands_expected_certain"]
        and result["unexcused_extra_bands"] == 0
    )
