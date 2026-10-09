"""Read a reference XML file into benchmark tokens with element provenance.

The file itself is never modified. Two documented, deterministic in-memory repairs exist, and
each applied repair is recorded in the output:

* ``header_quote_delimiters``: doubled quote delimiters (``""value""``) before the end of the
  root start tag. Everything after the root start tag stays byte-identical, so character data and
  element order cannot change.
* ``fragment_wrap``: several top-level elements are wrapped in one synthetic root. No original
  byte changes and the synthetic root carries no text.

Tokens use the benchmark tokenizer (case-sensitive NFKC ``[\\p{L}\\p{M}\\p{N}]+``) over element
character data; attribute values are not reading text. Inline markup never splits a word; every
other element boundary separates tokens.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from book_core.ledger.tokenization import TOKEN_PATTERN
from book_core.reference.dialects import SYNTHETIC_CONTAINER, Dialect, DialectSet

SYNTHETIC_ROOT = SYNTHETIC_CONTAINER
_DOUBLED = re.compile(rb'(?<=[=\s])""([^"\s][^"]*?)""(?=[\s>/?])')
_KEPT_ATTRIBUTES = {"id", "class", "role", "page", "type", "level", "label"}


class ReferenceRejected(ValueError):
    """The file cannot be read as XML without an undocumented change."""


@dataclass(frozen=True)
class Repair:
    kind: str
    detail: str


@dataclass(frozen=True)
class Element:
    index: int
    name: str
    path: str
    parent: int | None
    depth: int
    attributes: dict[str, str]


@dataclass(frozen=True)
class XmlToken:
    index: int
    value: str
    element: int
    segment: int


@dataclass(frozen=True)
class PageMarker:
    label: str
    element: int
    token_index: int  # tokens before this index precede the marker
    segment: int  # the segment this marker opens


@dataclass(frozen=True)
class ReferenceDocument:
    sha256: str
    dialect: Dialect
    repairs: tuple[Repair, ...]
    elements: tuple[Element, ...]
    tokens: tuple[XmlToken, ...]
    markers: tuple[PageMarker, ...]
    segment_count: int
    units: tuple[int, ...]  # text-unit element of each token

    def ancestors(self, element: int) -> list[int]:
        chain = []
        parent = self.elements[element].parent
        while parent is not None:
            chain.append(parent)
            parent = self.elements[parent].parent
        return chain


def _root_start_end(data: bytes) -> int:
    """Byte offset just after the root start tag, skipping prolog, comments, PIs and DOCTYPE."""
    position = 0
    while True:
        start = data.find(b"<", position)
        if start < 0:
            raise ReferenceRejected("No root element")
        if data.startswith(b"<?", start):
            position = data.index(b"?>", start) + 2
        elif data.startswith(b"<!--", start):
            position = data.index(b"-->", start) + 3
        elif data.startswith(b"<!", start):
            subset = data.find(b"[", start)
            close = data.index(b">", start)
            if 0 <= subset < close:
                close = data.index(b">", data.index(b"]", subset))
            position = close + 1
        else:
            return data.index(b">", start) + 1


def repair_header_quotes(data: bytes) -> tuple[bytes, list[Repair]]:
    """Undo doubled quote delimiters before the end of the root start tag only."""
    end = _root_start_end(data)
    head, tail = data[:end], data[end:]
    fixed, changes = _DOUBLED.subn(rb'"\1"', head)
    if not changes:
        return data, []
    return fixed + tail, [
        Repair(
            "header_quote_delimiters",
            f"{changes} doubled delimiter pair(s) in the first {end} bytes; "
            "content after the root start tag is byte-identical",
        )
    ]


def _parse(data: bytes) -> ET.Element:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_pis=True))
    parser.feed(data)
    return parser.close()


def load_tree(data: bytes) -> tuple[ET.Element, list[Repair]]:
    """Parse with the documented repairs, recording each one that was needed."""
    try:
        return _parse(data), []
    except ET.ParseError as error:
        failure = error
    repaired, repairs = repair_header_quotes(data)
    if repairs:
        try:
            return _parse(repaired), repairs
        except ET.ParseError as error:
            failure = error
    body = re.sub(rb"^\s*<\?xml[^>]*\?>", b"", repaired, count=1)
    wrapper = SYNTHETIC_ROOT.encode()
    try:
        root = _parse(b"<" + wrapper + b">" + body + b"</" + wrapper + b">")
    except ET.ParseError as error:
        raise ReferenceRejected(f"Unreadable reference XML: {failure}; {error}") from error
    if len(root) < 2 or (root.text or "").strip():
        raise ReferenceRejected(f"Unreadable reference XML: {failure}")
    return root, [*repairs, Repair("fragment_wrap", f"{len(root)} top-level elements wrapped")]


def local_name(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _attributes(node: ET.Element) -> dict[str, str]:
    return {
        local_name(key): value
        for key, value in node.attrib.items()
        if local_name(key) in _KEPT_ATTRIBUTES
    }


def _marker_label(dialect: Dialect, node: ET.Element) -> str | None:
    if node.tag is ET.ProcessingInstruction:
        match = re.match(r'\s*page\s+value="([^"]*)"', node.text or "")
        return match.group(1) if match else None
    if isinstance(node.tag, str) and local_name(node.tag) in dialect.page_marker_elements:
        return "".join(node.itertext()).strip() or node.get("page", "")
    return None


def read_reference(data: bytes, dialects: DialectSet) -> ReferenceDocument:
    """Benchmark tokens in document order, each owned by its innermost element."""
    root, repairs = load_tree(data)
    dialect = dialects.detect(root)
    elements: list[Element] = []
    pieces: list[tuple[str, int]] = []  # (text, owner); owner -1 marks a hard token boundary
    markers: list[tuple[str, int, int]] = []  # (label, element, position in pieces)

    def add_element(node, parent, path, depth, counts) -> tuple[int, str]:
        name = local_name(node.tag)
        counts[name] = counts.get(name, 0) + 1
        own_path = f"{path}/{name}[{counts[name]}]"
        elements.append(Element(len(elements), name, own_path, parent, depth, _attributes(node)))
        return len(elements) - 1, own_path

    def visit(node: ET.Element, index: int, own_path: str, depth: int):
        inline = elements[index].name in dialect.inline_elements
        if not inline:
            pieces.append(("", -1))
        if node.text:
            pieces.append((node.text, index))
        counts: dict[str, int] = {}
        for child in node:
            label = _marker_label(dialect, child)
            if label is not None:
                marker = index
                if isinstance(child.tag, str):
                    marker, _ = add_element(child, index, own_path, depth + 1, counts)
                pieces.append(("", -1))
                markers.append((label, marker, len(pieces)))
            elif isinstance(child.tag, str):
                child_index, child_path = add_element(child, index, own_path, depth + 1, counts)
                visit(child, child_index, child_path, depth + 1)
            if child.tail:
                pieces.append((child.tail, index))
        if not inline:
            pieces.append(("", -1))

    root_index, root_path = add_element(root, None, "", 0, {})
    visit(root, root_index, root_path, 0)

    tokens: list[XmlToken] = []
    marker_at = {position: number for number, (_, _, position) in enumerate(markers)}
    marker_token: dict[int, int] = {}
    segment = 0
    run_text: list[str] = []
    run_owner: list[int] = []

    def flush():
        text = "".join(run_text)
        for match in TOKEN_PATTERN.finditer(text):
            tokens.append(XmlToken(len(tokens), match.group(), run_owner[match.start()], segment))
        run_text.clear()
        run_owner.clear()

    for position, (text, owner) in enumerate(pieces):
        if position in marker_at:
            flush()
            segment = marker_at[position] + 1
            marker_token[marker_at[position]] = len(tokens)
        if owner < 0:
            flush()
            continue
        normalized = unicodedata.normalize("NFKC", text)
        run_text.append(normalized)
        run_owner.extend([owner] * len(normalized))
    flush()
    for number in range(len(markers)):  # trailing markers open empty segments
        marker_token.setdefault(number, len(tokens))
    return ReferenceDocument(
        sha256=hashlib.sha256(data).hexdigest(),
        dialect=dialect,
        repairs=tuple(repairs),
        elements=tuple(elements),
        tokens=tuple(tokens),
        markers=tuple(
            PageMarker(label, element, marker_token[number], number + 1)
            for number, (label, element, _) in enumerate(markers)
        ),
        segment_count=len(markers) + 1,
        units=tuple(dialect.unit_of(token.element, elements) for token in tokens),
    )
