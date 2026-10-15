"""Vector glyph evidence: filled outlines at text scale whose shapes recur in the book.

Some producers draw every equation character as a filled path instead of text. A drawn glyph
has no Unicode, so it is recognised by evidence only: it is a filled outline about the size of
the page's text, it holds no text, and its scale-free shape recurs in the book (a drawn font
repeats the same outline for every occurrence of a character, at any size). Thin filled or
stroked horizontal bars at text scale are rule candidates (fraction bars, overlines).

No font, producer, book or page is named; sizes are relative to the page's median text size.
"""

import hashlib
from collections import Counter

from book_core.model.common import BBox

# Heights relative to the page's median text size.
GLYPH_MIN_HEIGHT = 0.12
GLYPH_MAX_HEIGHT = 2.5
TALL_GLYPH_MAX_HEIGHT = 6.0  # tall delimiters/radicals, only when narrow
TALL_GLYPH_MAX_WIDTH = 1.0
GLYPH_MAX_WIDTH = 4.0
BAR_MAX_HEIGHT = 0.2
BAR_MIN_WIDTH = 0.3
SIGNATURE_DIGITS = 2
MIN_RECURRENCE = 2  # pages on which a shape occurs
# Share of a shape's occurrences written next to other glyphs: drawn characters of a font are
# set in words and expressions, while icons and markers stand alone.
SOCIAL_SHARE = 0.3


def _height(box: BBox) -> float:
    return box.y1 - box.y0


def _width(box: BBox) -> float:
    return box.x1 - box.x0


def shape_signature(obj) -> str | None:
    """Scale- and position-free outline identity: path operators and coordinates relative to
    the box origin, divided by the box height and rounded."""
    box = obj.bbox
    height = _height(box)
    if height <= 0 or not obj.path_items:
        return None
    parts = []
    for item in obj.path_items:
        values = item.coordinates
        points = [
            (
                round((values[i] - box.x0) / height, SIGNATURE_DIGITS),
                round((values[i + 1] - box.y0) / height, SIGNATURE_DIGITS),
            )
            for i in range(0, len(values) - 1, 2)
        ]
        parts.append(f"{item.operator}{points}")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:20]


def is_bar(obj, size: float) -> bool:
    """A thin horizontal filled rectangle or stroked line at text scale."""
    if obj.kind != "drawing" or obj.bbox is None:
        return False
    box = obj.bbox
    operators = [item.operator for item in obj.path_items]
    thin = _height(box) <= BAR_MAX_HEIGHT * size and _width(box) >= BAR_MIN_WIDTH * size
    simple = operators in (["re"], ["l"], ["qu"]) or (
        len(operators) <= 5 and set(operators) <= {"l"}
    )
    painted = obj.fill is not None or obj.stroke is not None
    return thin and simple and painted


def is_glyph_shape(obj, size: float, text_boxes) -> bool:
    """A filled outline at text scale that holds no text."""
    if obj.kind != "drawing" or obj.bbox is None or obj.fill is None:
        return False
    box = obj.bbox
    height, width = _height(box), _width(box)
    if height < GLYPH_MIN_HEIGHT * size or width <= 0:
        return False
    regular = height <= GLYPH_MAX_HEIGHT * size and width <= GLYPH_MAX_WIDTH * size
    tall = height <= TALL_GLYPH_MAX_HEIGHT * size and width <= TALL_GLYPH_MAX_WIDTH * size
    if not (regular or tall):
        return False
    operators = [item.operator for item in obj.path_items]
    outline = "c" in operators or len(operators) >= 4
    if not outline:
        return False
    return not any(box.contains_center(other) for other in text_boxes)


def page_glyphs(native, size: float, text_boxes) -> tuple[list, list, dict]:
    """(glyph objects, bar objects, {object id: signature}) of one page."""
    glyphs, bars, signatures = [], [], {}
    for obj in native.objects:
        if is_bar(obj, size):
            bars.append(obj)
        elif is_glyph_shape(obj, size, text_boxes):
            signature = shape_signature(obj)
            if signature is not None:
                glyphs.append(obj)
                signatures[obj.id] = signature
    return glyphs, bars, signatures


def recurring(counts: Counter) -> frozenset:
    return frozenset(s for s, n in counts.items() if n >= MIN_RECURRENCE)


def accepted(counts: Counter, joined: Counter, pages: dict) -> frozenset:
    """Shapes that recur on several pages and are often set beside a different glyph, as the
    characters of a drawn font are (book-level evidence); ornaments repeat beside copies of
    themselves, and a logo or cover drawing stays on one page."""
    return frozenset(
        s
        for s, n in counts.items()
        if len(pages.get(s, ())) >= MIN_RECURRENCE and joined.get(s, 0) >= SOCIAL_SHARE * n
    )
