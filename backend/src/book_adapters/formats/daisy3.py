"""DAISY 3 (ANSI/NISO Z39.86-2005) text-only DTB around a DTBook file: SMIL files (the
standard requires at least one, and only SMIL files in the spine, also for a text-only book),
the NCX with navigation points and page list, the resource file and the package file.

Version: Z39.86-2005 (DTBook 2005-3, NCX 2005-1, DTB SMIL 2005-2, Resource 2005-1, package =
OEB 1.2 package DTD). Files written: ``<isbn>.xml``, ``<isbn>.opf``, ``<isbn>.ncx``,
``<isbn>.res``, ``<isbn>_NNN.smil``, images. ``dtb:multimediaType`` is ``textNCX``."""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from lxml import etree

NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
SMIL_NS = "http://www.w3.org/2001/SMIL20/"
RES_NS = "http://www.daisy.org/z3986/2005/resource/"
DT = "{http://www.daisy.org/z3986/2005/dtbook/}"
SYNC = (
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hd",
    "p",
    "li",
    "dt",
    "caption",
    "doctitle",
    "docauthor",
)
STRUCT = {"pagenum": ("pagenum", "PAGE_NUMBER"), "note": ("note", "NOTE")}
LEVEL = ("level1", "level2", "level3", "level4", "level5", "level6")
MEDIA = {
    "dtbook": "application/x-dtbook+xml",
    "ncx": "application/x-dtbncx+xml",
    "smil": "application/smil",
    "res": "application/x-dtbresource+xml",
    "package": "text/xml",
}


def local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def flat(el) -> str:
    return " ".join("".join(el.itertext()).split())


def assign_ids(root, smil_of) -> list[etree._Element]:
    """Every element to synchronize carries an id (kept if it has one) and, once its SMIL
    par is known, a smilref. Returns the synchronized elements in document order."""
    out, n = [], 0
    for el in root.iter():
        name = local(el)
        if name in SYNC or name in ("pagenum", "note"):
            n += 1
            if not el.get("id"):
                el.set("id", f"dtb{n}")
            out.append(el)
    return out


def smil_documents(sync, dtbook_name: str, uid: str, split: str, generator: str):
    """[(smil file index, bytes, {element id: (file index, par id)})] grouped by top-level
    level1 (or one file). ``sync`` is [(element, top-level group number)]."""
    groups: dict[int, list] = {}
    for el, g in sync:
        groups.setdefault(g if split == "level1" else 0, []).append(el)
    kinds = {name for els in groups.values() for e in els for name in [local(e)] if name in STRUCT}
    custom = {k: STRUCT[k] for k in sorted(kinds)}
    files, where = [], {}
    for k, (_, els) in enumerate(sorted(groups.items()), 1):
        out = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE smil PUBLIC "-//NISO//DTD dtbsmil 2005-2//EN" '
            '"http://www.daisy.org/z3986/2005/dtbsmil-2005-2.dtd">',
            f'<smil xmlns="{SMIL_NS}">',
            "<head>",
            f'<meta name="dtb:uid" content={quoteattr(uid)}/>',
            f'<meta name="dtb:generator" content={quoteattr(generator)}/>',
            '<meta name="dtb:totalElapsedTime" content="0"/>',
        ]
        if custom:
            out.append("<customAttributes>")
            for name, (cid, _) in custom.items():
                state = "false" if name == "pagenum" else "true"
                out.append(f'<customTest id="{cid}" defaultState="{state}" override="visible"/>')
            out.append("</customAttributes>")
        out += ["</head>", "<body>", f'<seq id="seq{k}">']
        for i, el in enumerate(els, 1):
            name = local(el)
            par = f"par{k}_{i}"
            test = f' customTest="{STRUCT[name][0]}"' if name in STRUCT else ""
            out.append(
                f'<par id="{par}" class={quoteattr(name)}{test}>'
                f'<text id="txt{k}_{i}" src={quoteattr(dtbook_name + "#" + el.get("id"))}/></par>'
            )
            where[el.get("id")] = (k, par)
        out += ["</seq>", "</body>", "</smil>", ""]
        files.append((k, "\n".join(out).encode("utf-8")))
    return files, where, custom


