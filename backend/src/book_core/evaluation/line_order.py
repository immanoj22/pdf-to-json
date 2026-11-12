"""Word order against the PDF's own line order.

The lossless check counts tokens, so text from two columns woven into one paragraph passes it:
every word is there, in the wrong place. This check compares the order of the lines a unit
(paragraph, list item, heading) is made of with the order the PDF stored them in. A unit read
from one column runs forward through the PDF lines, with at most one jump when the reading
order leaves the native order (the next column); a unit woven from two columns jumps back and
forth: its lines come from two runs of PDF lines taken alternately.

``native_lines``: {page: [line text, ...]} in the PDF's native order. ``units``: [(id, page,
text)] where text keeps the line breaks the unit was read with. Pure function: the reader of
the PDF is the caller's.
"""

from __future__ import annotations

import unicodedata

MIN_DESCENTS = 2  # back jumps in a unit's line sequence that mark a weave


def normal(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def native_positions(lines):
    """{normalised line: [native positions]}."""
    found = {}
    for position, text in enumerate(lines):
        found.setdefault(normal(text), []).append(position)
    return found


def sequence(text: str, positions: dict[str, list[int]]) -> list[int]:
    """The native position of each line of a unit (lines found nowhere are skipped); when a
    line occurs several times the first position after the previous one is taken."""
    out: list[int] = []
    for line in text.split("\n"):
        key = normal(line)
        if not key or key not in positions:
            continue
        options = positions[key]
        after = [p for p in options if not out or p > out[-1]]
        out.append(min(after) if after else options[0])
    return out


def descents(order: list[int]) -> int:
    return sum(b < a for a, b in zip(order, order[1:], strict=False))


def interleaved(order: list[int]) -> bool:
    """Back jumps twice or more: two runs of PDF lines taken alternately."""
    return descents(order) >= MIN_DESCENTS


def check(native_lines: dict[int, list[str]], units) -> list[dict]:
    """The units whose lines are woven from separate runs of the PDF's lines."""
    positions = {page: native_positions(lines) for page, lines in native_lines.items()}
    found = []
    for unit_id, page, text in units:
        if page not in positions or "\n" not in text:
            continue
        order = sequence(text, positions[page])
        if interleaved(order):
            found.append({"unit": unit_id, "page": page, "native_order": order,
                          "text": text[:120]})  # fmt: skip
    return found
