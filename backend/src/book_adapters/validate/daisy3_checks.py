"""DAISY 3 text-only DTB checks on the written files, re-read from disk: every file against
its official DTD (DTBook + MathML, SMIL, NCX, resource, OEB package), cross-file references
(NCX -> SMIL -> DTBook ids), play order, page list against the page numbers, the navigation
metadata (dtb:depth, dtb:totalPageCount), the package (manifest complete, spine = SMIL files
only), and the lossless check on the DTBook file."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from . import dtbook_checks as dc
from . import format_checks as fc
from . import schemas

ITEMS = {
    **dc.ITEMS,
    "smil": "SMIL: every par points at a DTBook id; every synchronized element is in a SMIL",
    "ncx": "NCX: content resolves to a par; playOrder unique and ascending",
    "ncx_meta": "NCX metadata matches the content (depth, page count)",
    "spine": "spine lists only SMIL files, all in the manifest",
}
NCX = "{http://www.daisy.org/z3986/2005/ncx/}"
SMIL = "{http://www.w3.org/2001/SMIL20/}"
DT = "{http://www.daisy.org/z3986/2005/dtbook/}"
FOLDERS = {
    "smil": ["daisy3"],
    "ncx": ["daisy3"],
    "res": ["daisy3"],
    "opf": ["oeb1_2"],
}


def check(root_dir, delivery, doc, book, profile, cfg) -> dict:
    root_dir = Path(root_dir)
    base = dc.check(root_dir, delivery, doc, book, profile, cfg)
    f = fc.Findings(ITEMS)
    for name, item in base["house_rules"]["checks"].items():
        f.checks[name] = item
    errors = base["dtd"]["errors"]
    by_file = dict(base["dtd"]["by_file"])
    files = 1 + (1 if getattr(delivery, "package_file", None) else 0)
    for rel, role in sorted(delivery.split_files.items()):
        if role not in ("smil", "ncx", "res"):
            continue
        errs = schemas.validate((root_dir / rel).read_bytes(), FOLDERS[role])
        files += 1
        errors += len(errs)
        if errs:
            by_file[rel] = {"errors": len(errs), "first": errs[:5]}
    tree = dc.parse((root_dir / delivery.main_file).read_bytes())
    ids = {e.get("id") for e in tree.iter() if e.get("id")}
    sync_ids = {e.get("id") for e in tree.iter() if e.get("smilref")}
    parts = {}  # smil file -> {par id}
    targets = set()
    for rel in delivery.smil_files:
        st = dc.parse((root_dir / rel).read_bytes())
        parts[rel] = {p.get("id") for p in st.iter(SMIL + "par")}
        for text in st.iter(SMIL + "text"):
            ref = text.get("src", "")
            file, _, frag = ref.partition("#")
            f.check("smil", file == delivery.main_file and frag in ids, ref)
            targets.add(frag)
    f.check("smil", sync_ids <= targets, "synchronized elements missing from the SMIL files")
    for e in tree.iter():
        ref = e.get("smilref")
        if ref:
            file, _, par = ref.partition("#")
            f.check("smil", par in parts.get(file, ()), ref)
    ncx_name = next(r for r, role in delivery.split_files.items() if role == "ncx")
    ntree = dc.parse((root_dir / ncx_name).read_bytes())
    seen_orders: set[int] = set()
    for group in (NCX + "navPoint", NCX + "pageTarget"):
        last = 0
        for node in ntree.iter(group):
            po = int(node.get("playOrder"))
            f.check("ncx", po > last and po not in seen_orders, f"playOrder {po} after {last}")
            seen_orders.add(po)
            last = po
            src = node.find(NCX + "content").get("src")
            file, _, par = src.partition("#")
            f.check("ncx", par in parts.get(file, ()), src)
    meta = {m.get("name"): m.get("content") for m in ntree.iter(NCX + "meta")}
    points = list(ntree.iter(NCX + "navPoint"))
    pages = list(ntree.iter(NCX + "pageTarget"))
    f.check("ncx_meta", int(meta["dtb:totalPageCount"]) == len(pages), "totalPageCount")
    marks = [p.get("id") for p in tree.iter(DT + "pagenum")]
    f.check("ncx_meta", len(marks) == len(pages), "pageList does not list every pagenum")
    depth = 0
    for p in points:
        d = 1 + sum(1 for a in p.iterancestors() if a.tag == NCX + "navPoint")
        depth = max(depth, d)
    f.check("ncx_meta", points == [] or int(meta["dtb:depth"]) == depth, "dtb:depth")
    pkg = etree.fromstring(
        (root_dir / delivery.package_file).read_bytes(), etree.XMLParser(load_dtd=False)
    )
    ons = "{http://openebook.org/namespaces/oeb-package/1.0/}"
    items = {i.get("id"): i for i in pkg.iter(ons + "item", "item")}
    listed = {i.get("href") for i in items.values()}
    f.check("spine", delivery.package_file in listed, "package file not in its own manifest")
    for rel in delivery.files:
        if rel.endswith(".xml") or rel.endswith((".ncx", ".res", ".smil", ".opf")):
            f.check("spine", rel in listed, f"{rel} not in the manifest")
    for ref in pkg.iter(ons + "itemref", "itemref"):
        item = items.get(ref.get("idref"))
        f.check(
            "spine",
            item is not None and item.get("media-type") == "application/smil",
            ref.get("idref"),
        )
    base["dtd"].update(
        {
            "dtd": "DAISY 3 / Z39.86-2005: DTBook, SMIL 2005-2, NCX 2005-1, resource 2005-1, "
            "OEB 1.2 package (pinned, offline)",
            "files": files,
            "errors": errors,
            "by_file": by_file,
        }
    )
    base["house_rules"] = f.result()
    return base
