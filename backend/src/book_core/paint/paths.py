"""Exact inscribed cores for supported closed fill paths."""

from collections import Counter


def core(items):
    if len(items) == 1 and items[0][0] == "re":
        return tuple(items[0][1])
    if len(items) != 8 or Counter(i[0] for i in items) != {"c": 4, "l": 4}:
        return None
    endpoints = []
    lines = []
    curves = []
    for item in items:
        points = [tuple(p) for p in item[1:]]
        if item[0] == "l":
            lines.append(points)
        else:
            curves.append(points)
        endpoints.extend([points[0], points[-1]])
    xs = [p[0] for p in endpoints]
    ys = [p[1] for p in endpoints]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    sides = {}
    for a, b in lines:
        if a[0] == b[0] and a[0] in (xmin, xmax):
            sides["left" if a[0] == xmin else "right"] = sorted([a[1], b[1]])
        elif a[1] == b[1] and a[1] in (ymin, ymax):
            sides["top" if a[1] == ymin else "bottom"] = sorted([a[0], b[0]])
        else:
            return None
    if len(sides) != 4:
        return None
    box = (
        max(sides["top"][0], sides["bottom"][0]),
        max(sides["left"][0], sides["right"][0]),
        min(sides["top"][1], sides["bottom"][1]),
        min(sides["left"][1], sides["right"][1]),
    )
    if box[0] >= box[2] or box[1] >= box[3]:
        return None
    # Four cubic corner paths stay in disjoint corner rectangles. No sampled
    # approximation or path bounding-box-as-fill assumption is used.
    corners = set()
    for pts in curves:
        matching = []
        for ix, (lo, hi) in enumerate(((xmin, box[0]), (box[2], xmax))):
            for iy, (bot, top) in enumerate(((ymin, box[1]), (box[3], ymax))):
                if all(lo <= x <= hi and bot <= y <= top for x, y in pts):
                    matching.append((ix, iy))
        if len(matching) != 1:
            return None
        corners.add(matching[0])
    if len(corners) != 4:
        return None
    # Require one continuous closed contour, allowing arbitrary start/direction.
    if any(tuple(a[-1]) != tuple(b[1]) for a, b in zip(items, items[1:] + items[:1], strict=True)):
        return None
    return box