def ncx_bytes(root, where, smil_name, uid, title, authors, lang, generator, labels):
    """The NCX: navMap from the level/heading structure, pageList from the page numbers.
    Returns (bytes, stats)."""
    items = []  # (kind, element, label, depth)
    for el in root.iter():
        name = local(el)
        if name in LEVEL:
            h = next((c for c in el if local(c) == "h" + name[5] or local(c) == "hd"), None)
            if h is not None and h.get("id") in where:
                items.append(("nav", h, flat(h) or el.get("class") or name, int(name[5]), el))
        elif name == "pagenum" and el.get("id") in where:
            items.append(("page", el, flat(el), 0, el))
    order = {id(e): i for i, e in enumerate(root.iter())}
    items.sort(key=lambda it: order[id(it[1])])
    play = {id(it[1]): n for n, it in enumerate(items, 1)}
    nav_items = [it for it in items if it[0] == "nav"]
    pages = [it for it in items if it[0] == "page"]

    def content(el):
        k, par = where[el.get("id")]
        return f'<content src="{smil_name(k)}#{par}"/>'

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" '
        '"http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">',
        f'<ncx version="2005-1" xml:lang={quoteattr(lang)} xmlns="{NCX_NS}">',
        "<head>",
    ]
    if pages:
        out.append('<smilCustomTest id="pagenum" defaultState="false" override="visible" '
                   'bookStruct="PAGE_NUMBER"/>')  # fmt: skip
    if any(local(e) == "note" for e in root.iter()):
        out.append('<smilCustomTest id="note" defaultState="true" override="visible" '
                   'bookStruct="NOTE"/>')  # fmt: skip
    depth = max((it[3] for it in nav_items), default=1)
    numeric = [int(it[2]) for it in pages if it[2].isdigit()]
    kinds = {"front": 0, "normal": 0, "special": 0}
    for it in pages:
        kinds[it[4].get("page", "normal")] += 1
    metas = [
        ("dtb:uid", uid),
        ("dtb:depth", str(depth)),
        ("dtb:generator", generator),
        ("dtb:totalPageCount", str(len(pages))),
        ("dtb:maxPageNumber", str(max(numeric, default=0))),
    ]
    out += [f"<meta name={quoteattr(k)} content={quoteattr(v)}/>" for k, v in metas]
    out += ["</head>", f"<docTitle><text>{escape(title)}</text></docTitle>"]
    out += [f"<docAuthor><text>{escape(a)}</text></docAuthor>" for a in authors]
    out.append("<navMap>")
    stack: list[int] = []
    for _kind, h, label, lvl, lv in nav_items:
        while stack and stack[-1] >= lvl:
            stack.pop()
            out.append("</navPoint>")
        stack.append(lvl)
        cls = (lv.get("class") or "section").split()[0]
        out.append(
            f'<navPoint id="np{play[id(h)]}" class={quoteattr(cls)} playOrder="{play[id(h)]}">'
            f"<navLabel><text>{escape(label)}</text></navLabel>{content(h)}"
        )
    out += ["</navPoint>"] * len(stack)
    if not nav_items:
        out.append('<navPoint id="np0" playOrder="0"><navLabel><text/></navLabel></navPoint>')
    out.append("</navMap>")
    if pages:
        out.append("<pageList>")
        out.append(f"<navLabel><text>{escape(labels.get('pagelist', 'Pages'))}</text></navLabel>")
        for _kind, el, label, _d, _lv in pages:
            value = f' value="{int(label)}"' if label.isdigit() and int(label) > 0 else ""
            out.append(
                f'<pageTarget id="pt{play[id(el)]}" type="{el.get("page", "normal")}"{value} '
                f'playOrder="{play[id(el)]}"><navLabel><text>{escape(label)}</text></navLabel>'
                f"{content(el)}</pageTarget>"
            )
        out.append("</pageList>")
    out += ["</ncx>", ""]
    stats = {"depth": depth, "pages": len(pages), "nav_points": len(nav_items), "kinds": kinds}
    return "\n".join(out).encode("utf-8"), stats


def resource_bytes(lang: str, labels: dict) -> bytes:
    rows = [("pagenum", labels["pagenum"]), ("note", labels["note"]),
            ("sidebar", labels["sidebar"]), ("prodnote", labels["prodnote"])]  # fmt: skip
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE resources PUBLIC "-//NISO//DTD resource 2005-1//EN" '
        '"http://www.daisy.org/z3986/2005/resource-2005-1.dtd">',
        f'<resources xmlns="{RES_NS}" version="2005-1">',
        '<scope nsuri="http://www.daisy.org/z3986/2005/dtbook/">',
    ]
    for i, (name, text) in enumerate(rows, 1):
        out.append(
            f'<nodeSet id="ns{i}" select="//{name}"><resource xml:lang={quoteattr(lang)}>'
            f"<text>{escape(text)}</text></resource></nodeSet>"
        )
    out += ["</scope>", "</resources>", ""]
    return "\n".join(out).encode("utf-8")
