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
reference — or when a span set in a math font contains a letter or operator — or when a
single letter is applied to a bracketed argument (``f(x)``, ``P(A|B)``). Words inside a
bracket applied with no space to a single letter or a closing bracket belong to the
expression (``P(A AND B)``); spaced dashes are minus signs only next to a relation; commas,
semicolons and colons at bracket depth 0 end an expression.

With ``attachable`` a line also yields runs without evidence of their own (``f(x) =``, a
lone ``=``): they never become regions alone, only parts of an expression whose drawn part
they join (``detect``).
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
SCRIPT_SPAN = 3  # characters of a span holding a script letter


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


def line_runs(store, line, geometry, math_fonts, attachable=False) -> list[TextRun]:
    rows = line_characters(store, line, geometry)
    text = "".join(row[2] for row in rows)
    tokens = []
    for match in TOKEN.finditer(text):
        kind = match.lastgroup
        tokens.append((kind, match.start(), match.end()))
    if line.horizontal:
        tokens = _split_at_scripts(tokens, rows, text, store)
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
            continue
        # A dash set with a space on both sides between two operands is a minus inside an
        # expression with a relation (``x = 1 – 0.80``); elsewhere it is a range
        # (``1933 - 1944``, ``A – G``) and the run is cut there (below).
        before_token = [t for t in tokens[:index] if t[0] != "space"][-1:]
        after_token = [t for t in tokens[index + 1 :] if t[0] != "space"][:1]
        spaced = text[token[1] - 1 : token[1]].isspace() and text[token[2] : token[2] + 1].isspace()
        if (
            spaced
            and before_token
            and after_token
            and _ends_operand(before_token[0], text)
            and _starts_operand(after_token[0], text)
        ):
            tokens[index] = ("dash", token[1], token[2])
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
    # A modifier symbol glued between operands is an operator (``e^(−0.5)``).
    for index, token in enumerate(tokens):
        if token[0] != "other" or unicodedata.category(text[token[1]]) != "Sk":
            continue
        if 0 < index < len(tokens) - 1:
            before, after = tokens[index - 1], tokens[index + 1]
            if (
                before[2] == token[1]
                and after[1] == token[2]
                and _ends_operand(before, text)
                and (_starts_operand(after, text) or after[0] == "operator")
            ):
                tokens[index] = ("operator", token[1], token[2])
    # A bracket applied with no space to a single letter or a closing bracket holds one
    # argument (``P(A AND B)``, ``(1.5)(IQR)``): words inside it belong to the expression.
    for index in _arguments(tokens, text):
        kind, start, end = tokens[index]
        if kind in {"word", "other"}:
            tokens[index] = ("argument", start, end)
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
        # A comma, semicolon or colon at bracket depth 0 followed by a space ends an
        # expression (``β = –.30, p < .001``; ``H₀: μ = 6``); inside brackets it does not
        # (``F(1, 147)``).
        if kind == "group" and text[token[1]] in ",;:" and text[token[2] : token[2] + 1].isspace():
            if _depth(current, text) == 0:
                close()
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
    runs = [piece for run in runs for piece in _ranges_cut(run, text)]
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
        if not evidence["rules"] and not (attachable and _attaches(tokens_of_run)):
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


def _split_at_scripts(tokens, rows, text, store):
    """A standalone letter followed by a short raised or lowered span is a base and its
    script, not a word (``H`` with a lowered ``a`` is ``Hₐ``, not ``Ha``). The base stands
    alone (not glued to a letter or digit) and the script span holds at most
    ``SCRIPT_SPAN`` characters; a longer shifted span is other lettering (a label). Only
    horizontal lines are split: letters of rotated labels shift against each other."""
    result = []
    for kind, start, end in tokens:
        if kind != "word" or end - start < 2:
            result.append((kind, start, end))
            continue
        base_alone = start == 0 or not text[start - 1].isalnum()
        script = rows[start + 1 : end]
        split = (
            base_alone
            and not rows[start][4]
            and all(row[4] for row in script)
            and len({row[0] for row in script}) == 1
            and len(store.spans[script[0][0]].raw_text.strip()) <= SCRIPT_SPAN
        )
        if split:
            result += [
                ("letter", start, start + 1),
                ("letter" if end - start == 2 else "word", start + 1, end),
            ]
        else:
            result.append((kind, start, end))
    return result


