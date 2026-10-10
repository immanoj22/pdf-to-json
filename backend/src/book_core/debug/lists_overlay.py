"""Lists review overlay (Step 11).

Each list item or entry is boxed in its list's colour and labelled ``<tag><n> L<level>``
(``B`` bulleted, ``N`` numbered, ``A`` lettered, ``U`` unmarked, ``D`` definition, ``G``
glossary, ``X`` index, ``R`` bibliography, ``T`` contents); the marker and the term are
underlined; index locators resolved to a physical page are marked ``→p<n>``. Other text units
are thin grey boxes. A glossary page shows its entry order as numbered arrows between entry
starts. Flagged units are red; a cross-page entry link is marked ``p<n>->`` / ``->p<n>``.
"""

from pathlib import Path

import cv2
import numpy as np

from book_core.objects.roles import raster_array

TAGS = {"bulleted": "B", "numbered": "N", "lettered": "A", "unmarked": "U",
        "definition": "D", "glossary": "G", "index": "X", "bibliography": "R",
        "contents": "T"}  # fmt: skip
PALETTE = [(200, 90, 20), (40, 140, 40), (160, 60, 160), (0, 140, 220), (120, 120, 0),
           (0, 90, 200), (150, 40, 90)]  # fmt: skip
REVIEW = (0, 0, 255)
GREY = (160, 160, 160)


def render_lists_overlay(raster, layout, page_lists, lists, output: Path, incoming=(),
                         outgoing=()):  # fmt: skip
    """``lists``: the book's StructuredLists; ``incoming``/``outgoing``: [(unit id, page)]."""
    base = raster_array(raster)
    canvas = cv2.addWeighted(base, 0.55, np.full_like(base, 255), 0.45, 0)
    sx, sy = raster.width / raster.page_width, raster.height / raster.page_height
    lines = {line.id: line for line in layout.lines}
    spans = {sid: line for line in layout.lines for sid in line.span_ids}
    by_id = {lst.id: lst for lst in lists}
    colour_of = {}
    incoming, outgoing = dict(incoming), dict(outgoing)

    def box(ids):
        b = [lines[i].bbox for i in ids]
        return (
            (round(min(x.x0 for x in b) * sx) - 2, round(min(x.y0 for x in b) * sy) - 2),
            (round(max(x.x1 for x in b) * sx) + 2, round(max(x.y1 for x in b) * sy) + 2),
        )

    def underline(refs, colour):
        for ref in refs:
            line = spans.get(ref.span_id)
            if line is None:
                continue
            b = line.bbox
            y = round(b.y1 * sy) + 1
            cv2.line(canvas, (round(b.x0 * sx), y), (round(b.x1 * sx), y), colour, 1)

    counts, numbers, flagged, starts = {}, {}, 0, []
    for unit in page_lists.units:
        if unit.list_id is None:
            if unit.kind in {"paragraph", "heading_candidate", "caption", "list_item_candidate"}:
                p, q = box(unit.line_ids)
                cv2.rectangle(canvas, p, q, GREY, 1)
            continue
        lst = by_id.get(unit.list_id)
        kind = lst.kind if lst else "unmarked"
        colour = colour_of.setdefault(unit.list_id, PALETTE[len(colour_of) % len(PALETTE)])
        numbers[unit.list_id] = numbers.get(unit.list_id, 0) + 1
        counts[kind] = counts.get(kind, 0) + 1
        flagged += unit.review_required
        shown = REVIEW if unit.review_required else colour
        p, q = box(unit.line_ids)
        cv2.rectangle(canvas, p, q, shown, 2)
        label = f"{TAGS.get(kind, '?')}{numbers[unit.list_id]} L{unit.level or 1}"
        if unit.id in incoming:
            label = f"p{incoming[unit.id]}-> " + label
        if unit.id in outgoing:
            label += f" ->p{outgoing[unit.id]}"
        targets = [loc.target_page for loc in unit.locators if loc.target_page]
        if targets:
            label += " >p" + ",".join(str(t) for t in targets[:3])
        cv2.putText(canvas, label, (max(0, p[0] - 2), max(10, p[1] - 2)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, shown, 1, cv2.LINE_AA)  # fmt: skip
        if unit.marker is not None:
            underline(unit.marker.refs, (0, 0, 0))
        underline(unit.term, colour)
        starts.append((p, kind))
    if page_lists.order_changes:  # glossary entry order: arrows between entry starts
        entry_starts = [p for p, kind in starts if kind == "glossary"]
        for index, (a, b) in enumerate(zip(entry_starts, entry_starts[1:], strict=False)):
            cv2.arrowedLine(canvas, a, b, (0, 120, 255), 1, cv2.LINE_AA, tipLength=0.02)
            if index < 40:
                cv2.putText(
                    canvas,
                    str(index + 1),
                    (a[0] - 14, a[1] + 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.35,
                    (0, 120, 255),
                    1,
                    cv2.LINE_AA,
                )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), canvas):
        raise OSError(f"Could not write {output}")
    return {"output": str(output), "items": counts, "flagged": flagged}
