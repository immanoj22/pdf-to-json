"""Breakdowns that explain element-count differences, and the label of each difference:
``adapter`` (the adapter's mapping decides it), ``Stage 1`` (book.json decides it),
``source`` (the PDF lacks it), ``reference`` (the reference delivery's own slip) or
``check`` (no rule explains it; a person decides). Labels come from evidence in the two
deliveries and, when given, the book folder; the evidence is in the report."""

from __future__ import annotations

import re
from collections import Counter


def link_kind(el) -> str:
    url = el.get("url", "") if el.tag == "ulink" else ""
    if el.tag == "email":
        return "email"
    if any(a.tag == "index" for a in el.iterancestors()):
        return "index page link"
    if url.startswith("mailto:"):
        return "mailto"
    if re.match(r"(?i)(https?://|www\.)", url):
        return "web"
    if re.match(r"#ch\w*bib", url):
        return "citation"
    if re.match(r"#page", url):
        return "page"
    if url.startswith("#"):
        kind = re.sub(r"[\d_]+", "", url[1:])
        return f"object ({kind})"
    return "other"


def links(root) -> Counter:
    return Counter(link_kind(e) for e in root.iter("ulink", "email"))


def sidebars(root) -> Counter:
    out = Counter()
    for s in root.iter("sidebar"):
        content = [c for c in s if c.tag != "title"]
        tables = [c for c in content if c.tag in ("table", "informaltable")] + [
            t for c in content if c.tag == "para" for t in c if t.tag in ("table", "informaltable")
        ]
        in_partintro = any(a.tag == "partintro" for a in s.iterancestors())
        if in_partintro:
            out["part intro"] += 1
        elif tables and len(content) == len(tables):
            out["holds only a table"] += 1
        else:
            out["box"] += 1
    return out


def _norm(text: str) -> str:
    return re.sub(r"\W+", "", text.casefold())


def _leaf_paras(root, skip=("entry", "legalnotice")):
    out = []
    for e in root.iter("para"):
        if any(a.tag in skip for a in e.iterancestors()) or e.find(".//para") is not None:
            continue
        text = _norm("".join(e.itertext()))
        if text:
            out.append((text, e))
    return out


def paragraph_splits(ours, reference, units_by_text=None) -> dict:
    """Pairs of consecutive paragraphs of ours that the reference holds in one paragraph,
    and reference pairs that ours holds in one. With the book's units, each split of ours is
    labelled: Stage 1 (book.json has no continuation link between the two units) or adapter
    (a continuation link exists but was not joined)."""
    ref = _leaf_paras(reference)
    mine = _leaf_paras(ours)
    ref_texts = [t for t, _ in ref]
    big = "\x00".join(ref_texts)
    split = Counter()
    examples = []
    for (a, ea), (b, eb) in zip(mine, mine[1:], strict=False):
        joined = a + b
        if len(joined) < 12 or joined not in big:  # separators keep matches inside one para
            continue
        cause = "Stage 1"
        if units_by_text is not None:
            ua, ub = units_by_text.get(a), units_by_text.get(b)
            if ua and ub and (ua.get("continues_to") or {}).get("unit") == ub.get("id"):
                cause = "adapter"
        split[cause] += 1
        if len(examples) < 8:
            examples.append(
                {
                    "cause": cause,
                    "end_of_first": "".join(ea.itertext())[-60:],
                    "start_of_second": "".join(eb.itertext())[:60],
                }
            )
    ours_big = "\x00".join(t for t, _ in mine)
    merged = 0
    for (a, _), (b, _) in zip(ref, ref[1:], strict=False):
        joined = a + b
        if len(joined) >= 12 and joined in ours_big:
            merged += 1
    return {
        "ours_split_reference_one": dict(split),
        "ours_one_reference_split": merged,
        "examples": examples,
    }


