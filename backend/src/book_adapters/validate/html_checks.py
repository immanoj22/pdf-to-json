"""HTML5 checks on the written pages, re-read from disk: well-formed (strict reader), unique
ids, internal links that resolve to a file and an id, images that exist and have ``alt``,
a ``lang`` and a ``title`` on every page, no skipped heading level, ``th`` with ``scope``,
page-break marks complete and in order, a contents page that lists every division page, and
the lossless check."""

from __future__ import annotations

import posixpath
import re

from . import format_checks as fc

ITEMS = {
    "well_formed": "HTML5 syntax (strict reader)",
    "page": "page has doctype, lang, title, one main heading",
    "ids": "ids unique within a page",
    "links": "internal links resolve to a file and an id",
    "images": "images exist and have alt",
    "headings": "no skipped heading level",
    "tables": "th has scope; table has a caption or is a layout of data",
    "page_breaks": "page-break marks complete and in order",
    "contents": "contents page links every division page",
    "css": "linked style sheets exist",
}
INLINE = frozenset({"a", "b", "i", "u", "em", "strong", "sup", "sub", "br"})
HEADING = re.compile(r"^h([1-6])$")


def _inline(el) -> bool:
    if el.tag in INLINE:
        return True
    return el.tag == "span" and (
        (el.get("class") or "").startswith("f-") or el.get("role") == "doc-pagebreak"
    )


def html_tokens(root) -> list[str]:
    """Tokens of a content page in reading order, grouped by block as the ledger groups
    them. Printed labels written from attributes (span.label) and MathML (but not its
    plain-text annotation) are not source text."""
    body = next((c for c in root if c.tag == "body"), None)
    segments: list[tuple[int, str]] = []

    def block_of(el):
        while el is not None and _inline(el):
            el = el.getparent()
        return id(el)

    def walk(el, skip):
        if el.tag == "math":
            for ann in el.iter("annotation"):
                if ann.get("encoding") == "text/plain":
                    segments.append((id(ann), "".join(ann.itertext())))
            return
        here = skip or (el.tag == "span" and "label" in (el.get("class") or "").split())
        if el.text and not here:
            segments.append((block_of(el), el.text))
        for child in el:
            walk(child, here)
            if child.tail and not here:
                segments.append((block_of(el), child.tail))

    if body is not None:
        walk(body, False)
    return fc.tokens_in_blocks(segments)


def check(root_dir, delivery, doc, book, profile, cfg) -> dict:
    """Run every check on ``root_dir`` (the written delivery folder)."""
    from pathlib import Path

    root_dir = Path(root_dir)
    f = fc.Findings(ITEMS)
    pages: dict[str, object] = {}
    syntax_errors = 0
    html_files = sorted(p for p in delivery.files if p.endswith(".html"))
    for name in html_files:
        tree, errors, doctype = fc.parse_html((root_dir / name).read_bytes())
        f.check("well_formed", not errors and tree is not None, f"{name}: {errors[:2]}")
        syntax_errors += len(errors)
        if tree is not None:
            pages[name] = tree
    ids: dict[str, set[str]] = {}
    for name, tree in pages.items():
        head = next((c for c in tree if c.tag == "head"), None)
        title = head.find("title") if head is not None else None
        h1 = [e for e in tree.iter("h1")]
        f.check(
            "page",
            tree.get("lang") is not None
            and title is not None
            and bool((title.text or "").strip())
            and len(h1) >= 1,
            f"{name}: lang/title/h1 missing",
        )
        seen: set[str] = set()
        for e in tree.iter():
            eid = e.get("id")
            if eid:
                f.check("ids", eid not in seen, f"{name}: duplicate id {eid}")
                seen.add(eid)
        ids[name] = seen
        if head is not None:
            for link in head.iter("link"):
                if link.get("rel") == "stylesheet":
                    f.check(
                        "css",
                        posixpath.normpath(
                            posixpath.join(posixpath.dirname(name), link.get("href"))
                        )
                        in delivery.files,
                        f"{name}: {link.get('href')}",
                    )
    for name, tree in pages.items():
        for a in tree.iter("a"):
            href = a.get("href") or ""
            if "://" in href or href.startswith(("mailto:", "tel:")):
                continue
            path, _, frag = href.partition("#")
            target = (
                posixpath.normpath(posixpath.join(posixpath.dirname(name), path)) if path else name
            )
            ok = target in pages and (not frag or frag in ids[target])
            f.check("links", ok, f"{name}: {href}")
        for img in tree.iter("img"):
            src = img.get("src") or ""
            exists = (
                root_dir / posixpath.normpath(posixpath.join(posixpath.dirname(name), src))
            ).is_file()
            f.check("images", exists and img.get("alt") is not None, f"{name}: {src}")
        last = 0
        for h in tree.iter():
            m = HEADING.match(h.tag) if isinstance(h.tag, str) else None
            if m:
                level = int(m.group(1))
                f.check("headings", level <= last + 1, f"{name}: h{last} then h{level}")
                last = level
        for table in tree.iter("table"):
            ths = list(table.iter("th"))
            f.check("tables", all(t.get("scope") for t in ths), f"{name}: th without scope")
    # page breaks: every anchor the writer made appears once, in order
    want = [a for _, a in sorted(((p, a) for p, a in delivery.anchors.items()), key=lambda x: x[0])]
    found: list[str] = []
    for name in delivery.spine:
        tree = pages.get(name)
        if tree is not None:
            found += [s.get("id") for s in tree.iter("span") if s.get("role") == "doc-pagebreak"]
    expected = [w for w in want if w in set(found)]
    first = next((i for i, (a, b) in enumerate(zip(found, expected, strict=False)) if a != b), None)
    f.check(
        "page_breaks",
        found == expected,
        f"page-break marks out of order at #{first}",
    )
    f.check("page_breaks", len(found) == len(set(found)), "duplicate page-break ids")
    # contents page
    index = pages.get(delivery.main_file)
    if index is not None:
        linked = {a.get("href", "").partition("#")[0] for a in index.iter("a")}
        for name in delivery.spine:
            if delivery.split_files.get(name) not in (None, "toc", "titlepage", "copyright"):
                f.check("contents", name in linked, f"{name} not linked from the contents page")
    actual: list[str] = []
    for name in delivery.spine:
        if name in pages and name not in delivery.generated_files:
            actual += html_tokens(pages[name])
    return {
        "dtd": {
            "dtd": "HTML5 syntax (strict reader; no validator installed)",
            "files": len(html_files),
            "errors": syntax_errors,
            "by_file": {},
        },
        "house_rules": f.result(),
        "lossless": fc.lossless_check(actual, doc, delivery.ledger),
    }
