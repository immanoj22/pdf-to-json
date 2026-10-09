"""Furniture review overlay: classes coloured, the folio with its fitted label, flagged lines.

Each furniture line is filled in its class colour and tagged (``RH`` running head, ``RF``
running foot, ``F`` folio with its fitted label, ``PM`` production mark, ``RB`` repeated box).
Flagged lines get a red frame and ``!``. A banner shows the page marker (label, source,
confidence) and a legend. Content lines are left untouched.
"""

from pathlib import Path

import cv2
import numpy as np

from book_core.objects.roles import raster_array

COLORS = {
    "running_head": (200, 120, 0),
    "running_foot": (160, 60, 160),
    "folio": (0, 150, 0),
    "production_mark": (110, 110, 110),
    "repeated_box": (0, 160, 230),
}
TAGS = {
    "running_head": "RH",
    "running_foot": "RF",
    "folio": "F",
    "production_mark": "PM",
    "repeated_box": "RB",
}
REVIEW = (0, 0, 255)


def render_furniture_overlay(raster, layout, result, output: Path):
    """``result`` is a PageFurniture. Returns counts for the overlay index."""
    base = raster_array(raster)
    margin = 54
    page = cv2.addWeighted(base, 0.6, np.full_like(base, 255), 0.4, 0)
    canvas = np.full((page.shape[0] + margin, page.shape[1], 3), 255, np.uint8)
    canvas[margin:] = page
    sx, sy = raster.width / raster.page_width, raster.height / raster.page_height
    lines = {line.id: line for line in layout.lines}

    def box(line):
        b = line.bbox
        return (round(b.x0 * sx), round(b.y0 * sy) + margin), (
            round(b.x1 * sx),
            round(b.y1 * sy) + margin,
        )

    overlay = canvas.copy()
    counts = {}
    flagged = 0
    for role in result.roles:
        line = lines[role.line_id]
        if role.role in COLORS:
            counts[role.role] = counts.get(role.role, 0) + 1
            a, b = box(line)
            cv2.rectangle(overlay, a, b, COLORS[role.role], -1)
    canvas = cv2.addWeighted(overlay, 0.35, canvas, 0.65, 0)
    marker = result.marker
    for role in result.roles:
        line = lines[role.line_id]
        a, b = box(line)
        if role.role in COLORS:
            cv2.rectangle(canvas, a, b, COLORS[role.role], 2)
            tag = TAGS[role.role]
            if role.role == "folio":
                tag = f"F={marker.label}" if marker.label else "F"
            cv2.putText(
                canvas,
                tag,
                (a[0], max(margin + 12, a[1] - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                COLORS[role.role],
                2,
                cv2.LINE_AA,
            )
        if role.review_required:
            flagged += 1
            cv2.rectangle(canvas, (a[0] - 3, a[1] - 3), (b[0] + 3, b[1] + 3), REVIEW, 2)
            cv2.putText(canvas, "!", (b[0] + 5, b[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, REVIEW, 2)
    banner = (
        f"p{result.page}  label {marker.label!r}  {marker.source}  "
        f"conf {marker.confidence:.2f}" + ("  REVIEW" if marker.review_required else "")
    )
    cv2.putText(canvas, banner, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    x = 8
    for role, color in COLORS.items():
        cv2.rectangle(canvas, (x, 30), (x + 14, 44), color, -1)
        cv2.putText(canvas, TAGS[role], (x + 18, 43), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        x += 60
    cv2.rectangle(canvas, (x, 30), (x + 14, 44), REVIEW, 2)
    cv2.putText(canvas, "flag", (x + 18, 43), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), canvas):
        raise OSError(f"Could not write {output}")
    return {"output": str(output), "roles": counts, "flagged": flagged}
