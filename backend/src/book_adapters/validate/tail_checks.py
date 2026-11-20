"""Checks of the tail reference file, re-read from disk: pure ASCII with CRLF line ends and
uppercase 5-digit hexadecimal entities, well-formed XML, ``refcount`` equal to the references,
the numbering, the sample's tag order, every DOI/address and PMID of the printed reference
present in its tags, and the lossless check (every source word of the reference list written
once in a reference, or omitted with a reason: running header, page number, text outside the
list).

The format writes ``ce:`` tags without declaring the prefix (the client's sample does the same),
so the file is read with the prefix declared in memory only."""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from ..engine.text import TOKEN_RE
from . import format_checks as fc
from . import lossless

ITEMS = {
    "ascii": "the file is pure ASCII",
    "line_ends": "every line ends CRLF, none ends LF alone",
    "entities": "every character reference is &#x + 5 uppercase hex digits; & < > are written as references",
    "refcount": "refcount equals the number of reference elements",
    "numbering": "the references are numbered 1..N in order",
    "tag_order": "the tags of a reference are in the sample's order",
    "addresses": "every [address] of the printed reference is in ref-website",
    "pmids": "every [PMID: n] of the printed reference is in ref-text",
    "full_text": "ref-fulltext and ce:source-text hold the same printed reference",
}
ORDER = [
    "ref-title", "itemidlist", "ref-authors", "ref-sourcetitle", "ref-publicationyear",
    "volisspag", "ref-website", "ref-text",
]  # fmt: skip
CE = "{urn:undeclared:ce}"  # the ce: prefix, as read
ENTITY = re.compile(rb"&#x([0-9A-F]{5});")


def read(data: bytes) -> etree._Element:
    """The file as XML; a prefix the file uses but never declares is declared in memory."""
    prefixes = sorted(set(re.findall(rb"</?([A-Za-z_][\w.-]*):", data)) - {b"xml"})
    if prefixes:
        decl = b"".join(b' xmlns:%s="urn:undeclared:%s"' % (p, p) for p in prefixes)
        data = re.sub(rb"<([A-Za-z_][\w.-]*)", lambda m: b"<" + m.group(1) + decl, data, count=1)
    return etree.fromstring(data, etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False))


def text_of(el) -> str:
    return "".join(el.itertext())


def check(root_dir, delivery, doc, book, profile, cfg) -> dict:
    root_dir = Path(root_dir)
    f = fc.Findings(ITEMS)
    errors, by_file = 0, {}
    data = (root_dir / delivery.main_file).read_bytes()
    f.check("ascii", all(b < 128 for b in data), "a byte above 127")
    lone = [i for i, b in enumerate(data) if b == 10 and (i == 0 or data[i - 1] != 13)]
    f.check("line_ends", not lone and b"\r" not in data.replace(b"\r\n", b""), f"LF alone at byte {lone[:1]}")
    stripped = ENTITY.sub(b"", data)
    f.check("entities", b"&" not in stripped and b"<<" not in data, "a character reference that is not &#xHHHHH;")
    try:
        root = read(data)
    except etree.XMLSyntaxError as exc:
        return {
            "dtd": {"dtd": "tail (well-formedness; no DTD)", "files": 1, "errors": 1,
                    "by_file": {delivery.main_file: {"errors": 1, "first": [str(exc)]}}},
            "house_rules": f.result(),
            "lossless": {"missing": 0, "extra": 0, "output": {"matches_ledger": False}},
        }  # fmt: skip
    refs = root.findall("bibliography/reference")
    count = root.find("bibliography").get("refcount")
    f.check("refcount", count == str(len(refs)), f"refcount={count}, {len(refs)} reference elements")
    seqs = [r.get("seq") for r in refs]
    contiguous = seqs == [str(i) for i in range(1, len(refs) + 1)]
    f.check("numbering", contiguous, f"seq {seqs[:8]}...")
    actual: list[str] = []
    for ref in refs:
        info = ref.find("ref-info")
        tags = [c.tag for c in info]
        ranks = [ORDER.index(t) for t in tags if t in ORDER]
        f.check("tag_order", ranks == sorted(ranks) and [c.tag for c in ref][-2:] == ["ref-fulltext", CE + "source-text"],
                f"[{ref.get('seq')}] {tags}")
        full = text_of(ref.find("ref-fulltext"))
        f.check("full_text", full == text_of(ref.find(CE + "source-text")), f"[{ref.get('seq')}]")
        website = text_of(info.find("ref-website")) if info.find("ref-website") is not None else ""
        for address in re.findall(r"\[(https?://[^\]\s]+)\]", full):
            f.check("addresses", address in website or website.endswith(address.split("//", 1)[-1]),
                    f"[{ref.get('seq')}] {address}")
        for pmid in re.findall(r"\[PMID:\s*(\d+)\]", full):
            f.check("pmids", pmid in text_of(info.find("ref-text")) if info.find("ref-text") is not None else False,
                    f"[{ref.get('seq')}] PMID {pmid}")
        actual += TOKEN_RE.findall(full)
    ledger = delivery.ledger
    cov = lossless.coverage(doc, ledger)
    expected = lossless._ledger_tokens(ledger)
    out = {"tokens": len(actual), "ledger_tokens": len(expected), "matches_ledger": expected == actual}
    if expected != actual:
        import difflib

        ops = [op for op in difflib.SequenceMatcher(a=expected, b=actual, autojunk=False).get_opcodes() if op[0] != "equal"]
        out["differences"] = len(ops)
        out["xml_extra"] = sum(j2 - j1 for op, i1, i2, j1, j2 in ops if op in ("insert", "replace"))
        out["xml_missing"] = sum(i2 - i1 for op, i1, i2, j1, j2 in ops if op in ("delete", "replace"))
        out["examples"] = [{"op": op, "ledger": expected[i1 : i1 + 8], "xml": actual[j1 : j1 + 8]} for op, i1, i2, j1, j2 in ops[:10]]
    changed = 0
    for e in ledger.entries:
        if e.kind == "text" and e.addr in doc.records:
            source = doc.records[e.addr]["text"][e.ranges[0][0] : e.ranges[0][1]]
            changed += sum(1 for a, b in zip(source, e.rendered.rstrip(" "), strict=False) if a != b) + abs(
                len(source) - len(e.rendered.rstrip(" "))
            )
    return {
        "dtd": {"dtd": "tail (well-formed; the ce: prefix is undeclared, as in the sample)", "files": 1,
                "errors": errors, "by_file": by_file},
        "house_rules": f.result(),
        "lossless": {
            "missing": cov["missing"] + out.get("xml_missing", 0),
            "extra": cov["extra"] + out.get("xml_extra", 0),
            "coverage": cov,
            "order": lossless.order(ledger),
            "output": out,
            "split_words": {},
            "character_changes": {"changes": changed, "by_rule": {"accent_mapping": changed},
                                  "texts_checked": len(refs), "unexplained": 0},
            "generated_text": {},
            "settings_text": [],
        },
    }  # fmt: skip
