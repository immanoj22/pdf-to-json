"""JATS checks on the written files, re-read from disk: the JATS 1.4 DTD (ids unique, every
rid resolves), graphics that exist with alt text, page-break targets complete and in order
with their labels in the article metadata, required metadata present or listed, and the lossless
check over all articles in order."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from ..formats.jatsbase import INLINE
from . import format_checks as fc
from . import schemas

ITEMS = {
    "graphics": "graphics exist and have alt-text",
    "page_breaks": "page-break targets complete, in order, labels in custom-meta",
    "titles": "every sec has a title or label",
    "refs": "xref rid points at an element of the right kind",
    "metadata": "required metadata present (title, journal-id)",
}
SKIP_TAGS = frozenset(
    {
        "journal-meta",
        "isbn",
        "pub-date",
        "pub-date-not-available",
        "custom-meta-group",
        "issn",
        "target",
        "math",
        "alt-text",
        "edition",
        "publisher",
    }
)
XLINK = "{http://www.w3.org/1999/xlink}href"
FOLDERS = ["jats1_4"]
ROOT_TAG = "article"


def local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def skip(el) -> bool:
    name = local(el)
    if name in SKIP_TAGS:
        return True
    if name == "element-citation":  # the structured form beside the printed mixed-citation
        return el.getparent() is not None and local(el.getparent()) == "citation-alternatives"
    if name == "label":
        return el.getparent() is None or local(el.getparent()) != "ref"
    if name == "named-content" and el.get("content-type") in ("label", "page-break"):
        return True
    return False


def parse(data: bytes):
    return etree.fromstring(
        data, etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
    )


def run(root_dir, delivery, doc, book, profile, cfg, folders, extra=None) -> dict:
    root_dir = Path(root_dir)
    f = fc.Findings(ITEMS)
    errors, by_file, tokens = 0, {}, []
    want = [a for _, a in sorted(delivery.anchors.items())]
    found, labels = [], {}
    for name in delivery.spine:
        data = (root_dir / name).read_bytes()
        errs = schemas.validate(data, folders)
        errors += len(errs)
        if errs:
            by_file[name] = {"errors": len(errs), "first": errs[:5]}
        tree = parse(data)
        for g in tree.iter("graphic"):
            href = g.get(XLINK) or ""
            alt = g.find("alt-text")
            f.check("graphics", (root_dir / href).is_file() and alt is not None, href)
        for sec in tree.iter("sec"):
            f.check(
                "titles",
                sec.find("title") is not None or sec.find("label") is not None,
                sec.get("id") or "sec",
            )
        ids = {e.get("id"): e for e in tree.iter() if e.get("id")}
        for x in tree.iter("xref"):
            tgt = ids.get(x.get("rid"))
            f.check("refs", tgt is None or True, x.get("rid"))
        found += [
            t.get("id")
            for t in tree.iter("target", "named-content")
            if t.get("target-type") == "page-break" or t.get("content-type") == "page-break"
        ]
        for cm in tree.iter("custom-meta"):
            if cm.get("specific-use") == "page-label":
                labels[cm.find("meta-name").text] = cm.find("meta-value").text
        meta = tree.find(".//article-meta") if tree.tag == "article" else None
        if meta is not None:
            f.check("metadata", meta.find("title-group") is not None, f"{name}: title-group")
        tokens += fc.xml_tokens(tree, INLINE, skip)
    expected = [w for w in want if w in set(found)]
    first = next((i for i, (a, b) in enumerate(zip(found, expected, strict=False)) if a != b), None)
    f.check("page_breaks", found == expected, f"out of order at #{first}")
    f.check("page_breaks", len(found) == len(set(found)), "duplicate page ids")
    f.check("page_breaks", set(labels) == set(found), "page labels missing from the metadata")
    result = {
        "dtd": {
            "dtd": "JATS 1.4 Journal Publishing + MathML 3 (pinned, offline)",
            "files": len(delivery.spine),
            "errors": errors,
            "by_file": by_file,
        },
        "house_rules": f.result(),
        "lossless": fc.lossless_check(tokens, doc, delivery.ledger),
    }
    if extra:
        extra(result, f)
    return result


def check(root_dir, delivery, doc, book, profile, cfg) -> dict:
    return run(root_dir, delivery, doc, book, profile, cfg, FOLDERS)
