"""A neutral expression tree shared by every recognition path.

Leaves are tokens (``number``, ``identifier``, ``operator``, ``text``); inner nodes are
layout structures (``row``, ``fraction``, ``radical``, ``root``, scripts, ``over``/``under``,
``table``). Token kinds come from Unicode general categories, never from a character list:
decimal digits are numbers, letters are identifiers, everything else is an operator. The
tree is serialized to MathML and LaTeX by ``mathml.markup`` and ``mathml.latex``; the
comparison form (``canonical``) splits every token into characters so that equal content
compares equal whatever token grouping a path chose.
"""

import unicodedata
from dataclasses import dataclass, field

TOKENS = ("number", "identifier", "operator", "text")
ARITY = {
    "fraction": 2,
    "root": 2,
    "sub": 2,
    "sup": 2,
    "subsup": 3,
    "over": 2,
    "under": 2,
    "underover": 3,
}
VARIADIC = ("row", "radical", "table", "table_row", "table_cell")


@dataclass(frozen=True)
class Node:
    kind: str
    text: str = ""
    children: tuple = field(default_factory=tuple)
    accent: bool = False  # ``over``/``under``: the script is an accent (x̄, ŷ)
    # Source symbol ids of a token, one per character (layout paths); not compared.
    ids: tuple = field(default=(), compare=False, repr=False)

    def __post_init__(self):
        if self.kind in TOKENS:
            if self.children or not self.text:
                raise ValueError("A token holds text and no children")
        elif self.kind in ARITY:
            if len(self.children) != ARITY[self.kind] or self.text:
                raise ValueError(f"A {self.kind} has {ARITY[self.kind]} children")
        elif self.kind not in VARIADIC or self.text:
            raise ValueError(f"Unknown expression node {self.kind!r}")


def token(text, ids=()):
    return Node(token_kind(text), text, ids=tuple(ids))


def row(children):
    """A row; a single child stands for itself, nested rows are spliced."""
    flat = []
    for child in children:
        if child.kind == "row":
            flat.extend(child.children)
        else:
            flat.append(child)
    if len(flat) == 1:
        return flat[0]
    return Node("row", children=tuple(flat))


def character_kind(character):
    category = unicodedata.category(character)
    if category == "Nd":
        return "number"
    if category[0] == "L":
        return "identifier"
    return "operator"


def token_kind(text):
    kinds = {character_kind(c) for c in text if not c.isspace()}
    if kinds == {"number"} or (kinds == {"number", "operator"} and _numeric(text)):
        return "number"
    if kinds == {"identifier"}:
        return "identifier"
    if len(kinds) > 1 or " " in text.strip():
        return "text"
    return "operator"


def _numeric(text):
    """Digits with decimal or group separators between or before them (``0.25``, ``.5``)."""
    core = text.strip()
    if not core or character_kind(core[-1]) != "number":
        return False
    return all(
        character_kind(c) == "number" or unicodedata.category(c) == "Po" for c in core
    ) and not any(
        unicodedata.category(a) == "Po" and unicodedata.category(b) == "Po"
        for a, b in zip(core, core[1:], strict=False)
    )


def leaves(node):
    """Token texts in expression order (structure order: numerator before denominator, base
    before scripts)."""
    if node.kind in TOKENS:
        return [node.text]
    return [text for child in node.children for text in leaves(child)]


def characters(node):
    return [c for text in leaves(node) for c in text if not c.isspace()]


def sourced(node):
    """[(character, source id or None)] of a tree's tokens in expression order."""
    if node.kind in TOKENS:
        ids = node.ids
        if len(ids) == 1:  # one symbol read as several characters, or one merged rule
            ids = ids * len(node.text)
        if len(ids) != len(node.text):
            ids = (None,) * len(node.text)
        return [(c, i) for c, i in zip(node.text, ids, strict=True) if not c.isspace()]
    return [pair for child in node.children for pair in sourced(child)]


def structure_ids(node):
    """Source ids that a structure consumed without a character of their own (a radical
    sign is the square root itself)."""
    if node.kind in TOKENS:
        return []
    return [*node.ids, *(i for child in node.children for i in structure_ids(child))]


def size(node):
    return 1 + sum(size(child) for child in node.children)


def canonical(node, fold=None):
    """Comparison form: every token split into characters (``fold`` maps a character to its
    comparison class), rows flattened, empty rows dropped."""
    fold = fold or (lambda c: c)
    if node.kind in TOKENS:
        parts = [
            Node(character_kind(f), f)
            for c in unicodedata.normalize("NFKC", node.text)
            if not c.isspace()
            for f in fold(c)
        ]
        return row(parts) if parts else Node("row")
    children = [canonical(child, fold) for child in node.children]
    if node.kind == "over" and _bar_mark(node.children[1], fold):
        # An overline compares as one thing whichever bar character (macron, overline,
        # horizontal bar, minus) and accent flag a reader chose for it.
        return Node("over", children=(children[0], Node("operator", "¯")), accent=True)
    if node.kind in ("sub", "sup") and children[1].kind == "row" and not children[1].children:
        return children[0]  # an empty script is no script
    if node.kind in VARIADIC:
        kept = [c for c in children if not (c.kind == "row" and not c.children)]
        if node.kind == "row":
            return row(kept) if kept else Node("row")
        return Node(node.kind, children=tuple(kept))
    return Node(node.kind, children=tuple(children), accent=node.accent)


def _bar_mark(mark, fold):
    """A mark of one horizontal-bar character (its comparison class is the minus or the
    macron)."""
    if mark.kind not in TOKENS:
        return False
    text = unicodedata.normalize("NFKC", mark.text).strip()
    return len(text) == 1 and fold(text) in (["−"], ["¯"])


def labels(node):
    """(label, children) view for tree edit distance."""
    if node.kind in TOKENS:
        return f"{node.kind}:{node.text}", ()
    return node.kind, node.children
