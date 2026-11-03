"""Step 20 seeded hand checks on a run's publication: contact sheets for a reviewer (the Step
19 tool with sheet numbering by counter, Step 20 runs and a ``cells`` kind).

  headings   40 seeded heading decisions: published headings and units flagged as
             heading-like; each crop shows the line(s), our level and whether it is flagged
  links      40 seeded page links: the end of the first part and the start of the next
  underline  20 seeded underline spans: the line holding the span, and the span text
  cells      20 seeded table cells of two or more lines: the cell's lines in published order

Crops come from the source PDF at the node's lines (the run's layout cache). Each sheet
holds up to eight numbered crops; ``items.json`` lists every item with its id, page and
what the publication claims, and a ``judgment`` field left empty for the reviewer.

Usage: python step20_handcheck.py --book medical_anatomy --tag final --kind headings
"""

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
OUT = ROOT / "experiments/out/step20"
SIZES = {"headings": 40, "links": 40, "underline": 20, "cells": 20}
SEED = 20
PER_SHEET = 8


def lines_of(record):
    """{page: {line prefix: bbox}} reader over the run's layout cache."""
    from book_core.cache_store import read_json

    root = Path(record["cache"]) / "layout" / record["run"]["cache_keys"]["layout"]
    found = {}

    def get(page):
        if page not in found:
            data = read_json(root / f"{page}.json")
            data = json.loads(data["payload"]) if "payload" in data else data
            found[page] = {line["id"][:16]: line["bbox"] for line in data.get("lines", [])}
        return found[page]

    return get


def text_of(node):
    content = node.get("content")
    return content.get("text", "") if isinstance(content, dict) else ""


def candidates(kind, book_json):
    import step17_json_eval as json_eval

    _, _, units = json_eval.json_view(book_json)
    rows, previous = [], None
    for uid, unit in units.items():  # book order
        node = unit["node"]
        flags = [f for f in node.get("flags", []) if f.startswith("heading:")]
        if kind == "headings" and (unit["type"] == "heading" or flags):
            rows.append({"unit": uid, "page": unit["page"], "lines": node["refs"]["lines"],
                         "text": text_of(node)[:120], "type": unit["type"],
                         "level": node.get("level"), "flags": flags,
                         "previous_heading": previous})  # fmt: skip
        if kind == "headings" and unit["type"] == "heading":
            previous = [node.get("level"), text_of(node)[:50].strip()]
        elif kind == "links" and (node.get("continues_to") or {}).get("kind", "page") == "page":
            link = node.get("continues_to")
            if not link or link.get("unit") not in units:
                continue
            other = units[link["unit"]]
            rows.append({"unit": uid, "page": unit["page"], "lines": node["refs"]["lines"][-2:],
                         "next_unit": link["unit"], "next_page": other["page"],
                         "next_lines": other["node"]["refs"]["lines"][:2],
                         "text": text_of(node)[-80:], "next_text": text_of(other["node"])[:80],
                         "word_join": link.get("word_join"),
                         "flagged": link.get("review_status") != "ok"})  # fmt: skip
        elif kind == "underline":
            content = node.get("content")
            for span in content.get("spans", []) if isinstance(content, dict) else ():
                if span.get("kind") == "underline":
                    rows.append({"unit": uid, "page": unit["page"],
                                 "lines": node["refs"]["lines"],
                                 "text": content["text"][span["start"]:span["end"]][:80],
                                 "context": content["text"][:120]})  # fmt: skip
    if kind == "cells":
        for node in book_json["content"]:
            if node["type"] != "table":
                continue
            for cell in node["cells"]:
                blocks = cell.get("content") or []
                lines = [lid for block in blocks for lid in block["refs"]["lines"]]
                if len(lines) >= 2:
                    rows.append({"unit": cell["id"], "page": cell["box"]["page"], "lines": lines,
                                 "text": " / ".join(b["content"]["text"] for b in blocks
                                                    if isinstance(b.get("content"), dict))[:150]})  # fmt: skip
    return sorted(rows, key=lambda r: (r["page"], r["unit"], r.get("text", "")))


