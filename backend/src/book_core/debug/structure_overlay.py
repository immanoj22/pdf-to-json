"""Structure review overlay.

Headings are boxed and tagged ``L<level> <role>`` (thick, coloured by role family); display
titles and labels are thin grey boxes tagged ``D`` and ``L`` (styled, not headings). A band
across the top shows the page's zone and section kind. Low-confidence decisions are red.
"""

from pathlib import Path

import cv2
import numpy as np

from book_core.objects.roles import raster_array

ROLE_COLORS = {
    "book_title": (120, 0, 120),
    "front_section_title": (160, 80, 0),
    "rear_section_title": (160, 80, 0),
    "part": (0, 90, 200),
    "unit": (0, 90, 200),
    "chapter": (0, 130, 0),
    "lesson": (0, 130, 0),
    "section": (0, 150, 150),
    "subsection": (0, 150, 150),
    "sidebar_title": (200, 120, 0),
    "feature_title": (200, 120, 0),
}
ZONE_COLORS = {"front": (210, 170, 120), "body": (150, 210, 150), "rear": (140, 160, 220)}
REVIEW = (0, 0, 255)
STYLED = (140, 140, 140)


def render_structure_overlay(raster, layout, units_of, structure, page, output: Path):
    """``units_of``: {unit id: [line ids]} for this page's units."""
    base = raster_array(raster)
    canvas = cv2.addWeighted(base, 0.55, np.full_like(base, 255), 0.45, 0)
    sx, sy = raster.width / raster.page_width, raster.height / raster.page_height
    lines = {line.id: line for line in layout.lines}

    def box(unit_ids):
        ids = [lid for u in unit_ids for lid in units_of.get(u, []) if lid in lines]
        if not ids:
            return None
        b = [lines[i].bbox for i in ids]
        return (
            (round(min(x.x0 for x in b) * sx) - 3, round(min(x.y0 for x in b) * sy) - 3),
            (round(max(x.x1 for x in b) * sx) + 3, round(max(x.y1 for x in b) * sy) + 3),
        )

    def label(text, at, color, scale=0.45):
        cv2.putText(canvas, text, (at[0], max(12, at[1] - 4)), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (255, 255, 255), 3, cv2.LINE_AA)  # fmt: skip
        cv2.putText(canvas, text, (at[0], max(12, at[1] - 4)), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    color, 1, cv2.LINE_AA)  # fmt: skip

    counts = {"headings": 0, "styled": 0, "flagged": 0}
    for item in structure.styled:
        if item.page != page:
            continue
        found = box(item.unit_ids)
        if found is None:
            continue
        color = REVIEW if item.review_required else STYLED
        cv2.rectangle(canvas, *found, color, 1)
        label("D" if item.role == "display_title" else "L", found[0], color, 0.4)
        counts["styled"] += 1
        counts["flagged"] += item.review_required
    for heading in structure.headings:
        if heading.page != page:
            continue
        found = box(heading.unit_ids)
        if found is None:
            continue
        color = REVIEW if heading.review_required else ROLE_COLORS.get(heading.role, (0, 0, 0))
        cv2.rectangle(canvas, *found, color, 2)
        tag = f"L{heading.level} {heading.role}" + (" run-in" if heading.run_in else "")
        label(tag, found[0], color)
        counts["headings"] += 1
        counts["flagged"] += heading.review_required
    zone = next(z for z in structure.page_zones if z.page == page)
    band = ZONE_COLORS[zone.zone]
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 22), band, -1)
    text = f"p{page}  {zone.zone} / {zone.section_kind}  ({zone.confidence:.2f})"
    cv2.putText(canvas, text, (8, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                REVIEW if zone.review_required else (0, 0, 0), 1, cv2.LINE_AA)  # fmt: skip
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), canvas):
        raise OSError(f"Could not write {output}")
    return {"output": str(output), **counts, "zone": zone.zone, "section": zone.section_kind}
