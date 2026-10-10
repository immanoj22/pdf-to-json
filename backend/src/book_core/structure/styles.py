"""Book-relative style evidence: the body style, coarse style groups and their ranks.

No absolute size is used. The body style is the character-weighted mode of the book's running
text (main-flow paragraph units). Every unit's size is expressed as a ratio to the body size,
and units fall into coarse style groups of (size step, weight, case): the size step is the
ratio on a logarithmic scale of SIZE_STEP (about 12% per step), weight is bold or regular, and
case is upper or mixed. Colour is deliberately not part of a group (books recolour headings by
section) but colour contrast with the body remains separate evidence. Groups are ranked by
prominence: size step, then weight, then case.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

SIZE_STEP = 1.12


def body_style(pages):
    sizes, colors, families, bold = Counter(), Counter(), Counter(), Counter()
    for page in pages:
        for unit in page["units"]:
            if unit["kind"] != "paragraph" or unit["stream"] != "main":
                continue
            weight = unit["letters"]
            sizes[round(unit["size"] * 2) / 2] += weight
            colors[unit["color"]] += weight
            families[unit["family"]] += weight
            bold[unit["bold"] >= 0.5] += weight
    if not sizes:  # no running text at all: fall back to every text unit
        for page in pages:
            for unit in page["units"]:
                sizes[round(unit["size"] * 2) / 2] += unit["letters"]
                colors[unit["color"]] += unit["letters"]
                families[unit["family"]] += unit["letters"]
                bold[unit["bold"] >= 0.5] += unit["letters"]
    if not sizes:
        return {"size": 10.0, "color": 0, "family": "", "bold": False, "letters": 0}
    return {
        "size": sizes.most_common(1)[0][0],
        "color": colors.most_common(1)[0][0],
        "family": families.most_common(1)[0][0],
        "bold": bold.most_common(1)[0][0],
        "letters": sum(sizes.values()),
    }


def size_step(size, body):
    return round(math.log(max(size, 0.1) / max(body["size"], 0.1)) / math.log(SIZE_STEP))


def case_of(unit):
    caps = unit.get("caps")
    return "upper" if caps is not None and caps >= 0.8 and unit["letters"] >= 3 else "mixed"


def group_of(unit, body):
    weight = "bold" if unit["bold"] >= 0.5 else "regular"
    return f"{size_step(unit['size'], body)}:{weight}:{case_of(unit)}"


def prominence(group):
    step, weight, case = group.split(":")
    return int(step), weight == "bold", case == "upper"


def group_table(units, body):
    """Book table of style groups among ``units`` (count, pages, mean size ratio)."""
    table = defaultdict(lambda: {"units": 0, "pages": set(), "ratio": 0.0})
    for unit in units:
        row = table[group_of(unit, body)]
        row["units"] += 1
        row["pages"].add(unit["page"])
        row["ratio"] += unit["size"] / body["size"]
    return {
        group: {"units": row["units"], "pages": len(row["pages"]),
                "ratio": round(row["ratio"] / row["units"], 3)}
        for group, row in table.items()
    }  # fmt: skip
