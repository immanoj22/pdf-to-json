"""Step 13a overlays: detected equation regions over rendered pages.

Colours: inline regions blue, display regions green, text-source regions orange outline,
layout-model-only formula boxes red dashed, verified gold equations (math book) grey.

Usage: python step13_overlays.py --book statistics --run before --pages 19 29 ...
       python step13_overlays.py --book immigrant_children --pages 117
"""

# ruff: noqa: E402
import argparse
import gzip
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step13_books import BOOKS, MATH_BOOK
from step13_equations import DEV, OUT

from book_core.equations.cache import load_page

GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK
ZOOM = 2.0
COLOURS = {"inline": (40, 90, 230), "display": (20, 160, 40)}


def _rect(image, box, colour, width=2, dashed=False):
    a = (int(box[0] * ZOOM), int(box[1] * ZOOM))
    b = (int(box[2] * ZOOM), int(box[3] * ZOOM))
    if not dashed:
        cv2.rectangle(image, a, b, colour, width)
        return
    for x in range(a[0], b[0], 10):
        cv2.line(image, (x, a[1]), (min(x + 5, b[0]), a[1]), colour, width)
        cv2.line(image, (x, b[1]), (min(x + 5, b[0]), b[1]), colour, width)
    for y in range(a[1], b[1], 10):
        cv2.line(image, (a[0], y), (a[0], min(y + 5, b[1])), colour, width)
        cv2.line(image, (b[0], y), (b[0], min(y + 5, b[1])), colour, width)


def main(book, run, pages, key):
    key = key or json.loads((OUT / "equations_dev" / f"{book}.json").read_text())["key"]
    gold = {}
    if book == MATH_BOOK:
        for line in gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8"):
            row = json.loads(line)
            if row["verified"]:
                gold.setdefault(row["page"], []).append(row["bbox"])
    target = OUT / "overlays"
    target.mkdir(parents=True, exist_ok=True)
    index = []
    with pymupdf.open(reference_path(BOOKS[book][0])) as document:
        for number in pages:
            page = document[number - 1]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM))
            image = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR).copy()
            for box in gold.get(number, []):
                _rect(image, [box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2], (150, 150, 150), 1)
            record = load_page(DEV, key, number)
            for region in record.regions:
                box = [region.bbox.x0, region.bbox.y0, region.bbox.x1, region.bbox.y1]
                colour = COLOURS.get(region.presentation, (120, 0, 120))
                _rect(image, box, colour, 2)
                if region.source != "vector":
                    _rect(image, [box[0] - 3, box[1] - 3, box[2] + 3, box[3] + 3], (0, 140, 255), 1)
            for only in record.model_only:
                box = [only.bbox.x0, only.bbox.y0, only.bbox.x1, only.bbox.y1]
                _rect(image, box, (0, 0, 220), 1, dashed=True)
            name = f"equations_{book}_p{number}.png"
            cv2.imwrite(str(target / name), image)
            index.append(
                {
                    "book": book,
                    "page": number,
                    "file": name,
                    "regions": len(record.regions),
                    "model_only": len(record.model_only),
                    "gold": len(gold.get(number, [])),
                }
            )
    path = target / "overlays.json"
    existing = json.loads(path.read_text("utf-8")) if path.exists() else []
    existing = [r for r in existing if not (r["book"] == book and r["page"] in pages)] + index
    path.write_text(json.dumps(existing, indent=1) + "\n", "utf-8")
    print(index)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--run", default="step12")
    parser.add_argument("--pages", type=int, nargs="+", required=True)
    parser.add_argument("--key")
    args = parser.parse_args()
    main(args.book, args.run, args.pages, args.key)