def crop(document, page, boxes, scale=2.0, margin=40):
    import pymupdf

    target = document[page - 1]
    x0 = max(0, min(b["x0"] for b in boxes) - margin)
    y0 = max(0, min(b["y0"] for b in boxes) - margin)
    x1 = min(target.rect.width, max(b["x1"] for b in boxes) + margin)
    y1 = min(target.rect.height, max(b["y1"] for b in boxes) + margin)
    shape = target.new_shape()
    for b in boxes:
        shape.draw_rect(pymupdf.Rect(b["x0"], b["y0"], b["x1"], b["y1"]))
    shape.finish(color=(1, 0, 0), width=0.8)
    shape.commit(overlay=True)
    pixmap = target.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                               clip=pymupdf.Rect(x0, y0, x1, y1))  # fmt: skip
    return pixmap


def sheet(images, path):
    """Labelled crops stacked on one page, saved as a PNG (and the labels as text)."""
    import pymupdf

    width = max(p.width for _, p in images) / 2 + 20
    height = sum(p.height / 2 + 22 for _, p in images) + 10
    with pymupdf.open() as document:
        page = document.new_page(width=max(width, 400), height=height)
        y = 6
        for label, pixmap in images:
            page.insert_text((8, y + 11), label[:150], fontsize=8, color=(0, 0, 0.7))
            rect = pymupdf.Rect(8, y + 16, 8 + pixmap.width / 2, y + 16 + pixmap.height / 2)
            page.insert_image(rect, pixmap=pixmap)
            y += pixmap.height / 2 + 22
        page.get_pixmap(dpi=144).save(path)
    Path(path).with_suffix(".txt").write_text(
        "\n".join(label for label, _ in images) + "\n", "utf-8"
    )


def main():
    import pymupdf
    from reference_paths import reference_path
    from step20_run import BOOKS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True, choices=BOOKS)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--kind", required=True, choices=SIZES)
    args = parser.parse_args()
    record = json.loads((OUT / args.tag / "performance" / f"{args.book}.json").read_text("utf-8"))
    book_json = json.loads((Path(record["run"]["book_json"]) / "book.json").read_text("utf-8"))
    rows = candidates(args.kind, book_json)
    chosen = sorted(random.Random(SEED).sample(rows, min(SIZES[args.kind], len(rows))),
                    key=lambda r: (r["page"], r["unit"]))  # fmt: skip
    folder = OUT / args.tag / "handcheck" / args.book / args.kind
    folder.mkdir(parents=True, exist_ok=True)
    boxes_of = lines_of(record)
    with pymupdf.open(reference_path(BOOKS[args.book])) as document:
        images, sheets = [], 0  # a link item makes two crops, so count sheets, not items
        for number, row in enumerate(chosen, 1):
            row["item"], row["judgment"] = number, None
            parts = [(row["page"], row["lines"])]
            if args.kind == "links":
                parts.append((row["next_page"], row["next_lines"]))
            for page, lines in parts:
                found = boxes_of(page)
                boxes = [found[lid] for lid in lines if lid in found]
                if not boxes:
                    continue
                label = f"#{number} p{page}"
                if args.kind == "headings":
                    label += (f" {row['type']} level={row['level']} flags={row['flags']}"
                              f" | previous heading: {row['previous_heading']}")
                elif args.kind == "underline":
                    label += f" underlined: {row['text']!r}"
                elif args.kind == "cells":
                    label += f" cell text in order: {row['text']!r}"
                images.append((label, crop(document, page, boxes)))
            if len(images) >= PER_SHEET or number == len(chosen):
                sheets += 1
                sheet(images, folder / f"sheet_{sheets:02d}.png")
                images = []
    (folder / "items.json").write_text(json.dumps({"book": args.book, "tag": args.tag,
                                       "kind": args.kind, "seed": SEED,
                                       "population": len(rows), "items": chosen},
                                       indent=1, ensure_ascii=False) + "\n", "utf-8")  # fmt: skip
    print(args.book, args.kind, f"{len(chosen)} of {len(rows)}", folder)


if __name__ == "__main__":
    main()
