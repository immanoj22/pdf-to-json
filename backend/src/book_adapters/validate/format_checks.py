"""Checks shared by the format writers, run on the written files (re-read from disk):

* ``lossless_check``: the tokens of the content files, in order, equal the emission ledger's
  tokens (the same rule as the DocBook and ePub checks), plus the coverage, order and
  character-change results of the ledger.
* ``Findings``: the rule checks, in the shape the QC report reads (``house_rules``).
* ``parse_html``: a strict HTML5 reader (void elements, matching end tags, quoted attributes)
  that returns an element tree and every nesting error."""

from __future__ import annotations

import difflib
from collections import Counter
from html.parser import HTMLParser

from lxml import etree

from ..engine.text import TOKEN_RE
from . import lossless

VOID = frozenset(
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


class Findings:
    def __init__(self, items: dict[str, str]):
        self.checks = {
            name: {"item": item, "checked": 0, "violations": 0, "examples": []}
            for name, item in items.items()
        }

    def check(self, name: str, ok: bool, example: str = ""):
        c = self.checks[name]
        c["checked"] += 1
        if not ok:
            c["violations"] += 1
            if len(c["examples"]) < 10:
                c["examples"].append(example)

    @property
    def violations(self) -> int:
        return sum(c["violations"] for c in self.checks.values())

    def result(self) -> dict:
        return {"violations": self.violations, "checks": self.checks}


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = None
        self.stack: list[etree._Element] = []
        self.errors: list[str] = []
        self.doctype = None

    def handle_decl(self, decl):
        self.doctype = decl

    def handle_starttag(self, tag, attrs):
        node = etree.Element(tag)
        for k, v in attrs:
            if v is None:
                self.errors.append(f"line {self.getpos()[0]}: attribute {k!r} has no value")
                v = ""
            if k in node.attrib:
                self.errors.append(f"line {self.getpos()[0]}: duplicate attribute {k!r} on <{tag}>")
            node.set(k, v)
        if self.stack:
            self.stack[-1].append(node)
        elif self.root is None:
            self.root = node
        else:
            self.errors.append(f"line {self.getpos()[0]}: content after the root element")
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID:
            self.errors.append(f"line {self.getpos()[0]}: <{tag}/> is not an HTML void element")
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)
        else:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in VOID:
            self.errors.append(f"line {self.getpos()[0]}: end tag </{tag}> of a void element")
            return
        if not self.stack or self.stack[-1].tag != tag:
            open_tag = self.stack[-1].tag if self.stack else None
            self.errors.append(f"line {self.getpos()[0]}: </{tag}> closes <{open_tag}>")
            return
        self.stack.pop()

    def handle_data(self, data):
        if not self.stack:
            if data.strip():
                self.errors.append(f"line {self.getpos()[0]}: text outside the root element")
            return
        top = self.stack[-1]
        if len(top):
            top[-1].tail = (top[-1].tail or "") + data
        else:
            top.text = (top.text or "") + data


def parse_html(data: bytes) -> tuple[etree._Element | None, list[str], str | None]:
    b = _Builder()
    b.feed(data.decode("utf-8"))
    b.close()
    for node in b.stack:
        b.errors.append(f"<{node.tag}> is never closed")
    return b.root, b.errors, b.doctype


def tokens_in_blocks(segments: list[tuple[int, str]]) -> list[str]:
    out: list[str] = []
    group: list[str] = []
    current = None
    for key, text in segments:
        if key != current and group:
            out += TOKEN_RE.findall("".join(group))
            group = []
        current = key
        group.append(text)
    if group:
        out += TOKEN_RE.findall("".join(group))
    return out


def lossless_check(actual: list[str], doc, ledger) -> dict:
    """Coverage, order, character changes and the written tokens against the ledger."""
    cov = lossless.coverage(doc, ledger)
    expected = lossless._ledger_tokens(ledger)
    if expected == actual:
        out = {"tokens": len(actual), "matches_ledger": True, "differences": 0}
    else:
        sm = difflib.SequenceMatcher(a=expected, b=actual, autojunk=False)
        diffs = [op for op in sm.get_opcodes() if op[0] != "equal"]
        out = {
            "tokens": len(actual),
            "ledger_tokens": len(expected),
            "matches_ledger": False,
            "differences": len(diffs),
            "xml_extra": sum(
                j2 - j1 for op, i1, i2, j1, j2 in diffs if op in ("insert", "replace")
            ),
            "xml_missing": sum(
                i2 - i1 for op, i1, i2, j1, j2 in diffs if op in ("delete", "replace")
            ),
            "examples": [
                {
                    "op": op,
                    "ledger": expected[i1 : min(i2, i1 + 8)],
                    "xml": actual[j1 : min(j2, j1 + 8)],
                }
                for op, i1, i2, j1, j2 in diffs[:10]
            ],
        }
    return {
        "missing": cov["missing"] + out.get("xml_missing", 0),
        "extra": cov["extra"] + out.get("xml_extra", 0),
        "coverage": cov,
        "order": lossless.order(ledger),
        "output": out,
        "split_words": lossless.split_words(doc, actual),
        "character_changes": lossless.character_changes(doc, ledger),
        "generated_text": Counter(e.note for e in ledger.entries if e.kind == "generated"),
        "settings_text": sorted({e.note for e in ledger.entries if e.kind == "settings"}),
    }


def xml_tokens(root, inline: frozenset[str], skip, files_root=None) -> list[str]:
    """Tokens of an XML content file in order, grouped by block (an element not in
    ``inline`` starts a block). ``skip(el)`` is true for elements whose text is not source
    text: generated labels, page numbers, MathML, metadata."""
    segments: list[tuple[int, str]] = []

    def local(el):
        return etree.QName(el).localname

    def block_of(el):
        while el is not None and local(el) in inline:
            el = el.getparent()
        return id(el)

    def walk(el, skipped):
        if not isinstance(el.tag, str):
            return
        here = skipped or skip(el)
        if el.text and not here:
            segments.append((block_of(el), el.text))
        for child in el:
            walk(child, here)
            if child.tail and not here:
                segments.append((block_of(el), child.tail))

    walk(root, False)
    return tokens_in_blocks(segments)
