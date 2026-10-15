"""Text equation evidence on one visual line: runs of operands joined by math operators.

Evidence is Unicode properties of the original text, span baselines and sizes, and font
program evidence (``fonts``); there is no list of words, fonts, books or code points. The
text itself is never changed and nothing is copied out of the span store: a run is a set of
character ranges.

A run is a maximal sequence of operand tokens (numbers, single letters or Greek letters,
optionally primed), math operators (Unicode Sm) and grouping punctuation, with no word of
two or more letters inside. It is equation evidence when an operator stands between two
operands (``x = 2``, ``p < .001``, ``F(1, 147) = 4.50``), when an operand carries a raised or
lowered script (``x²``, ``n₁``) — but not a word followed by a raised number, which is a note
reference — or when a span set in a math font contains a letter or operator.
"""

import unicodedata
from dataclasses import dataclass, field

import regex

TOKEN = regex.compile(
    r"(?P<number>\d+(?:[.,]\d+)*(?:\.\d+)?|\.\d+)"
    r"|(?P<word>[\p{L}\p{M}]{2,})"
    r"|(?P<letter>\p{L}\p{M}*['′″]*)"
    r"|(?P<script>[\u00b2\u00b3\u00b9\u2070-\u209f])"
    r"|(?P<operator>\p{Sm})"
    r"|(?P<group>[()\[\]{}|,;:/])"
    r"|(?P<space>\s+)"
    r"|(?P<other>.)"
)
# A raised/lowered span: smaller than the line's text and off its baseline.
SCRIPT_SIZE_RATIO = 0.85
SCRIPT_SHIFT_RATIO = 0.15
SHORT_NAME = 3  # letters of a named quantity right before a relation


@dataclass
class TextRun:
    """Character ranges of one run: [(span id, start, end)] in line order."""

    ranges: list[tuple[str, int, int]]
    signals: dict = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)
    whole_line: bool = False


def _category(character: str) -> str:
    return unicodedata.category(character)


def _script_greek(character: str) -> bool:
    return "GREEK" in unicodedata.name(character, "")


def line_characters(store, line, geometry):
    """[(span id, offset, character, size, raised/lowered)] in native order."""
    spans = [store.spans[sid] for sid in line.span_ids]
    base = max(spans, key=lambda s: (len(s.raw_text.strip()), s.size))
    base_size = base.size or line.font_size or 1.0
    origin = geometry.get(base.id)
    rows = []
    for span in spans:
        shifted = False
        own = geometry.get(span.id)
        if origin is not None and own is not None and span.size:
            # Offset across the line's own writing direction (any rotation).
            dx, dy = origin.direction
            length = (dx * dx + dy * dy) ** 0.5 or 1.0
            ox, oy = own.origin[0] - origin.origin[0], own.origin[1] - origin.origin[1]
            across = abs(-dy / length * ox + dx / length * oy)
            shifted = (
                span.size <= SCRIPT_SIZE_RATIO * base_size
                and across >= SCRIPT_SHIFT_RATIO * base_size
            )
        for offset, character in enumerate(span.raw_text):
            rows.append((span.id, offset, character, span.size, shifted))
    return rows


