"""House-rule checks generated from the profile: every pattern the profile sets is checked
in the written files. Each check reports its violations with a few examples."""

from __future__ import annotations

import re
import string
from collections import defaultdict
from pathlib import Path

from lxml import etree

HOSTS = frozenset(
    {
        "para",
        "title",
        "bibliomisc",
        "primaryie",
        "secondaryie",
        "tertiaryie",
        "entry",
        "term",
        "emphasis",
        "superscript",
        "subscript",
        "ulink",
        "phrase",
    }
)
PLACEHOLDER_RE = {
    "chapter": r"(?P<chapter>\w+)",
    "part": r"(?P<part>\d+)",
    "level": r"(?P<level>\d+)",
    "n": r"(?P<n>[0-9A-Za-z]+)",
    "num": r"(?P<num>[0-9A-Za-z.\-]+)",
    "k": r"(?P<k>\d+)",
    "word": r"(?P<word>.+)",
    "isbn": r"(?P<isbn>[\w-]+)",
    "page_label": r"(?P<page_label>[\w.\-]+?)",
    "page": r"(?P<page>\d+)",
}


def _printed_label(label: str, match) -> bool:
    """A label kept as the book prints it for several figures ("Figs. 1A and B"): a word, then
    the figure's own number first. The label is the book's text; the house label is not forced
    onto it."""
    number = (match.groupdict().get("n") or "") if match else ""
    return bool(number) and bool(re.match(rf"^\S+\s+{re.escape(number)}\b", label))


def pattern_regex(pattern: str) -> re.Pattern:
    out = "^"
    for literal, name, _, _ in string.Formatter().parse(pattern):
        out += re.escape(literal)
        if name is not None:
            group = PLACEHOLDER_RE[name]
            if f"(?P<{name}>" in out:  # repeated placeholder: back reference
                group = f"(?P={name})"
            out += group
    return re.compile(out + "$")


class Checks:
    def __init__(self):
        self.results: dict[str, dict] = {}

    def add(self, name: str, item: str, bad: list, checked: int):
        self.results[name] = {
            "item": item,
            "checked": checked,
            "violations": len(bad),
            "examples": [str(b)[:200] for b in bad[:5]],
        }


