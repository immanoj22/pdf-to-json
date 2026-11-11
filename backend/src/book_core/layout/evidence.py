"""Script-agnostic text evidence shared by layout rules and invariant checks.

Counts use Unicode letter/mark/number runs, never spaces or Latin assumptions. A run of a
script written without spaces counts by characters (one token per CJK-width pair), so a
long unspaced line is not mistaken for a short label. Geometry is in line-height or font
units; nothing here depends on page coordinates.
"""

from statistics import median

import regex

TOKEN = regex.compile(r"[\p{L}\p{M}\p{N}]+")
DIGIT = regex.compile(r"\p{Nd}")
LETTER = regex.compile(r"\p{L}")
ROMAN = regex.compile(r"^[ivxlcdm]+$", regex.IGNORECASE)
ABBREVIATION = 4  # letters of a locator qualifier ending in a period ("pág.")
# A page label: a short letter prefix joined to digits ("HT19", "A-12"), one locator.
PAGE_LABEL = regex.compile(
    rf"(?<![\p{{L}}\p{{M}}\p{{N}}])\p{{L}}{{1,{ABBREVIATION}}}[-\u2010\u2011]?\p{{Nd}}+"
    rf"(?![\p{{L}}\p{{M}}\p{{N}}])"
)
# Cells made only of digits, signs, separators, brackets and symbols (numeric table data).
NUMERIC_CELL = regex.compile(r"^[\p{Nd}\p{P}\p{S}\p{Zs}]+$")
UNSPACED = regex.compile(r"[\p{Han}\p{Hiragana}\p{Katakana}\p{Thai}\p{Lao}\p{Khmer}\p{Myanmar}]")
BOLD_FLAG = 16
# A strip at most this share of its frame's width, within EDGE_TOUCH of an edge, is an
# edge strip.
EDGE_STRIP_WIDTH = 0.10
EDGE_TOUCH = 0.05
PARAGRAPH_TOKENS = 5


def line_text(line, store):
    return "".join(store.spans[sid].raw_text for sid in line.span_ids).strip()


