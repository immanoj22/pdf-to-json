"""LaTeX of a tree (every equation record carries LaTeX beside its MathML), and the reading
of recognizer LaTeX into a tree through latex2mathml.

Characters are written as Unicode (LaTeX with Unicode input reads them); only characters
special to LaTeX are escaped. Multi-letter identifiers are upright (``\\mathrm``).
"""

import unicodedata

from book_core.mathml.tree import TOKENS

SPECIAL = {
    "\\": r"\backslash ",
    "{": r"\{",
    "}": r"\}",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "&": r"\&",
    "_": r"\_",
    "^": r"\hat{}",
    "~": r"\sim ",
}
# Accent marks above a base: drawn bars and the spacing macron/overline characters.
OVERLINES = {"¯", "‾", "―", "‐", "-", "−", "_"}


def _escape(text):
    return "".join(SPECIAL.get(c, c) for c in text)


def _group(node):
    return "{" + latex(node) + "}"


def latex(node):
    kind = node.kind
    if kind in TOKENS:
        if kind == "text":
            return r"\text{" + _escape(node.text) + "}"
        if kind == "identifier" and len(node.text) > 1:
            return r"\mathrm{" + _escape(node.text) + "}"
        return _escape(node.text)
    parts = node.children
    if kind == "row":
        return " ".join(latex(c) for c in parts)
    if kind == "fraction":
        return r"\frac" + _group(parts[0]) + _group(parts[1])
    if kind == "radical":
        return (
            r"\sqrt" + _group(parts[0])
            if len(parts) == 1
            else r"\sqrt{" + " ".join(latex(c) for c in parts) + "}"
        )
    if kind == "root":
        return r"\sqrt[" + latex(parts[1]) + "]" + _group(parts[0])
    if kind == "sub":
        return _group(parts[0]) + "_" + _group(parts[1])
    if kind == "sup":
        return _group(parts[0]) + "^" + _group(parts[1])
    if kind == "subsup":
        return _group(parts[0]) + "_" + _group(parts[1]) + "^" + _group(parts[2])
    if kind == "over":
        mark = parts[1]
        if node.accent and mark.kind in TOKENS and mark.text in OVERLINES:
            return r"\overline" + _group(parts[0])
        if node.accent and mark.kind in TOKENS and mark.text in {"^", "ˆ", "̂"}:
            return r"\hat" + _group(parts[0])
        return r"\overset" + _group(mark) + _group(parts[0])
    if kind == "under":
        return r"\underset" + _group(parts[1]) + _group(parts[0])
    if kind == "underover":
        return (
            r"\underset"
            + _group(parts[1])
            + "{"
            + r"\overset"
            + _group(parts[2])
            + _group(parts[0])
            + "}"
        )
    if kind == "table":
        rows = [
            " & ".join(latex(cell) for cell in r.children) if r.kind == "table_row" else latex(r)
            for r in parts
        ]
        columns = max((len(r.children) for r in parts if r.kind == "table_row"), default=1)
        return r"\begin{array}{" + "l" * columns + "}" + r" \\ ".join(rows) + r"\end{array}"
    if kind in ("table_row", "table_cell"):
        return " ".join(latex(c) for c in parts)
    raise ValueError(f"No LaTeX for {kind}")


def from_latex(source):
    """Tree of recognizer LaTeX (via latex2mathml, optional math-conversion extra), or None
    when it cannot be read or the converter is not installed."""
    try:
        from latex2mathml.converter import convert
    except ImportError:
        return None

    from book_core.mathml.markup import read

    try:
        markup = convert(unicodedata.normalize("NFC", source))
        return read(markup)
    except Exception:  # any converter failure means "no reading"
        return None