def run(root: Path, delivery, doc, book, profile) -> dict:
    p = profile
    checks = Checks()
    parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
    main_path = root / delivery.main_file
    tree = etree.parse(str(main_path), parser)
    book_el = tree.getroot()
    ids = p.get("ids")

    # ids and title roles (items 34, 35)
    def id_check(tag, pattern_key, role_key, item, where=None):
        pattern = pattern_regex(ids[pattern_key])
        role_pattern = ids.get(role_key) if role_key else None
        bad, n = [], 0
        for el in book_el.iter(tag):
            if where and not where(el):
                continue
            n += 1
            m = pattern.match(el.get("id") or "")
            if not m:
                bad.append(f"<{tag} id={el.get('id')!r}>")
                continue
            if role_pattern:
                title = el.find("title")
                expected = role_pattern.format(
                    **{k: v for k, v in m.groupdict().items()},
                    **{k: "" for k in ("num", "k", "part") if k not in m.groupdict()},
                )
                if title is None or title.get("role") != expected:
                    bad.append(
                        f"{el.get('id')}: title role "
                        f"{title.get('role') if title is not None else None!r}, "
                        f"expected {expected!r}"
                    )
        checks.add(f"ids.{tag}", item, bad, n)

    id_check("chapter", "chapter", None, "34/16")
    id_check("part", "part", None, "34")
    id_check("section", "section", "section_title_role", "34/35", where=lambda el: _in_chapter(el))
    id_check("table", "table", "table_title_role", "34/35")
    id_check("sidebar", "sidebar", "sidebar_title_role", "34/35", where=lambda el: el.get("id"))

    kinds = p.get("figures.kinds") or []
    bad, n = [], 0
    for el in book_el.iter("figure"):
        n += 1
        fid = el.get("id") or ""
        title = el.find("title")
        ok = False
        for kind in kinds:
            m = pattern_regex(kind["id"]).match(fid) or pattern_regex(
                ids["continued_figure"]
            ).match(fid)
            if m:
                ok = True
                if el.get("label", "").strip() and pattern_regex(kind["id"]).match(fid):
                    label = el.get("label")
                    if (
                        not pattern_regex(kind["label"]).match(label)
                        and not any(pattern_regex(k["label"]).match(label) for k in kinds)
                        and not _printed_label(label, m)
                    ):
                        bad.append(f"{fid}: label {label!r}")
                break
        if not ok:
            bad.append(f"figure id {fid!r} matches no figure kind pattern")
        if title is None:
            bad.append(f"{fid}: no title")
    checks.add("ids.figure_labels", "28/34/35", bad, n)

    bad = [
        f"informalfigure with {a}"
        for el in book_el.iter("informalfigure")
        for a in ("id", "label")
        if el.get(a)
    ]
    checks.add("figure_vs_informalfigure", "28", bad, len(list(book_el.iter("informalfigure"))))

    # labels
    for tag, key in (
        ("chapter", "labels.chapter"),
        ("part", "labels.part"),
        ("table", "labels.table"),
    ):
        pattern = p.get(key)
        if not pattern:
            continue
        rx = pattern_regex(pattern.replace("{n}", "{num}"))
        els = [el for el in book_el.iter(tag) if el.get("label") is not None]
        bad = [f"<{tag} label={el.get('label')!r}>" for el in els if not rx.match(el.get("label"))]
        checks.add(f"labels.{tag}", "5.1", bad, len(els))
    bad = [el.get("id") for el in book_el.iter("section") if el.get("label")]
    checks.add("labels.no_section_label", "5.2", bad, len(list(book_el.iter("section"))))

    # anchors (items 8, 32)
    anchors = list(book_el.iter("anchor"))
    allowed_titles = set(p.get("anchors.titles"))
    bad_place = []
    for a in anchors:
        parent = a.getparent()
        if parent.tag not in HOSTS:
            bad_place.append(f"{a.get('id')} directly inside <{parent.tag}>")
        elif parent.tag == "title":
            owner = parent.getparent().tag
            if owner not in allowed_titles:
                bad_place.append(f"{a.get('id')} in a <{owner}> title")
    checks.add("anchors.placement", "8/32", bad_place, len(anchors))
    seen = defaultdict(int)
    for a in anchors:
        seen[a.get("id")] += 1
    expected = {m.anchor_id for m in _marks(doc) if m.keep}
    bad = [f"{i} x{c}" for i, c in seen.items() if c > 1]
    bad += [f"missing {i}" for i in sorted(expected - set(seen))]
    bad += [f"unexpected {i}" for i in sorted(set(seen) - expected)]
    checks.add("anchors.one_per_page", "delivery", bad, len(expected))
    bad, mid_page = [], []
    if p.get("anchors.first_last_roles"):
        for chapter in book_el.iter("chapter", "part"):
            own = [a for a in chapter.iter("anchor") if _owner(a, ("chapter", "part")) is chapter]
            if not own:
                continue
            if own[0].get("role") != "first":
                bad.append(
                    f"{chapter.get('id')}: first anchor {own[0].get('id')} without role first"
                )
            if len(own) > 1 and own[-1].get("role") != "last":
                bad.append(
                    f"{chapter.get('id')}: last anchor {own[-1].get('id')} without role last"
                )
            title = chapter.find("title")
            if title is None or title.find("anchor") is None:
                mid_page.append(chapter.get("id"))  # starts mid-page: its page began earlier
    checks.add("anchors.first_last", "delivery", bad, len(list(book_el.iter("chapter", "part"))))
    checks.results["anchors.first_last"]["info_starts_mid_page"] = mid_page

    # images (items 17, 24, 33)
    fileref = pattern_regex(p.get("delivery.fileref").replace("{image}", "{word}"))
    images_dir = root / p.get("delivery.images_folder")
    stem_rx = pattern_regex(p.get("images.name"))
    front_rx = pattern_regex(p.get("images.front_name"))
    bad, names = [], []
    for data in book_el.iter("imagedata"):
        ref = data.get("fileref")
        m = fileref.match(ref)
        name = m.group("word") if m else None
        if not m:
            bad.append(f"fileref {ref!r}")
            continue
        names.append(name)
        if not (images_dir / name).exists():
            bad.append(f"{name} missing in {p.get('delivery.images_folder')}")
        stem = name.rsplit(".", 1)[0]
        if not (stem_rx.match(stem) or front_rx.match(stem)):
            bad.append(f"name {name!r}")
    checks.add("images.names", "24/33", bad, len(names))
    by_page = defaultdict(list)
    for name in names:
        stem = name.rsplit(".", 1)[0]
        m = stem_rx.match(stem) or front_rx.match(stem)
        if m and "n" in m.groupdict():
            key = m.groupdict().get("page_label") or ("fm" if front_rx.match(stem) else "")
            by_page[key].append(int(m.group("n")))
    bad = [f"{k}: {v}" for k, v in by_page.items() if v != list(range(1, len(v) + 1))]
    checks.add("images.sequence", "24", bad, len(by_page))
    big = p.get("delivery.bigimages_folder")
    if big:
        want = set()
        for fig in book_el.iter("figure"):
            label = (fig.get("label") or "").strip()
            for data in fig.iter("imagedata"):
                m = fileref.match(data.get("fileref"))
                if m and (label or p.get("images.big_include") == "all_figures"):
                    want.add(m.group("word"))
        have = {f.name for f in (root / big).glob("*")} if (root / big).exists() else set()
        bad = [f"missing {n}" for n in sorted(want - have)] + [
            f"extra {n}" for n in sorted(have - want)
        ]
        checks.add("bigimages.complete", "17", bad, len(want))

    # files: chapter file = chapter id (item 16), split files equal the main file
    if p.get("delivery.split_files"):
        bad = []
        main_chapters = {el.get("id"): el for el in book_el.iter("chapter")}
        for rel, role in delivery.split_files.items():
            if role in ("front", "index"):
                continue
            path = root / rel
            stem = Path(rel).stem
            expected_name = p.get("delivery.chapter_file").format(chapter_id=role)
            if Path(rel).name != expected_name or stem != role:
                bad.append(f"{rel}: chapter id {role}")
            split = etree.parse(str(path), parser).getroot()
            chapter = split if split.tag == "chapter" else split.find("chapter")
            if chapter is None or chapter.get("id") != role:
                bad.append(
                    f"{rel}: holds chapter {chapter.get('id') if chapter is not None else None}"
                )
                continue
            if etree.tostring(chapter, method="c14n") != etree.tostring(
                main_chapters[role], method="c14n"
            ):
                bad.append(f"{rel}: differs from the main file")
        checks.add("files.chapter_files", "16", bad, len(delivery.split_files))

    # page_info (item 15)
    info = p.get("delivery.page_info.file")
    if info:
        bad = []
        pi = etree.parse(str(root / info), parser).getroot()
        rows = [
            (c.findtext("chnumber"), c.findtext("firstpage"), c.findtext("lastpage"))
            for c in pi.iter("ch")
        ]
        chapters = [c.get("id") for c in book_el.iter("chapter")]
        if [r[0] for r in rows] != chapters:
            bad.append(f"chapters {[r[0] for r in rows]} != {chapters}")
        anchor_label = {m.anchor_id: (book.pages[m.page - 1].get("label")) for m in _marks(doc)}
        for chapter in book_el.iter("chapter"):
            own = [a for a in chapter.iter("anchor") if a.get("role") in ("first", "last")]
            row = next((r for r in rows if r[0] == chapter.get("id")), None)
            if row and own:
                first = anchor_label.get(own[0].get("id"))
                last = anchor_label.get(own[-1].get("id")) if len(own) > 1 else first
                if (row[1], row[2]) != (first, last):
                    bad.append(f"{row}: anchors say {first}-{last}")
        checks.add("page_info", "15", bad, len(rows))

    # characters (items 18, 19, 20)
    escape = p.get("characters.escape") or {}
    raw = main_path.read_text("utf-8")
    bad = []
    for name in p.get("characters.forbidden_named_entities") or []:
        count = raw.count(f"&{name};")
        if count:
            bad.append(f"&{name}; x{count}")
    if p.get("characters.non_ascii") == "hex4":
        count = sum(1 for ch in raw if ord(ch) > 127)
        if count:
            bad.append(f"{count} raw non-ASCII characters")
    body = raw[raw.find("<" + book_el.tag) :]
    for segment in re.findall(r">([^<]*)<", body):
        for ch in escape:
            if ch != "&" and ch in segment:
                bad.append(f"raw {ch!r} in text: {segment[:60]!r}")
                break
    checks.add("characters.entities", "18/19/20", bad, 1)

    # tables (items 21, 38)
    bad = [
        etree.tostring(e)[:80]
        for e in book_el.iter("entry")
        if len(e) == 1 and e[0].tag == "para" and not len(e[0]) and not (e[0].text or "").strip()
    ]
    checks.add("tables.no_empty_entry_para", "21", bad, len(list(book_el.iter("entry"))))
    bad = [
        el.get("id") or el.tag
        for el in book_el.iter("table", "informaltable")
        if el.get("frame") == "none"
    ]
    checks.add("tables.no_frame_none", "38", bad, len(list(book_el.iter("table", "informaltable"))))

    # structure (items 26, 27, 29, 30)
    rules = set(p.get("rules") or [])
    if "sidebar_not_in_list" in rules:
        bad = [
            s.get("id") or "sidebar"
            for s in book_el.iter("sidebar")
            if any(a.tag in ("itemizedlist", "orderedlist") for a in s.iterancestors())
        ]
        checks.add("sidebar.not_in_list", "26", bad, len(list(book_el.iter("sidebar"))))
    if "sidebar_children_in_para" in rules:
        bad = [
            f"<{c.tag}> directly in sidebar"
            for s in book_el.iter("sidebar")
            for c in s
            if c.tag
            in ("itemizedlist", "orderedlist", "figure", "table", "informalfigure", "informaltable")
        ]
        checks.add("sidebar.children_in_para", "27", bad, len(list(book_el.iter("sidebar"))))
    if "nested_list_in_para" in rules:
        bad = [
            f"list directly in {li.getparent().tag}/listitem"
            for li in book_el.iter("listitem")
            for c in li
            if c.tag in ("itemizedlist", "orderedlist")
        ]
        checks.add("lists.nested_in_para", "29", bad, len(list(book_el.iter("listitem"))))
    if "list_in_entry_in_para" in rules:
        bad = [
            e.get("colname")
            for e in book_el.iter("entry")
            for c in e
            if c.tag in ("itemizedlist", "orderedlist")
        ]
        checks.add("lists.in_entry_in_para", "29", bad, len(list(book_el.iter("entry"))))
    bad = [b.sourceline for b in book_el.iter("bibliography") if not b.get("id")]
    checks.add("bibliography.id", "30", bad, len(list(book_el.iter("bibliography"))))
    total = sum(r["violations"] for r in checks.results.values())
    return {"violations": total, "checks": checks.results}


def _in_chapter(el) -> bool:
    return any(a.tag == "chapter" for a in el.iterancestors())


def _owner(el, tags):
    for a in el.iterancestors():
        if a.tag in tags:
            return a
    return None


def _marks(doc):
    from ..writers.docbook import _walk_marks

    seen = set()
    for m in _walk_marks(doc):
        if id(m) not in seen:
            seen.add(id(m))
            yield m
