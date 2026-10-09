"""Reading-order review overlay.

Main flow: numbered lines joined by blue arrows (thick at lane/band transitions). Floats: one
colour per kind, a box around the stream's lines, label ``F<n> kind @<anchor>``, and a dashed
arrow from the anchor line. Furniture is grey. Low-confidence decisions are red (``!``).
"""

from pathlib import Path

import cv2
import numpy as np

from book_core.objects.roles import raster_array

MAIN = (200, 90, 20)
FLOAT_COLORS = {
    "sidebar": (0, 140, 255),
    "callout": (0, 190, 230),
    "figure": (190, 60, 200),
    "table": (120, 60, 20),
    "card": (40, 150, 40),
    "credit": (80, 140, 140),
    "note": (90, 90, 160),
}
SIDE_COLORS = {
    "furniture": (130, 130, 130),
    "artifact": (190, 190, 190),
    "invisible": (0, 100, 255),
}
REVIEW = (0, 0, 255)
TRANSITIONS = {"next_lane_in_band", "next_band", "continues_across_column"}


def _union(boxes):
    return (
        min(b.x0 for b in boxes),
        min(b.y0 for b in boxes),
        max(b.x1 for b in boxes),
        max(b.y1 for b in boxes),
    )


def _dashed(canvas, a, b, color):
    length = max(1, int(np.hypot(b[0] - a[0], b[1] - a[1]) / 8))
    for i in range(0, length, 2):
        p = (a[0] + (b[0] - a[0]) * i // length, a[1] + (b[1] - a[1]) * i // length)
        q = (a[0] + (b[0] - a[0]) * (i + 1) // length, a[1] + (b[1] - a[1]) * (i + 1) // length)
        cv2.line(canvas, p, q, color, 2, cv2.LINE_AA)


def render_reading_order_overlay(raster, layout, order, output: Path):
    canvas = cv2.addWeighted(
        raster_array(raster), 0.55, np.full_like(raster_array(raster), 255), 0.45, 0
    )
    sx, sy = raster.width / raster.page_width, raster.height / raster.page_height
    lines = {line.id: line for line in layout.lines}

    def point(x, y):
        return round(x * sx), round(y * sy)

    def centre(lid):
        box = lines[lid].bbox
        return point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)

    def start(lid):
        box = lines[lid].bbox
        return point(box.x0, (box.y0 + box.y1) / 2)

    flagged = {s for d in order.decisions if d.review_required for s in d.subject_ids}
    kinds = {(e.source, e.target): e.kind for e in order.edges}
    for stream in order.streams:
        if stream.kind in SIDE_COLORS:
            for lid in stream.line_ids:
                box = lines[lid].bbox
                cv2.rectangle(
                    canvas,
                    point(box.x0, box.y0),
                    point(box.x1, box.y1),
                    SIDE_COLORS[stream.kind],
                    1,
                )
    main = order.main.line_ids
    for a, b in zip(main, main[1:], strict=False):
        thick = kinds.get((a, b)) in TRANSITIONS
        color = REVIEW if (a in flagged and b in flagged) else MAIN
        if thick:
            cv2.arrowedLine(canvas, centre(a), centre(b), color, 3, cv2.LINE_AA, tipLength=0.04)
        else:
            cv2.arrowedLine(canvas, start(a), start(b), color, 1, cv2.LINE_AA, tipLength=0.2)
    for lid in flagged & set(lines):
        box = lines[lid].bbox
        cv2.rectangle(canvas, point(box.x0, box.y0), point(box.x1, box.y1), REVIEW, 2)
    for number, lid in enumerate(main, 1):
        x, y = start(lid)
        color = REVIEW if lid in flagged else MAIN
        label = f"{number}{'!' if lid in flagged else ''}"
        cv2.putText(
            canvas,
            label,
            (max(0, x - 8 * len(label) - 4), y + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            color,
            1,
            cv2.LINE_AA,
        )
    floats = [s for s in order.streams if s.anchor is not None]
    floats.sort(key=lambda s: (s.anchor.position, s.anchor.order))
    for number, stream in enumerate(floats, 1):
        color = FLOAT_COLORS[stream.kind]
        if stream.anchor.review_required:
            color = REVIEW
        boxes = [lines[lid].bbox for lid in stream.line_ids]
        regions = {r.id: r for r in layout.regions}
        boxes += [regions[r].bbox for r in stream.region_ids if r in regions]
        if not boxes:
            continue
        x0, y0, x1, y1 = _union(boxes)
        p0, p1 = point(x0, y0), point(x1, y1)
        cv2.rectangle(canvas, p0, p1, color, 2, cv2.LINE_AA)
        for i, lid in enumerate(stream.line_ids[:-1]):
            cv2.line(canvas, centre(lid), centre(stream.line_ids[i + 1]), color, 1, cv2.LINE_AA)
        anchor = stream.anchor
        at = "start" if anchor.after_line_id is None else str(anchor.position + 1)
        label = f"F{number} {stream.kind} @{at}{'!' if anchor.review_required else ''}"
        cv2.putText(
            canvas,
            label,
            (p0[0] + 2, max(12, p0[1] - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )
        target = centre(anchor.after_line_id) if anchor.after_line_id else (8, 8)
        cv2.circle(canvas, target, 6, color, 2, cv2.LINE_AA)
        _dashed(canvas, target, p0, color)
    legend = np.full((canvas.shape[0], 330, 3), 255, dtype=np.uint8)
    rows = [
        ("main flow: numbered lines, arrows", MAIN),
        ("thick arrow: lane/band transition", MAIN),
        *[(f"float: {k}", c) for k, c in FLOAT_COLORS.items()],
        *[(f"side stream: {k}", c) for k, c in SIDE_COLORS.items()],
        ("red / '!': low confidence, review", REVIEW),
        ("dashed: float -> anchor (circle)", (0, 0, 0)),
    ]
    for i, (text, color) in enumerate(rows):
        y = 24 + i * 22
        cv2.rectangle(legend, (10, y - 10), (24, y + 3), color, -1)
        cv2.putText(legend, text, (32, y + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    notes = [
        f"page {order.page}",
        f"main lines: {len(main)}",
        f"floats: {len(floats)}",
        f"low-confidence decisions: {sum(d.review_required for d in order.decisions)}",
        "F numbers: float order in the flow",
        "@n: read after main line n",
    ]
    for i, note in enumerate(notes):
        cv2.putText(legend, note, (10, 340 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", np.concatenate([canvas, legend], axis=1))
    if not ok:
        raise ValueError("PNG encoding failed")
    output.write_bytes(encoded.tobytes())
    return {"output": str(output), "main_lines": len(main), "floats": len(floats)}
