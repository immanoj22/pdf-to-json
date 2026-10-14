"""Spreads: one picture printed across two consecutive pages, found only from evidence.

Candidate: a figure on page n reaching the right content edge and a figure on page n+1
reaching the left content edge, overlapping vertically over most of their height. A
candidate is a spread only when the rendered pixels continue across the gutter: the
picture's last column on page n matches the first column on page n+1 about as well as
neighbouring columns inside each half match each other, and the edges are not blank.
"""

import numpy as np

EDGE_BLANK = 8.0  # intensity standard deviation (0-255) of a column with visible content
CONTINUITY = 3.0  # cross-gutter difference allowed, in units of the in-picture difference
CONTINUITY_FLOOR = 8.0  # intensity (0-255) for very smooth pictures


def candidates(drafts_by_page, contents, edge_share, overlap):
    """[(page, draft, next page, next draft, evidence)]."""
    found = []
    for number in sorted(drafts_by_page):
        following = drafts_by_page.get(number + 1)
        if not following:
            continue
        content, next_content = contents[number], contents[number + 1]
        reach = edge_share * (content.x1 - content.x0)
        next_reach = edge_share * (next_content.x1 - next_content.x0)
        for left in drafts_by_page[number]:
            a = left.region.bbox
            if a.x1 < content.x1 - reach:
                continue
            for right in following:
                b = right.region.bbox
                if b.x0 > next_content.x0 + next_reach:
                    continue
                shared = min(a.y1, b.y1) - max(a.y0, b.y0)
                smaller = min(a.y1 - a.y0, b.y1 - b.y0)
                if smaller <= 0 or shared / smaller < overlap:
                    continue
                found.append(
                    (
                        number,
                        left,
                        number + 1,
                        right,
                        {"vertical_overlap": round(shared / smaller, 4)},
                    )
                )
    return found


def continuous(left_rgb, left_box, right_rgb, right_box):
    """(continues?, evidence): pixel continuity across the gutter over the shared rows."""
    top, bottom = max(left_box.y0, right_box.y0), min(left_box.y1, right_box.y1)

    def rows(rgb, box):
        scale = rgb.shape[0] / max(1e-6, box.y1 - box.y0)
        start = int(round((top - box.y0) * scale))
        stop = max(start + 1, int(round((bottom - box.y0) * scale)))
        return rgb[start:stop].astype(np.float32)

    a, b = rows(left_rgb, left_box), rows(right_rgb, right_box)
    count = min(a.shape[0], b.shape[0])
    if count < 2 or a.shape[1] < 2 or b.shape[1] < 2:
        return False, {"reason": "too small"}
    a, b = a[:count], b[:count]
    edge_a, edge_b = a[:, -1], b[:, 0]
    across = float(np.mean(np.abs(edge_a - edge_b)))
    inside = float((np.mean(np.abs(a[:, -1] - a[:, -2])) + np.mean(np.abs(b[:, 0] - b[:, 1]))) / 2)
    texture = float(min(edge_a.std(), edge_b.std()))
    limit = max(CONTINUITY_FLOOR, CONTINUITY * inside)
    evidence = {
        "gutter_difference": round(across, 3),
        "in_picture_difference": round(inside, 3),
        "edge_texture": round(texture, 3),
    }
    return texture >= EDGE_BLANK and across <= limit, evidence