def _ends_operand(token, text):
    kind, start, _end = token
    return kind in {"number", "letter", "script"} or (kind == "group" and text[start] in ")]}")


def _starts_operand(token, text):
    kind, start, _end = token
    return kind in {"number", "letter"} or (kind == "group" and text[start] in "([{")


def _attaches(run):
    """A run that may join a drawn part: it holds an operator, a bracket or an operand."""
    return any(t[0] in {"operator", "number", "letter", "script"} for t in run) or any(
        t[0] == "group" for t in run
    )


def _ranges_cut(run, text):
    """Spaced dashes are minus signs in a run holding a relation; otherwise they separate
    the run's pieces (ranges are not subtraction)."""
    if any(t[0] == "operator" and _relation(text[t[1]]) for t in run):
        return [[("operator", s, e) if k == "dash" else (k, s, e) for k, s, e in run]]
    pieces, current = [], []
    for token in run:
        if token[0] == "dash":
            pieces.append(current)
            current = []
        else:
            current.append(token)
    pieces.append(current)
    return [piece for piece in pieces if piece]


def _arguments(tokens, text):
    """Indexes of tokens inside brackets applied, with no space, to a single letter or to a
    closing bracket, up to the matching bracket on the same line; an argument holding a
    sentence end (a full stop before a space) is not one."""
    inside = set()
    for index, (kind, start, _end) in enumerate(tokens):
        if kind != "group" or text[start] != "(" or index == 0:
            continue
        previous = tokens[index - 1]
        applied = previous[2] == start and (
            (previous[0] == "letter" and previous[2] - previous[1] == 1)
            or (previous[0] == "group" and text[previous[1]] == ")")
        )
        if not applied:
            continue
        depth, found = 0, []
        for position in range(index, len(tokens)):
            k, a, b = tokens[position]
            if k == "group" and text[a] == "(":
                depth += 1
            elif k == "group" and text[a] == ")":
                depth -= 1
                if depth == 0:
                    if not any(
                        tokens[i][0] == "other"
                        and text[tokens[i][1]] == "."
                        and text[tokens[i][2] : tokens[i][2] + 1].isspace()
                        for i in found
                    ):
                        inside.update(found)
                    break
            elif position > index:
                found.append(position)
    return inside


def _depth(tokens, text):
    """Open bracket depth at the end of a token sequence."""
    depth = 0
    for kind, start, _end in tokens:
        if kind == "group" and text[start] in "([{":
            depth += 1
        elif kind == "group" and text[start] in ")]}":
            depth = max(0, depth - 1)
    return depth


def _function_application(run, text):
    """A single letter applied to a bracketed argument holding an operand: ``f(x)``."""
    for index, (kind, start, end) in enumerate(run[:-2]):
        if kind != "letter" or end - start != 1:
            continue
        opening = run[index + 1]
        if opening[0] != "group" or text[opening[1]] != "(" or opening[1] != end:
            continue
        depth, inside = 0, []
        for token in run[index + 1 :]:
            if token[0] == "group" and text[token[1]] == "(":
                depth += 1
                continue
            if token[0] == "group" and text[token[1]] == ")":
                depth -= 1
                if depth == 0:
                    if any(t[0] in {"number", "letter", "script"} for t in inside):
                        return True
                    break
                continue
            inside.append(token)
    return False


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
        if kind in {"number", "letter", "script", "argument"}:
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
    if _function_application(run, text):
        rules.append("function_application")
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
