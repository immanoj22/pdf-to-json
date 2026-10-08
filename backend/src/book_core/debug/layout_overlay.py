"""Layout review overlay: bands, gutters, lanes, typed regions, confidence and review flags."""

from pathlib import Path

import cv2
import numpy as np

from book_core.layout.frames import from_frame, to_frame
from book_core.model.common import BBox
from book_core.objects.roles import raster_array

REGION_COLORS = {
    "title_candidate": (40, 40, 200),
    "heading_candidate": (30, 110, 230),
    "main_text": (60, 160, 60),
    "sidebar": (160, 120, 0),
    "callout": (0, 170, 230),
    "figure": (190, 60, 200),
    "caption_candidate": (200, 90, 140),
    "table_candidate": (120, 60, 20),
    "footnote_candidate": (90, 90, 160),
    "header_footer_candidate": (110, 110, 110),
    "page_number_candidate": (20, 20, 20),
    "credit_candidate": (80, 140, 140),
    "artifact_candidate": (170, 170, 170),
    "unknown": (0, 100, 255),
}
BAND_TINTS = [(255, 235, 200), (220, 245, 220)]
GUTTER_COLOR = (230, 60, 230)
REVIEW_COLOR = (0, 0, 255)


def render_layout_overlay(raster, layout, output: Path):
    canvas = raster_array(raster)
    sx, sy = raster.width / raster.page_width, raster.height / raster.page_height

    def point(x, y):
        return round(x * sx), round(y * sy)

    page_scope = next(scope.id for scope in layout.scopes if scope.kind == "page")
    # Rotated scopes measure gutters along their own reading frame; draw them on the page.
    rotation = {scope.id: scope.rotation for scope in layout.scopes if scope.kind == "rotated"}
    # Bands: alternating translucent tints; nested-scope bands use a dashed outline.
    tint = canvas.copy()
    for i, band in enumerate(
        sorted(layout.bands, key=lambda b: (b.scope_id != page_scope, b.bbox.y0))
    ):
        p0, p1 = point(band.bbox.x0, band.bbox.y0), point(band.bbox.x1, band.bbox.y1)
        if band.scope_id == page_scope:
            cv2.rectangle(tint, p0, p1, BAND_TINTS[i % 2], -1)
    canvas = cv2.addWeighted(tint, 0.35, canvas, 0.65, 0)
    for band in layout.bands:
        p0, p1 = point(band.bbox.x0, band.bbox.y0), point(band.bbox.x1, band.bbox.y1)
        nested = band.scope_id != page_scope
        color = REVIEW_COLOR if band.review_required else (200, 120, 0)
        cv2.rectangle(canvas, p0, p1, color, 1 if nested else 2, cv2.LINE_AA)
        lanes = "/".join(lane.kind[:3] for lane in band.lanes)
        flag = " !" if band.review_required else ""
        prefix = "R" if band.scope_id in rotation else ("S" if nested else "B")
        label = f"{prefix} cols={band.column_count} [{lanes}] {band.confidence:.2f}{flag}"
        cv2.putText(
            canvas,
            label,
            (p0[0] + 2, max(10, p0[1] - 3)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            color,
            1,
            cv2.LINE_AA,
        )
        angle = rotation.get(band.scope_id)
        frame = to_frame(band.bbox, angle) if angle is not None else band.bbox
        for gutter in band.gutters:
            box = BBox(
                x0=gutter.x0,
                y0=max(gutter.y0, frame.y0),
                x1=gutter.x1,
                y1=max(max(gutter.y0, frame.y0), min(gutter.y1, frame.y1)),
            )
            if angle is not None:
                box = from_frame(box, angle)
            g0, g1 = point(box.x0, box.y0), point(box.x1, box.y1)
            layer = canvas.copy()
            cv2.rectangle(layer, g0, g1, GUTTER_COLOR, -1)
            canvas = cv2.addWeighted(layer, 0.35, canvas, 0.65, 0)
    for region in layout.regions:
        color = REGION_COLORS[region.type]
        p0, p1 = point(region.bbox.x0, region.bbox.y0), point(region.bbox.x1, region.bbox.y1)
        thickness = 2 if region.type in {"figure", "callout", "table_candidate"} else 1
        cv2.rectangle(canvas, p0, p1, color, thickness, cv2.LINE_AA)
        if region.review_required:
            cv2.rectangle(canvas, p0, p1, REVIEW_COLOR, 1, cv2.LINE_4)
        name = region.type.replace("_candidate", "")
        flag = "!" if region.review_required else ""
        label = f"{name} {region.confidence:.2f}{flag}"
        cv2.putText(
            canvas,
            label,
            (p0[0] + 2, min(canvas.shape[0] - 2, p0[1] + 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.32,
            color,
            1,
            cv2.LINE_AA,
        )
    legend = np.full((canvas.shape[0], 300, 3), 255, dtype=np.uint8)
    cv2.putText(legend, "Region types", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    counts = {}
    for region in layout.regions:
        counts[region.type] = counts.get(region.type, 0) + 1
    for i, (name, color) in enumerate(REGION_COLORS.items()):
        y = 40 + i * 22
        cv2.rectangle(legend, (10, y), (24, y + 13), color, -1)
        cv2.putText(
            legend,
            f"{name} ({counts.get(name, 0)})",
            (32, y + 11),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (0, 0, 0),
            1,
        )
    page_columns = [b.column_count for b in layout.bands if b.scope_id == page_scope]
    notes = [
        "tinted rows: page bands",
        "thin boxes: bands inside callouts (S) or rotated frames (R)",
        "magenta: gutters",
        "red outline / '!': review required",
        f"bands: {len(layout.bands)}",
        f"columns per page band: {page_columns}",
        f"review flags: {len(layout.review_flags)}",
        "proposals only; no reading order",
    ]
    for i, note in enumerate(notes):
        cv2.putText(legend, note, (10, 380 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 0, 0), 1)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", np.concatenate([canvas, legend], axis=1))
    if not ok:
        raise ValueError("PNG encoding failed")
    output.write_bytes(encoded.tobytes())
    output.with_suffix(".json").write_text(layout.model_dump_json(), encoding="utf-8")
    return {
        "output": str(output),
        "bands": len(layout.bands),
        "regions": len(layout.regions),
        "review_flags": len(layout.review_flags),
    }
