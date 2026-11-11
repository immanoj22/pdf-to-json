"""Step 21: bibliography checks on a book.json (Hypertension in the Young).

All entries of the printed bibliography sit in one section, numbered from their printed
numbers in order (1..N), nothing of the list stands in the chapter before it, and no heading
is empty. ``check(book, entries)`` returns each check with its evidence; ``ok(result)`` is true
when every check holds.

Usage: python step21_bibliography.py BOOK_JSON [--entries 112]
"""

import argparse
import json
import sys
from pathlib import Path


DIVISIONS = {"part", "chapter", "preface", "appendix", "bibliography", "glossary", "index",
             "section", "sect1", "sect2", "dedication"}


def walk(units):
    for unit in units:
        yield unit
        for key in ("items", "children"):
            yield from walk(unit.get(key) or [])


def text(unit):
    return ((unit.get("content") or {}).get("text") or "").strip()


def numbered_items(book):
    """[(order, page, printed number, node id)] of decimal-numbered list items."""
    rows = []
    for node in walk(book["content"]):
        marker = node.get("marker") or {}
        if node["type"] == "list_item" and marker.get("type") == "decimal":
            rows.append((node["order"], node["pages"][0], marker.get("value"), node["id"]))
    return sorted(rows)


def check(book, entries):
    """Stage 1 checks: the list sits under its heading, in order, in one rear section."""
    content = list(walk(book["content"]))
    headings = [u for u in content if u["type"] == "heading"]
    heading = next((h for h in headings if text(h).casefold() == "bibliography"), None)
    rows = numbered_items(book)
    by_id = {u["id"]: u for u in content}
    result = {"entries_expected": entries, "heading_found": heading is not None}
    after = [r for r in rows if heading is not None and r[0] > heading["order"]]
    before = [r for r in rows if heading is not None and r[0] < heading["order"]]
    result["entries_after_heading"] = len(after)
    result["numbers_one_to_n_in_order"] = [r[2] for r in after] == list(range(1, entries + 1))
    listed = {text(by_id[r[3]])[:60] for r in after}
    # an entry of the list standing before its heading (in the chapter before it)
    result["entries_before_heading"] = [
        r[2] for r in before if text(by_id[r[3]])[:60] in listed
    ][:5]
    zones = {p["index"]: p["zone"] for p in book["pages"]}
    result["entry_pages_in_rear"] = all(zones.get(r[1]) == "rear" for r in after)
    result["empty_headings"] = sum(1 for h in headings if not text(h))
    sections = {
        s["id"]
        for s in book["navigation"]["sections"]
        if s["kind"] == "bibliography"
        and any(s["first_page"] <= r[1] <= s["last_page"] for r in after)
    }
    result["one_bibliography_section"] = len(sections) == 1
    return result


def ok(result):
    return (
        result["heading_found"]
        and result["entries_after_heading"] == result["entries_expected"]
        and result["numbers_one_to_n_in_order"]
        and not result["entries_before_heading"]
        and result["entry_pages_in_rear"]
        and result["empty_headings"] == 0
        and result["one_bibliography_section"]
    )


def check_delivery(root, entries):
    """Delivery checks on a DocBook delivery folder (every XML file of it): every entry in the
    one division titled Bibliography, none repeated in any other file, no empty title, and
    every ordered list's starting number equal to the printed number of its first entry."""
    from lxml import etree

    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    files = sorted(p for p in Path(root).rglob("*.xml") if p.name != "page_info.xml")
    trees = {p: etree.parse(str(p), parser).getroot() for p in files}

    def title_of(div):
        node = div.find("title")
        return "".join(node.itertext()).strip() if node is not None else None

    divisions = [
        (p, d) for p, tree in trees.items() for d in tree.iter()
        if isinstance(d.tag, str) and d.tag in DIVISIONS and d.find("title") is not None
    ]  # fmt: skip
    holders = [(p, d) for p, d in divisions if (title_of(d) or "").casefold() == "bibliography"]
    result = {"bibliography_divisions": len(holders),
              "bibliography_file": holders[0][0].name if holders else None}  # fmt: skip
    items = list(holders[0][1].iter("listitem")) if holders else []
    result["entries_in_bibliography"] = len(items)
    texts = {"".join(li.itertext()).strip()[:60] for li in items}
    stray = 0
    for path, tree in trees.items():
        if holders and path == holders[0][0]:
            continue
        for li in tree.iter("listitem"):
            stray += "".join(li.itertext()).strip()[:60] in texts
    result["repeated_elsewhere"] = stray
    result["empty_titles"] = sum(1 for _, d in divisions if not title_of(d))
    starts_ok, seen = True, 0
    for lst in holders[0][1].iter("orderedlist") if holders else []:
        role = lst.get("role")
        if lst.get("continuation") != "continues" and role and role.isdigit():
            starts_ok = starts_ok and int(role) == seen + 1
        seen += len(lst.findall("listitem"))
    result["list_starts_are_printed_numbers"] = starts_ok
    return result


def delivery_ok(result, entries):
    return (
        result["bibliography_divisions"] == 1
        and result["entries_in_bibliography"] == entries
        and result["repeated_elsewhere"] == 0
        and result["empty_titles"] == 0
        and result["list_starts_are_printed_numbers"]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_json")
    parser.add_argument("--entries", type=int, default=112)
    args = parser.parse_args()
    result = check(json.loads(Path(args.book_json).read_text("utf-8")), args.entries)
    print(json.dumps({**result, "ok": ok(result)}, indent=1))
    return 0 if ok(result) else 1


if __name__ == "__main__":
    sys.exit(main())
