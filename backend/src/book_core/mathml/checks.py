"""Checks of a reading: MathML validity, symbol count, brackets, SymPy and arithmetic.

- **MathML**: the written markup is well-formed (lxml) and follows MathML 3 presentation
  structure (``markup.validate``).
- **Symbols**: the reading has as many characters as the region's evidence produced.
- **Brackets**: opening and closing brackets balance in every row.
- **SymPy**: an expression made only of numbers, single-letter names, arithmetic, relations,
  fractions, powers and roots must parse; when every side of a relation is a number, the
  relation is checked within the rounding of its written result (``numeric``).
"""

import unicodedata
from decimal import Decimal, InvalidOperation

from book_core.mathml import markup
from book_core.mathml.tree import TOKENS, characters

ARITHMETIC = {"+": "+", "−": "-", "-": "-", "×": "*", "·": "*", "⋅": "*", "∙": "*", "•": "*",
              "*": "*", "/": "/", "÷": "/"}  # fmt: skip
RELATIONS = {"=": "==", "<": "<", ">": ">", "≤": "<=", "≥": ">=", "≈": "==", "≠": "!="}


class NotApplicable(Exception):
    pass


def _expression(node):
    """SymPy source of a tree, or NotApplicable."""
    kind = node.kind
    if kind == "number":
        text = node.text.replace(",", "")
        try:
            Decimal(text)
        except InvalidOperation as error:
            raise NotApplicable from error
        return f"({text})"
    if kind == "identifier":
        if len(node.text) != 1:
            raise NotApplicable
        return f"Symbol({node.text!r})"
    if kind == "operator":
        if node.text in ARITHMETIC:
            return ARITHMETIC[node.text]
        if node.text in "()[]":
            return "(" if node.text in "([" else ")"
        raise NotApplicable
    if kind == "row":
        parts = [_expression(c) for c in node.children]
        out = []
        for part in parts:
            # Juxtaposition is multiplication: "2(3)", "(a)(b)", "np".
            if out and out[-1] not in "+-*/(" and part not in "+-*/)":
                out.append("*")
            out.append(part)
        return "(" + "".join(out) + ")"
    if kind == "fraction":
        return f"(({_expression(node.children[0])})/({_expression(node.children[1])}))"
    if kind == "sup":
        return f"(({_expression(node.children[0])})**({_expression(node.children[1])}))"
    if kind == "radical":
        return f"sqrt({_expression(node.children[0])})"
    if kind == "root":
        return f"(({_expression(node.children[0])})**(1/({_expression(node.children[1])})))"
    raise NotApplicable


def _sides(tree):
    """Split a top-level row at relations: (sides, relations)."""
    items = tree.children if tree.kind == "row" else (tree,)
    sides, relations, current = [], [], []
    for item in items:
        if item.kind == "operator" and item.text in RELATIONS:
            sides.append(current)
            relations.append(item.text)
            current = []
        else:
            current.append(item)
    sides.append(current)
    return sides, relations


def _decimals(node):
    text = "".join(c for c in "".join(_leaves(node)) if c.isdigit() or c == ".")
    return len(text.split(".")[1]) if "." in text else 0


def _leaves(node):
    if node.kind in TOKENS:
        return [node.text]
    return [t for c in node.children for t in _leaves(c)]


def sympy_check(tree):
    """("parsed" | "failed" | "not_applicable" | "unavailable", "consistent" |
    "inconsistent" | "not_applicable"). SymPy is optional (models / math-conversion
    extras); without it the check is "unavailable"."""
    try:
        from sympy import Symbol, sqrt
        from sympy.parsing.sympy_parser import parse_expr
    except ImportError:
        return "unavailable", "not_applicable"

    from book_core.mathml.tree import Node

    sides, relations = _sides(tree)
    if any(not side for side in sides):
        return "not_applicable", "not_applicable"
    try:
        sources = [_expression(Node("row", children=tuple(side))) for side in sides]
    except NotApplicable:
        return "not_applicable", "not_applicable"
    try:
        values = [
            parse_expr(s, local_dict={"Symbol": Symbol, "sqrt": sqrt}, evaluate=True)
            for s in sources
        ]
    except Exception:  # any SymPy failure is a failed parse
        return "failed", "not_applicable"
    if not relations or any(v.free_symbols for v in values):
        return "parsed", "not_applicable"
    try:
        numbers = [float(v) for v in values]
    except (TypeError, ValueError):
        return "parsed", "not_applicable"
    for (left, right), relation, side in zip(
        zip(numbers, numbers[1:], strict=False), relations, sides[1:], strict=True
    ):
        tolerance = 0.51 * 10 ** (-_decimals(_row(side))) + 1e-9 * max(1.0, abs(right))
        if relation in {"=", "≈"} and abs(left - right) > tolerance:
            return "parsed", "inconsistent"
        if relation == "<" and not left < right + tolerance:
            return "parsed", "inconsistent"
        if relation == ">" and not left > right - tolerance:
            return "parsed", "inconsistent"
    return "parsed", "consistent"


def _row(items):
    from book_core.mathml.tree import Node

    return Node("row", children=tuple(items)) if len(items) != 1 else items[0]


def check(tree, expected, display=False):
    """Check record of one reading against ``expected`` characters (None: unknown)."""
    written = markup.write(tree, display)
    problems = markup.validate(written)
    found = len(characters(tree))
    parsed, numeric = sympy_check(tree)
    return {
        "mathml": written,
        "well_formed": not any(p.startswith("not well-formed") for p in problems),
        "mathml3": not problems,
        "problems": problems,
        "symbols_expected": expected,
        "symbols_found": found,
        "symbols_match": None if expected is None else found == expected,
        "brackets_balanced": markup.balanced(tree),
        "sympy": parsed,
        "numeric": numeric,
    }


def region_characters(tree_or_none, symbols):
    """Expected characters of a region: those its position reading holds when it exists."""
    if tree_or_none is not None:
        return len(characters(tree_or_none))
    return symbols or None


def fold(character):
    """Comparison class of one character: compatibility form, and the dash, dot, bar and
    prime variants a reader may choose for the same mark."""
    text = unicodedata.normalize("NFKC", character)
    out = []
    for c in text:
        name = unicodedata.name(c, "")
        if c in "-‐‑‒–—―−":
            out.append("−")
        elif c in "·⋅∙•":
            out.append("⋅")
        elif c in "¯‾ˉ_̄":
            out.append("¯")
        elif c in "'′’ʹ":
            out.append("′")
        elif c in "ˆ^̂":
            out.append("^")
        elif c in "∼~":
            out.append("∼")
        elif c in "|∣":
            out.append("|")
        elif c == "∑" or "N-ARY SUMMATION" in name:
            out.append("Σ")
        else:
            out.append(c)
    return out