# element -> (label, reason) when nothing more specific applies
DEFAULT_LABELS = {
    "section": ("Stage 1", "sections come from book.json headings"),
    "title": ("Stage 1", "titles follow headings, figures and tables in book.json"),
    "chapter": ("Stage 1", "chapter starts come from book.json headings"),
    "part": ("Stage 1", "part starts come from book.json headings"),
    "partintro": ("Stage 1", "part openers come from book.json headings"),
    "listitem": ("Stage 1", "list items come from book.json lists"),
    "itemizedlist": ("Stage 1", "lists come from book.json lists"),
    "orderedlist": ("Stage 1", "lists come from book.json lists"),
    "figure": ("Stage 1", "numbered figures need a linked caption in book.json"),
    "informalfigure": ("Stage 1", "figures without a linked caption, or not decorative"),
    "table": ("Stage 1", "tables and their titles come from book.json"),
    "informaltable": ("Stage 1", "a table without a linked title in book.json"),
    "entry": ("Stage 1", "table cells come from book.json"),
    "row": ("Stage 1", "table rows come from book.json"),
    "colspec": ("Stage 1", "table columns come from book.json"),
    "tbody": ("Stage 1", "tables come from book.json"),
    "tgroup": ("Stage 1", "tables come from book.json"),
    "thead": ("Stage 1", "header rows come from book.json tables"),
    "abbrev": ("Stage 1", "reference entry numbers come from book.json lists"),
    "bibliomisc": ("Stage 1", "reference entries come from book.json lists"),
    "preface": ("Stage 1", "front-matter divisions start at book.json title headings"),
    "dedication": ("Stage 1", "front-matter divisions start at book.json title headings"),
    "appendix": ("Stage 1", "back-matter divisions come from book.json zones"),
    "variablelist": ("Stage 1", "definition lists come from book.json lists"),
    "qandaentry": ("Stage 1", "question sets come from book.json lists"),
    "emphasis": ("Stage 1", "styles come from book.json spans"),
    "bibliomixed": ("Stage 1", "reference entries come from book.json lists"),
    "superscript": ("Stage 1", "superscripts come from book.json spans"),
    "caption": ("Stage 1", "figure notes and credits come from book.json"),
    "anchor": ("source", "one anchor per printed page of the PDF"),
    "mediaobject": ("Stage 1", "one per figure or equation in book.json"),
    "imageobject": ("Stage 1", "one per figure or equation in book.json"),
    "imagedata": ("Stage 1", "one per figure or equation in book.json"),
    "textobject": ("Stage 1", "one per figure or equation in book.json"),
    "phrase": ("Stage 1", "one per figure or equation in book.json"),
    "legalnotice": ("adapter", "no rule says which copyright lines go after the ISBN"),
}

INDEX_ELEMENTS = ("index", "indexdiv", "indexentry", "primaryie", "secondaryie", "tertiaryie")


def label(element: str, diff: int, ctx: dict) -> tuple[str, str]:
    """Label and reason for one element-count difference."""
    if element in INDEX_ELEMENTS:
        if not ctx.get("ours_has_index"):
            if ctx.get("book_has_index") is False:
                return "source", "book.json has no index (the PDF has none)"
            return "Stage 1", "no index division in our delivery"
        return "Stage 1", "index entries and levels come from book.json"
    if element in ("ulink", "email"):
        parts = ctx.get("link_diff") or {}
        main = max(parts.items(), key=lambda kv: abs(kv[1]), default=(None, 0))[0]
        if main == "index page link" and not ctx.get("ours_has_index"):
            return label("index", diff, ctx)[0], (
                "mostly index page links: " + label("index", diff, ctx)[1]
            )
        if main in ("web", "mailto", "email"):
            return "adapter", "web and e-mail address links (rule link_urls_emails)"
        if main == "citation":
            return "Stage 1", "citation numbers need superscript spans in book.json"
        if main and main.startswith("object"):
            return "check", "object mentions link only to objects numbered in the same chapter"
        return "check", "link kinds differ: see links"
    if element == "sidebar":
        parts = ctx.get("sidebar_diff") or {}
        if parts.get("holds only a table", 0) > 0:
            return "adapter", "boxes holding only a table (profile sidebars.table_only)"
        return "Stage 1", "boxes come from book.json callout regions"
    if element == "para":
        split = ctx.get("para_split") or {}
        stage1 = split.get("ours_split_reference_one", {}).get("Stage 1", 0)
        adapter = split.get("ours_split_reference_one", {}).get("adapter", 0)
        if adapter > stage1:
            return "adapter", f"{adapter} paragraph splits with a continuation link not joined"
        if stage1:
            return "Stage 1", (
                f"{stage1} of our paragraph splits are one paragraph in the reference and "
                "book.json has no continuation link between them"
            )
        return "Stage 1", "paragraphs come from book.json"
    if element in DEFAULT_LABELS:
        return DEFAULT_LABELS[element]
    return "check", "no rule explains this difference"
