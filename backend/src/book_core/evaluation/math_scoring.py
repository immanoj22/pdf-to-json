"""Expression-level MathML scoring against derived math gold (evaluation only).

Normalisation (both sides): the comparison form of ``mathml.tree.canonical`` (tokens split
into characters, rows flattened, compatibility characters and the dash/dot/bar/prime variants
of ``mathml.checks.fold`` unified), limits written above/below an operator scored like
scripts (``\\sum_{i=1}`` either way), a superscript of primes scored as primes written beside
their base (the reference convention ``p ′``; owner decision at the Step 13c gate; gold is
never edited), and sentence punctuation at the very end of an expression dropped (the
reference sometimes keeps a full stop inside the math).

Metrics: exact match of the normalised trees; tree edit distance (Zhang–Shasha, unit costs)
and its share of the gold tree's size; symbol accuracy = 1 − character edit distance / gold
characters (floored at 0). ``window`` scores a gold equation inside a longer expression (a
region that joins several reference equations through text-set operators): the best
contiguous run of the expression's top-level items.
"""

import unicodedata

from book_core.mathml.checks import fold
from book_core.mathml.distance import sequence_distance, tree_distance
from book_core.mathml.tree import TOKENS, Node, canonical, characters, row, size

LIMITS = {"underover": "subsup", "under": "sub", "over": "sup"}


def _limits(node):
    if node.kind in TOKENS:
        return node
    children = tuple(_limits(c) for c in node.children)
    if node.kind in LIMITS and not node.accent and children[0].kind == "operator":
        return Node(LIMITS[node.kind], children=children)
    return Node(node.kind, children=children, accent=node.accent)


def _primes(node):
    """A superscript made only of primes is the prime written beside its base (the
    reference writes ``p ′``; a layout may read the raised mark as a script)."""
    if node.kind in TOKENS:
        return node
    children = tuple(_primes(c) for c in node.children)
    if node.kind == "sup" and set(characters(children[1])) == {"′"}:
        return row([children[0], children[1]])
    return Node(node.kind, children=children, accent=node.accent)


def _trailing(node):
    items = list(node.children) if node.kind == "row" else [node]
    while items and items[-1].kind == "operator" and unicodedata.category(items[-1].text) == "Po":
        items.pop()
    return row(items) if items else Node("row")


def normalise(tree):
    return _trailing(_primes(_limits(canonical(tree, fold))))


def score(predicted, gold):
    """{exact, ted, ted_share, symbol_accuracy} of a predicted tree against a gold tree."""
    if predicted is None:
        return {"exact": False, "ted": None, "ted_share": None, "symbol_accuracy": 0.0}
    p, g = normalise(predicted), normalise(gold)
    distance = tree_distance(p, g)
    gold_chars, predicted_chars = characters(g), characters(p)
    edits = sequence_distance(predicted_chars, gold_chars)
    return {
        "exact": p == g,
        "ted": distance,
        "ted_share": round(distance / max(1, size(g)), 4),
        "symbol_accuracy": round(max(0.0, 1 - edits / max(1, len(gold_chars))), 4),
    }


def window(predicted, gold):
    """Best ``score`` of the gold tree against any contiguous run of the predicted
    expression's top-level items (the whole expression included). Runs are ranked by
    symbol accuracy first; the tree distance is computed for the best few only."""
    if predicted is None:
        return score(None, gold)
    p, g = normalise(predicted), normalise(gold)
    items = list(p.children) if p.kind == "row" else [p]
    gold_chars = characters(g)
    candidates = []
    for start in range(len(items)):
        for end in range(start + 1, len(items) + 1):
            part = row(items[start:end])
            chars = characters(part)
            if len(chars) > 2 * len(gold_chars) + 4:
                break
            edits = sequence_distance(chars, gold_chars)
            candidates.append((edits, end - start, start, part))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    best = score(predicted, gold)
    for _, _, _, part in candidates[:5]:
        result = score(part, gold)
        if (result["exact"], result["symbol_accuracy"], -result["ted"]) > (
            best["exact"],
            best["symbol_accuracy"],
            -best["ted"],
        ):
            best = result
    return best
