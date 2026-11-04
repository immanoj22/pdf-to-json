"""XHTML 1.1-style serialization for the ePub writer.

The writer builds plain lxml elements (``p``, ``span``, ...). Names that XML trees cannot hold
are written with a placeholder and mapped here: attribute ``epub_type`` becomes ``epub:type``,
``xml_lang`` becomes ``xml:lang``, ``aria_label`` becomes ``aria-label`` and so on. Output
depends only on the tree, so runs are byte-identical."""

from __future__ import annotations

from lxml import etree

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
MATHML_NS = "http://www.w3.org/1998/Math/MathML"

ATTR_NAMES = {
    "epub_type": "epub:type",
    "xml_lang": "xml:lang",
    "aria_label": "aria-label",
    "aria_hidden": "aria-hidden",
    "aria_labelledby": "aria-labelledby",
}

# Elements whose children go on their own lines when they hold elements only.
CONTAINERS = frozenset(
    {
        "html",
        "head",
        "body",
        "section",
        "div",
        "aside",
        "nav",
        "ul",
        "ol",
        "li",
        "dl",
        "dd",
        "table",
        "thead",
        "tbody",
        "tr",
        "figure",
        "semantics",
    }
)
BLOCKS = frozenset(
    {
        "html",
        "head",
        "body",
        "section",
        "div",
        "aside",
        "nav",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "table",
        "caption",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "figure",
        "figcaption",
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "meta",
        "link",
        "title",
    }
)
# Elements inside running text. A span is inline only as a formatting span or a page break.
INLINE = frozenset({"a", "b", "i", "u", "em", "strong", "sup", "sub", "br"})
FORMAT_SPAN_PREFIX = "f-"


def is_inline(el) -> bool:
    tag = el.tag
    if tag in INLINE:
        return True
    if tag == "span":
        cls = el.get("class") or ""
        return cls.startswith(FORMAT_SPAN_PREFIX) or el.get("epub_type") == "pagebreak"
    return False


def _text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _attr(value: str) -> str:
    return _text(value).replace('"', "&quot;")


def serialize(el, indent_unit: str = "") -> str:
    out: list[str] = []
    _write(el, out)
    return "".join(out)


def _write(el, out: list[str], root: bool = False) -> None:
    tag = el.tag
    attrs = []
    if tag == "html":
        attrs.append(f'xmlns="{XHTML_NS}"')
        attrs.append(f'xmlns:epub="{EPUB_NS}"')
    if tag == "math":
        attrs.append(f'xmlns="{MATHML_NS}"')
    for key, value in el.attrib.items():
        attrs.append(f'{ATTR_NAMES.get(key, key)}="{_attr(value)}"')
    head = f"<{tag}{' ' + ' '.join(attrs) if attrs else ''}"
    if not len(el) and not el.text:
        out.append(head + "/>")
        return
    out.append(head + ">")
    element_only = (
        tag in CONTAINERS
        and not (el.text or "").strip()
        and all(c.tag in BLOCKS and not (c.tail or "").strip() for c in el)
    )
    if element_only:
        out.append("\n")
        for child in el:
            _write(child, out)
            out.append("\n")
    else:
        if el.text:
            out.append(_text(el.text))
        for child in el:
            _write(child, out)
            if child.tail:
                out.append(_text(child.tail))
    out.append(f"</{tag}>")


def document(html) -> bytes:
    """A complete XHTML file for an ``html`` element."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n' + serialize(html) + "\n"
    ).encode("utf-8")


def new_html(lang: str, title: str, css_hrefs: list[str], body_attrs: dict | None = None):
    """An empty page: ``html`` with a head (charset, title, style sheets) and a body."""
    html = etree.Element("html")
    html.set("lang", lang)
    html.set("xml_lang", lang)
    head = etree.SubElement(html, "head")
    etree.SubElement(head, "meta").set("charset", "utf-8")
    etree.SubElement(head, "title").text = title
    for href in css_hrefs:
        link = etree.SubElement(head, "link")
        link.set("rel", "stylesheet")
        link.set("type", "text/css")
        link.set("href", href)
    body = etree.SubElement(html, "body")
    for k, v in (body_attrs or {}).items():
        body.set(k, v)
    return html, body
