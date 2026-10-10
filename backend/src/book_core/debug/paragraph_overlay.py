"""Paragraph review overlay.

Each unit is boxed and numbered in reading order (``P<n>``; ``H`` heading candidates, ``L``
list candidates, ``C`` captions; figure/table text thin grey). Joins across columns are drawn
as arrows from the last line of one lane to the first line of the next; a join onto the next
page is marked ``-> p<n>`` and one from the previous page ``p<n> ->``. Hyphen decisions are
marked at the line end (``J`` join, ``K`` keep, ``S`` soft). Flagged units are red. Furniture
lines stay grey, unnumbered.
"""

from pathlib import Path

import cv2
import numpy as np

from book_core.objects.roles import raster_array

COLORS = {
    "paragraph": (200, 90, 20),
    "heading_candidate": (40, 140, 40),
    "list_item_candidate": (160, 60, 160),
    "caption": (0, 140, 220),
    "figure_text": (150, 150, 150),
    "table_text": (150, 150, 150),
}
TAGS = {"paragraph": "P", "heading_candidate": "H", "list_item_candidate": "L", "caption": "C"}
REVIEW = (0, 0, 255)
HYPHEN = {"join": "J", "keep": "K", "soft_join": "S"}


def render_paragraph_overlay(raster, layout, result, output: Path, incoming=(), outgoing=()):
    """``incoming``/``outgoing``: [(unit id, other page)] cross-page joins of this page."""
    base = raster_array(raster)
    canvas = cv2.addWeighted(base, 0.55, np.full_like(base, 255), 0.45, 0)
    sx, sy = raster.width / raster.page_width, raster.height / raster.page_height
    lines = {line.id: line for line in layout.lines}

    def box(ids):
        b = [lines[i].bbox for i in ids]
        return (
            (round(min(x.x0 for x in b) * sx) - 2, round(min(x.y0 for x in b) * sy) - 2),
            (round(max(x.x1 for x in b) * sx) + 2, round(max(x.y1 for x in b) * sy) + 2),
        )

    def centre(lid, end=False):
        b = lines[lid].bbox
        return round((b.x1 if end else b.x0) * sx), round((b.y0 + b.y1) / 2 * sy)

    incoming, outgoing = dict(incoming), dict(outgoing)
    counts, number, flagged = {}, 0, 0
    for unit in result.units:
        color = COLORS.get(unit.kind)
        if color is None:
            continue
        counts[unit.kind] = counts.get(unit.kind, 0) + 1
        # One box per column segment (a unit continued into the next column has two).
        segments, current = [], [unit.line_ids[0]]
        for join in unit.joins:
            if join.kind == "column":
                segments.append(current)
                current = []
            current.append(join.next_line_id)
        segments.append(current)
        thin = unit.kind in {"figure_text", "table_text"}
        for segment in segments:
            p, q = box(segment)
            cv2.rectangle(canvas, p, q, REVIEW if unit.review_required else color, 1 if thin else 2)
        a, b = box(segments[0])
        flagged += unit.review_required
        if not thin:
            number += 1
            label = f"{TAGS.get(unit.kind, 'P')}{number}"
            if unit.id in incoming:
                label = f"p{incoming[unit.id]}-> " + label
            if unit.id in outgoing:
                label += f" ->p{outgoing[unit.id]}"
            cv2.putText(
                canvas, label, (a[0], max(12, a[1] - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                REVIEW if unit.review_required else color, 1, cv2.LINE_AA,
            )  # fmt: skip
        for join in unit.joins:
            if join.kind == "column":
                p, q = centre(join.previous_line_id, end=True), centre(join.next_line_id)
                cv2.arrowedLine(canvas, p, q, color, 2, cv2.LINE_AA, tipLength=0.03)
            if join.hyphen is not None:
                x, y = centre(join.previous_line_id, end=True)
                cv2.putText(
                    canvas, HYPHEN[join.hyphen.choice], (x + 3, y + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA,
                )  # fmt: skip
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), canvas):
        raise OSError(f"Could not write {output}")
    return {"output": str(output), "units": counts, "flagged": flagged}
