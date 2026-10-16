"""MathML 3 presentation markup: write a tree, read markup back, validate structure.

MathML is the content of an equation record (an output vocabulary for mathematics, not a
book adapter); it is written with lxml so every string is well-formed by construction, and
every string a path produces is validated again before it is recorded.
"""

from lxml import etree

from book_core.mathml.tree import ARITY, TOKENS, Node, row, token

NS = "http://www.w3.org/1998/Math/MathML"
TOKEN_TAGS = {"number": "mn", "identifier": "mi", "operator": "mo", "text": "mtext"}
STRUCTURE_TAGS = {
    "row": "mrow",
    "fraction": "mfrac",
    "radical": "msqrt",
    "root": "mroot",
    "sub": "msub",
    "sup": "msup",
    "subsup": "msubsup",
    "over": "mover",
    "under": "munder",
    "underover": "munderover",
    "table": "mtable",
    "table_row": "mtr",
    "table_cell": "mtd",
}
KINDS = {tag: kind for kind, tag in {**TOKEN_TAGS, **STRUCTURE_TAGS}.items()}

# MathML 3 presentation elements (W3C MathML 3.0, chapter 3) and fixed child counts.
PRESENTATION = {
    "math", "mi", "mn", "mo", "mtext", "mspace", "ms", "mglyph", "mrow", "mfrac", "msqrt",
    "mroot", "mstyle", "merror", "mpadded", "mphantom", "mfenced", "menclose", "msub", "msup",
    "msubsup", "munder", "mover", "munderover", "mmultiscripts", "mprescripts", "none",
    "mtable", "mlabeledtr", "mtr", "mtd", "maligngroup", "malignmark", "mstack", "mlongdiv",
    "msgroup", "msrow", "mscarries", "mscarry", "msline", "maction", "semantics",
    "annotation", "annotation-xml",
}  # fmt: skip
FIXED = {
    "mfrac": 2, "mroot": 2, "msub": 2, "msup": 2, "msubsup": 3, "munder": 2, "mover": 2,
    "munderover": 3,
}  # fmt: skip
TOKEN_ELEMENTS = {"mi", "mn", "mo", "mtext", "ms"}
EMPTY = {"mspace", "none", "mprescripts", "malignmark", "maligngroup", "mglyph", "msline"}
TRANSPARENT = {"mstyle", "mpadded", "mphantom", "menclose", "merror", "maction"}


def _element(node):
    if node.kind in TOKENS:
        element = etree.Element(f"{{{NS}}}{TOKEN_TAGS[node.kind]}")
        element.text = node.text
        return element
    element = etree.Element(f"{{{NS}}}{STRUCTURE_TAGS[node.kind]}")
    if node.kind in ("over", "under") and node.accent:
        element.set("accentunder" if node.kind == "under" else "accent", "true")
    for child in node.children:
        element.append(_element(child))
    return element


def write(node, display=False):
    """Serialized MathML for a tree (one ``math`` element in the MathML namespace)."""
    root = etree.Element(f"{{{NS}}}math", nsmap={None: NS})
    if display:
        root.set("display", "block")
    root.append(_element(node))
    return etree.tostring(root, encoding="unicode")


def _local(element):
    return etree.QName(element).localname


def _read(element):
    tag = _local(element)
    children = [c for c in element if isinstance(c.tag, str)]
    if tag in TOKEN_ELEMENTS:
        text = "".join(element.itertext())
        return token(text) if text.strip() else None
    if tag in EMPTY or tag in {"annotation", "annotation-xml"}:
        return None
    if tag == "semantics":
        return _read(children[0]) if children else None
    if tag == "mfenced":
        open_, close = element.get("open", "("), element.get("close", ")")
        parts = [token(open_)] if open_ else []
        for index, child in enumerate(children):
            if index:
                parts.append(token(element.get("separators", ",")[:1] or ","))
            parts.append(_read(child) or row([]))
        parts += [token(close)] if close else []
        return row(parts)
    kids = [_read(c) for c in children]
    if tag in FIXED:
        kids = [k if k is not None else row([]) for k in kids]
        kind = KINDS[tag]
        accent = element.get("accent" if tag != "munder" else "accentunder") == "true" or (
            tag in ("mover", "munder")
            and len(children) == 2
            and children[1].get("accent") == "true"
        )
        return Node(kind, children=tuple(kids), accent=accent)
    kept = [k for k in kids if k is not None]
    if tag in ("mtable", "mtr", "mlabeledtr", "mtd"):
        kind = {"mtable": "table", "mtr": "table_row", "mlabeledtr": "table_row"}.get(
            tag, "table_cell"
        )
        return Node(kind, children=tuple(kept))
    if tag == "msqrt":
        return Node("radical", children=(row(kept),))
    # mrow, math, transparent wrappers and anything else: a row of the children.
    return row(kept)


def read(markup):
    """Tree of a MathML string (namespaced or not); wrappers such as ``mstyle`` are rows."""
    root = etree.fromstring(markup.encode("utf-8"))
    return _read(root) or row([])


def validate(markup):
    """Problems of a MathML string against MathML 3 presentation structure ([] = valid)."""
    try:
        root = etree.fromstring(markup.encode("utf-8"))
    except etree.XMLSyntaxError as error:
        return [f"not well-formed: {error}"]
    problems = []
    if _local(root) != "math" or etree.QName(root).namespace != NS:
        problems.append("root is not a MathML math element")
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        tag = _local(element)
        if etree.QName(element).namespace != NS:
            problems.append(f"{tag}: outside the MathML namespace")
            continue
        if tag not in PRESENTATION:
            problems.append(f"{tag}: not a MathML 3 presentation element")
            continue
        children = [_local(c) for c in element if isinstance(c.tag, str)]
        if tag in FIXED and len(children) != FIXED[tag]:
            problems.append(f"{tag}: {len(children)} children, needs {FIXED[tag]}")
        if tag in TOKEN_ELEMENTS:
            if any(c not in {"mglyph", "malignmark"} for c in children):
                problems.append(f"{tag}: a token element holds elements")
            if not "".join(element.itertext()).strip():
                problems.append(f"{tag}: empty token")
        if tag in EMPTY and (children or (element.text or "").strip()):
            problems.append(f"{tag}: must be empty")
        if tag == "mtable" and any(c not in {"mtr", "mlabeledtr"} for c in children):
            problems.append("mtable: children must be table rows")
        if tag in {"mtr", "mlabeledtr"} and any(c != "mtd" for c in children):
            problems.append(f"{tag}: children must be table cells")
        if tag == "mtd" and _local(element.getparent()) not in {"mtr", "mlabeledtr"}:
            problems.append("mtd: outside a table row")
    if not [e for e in root.iter() if isinstance(e.tag, str) and _local(e) in TOKEN_ELEMENTS]:
        problems.append("no token: the expression is empty")
    return problems


def balanced(node):
    """Opening and closing brackets (Unicode Ps/Pe) balance within every row of the tree.

    Absolute-value bars and other symmetric fences cannot be checked by category alone and
    are left out."""
    import unicodedata

    def walk(n):
        if n.kind in TOKENS:
            return True
        depth = 0
        for child in n.children:
            if child.kind == "operator":
                for c in child.text:
                    category = unicodedata.category(c)
                    depth += category == "Ps"
                    depth -= category == "Pe"
                    if depth < 0:
                        return False
            if not walk(child):
                return False
        return depth == 0 or n.kind != "row"

    return walk(row([node]) if node.kind != "row" else node)


__all__ = ["ARITY", "NS", "balanced", "read", "validate", "write"]