def line_runs(store, line, geometry, math_fonts) -> list[TextRun]:
    rows = line_characters(store, line, geometry)
    text = "".join(row[2] for row in rows)
    tokens = []
    for match in TOKEN.finditer(text):
        kind = match.lastgroup
        tokens.append((kind, match.start(), match.end()))
    # A dash right before a number, after an operator or opening bracket, is a sign
    # (``= –.30``); a dash between two numbers stays punctuation (``1914–1918``).
    for index, token in enumerate(tokens):
        if token[0] != "other" or unicodedata.category(text[token[1]]) != "Pd":
            continue
        after = text[token[2] : token[2] + 1]
        previous = [t for t in tokens[:index] if t[0] != "space"][-1:]
        opens = (
            not previous
            or previous[0][0] == "operator"
            or (previous[0][0] == "group" and text[previous[0][1]] in "([{")
        )
        if (after.isdigit() or after == ".") and opens:
            tokens[index] = ("operator", token[1], token[2])
    # A short word standing right before a relation is a named quantity (``SD = 3.1``).
    for index, token in enumerate(tokens):
        if token[0] != "word" or token[2] - token[1] > SHORT_NAME:
            continue
        rest = tokens[index + 1 :]
        if len(rest) < 4 or [t[0] for t in rest[:3]] != ["space", "operator", "space"]:
            continue
        operand = [t for t in rest[3:] if t[0] != "space"][:1]
        signed = operand and operand[0][0] == "operator" and len(rest) > 4
        if signed:
            operand = [t for t in rest[4:] if t[0] != "space"][:1]
        # Symmetric spacing and a number after the relation: ``SD = 3.1``, not ``is >35``.
        if _relation(text[rest[1][1]]) and operand and operand[0][0] == "number":
            tokens[index] = ("letter", token[1], token[2])
    runs, current = [], []

    def close():
        if current:
            runs.append(list(current))
            current.clear()

    for token in tokens:
        kind = token[0]
        if kind in {"word", "other"}:
            close()
            continue
        # An operand glued to a preceding word or mark (``Cronbach's``) is part of that word.
        if kind == "letter" and token[1] > 0 and not current and _glued(text, token[1]):
            continue
        # Two operands separated by a space only, with no operator, start a new run
        # (``1999 (n = 234)``): the earlier operand is not part of the expression.
        if (
            current
            and kind in {"number", "letter", "script"} | {"group"}
            and _new_term(current, token, text)
        ):
            close()
        current.append(token)
    close()
    result = []
    visible = sum(1 for c in text if not c.isspace())
    for tokens_of_run in runs:
        # Trim grouping punctuation and spaces at both ends.
        while tokens_of_run and tokens_of_run[0][0] in {"space", "group"}:
            if text[tokens_of_run[0][1]] in "([{" and len(tokens_of_run) > 1:
                break
            tokens_of_run = tokens_of_run[1:]
        while tokens_of_run and tokens_of_run[-1][0] in {"space", "group"}:
            if text[tokens_of_run[-1][1]] in ")]}" and len(tokens_of_run) > 1:
                break
            tokens_of_run = tokens_of_run[:-1]
        if not tokens_of_run:
            continue
        evidence = _evidence(tokens_of_run, text, rows, tokens, math_fonts, store)
        if not evidence["rules"]:
            continue
        start, end = tokens_of_run[0][1], tokens_of_run[-1][2]
        ranges = []
        for sid, offset, _character, _size, _shift in rows[start:end]:
            if ranges and ranges[-1][0] == sid and ranges[-1][2] == offset:
                ranges[-1][2] = offset + 1
            else:
                ranges.append([sid, offset, offset + 1])
        covered = sum(1 for c in text[start:end] if not c.isspace())
        result.append(
            TextRun(
                ranges=[tuple(r) for r in ranges],
                signals=evidence["signals"],
                rules=evidence["rules"],
                whole_line=covered >= 0.9 * visible,
            )
        )
    return result


def _relation(character: str) -> bool:
    """Equality and order relations, from their Unicode names (no character list)."""
    name = unicodedata.name(character, "")
    return any(
        part in name
        for part in (
            "EQUAL",
            "LESS-THAN",
            "GREATER-THAN",
            "EQUIVALENT",
            "ALMOST",
            "PROPORTIONAL",
            "IDENTICAL",
        )
    )


def _glued(text: str, start: int) -> bool:
    """A letter written onto a word: after a letter, digit or apostrophe (``Cronbach's``);
    a mark such as a significance star (``*p``) does not glue."""
    previous = text[start - 1]
    return (
        previous.isalnum()
        or "APOSTROPHE" in unicodedata.name(previous, "")
        or ("SINGLE QUOTATION" in unicodedata.name(previous, ""))
    )


