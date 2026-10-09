"""Reusable native object overlays with role, short stable ID and confidence."""

from pathlib import Path

import cv2
import numpy as np

from book_core.objects.roles import raster_array

COLORS = {
    "background": (230, 140, 20),
    "container": (0, 170, 230),
    "figure_part": (190, 60, 200),
    "decorative": (110, 110, 110),
    "scan_layer": (0, 190, 80),
    "repeated_artifact": (200, 170, 0),
    "content_image": (20, 40, 230),
    "unknown": (0, 100, 255),
    "text": (150, 150, 150),
}


def render_overlay(raster, analysis, output: Path, all_objects=False):
    canvas = raster_array(raster)
    records = {record.object_id: record for record in analysis.asset_ledger.records}
    members = {member for compound in analysis.compounds for member in compound.member_ids}
    sx, sy = raster.width / raster.page_width, raster.height / raster.page_height
    label_count = 0
    for obj in analysis.all_objects():
        if obj.bbox is None or obj.kind in {"clip", "group"}:
            continue
        decision = records.get(obj.id)
        if obj.kind == "unmatched_paint" and not all_objects:
            continue
        if obj.is_text and not all_objects:
            continue
        if (
            not all_objects
            and obj.kind == "drawing"
            and decision is not None
            and decision.role == "unknown"
        ):
            continue
        role = decision.role if decision else "text"
        color = COLORS[role]
        rect = obj.bbox
        p0, p1 = (
            (round(rect.x0 * sx), round(rect.y0 * sy)),
            (round(rect.x1 * sx), round(rect.y1 * sy)),
        )
        cv2.rectangle(canvas, p0, p1, color, 1 if obj.id in members or obj.is_text else 2)
        visible_area = (
            (rect.x1 - rect.x0) * (rect.y1 - rect.y0) / (raster.page_width * raster.page_height)
        )
        if all_objects or (
            obj.id not in members
            and visible_area > 0.001
            and (role != "unknown" or obj.kind in {"image", "shading", "compound"})
        ):
            confidence = f"{decision.confidence:.2f}" if decision else ""
            label = f"{role} {obj.id[:7]} {confidence}"
            y = max(12, p0[1] - 3)
            cv2.putText(
                canvas, label, (p0[0], y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA
            )
            label_count += 1
    legend = np.full((canvas.shape[0], 260, 3), 255, dtype=np.uint8)
    cv2.putText(legend, "Object roles", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    for i, (role, color) in enumerate(COLORS.items()):
        cv2.rectangle(legend, (10, 40 + i * 25), (25, 55 + i * 25), color, -1)
        cv2.putText(legend, role, (35, 53 + i * 25), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1)
    lines = [
        "thin: compound members",
        "state clips/groups: JSON",
        "all IDs/roles: sidecar",
        f"assets: {len(records)}",
        f"compounds: {len(analysis.compounds)}",
        f"unknown: {sum(r.role == 'unknown' for r in records.values())}",
        f"graph complete: {analysis.graph_complete}",
    ]
    for i, line in enumerate(lines):
        cv2.putText(legend, line, (10, 315 + i * 23), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 0, 0), 1)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", np.concatenate([canvas, legend], axis=1))
    if not ok:
        raise ValueError("PNG encoding failed")
    output.write_bytes(encoded.tobytes())
    output.with_suffix(".json").write_text(analysis.model_dump_json(), encoding="utf-8")
    return {
        "output": str(output),
        "asset_count": len(records),
        "label_count": label_count,
        "unknown_count": sum(r.role == "unknown" for r in records.values()),
    }
