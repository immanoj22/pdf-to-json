"""Compare our delivery with a real one: element counts side by side (whole book and per
chapter), attribute patterns, files, images and page_info, and the biggest differences.
Labelling a difference "adapter" or "Stage 1" is a human judgement recorded in the report;
this module gives the numbers."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from lxml import etree

KEY_ELEMENTS = (
    "part",
    "chapter",
    "section",
    "para",
    "itemizedlist",
    "orderedlist",
    "listitem",
    "figure",
    "informalfigure",
    "table",
    "informaltable",
    "row",
    "entry",
    "sidebar",
    "bibliography",
    "bibliomixed",
    "index",
    "indexdiv",
    "indexentry",
    "anchor",
    "emphasis",
    "superscript",
    "subscript",
    "ulink",
    "qandaset",
    "preface",
    "dedication",
    "legalnotice",
    "authorgroup",
    "caption",
    "partintro",
)


def _parse(path: Path):
    parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False, recover=True)
    return etree.parse(str(path), parser).getroot()


def _main_file(folder: Path) -> Path:
    candidates = [p for p in folder.glob("*.xml") if p.name != "page_info.xml"]
    if len(candidates) != 1:
        raise ValueError(f"{folder}: expected one main XML file, found {candidates}")
    return candidates[0]


def counts(root) -> Counter:
    return Counter(e.tag for e in root.iter() if isinstance(e.tag, str))


def role_counts(root) -> Counter:
    out = Counter()
    for e in root.iter():
        if not isinstance(e.tag, str):
            continue
        role = e.get("role")
        if role and not re.match(r"ch\d+", role):
            out[f"{e.tag}@role={role}"] += 1
        for attr in ("mark", "numeration", "frame"):
            if e.get(attr):
                out[f"{e.tag}@{attr}={e.get(attr)}"] += 1
    return out


def per_chapter(root) -> dict[str, dict]:
    out = {}
    for chapter in root.iter("chapter"):
        c = Counter(e.tag for e in chapter.iter() if isinstance(e.tag, str))
        out[chapter.get("id") or "?"] = {
            k: c.get(k, 0)
            for k in (
                "section",
                "para",
                "figure",
                "table",
                "itemizedlist",
                "orderedlist",
                "bibliomixed",
                "sidebar",
                "anchor",
            )
        }
    return out


def page_info(folder: Path) -> list[tuple]:
    path = folder / "page_info.xml"
    if not path.exists():
        return []
    root = _parse(path)
    return [
        (c.findtext("chnumber"), c.findtext("firstpage"), c.findtext("lastpage"))
        for c in root.iter("ch")
    ]


def compare_deliveries(ours: Path, reference: Path) -> dict:
    a_main, b_main = _main_file(ours), _main_file(reference)
    a, b = _parse(a_main), _parse(b_main)
    ca, cb = counts(a), counts(b)
    tags = sorted(set(ca) | set(cb))
    table = {
        t: {"ours": ca.get(t, 0), "reference": cb.get(t, 0), "diff": ca.get(t, 0) - cb.get(t, 0)}
        for t in tags
    }
    biggest = sorted(
        ((t, v) for t, v in table.items() if v["diff"]), key=lambda kv: (-abs(kv[1]["diff"]), kv[0])
    )[:25]
    ra, rb = role_counts(a), role_counts(b)
    roles = {
        k: {"ours": ra.get(k, 0), "reference": rb.get(k, 0)}
        for k in sorted(set(ra) | set(rb))
        if ra.get(k, 0) != rb.get(k, 0)
    }
    pa, pb = per_chapter(a), per_chapter(b)
    chapters = {
        cid: {"ours": pa.get(cid), "reference": pb.get(cid)}
        for cid in sorted(set(pa) | set(pb), key=_natural)
    }
    files_a = sorted(str(p.relative_to(ours)) for p in ours.rglob("*") if p.is_file())
    files_b = sorted(str(p.relative_to(reference)) for p in reference.rglob("*") if p.is_file())
    labels = {
        "ours": Counter(e.get("label") for e in a.iter("figure", "table", "chapter", "part")),
        "reference": Counter(e.get("label") for e in b.iter("figure", "table", "chapter", "part")),
    }
    return {
        "main_files": [a_main.name, b_main.name],
        "elements": table,
        "biggest_differences": [{"element": t, **v} for t, v in biggest],
        "key_elements": {
            t: table.get(t, {"ours": 0, "reference": 0, "diff": 0}) for t in KEY_ELEMENTS
        },
        "attribute_values_differing": roles,
        "per_chapter": chapters,
        "files": {
            "only_ours": sorted(set(files_a) - set(files_b)),
            "only_reference": sorted(set(files_b) - set(files_a)),
            "common": len(set(files_a) & set(files_b)),
        },
        "labels": {k: dict(sorted((str(x), n) for x, n in v.items())) for k, v in labels.items()},
        "page_info": {
            "ours": page_info(ours),
            "reference": page_info(reference),
            "equal": page_info(ours) == page_info(reference),
        },
        "chapter_titles": {
            "ours": [_title(c) for c in a.iter("chapter")],
            "reference": [_title(c) for c in b.iter("chapter")],
        },
    }


def _title(el) -> str:
    t = el.find("title")
    return " ".join("".join(t.itertext()).split()) if t is not None else ""


def _natural(key: str):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", key)]