def _new_term(current, token, text):
    """A space-only gap between an operand (or closing group) and an operand (or opening
    group) separates two terms."""
    if token[0] == "group" and text[token[1]] not in "([{":
        return False
    meaningful = [t for t in current if t[0] != "space"]
    if not meaningful or current[-1][0] != "space":
        return False
    last = meaningful[-1]
    closing = last[0] == "group" and text[last[1]] in ")]}"
    return last[0] in {"number", "letter", "script"} or closing


def _reaches_operand(run, index, step, text):
    position = index + step
    while 0 <= position < len(run):
        kind, start, _end = run[position]
        if kind in {"number", "letter", "script"}:
            return True
        if kind == "space" or (kind == "group" and text[start] in "()[]{}|"):
            position += step
            continue
        if kind == "operator" and step > 0:
            position += step  # a sign after a relation (``= −2``)
            continue
        return False
    return False


def _operand(kind: str, text: str, start: int, end: int) -> bool:
    return kind in {"number", "letter", "script"}


def _evidence(run, text, rows, all_tokens, math_fonts, store):
    rules, signals = [], {}
    kinds = [t[0] for t in run]
    operands = [t for t in run if _operand(t[0], text, t[1], t[2])]
    operators = [t for t in run if t[0] == "operator"]
    signals["operators"] = len(operators)
    signals["operands"] = len(operands)
    # An operator between two operands; spaces and brackets may stand between them, but a
    # comma or semicolon separates list items (``83, 83+, 84``), not terms.
    for index, token in enumerate(run):
        if token[0] != "operator":
            continue
        if _reaches_operand(run, index, -1, text) and _reaches_operand(run, index, 1, text):
            rules.append("operator_between_operands")
            break
    # A leading relation applied to an operand (``< .05``) after a single-letter operand
    # inside parentheses or alone is covered above; unary minus alone is not evidence.
    shifted = [rows[i][4] for t in run for i in range(t[1], t[2])]
    if any(shifted) and not all(shifted):
        base_tokens = [t for t in run if t[0] in {"number", "letter"} and not rows[t[1]][4]]
        script_tokens = [t for t in run if rows[t[1]][4]]
        attached = any(
            b[2] == s[1] or (b[2] < s[1] and text[b[2] : s[1]].strip() == "")
            for b in base_tokens
            for s in script_tokens
        )
        if attached:
            rules.append("script_on_operand")
    if any(
        t[0] == "script" and any(b[2] == t[1] and b[0] in {"number", "letter"} for b in run)
        for t in run
    ):
        rules.append("script_on_operand")
    greek = [t for t in run if t[0] == "letter" and _script_greek(text[t[1]])]
    signals["greek_letters"] = len(greek)
    fonts = {store.spans[rows[i][0]].font for t in run for i in range(t[1], t[2])}
    in_math_font = sorted(font for font in fonts if font in math_fonts)
    if in_math_font and (operands or operators):
        rules.append("math_font")
        signals["math_font"] = True
    # A note reference: a raised number right after a word is never equation evidence.
    if set(rules) == {"script_on_operand"}:
        first = run[0]
        previous = [t for t in all_tokens if t[2] == first[1]]
        if previous and previous[0][0] == "word":
            rules = []
        # A raised letter on a bare number is a note or ordinal mark (``3.38ᵇ``), not an
        # exponent: only numbers carry the line's baseline and only letters are raised.
        raised = [t for t in run if rows[t[1]][4] and t[0] != "space"]
        level = [t for t in run if not rows[t[1]][4] and t[0] != "space"]
        if (
            raised
            and all(t[0] == "letter" for t in raised)
            and level
            and all(t[0] == "number" for t in level)
        ):
            rules = []
    signals["kinds"] = ",".join(sorted(set(kinds)))
    return {"rules": rules, "signals": signals}
