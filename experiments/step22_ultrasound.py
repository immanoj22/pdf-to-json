"""Step 22: the Ultrasound-guided Regional Blocks book, fixed by a person using only the app's
edit operations, then exported.

The book's converter output (a publication folder with book.json) is the starting point. The
scripted edits are the ones a reviewer makes in the browse view, chosen by page and title
start (page numbers are allowed in a scenario like this one). The script applies them as the
app does (``overlay.apply_checked``), prints the chapter list the app shows, writes the overlay
publication and runs the adapter on it.

Usage: python step22_ultrasound.py PUBLICATION_DIR OUT_DIR [--profile jaypee_v5]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

from book_adapters.engine.run import run_book
from book_app import overlay

# (page, title starts with, edit). "kind" edits set a heading's kind; "not" removes a heading.
SCENARIO = [
    (9, "Contents", {"op": "heading_kind", "kind": "front_matter"}),
    (9, "Fundamentals", {"op": "heading_remove"}),
    (9, "Upper Limb", {"op": "heading_remove"}),
    (9, "Truncal", {"op": "heading_remove"}),
    (9, "Lower Limb", {"op": "heading_remove"}),
    (9, "Recent Advances", {"op": "heading_remove"}),
    (11, "\t 1.", {"op": "heading_remove"}),
    (13, "1\n", {"op": "heading_kind", "kind": "chapter"}),
    (13, "PART I:", {"op": "heading_kind", "kind": "section"}),
    (14, "PART II:", {"op": "heading_kind", "kind": "section"}),
    (14, "Modes", {"op": "heading_kind", "kind": "section"}),
    (16, "PART III:", {"op": "heading_kind", "kind": "section"}),
    (19, "Upper Limb", {"op": "heading_kind", "kind": "part"}),
    (37, "Truncal", {"op": "heading_kind", "kind": "part"}),
    (59, "Lower Limb", {"op": "heading_kind", "kind": "part"}),
    (67, "Recent Advances", {"op": "heading_kind", "kind": "part"}),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("publication", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--profile", default="jaypee_v5")
    args = parser.parse_args()
    data = json.loads((args.publication / "book.json").read_text("utf-8"))
    headings = [u for u, _ in overlay.walk(data["content"]) if u["type"] == "heading"]
    edits = []
    for page, start, edit in SCENARIO:
        found = [u for u in headings if u["pages"][0] == page
                 and (u["content"]["text"] or "").startswith(start)
                 and not any(e.get("unit") == u["id"] for e in edits)]  # fmt: skip
        if not found:
            print(f"page {page}: no heading starts with {start!r} (already right?)")
            continue
        edits.append({**edit, "unit": found[0]["id"], "id": f"s{len(edits)}"})
    before = overlay.chapter_rows(data)
    fixed, applied, failed = overlay.apply_checked(data, edits)
    # The title editor: each part and chapter title loses its stray number (the number stays in
    # the chapter list and the label).
    titles = []
    for row in overlay.chapter_rows(fixed):
        if row["number"] and row["title"] != row["text"]:
            unit = overlay.index_units(fixed)[row["unit"]][0]
            old = unit["content"]["text"]
            new = old.strip()
            for token in (str(row["number"]),):
                lines = [ln for ln in new.split("\n")]
                lines = [ln for ln in lines if ln.strip(" .:-\t") != token]
                new = "\n".join(lines)
                for lead in (f"{token}. ", f"{token} ", f"\t {token}.\t "):
                    if new.startswith(lead):
                        new = new[len(lead):]
                if new.rstrip().endswith(" " + token):
                    new = new.rstrip()[: -len(token)].rstrip()
            if new.strip() and new != old:
                titles.append({"op": "heading_text", "unit": row["unit"], "text": new.strip(),
                               "id": f"t{len(titles)}"})
    fixed, applied2, failed2 = overlay.apply_checked(fixed, titles)
    applied += applied2
    failed += failed2
    rows = overlay.chapter_rows(fixed)
    print(f"before: {sum(r['role'] == 'part' for r in before)} parts, "
          f"{sum(r['role'] == 'chapter' for r in before)} chapters")
    print(f"edits applied {len(applied)}, refused {len(failed)}: {failed}")
    for r in rows:
        print(f"  {r['role']:8s} {r['number']!s:>4s}  p{r['page']:<3d} {r['title'][:70]}")
    print(f"after: {sum(r['role'] == 'part' for r in rows)} parts, "
          f"{sum(r['role'] == 'chapter' for r in rows)} chapters")
    target = overlay.write_overlay(args.publication, fixed, args.out / "overlay")
    report = run_book(target, args.out / "export", None, args.profile,
                      allow_alt_text_placeholders=True)  # fmt: skip
    root = Path(report["root"])
    xml = (root / f"{root.name}.xml").read_text("utf-8")
    chapters = sorted(root.glob("Chapters/ch*.xml"))
    print("export: parts", xml.count("<part "), "chapter files", len(chapters),
          "dtd errors", report["checks"]["dtd"]["errors"],
          "lossless missing", report["checks"]["lossless"]["missing"])
    from lxml import etree

    for f in sorted(root.glob("Chapters/ch*.xml"), key=lambda p: int(p.stem[2:])):
        tree = etree.parse(str(f)).getroot()
        for el in tree.iter("part", "chapter"):
            node = el.find("title")
            title = " ".join("".join(node.itertext()).split()) if node is not None else ""
            print(f"   {f.name:9s} {el.tag:8s} {el.get('label')} | {title[:60]}")


if __name__ == "__main__":
    main()
