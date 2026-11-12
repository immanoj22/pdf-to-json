"""Step 22: check that no paragraph weaves lines of two columns (word order against the PDF's
line order; the lossless check counts tokens and cannot see this).

Usage: python step22_line_order.py SOURCE_PDF BOOK_JSON [--examples 10]
Prints the units whose line sequence jumps back twice or more in the PDF's native line order.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src")]

import pymupdf
from book_core.evaluation.line_order import check


def walk(units):
    for unit in units:
        yield unit
        for key in ("items", "children"):
            yield from walk(unit.get(key) or [])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("book_json")
    parser.add_argument("--examples", type=int, default=10)
    args = parser.parse_args()
    native = {}
    with pymupdf.open(args.pdf) as document:
        for number, page in enumerate(document, 1):
            lines = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []) if block["type"] == 0 else []:
                    lines.append("".join(span["text"] for span in line["spans"]))
            native[number] = lines
    book = json.loads(Path(args.book_json).read_text("utf-8"))
    units = [(u["id"], u["pages"][0], u["content"]["text"]) for u in walk(book["content"])
             if u.get("pages") and isinstance(u.get("content"), dict)
             and isinstance(u["content"].get("text"), str)]  # fmt: skip
    found = check(native, units)
    print(f"units checked {len(units)}; woven from separate line runs: {len(found)}")
    for row in found[: args.examples]:
        print(f"  page {row['page']}: native line order {row['native_order']} | {row['text']!r}")


if __name__ == "__main__":
    main()
