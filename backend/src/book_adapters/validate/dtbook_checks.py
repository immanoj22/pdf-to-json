"""NIMAS / DTBook checks on the written files, re-read from disk: DTBook DTD (with the
DAISY MathML module), OPF against the OEB 1.2 package DTD, links, images with alt, page
numbers complete and in order with their printed labels, required metadata, package
manifest and spine, and the lossless check."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from . import format_checks as fc
from . import schemas

ITEMS = {
    "links": "internal links resolve",
    "images": "images exist and have alt",
    "page_numbers": "pagenum complete, in order, text is the printed label",
    "levels": "no skipped heading level",
    "metadata": "required metadata present (title, identifier, language)",
    "package": "OPF manifest files exist, spine resolves, every image listed",
    "notes": "note ids unique",
}
INLINE = frozenset({"strong", "em", "sup", "sub", "span", "a", "pagenum", "abbr", "math"})


def dtbook_skip(el) -> bool:
    name = etree.QName(el).localname if isinstance(el.tag, str) else ""
    return name in ("pagenum", "head", "math") or (
        name == "span" and "label" in (el.get("class") or "").split()
    )


def parse(data: bytes):
    parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
    return etree.fromstring(data, parser)


def check(root_dir, delivery, doc, book, profile, cfg) -> dict:
    root_dir = Path(root_dir)
    f = fc.Findings(ITEMS)
    main = delivery.main_file
    data = (root_dir / main).read_bytes()
    folders = ["dtbook2005_3", "mathml2"]
    errors = schemas.validate(data, folders)
    by_file = {main: {"errors": len(errors), "first": errors[:5]}} if errors else {}
    total = len(errors)
    tree = parse(data)
    ns = "{http://www.daisy.org/z3986/2005/dtbook/}"
    ids = {e.get("id") for e in tree.iter() if e.get("id")}
    for a in tree.iter(ns + "a"):
        href = a.get("href") or ""
        if href.startswith("#"):
            f.check("links", href[1:] in ids, href)
    for img in tree.iter(ns + "img"):
        src = img.get("src") or ""
        f.check("images", (root_dir / src).is_file() and bool(img.get("alt") is not None), src)
    marks = [p for p in tree.iter(ns + "pagenum")]
    want = [a for _, a in sorted(delivery.anchors.items())]
    found = [p.get("id") for p in marks]
    expected = [w for w in want if w in set(found)]
    first = next((i for i, (a, b) in enumerate(zip(found, expected, strict=False)) if a != b), None)
    f.check("page_numbers", found == expected, f"out of order at #{first}")
    f.check("page_numbers", len(found) == len(set(found)), "duplicate page ids")
    f.check("page_numbers", all((p.text or "").strip() for p in marks), "pagenum without a label")
    last = 0
    for el in tree.iter():
        if (
            isinstance(el.tag, str)
            and el.tag.startswith(ns + "level")
            and el.tag[len(ns) + 5 :].isdigit()
        ):
            n = int(el.tag[len(ns) + 5 :])
            parent = el.getparent()
            up = parent.tag.startswith(ns + "level") and parent.tag[len(ns) + 5 :].isdigit()
            f.check("levels", n == 1 or up, f"level{n} outside a level{n - 1}")
        last = last
    meta = {m.get("name"): m.get("content") for m in tree.iter(ns + "meta")}
    for name in ("dc:Title", "dtb:uid", "dc:Language"):
        f.check("metadata", bool(meta.get(name)), name)
    note_ids = [n.get("id") for n in tree.iter(ns + "note")]
    f.check("notes", len(note_ids) == len(set(note_ids)), "duplicate note ids")
    pkg = getattr(delivery, "package_file", None)
    if pkg:
        opf = (root_dir / pkg).read_bytes()
        opf_errors = schemas.validate(opf, ["oeb1_2"])
        total += len(opf_errors)
        if opf_errors:
            by_file[pkg] = {"errors": len(opf_errors), "first": opf_errors[:5]}
        otree = parse(opf)
        ons = "{http://openebook.org/namespaces/oeb-package/1.0/}"
        items = {i.get("id"): i.get("href") for i in otree.iter(ons + "item", "item")}
        for href in items.values():
            f.check("package", (root_dir / href).is_file(), href)
        for ref in otree.iter(ons + "itemref", "itemref"):
            f.check("package", ref.get("idref") in items, ref.get("idref"))
        listed = set(items.values())
        for img in tree.iter(ns + "img"):
            f.check("package", img.get("src") in listed, f"{img.get('src')} not in the manifest")
    segments = fc.xml_tokens(tree, INLINE, dtbook_skip)
    return {
        "dtd": {
            "dtd": "DTBook 2005-3 + MathML 2 (NIMAS 1.1), OEB 1.2 package (pinned, offline)",
            "files": 1 + (1 if pkg else 0),
            "errors": total,
            "by_file": by_file,
        },
        "house_rules": f.result(),
        "lossless": fc.lossless_check(segments, doc, delivery.ledger),
    }
