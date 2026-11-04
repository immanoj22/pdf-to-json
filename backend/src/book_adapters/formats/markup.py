"""Small markup helpers shared by the format transformers: building elements, adding text in
mixed content, and deterministic serialization (HTML syntax and XML)."""

from __future__ import annotations

from lxml import etree

HTML_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)


def el(tag: str, attrs: dict | None = None, text: str | None = None, parent=None):
    node = etree.SubElement(parent, tag) if parent is not None else etree.Element(tag)
    for key, value in (attrs or {}).items():
        if value is not None:
            node.set(key, str(value))
    if text:
        node.text = text
    return node


def add_text(parent, text: str | None):
    """Append text at the end of parent's content (mixed content aware)."""
    if not text:
        return
    if len(parent):
        parent[-1].tail = (parent[-1].tail or "") + text
    else:
        parent.text = (parent.text or "") + text


def text_of(node) -> str:
    """All text under node, whitespace collapsed (metadata strings, never delivered text)."""
    return " ".join("".join(node.itertext()).split())


def _esc(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _esc_attr(value: str) -> str:
    return _esc(value).replace('"', "&quot;")


def serialize(
    node,
    block: frozenset[str],
    html: bool = False,
    prefixes: dict[str, str] | None = None,
    only_children: frozenset[str] | None = None,
    declared: frozenset[str] = frozenset(),
) -> str:
    """Deterministic markup. ``html``: HTML syntax (void elements without an end tag, never
    self-closed); otherwise XML (empty elements self-closed). Elements in ``block`` with
    element-only content put each child on its own line; mixed content stays as written."""
    out: list[str] = []
    _write(node, block, html, out, prefixes or {}, None, only_children, declared)
    return "".join(out)


def _attr(key: str, value: str, prefixes: dict[str, str]) -> str:
    if key.startswith("{"):
        ns, local = key[1:].split("}")
        key = f"{prefixes[ns]}:{local}" if prefixes.get(ns) else local
    return f' {key}="{_esc_attr(value)}"'


def _write(node, block, html, out, prefixes, parent_ns, only_children, declared):
    if not isinstance(node.tag, str):
        if isinstance(node, etree._ProcessingInstruction):
            out.append(f"<?{node.target} {node.text}?>" if node.text else f"<?{node.target}?>")
        return
    tag = node.tag
    ns = None
    attrs = "".join(_attr(k, v, prefixes) for k, v in node.attrib.items())
    if tag.startswith("{"):
        ns, local = tag[1:].split("}")
        prefix = prefixes.get(ns, "")
        if ns != parent_ns and ns not in declared:
            attrs = (f' xmlns:{prefix}="{ns}"' if prefix else f' xmlns="{ns}"') + attrs
        tag = f"{prefix}:{local}" if prefix else local
    if html and tag in HTML_VOID:
        out.append(f"<{tag}{attrs}>")
        return
    if not html and not len(node) and not node.text:
        out.append(f"<{tag}{attrs}/>")
        return
    out.append(f"<{tag}{attrs}>")
    element_only = (
        tag in block
        and not (node.text or "").strip()
        and all(not (c.tail or "").strip() for c in node)
        and (only_children is None or all(c.tag in only_children for c in node))
    )
    if element_only:
        out.append("\n")
        for child in node:
            _write(child, block, html, out, prefixes, ns, only_children, declared)
            out.append("\n")
    else:
        if node.text:
            out.append(_esc(node.text))
        for child in node:
            _write(child, block, html, out, prefixes, ns, only_children, declared)
            if child.tail:
                out.append(_esc(child.tail))
    out.append(f"</{tag}>")