def token_count(text):
    count = 0
    for run in TOKEN.findall(text):
        unspaced = len(UNSPACED.findall(run))
        count += 1 + (unspaced // 2 if unspaced else 0)
    return count


def style_of(lines, store):
    """Dominant (font, size, colour, bold) by character weight; None for empty input."""
    weights = {}
    for line in lines:
        for sid in line.span_ids:
            span = store.spans[sid]
            count = len(span.raw_text.strip())
            if count:
                key = (span.font, round(span.size, 1), span.color, bool(span.flags & BOLD_FLAG))
                weights[key] = weights.get(key, 0) + count
    return max(weights, key=weights.get) if weights else None


def text_lines(lines):
    return [
        line
        for line in lines
        if not line.blank and line.visible and line.inside_content and line.font_size > 0
    ]


def page_body_style(lines, store):
    """Body style of the page from visible horizontal text; rotated text does not vote."""
    return style_of([line for line in text_lines(lines) if line.horizontal], store)


def numeric_cell(text):
    text = text.strip()
    return bool(text) and bool(DIGIT.search(text)) and bool(NUMERIC_CELL.match(text))


def short_reference(text):
    """A locator-like token group: at most three tokens, at least one digit."""
    return bool(DIGIT.search(text)) and token_count(text) <= 3


def locator_cell(text):
    """Locators only (page numbers, ranges, roman folios, short lettered page labels such as
    "HT19"), perhaps with a short abbreviated qualifier ("p. 45", "pág. 137"): no term or
    word beside them.

    An index or matching entry ("variable 7", "6. Malignant lesions") is text with a
    locator, not a locator cell; only a cell of bare locators can be a locator column.
    """
    if not short_reference(text):
        return False
    text = PAGE_LABEL.sub("0", text)
    for match in TOKEN.finditer(text):
        token = match.group()
        if DIGIT.search(token) and not LETTER.search(token) or ROMAN.match(token):
            continue
        abbreviated = text[match.end() : match.end() + 1] == "."
        if not (abbreviated and len(token) <= ABBREVIATION and not DIGIT.search(token)):
            return False
    return True


def word_count(text):
    """Letter-bearing tokens only: numbers and unit pairs do not make a sentence."""
    count = 0
    for run in TOKEN.findall(text):
        if not LETTER.search(run):
            continue
        unspaced = len(UNSPACED.findall(run))
        count += 1 + (unspaced // 2 if unspaced else 0)
    return count


def _stacked(line, other, store, style):
    """`other` sits directly above or below `line`, overlapping it, in the same style."""
    height = max(0.01, line.bbox.y1 - line.bbox.y0)
    gap = max(other.bbox.y0 - line.bbox.y1, line.bbox.y0 - other.bbox.y1)
    if gap > 0.6 * height or gap < -0.5 * height:
        return False
    overlap = min(line.bbox.x1, other.bbox.x1) - max(line.bbox.x0, other.bbox.x0)
    shorter = min(line.bbox.x1 - line.bbox.x0, other.bbox.x1 - other.bbox.x0)
    return overlap >= 0.5 * shorter and style_of([other], store) == style


def wrapped_sequence(line, others, store, style):
    """Part of >= 3 stacked same-style lines sharing an edge, or a justified pair."""
    font_unit = max(0.01, line.font_size)
    candidates = [o for o in others if o is not line and not o.blank]
    for edge in ("x0", "x1"):
        chain, frontier = {id(line)}, [line]
        while frontier:
            current = frontier.pop()
            for other in candidates:
                if id(other) in chain:
                    continue
                if abs(getattr(other.bbox, edge) - getattr(current.bbox, edge)) > font_unit:
                    continue
                if _stacked(current, other, store, style):
                    chain.add(id(other))
                    frontier.append(other)
        if len(chain) >= 3:
            return True
    for other in candidates:
        if (
            abs(other.bbox.x0 - line.bbox.x0) <= font_unit
            and abs(other.bbox.x1 - line.bbox.x1) <= font_unit
            and _stacked(line, other, store, style)
            and word_count(line_text(other, store)) >= PARAGRAPH_TOKENS
        ):
            return True
    return False


# A line that opens with an enumerator ("33.", "(2)", "a)") and runs to this many words is a
# numbered item (a question, a step), not a label: figure keys ("1. Cerebral hemisphere") are
# a few words. It is item text whatever its weight, alone on its line or not.
NUMBERED_PROSE_TOKENS = 8
# The marker is followed by a space: "33. A ...", "a) ...", "(2) ..." but not "(t)Getty Images"
# (a credit key), "S.C. ..." (an abbreviation) or "(1)Smith, J. ..." (a citation).
_ENUMERATED = regex.compile(r"^\s*[(\[]?(?:\p{N}{1,3}|\p{L})[.)\]]\s+\S")


def numbered_item(line, store):
    """A long line opening with an enumerator: a question stem or a numbered step."""
    text = line_text(line, store)
    return word_count(text) >= NUMBERED_PROSE_TOKENS and bool(_ENUMERATED.match(text))


_NUMBERED_LINE = regex.compile(r"^\s*\p{N}{1,3}[.)]\s+\S")
_OPTION_MARK = regex.compile(r"^\s*[(\[]?(\p{L})[.)\]]")


def question_frame(lines, store):
    """The lines of a frame hold a numbered stem (of any length) and at least two options
    marked with consecutive letters (any script): a question set around its picture."""
    texts = [line_text(line, store) for line in lines if not line.blank]
    if not any(_NUMBERED_LINE.match(text) for text in texts):
        return False
    marks = {m[1].casefold() for text in texts if (m := _OPTION_MARK.match(text))}
    return any(chr(ord(c) + 1) in marks for c in marks)


def paragraph_like(line, store, body_style, neighbours):
    """Several words AND (the page body style OR a wrapped/justified sequence), or a long
    numbered item."""
    if line.blank or word_count(line_text(line, store)) < PARAGRAPH_TOKENS:
        return False
    if numbered_item(line, store):
        return True
    style = style_of([line], store)
    if body_style is not None and style == body_style:
        return True
    return wrapped_sequence(line, neighbours, store, style)


ROTATED_STRUCTURE_LINES = 3
CREDIT_ISOLATION = 2.0
CREDIT_FIGURE_REACH = 4.0


def box_gap(a, b):
    """Smallest distance between two boxes (0 when they touch or overlap)."""
    dx = max(b.x0 - a.x1, a.x0 - b.x1, 0.0)
    dy = max(b.y0 - a.y1, a.y0 - b.y1, 0.0)
    return (dx * dx + dy * dy) ** 0.5


def rotation_key(line):
    return round(line.rotation) % 360


def isolated_rotated(line, lines):
    """No other line of the same rotation within a couple of font sizes."""
    reach = CREDIT_ISOLATION * max(line.font_size, 0.01)
    key = rotation_key(line)
    return not any(
        other is not line
        and not other.blank
        and not other.horizontal
        and rotation_key(other) == key
        and box_gap(line.bbox, other.bbox) <= reach
        for other in lines
    )


def near_figure_edge(line, figure_boxes):
    reach = CREDIT_FIGURE_REACH * max(line.font_size, 0.01)
    return any(box_gap(line.bbox, box) <= reach for box in figure_boxes)


def credit_like(line, lines, figure_boxes, body_size):
    """Rotated photo credit: small, isolated, and beside a figure edge."""
    small = body_size is None or line.font_size <= 1.05 * body_size
    return small and isolated_rotated(line, lines) and near_figure_edge(line, figure_boxes)


def median_font(lines, default=10.0):
    sizes = [line.font_size for line in lines if not line.blank and line.font_size > 0]
    return median(sizes) if sizes else default
