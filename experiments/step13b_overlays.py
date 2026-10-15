"""Step 13b overlays: equation regions with their owners over rendered pages.

Colours: regions owned by a text unit blue (an orange caret marks the inline place of drawn
objects), display equation units green with their reading index and a green link to the
anchor line, regions owned by a kept real figure purple inside the figure's dashed purple
box, figures converted to equations red dashed, regions for review black, verified gold
equations grey; the Step 13a regions of the same page thin red (``--before``).

Usage: python step13b_overlays.py --book statistics --pages 19 183 ... [--before]
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
from step13_equations import DEV, stage_inputs
from step13_overlays import _rect
from step13b_ownership import keys, legacy_regions

from book_core.cache_store import read_model
from book_core.equations.cache import load_page
from book_core.equations.detect import range_box
from book_core.figures.cache import load_page as figure_page
from book_core.model.spans import ExtractedPage

GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK
OUT = ROOT / "experiments/out/step13b/overlays"
ZOOM = 2.0
BLUE, GREEN, PURPLE, RED, BLACK = (
    (230, 90, 40),
    (40, 160, 20),
    (160, 40, 160),
    (0, 0, 220),
    (0, 0, 0),
)
ORANGE, GREY = (0, 140, 255), (150, 150, 150)


def _xy(box):
    return [box.x0, box.y0, box.x1, box.y1]


def main(book, pages, before, labels):
    after_keys, _ = keys("step13b", book)
    before_keys, _ = keys("step13", book)
    gold = {}
    if book == MATH_BOOK:
        for line in gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8"):
            row = json.loads(line)
            if row["verified"]:
                gold.setdefault(row["page"], []).append(row["bbox"])
    layout_of = stage_inputs(book, "final")["layout_of"]
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    with pymupdf.open(reference_path(BOOKS[book][0])) as document:
        for number, label in zip(pages, labels or [""] * len(pages), strict=True):
            source = read_model(
                DEV / "text" / after_keys["native"] / f"{number}.json",
                ExtractedPage,
                after_keys["native"],
            )
            layout = layout_of(source)
            lines = {line.id: line for line in layout.lines}
            page = document[number - 1]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM))
            image = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR).copy()
            for box in gold.get(number, []):
                _rect(image, [box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2], GREY, 1)
            if before:
                for region in legacy_regions(before_keys["equations"], number):
                    b = region["bbox"]
                    _rect(image, [b["x0"] - 1, b["y0"] - 1, b["x1"] + 1, b["y1"] + 1], RED, 1)
            record = load_page(DEV, after_keys["equations"], number)
            figures = {f.id: f for f in figure_page(DEV, after_keys["figures"], number).figures}
            for conversion in record.figure_conversions:
                _rect(image, _xy(figures[conversion.figure_id].bbox), RED, 2, dashed=True)
            for kept in record.figure_math:
                _rect(image, _xy(figures[kept.figure_id].bbox), PURPLE, 2, dashed=True)
            units = {u.id: u for u in record.units}
            for region in record.regions:
                owner = region.owner
                box = _xy(region.bbox)
                colour = {
                    "text_unit": BLUE,
                    "equation_unit": GREEN,
                    "figure": PURPLE,
                    "review": BLACK,
                }[owner.kind]
                _rect(image, box, colour, 2)
                if owner.place is not None:
                    span = source.store.spans[owner.place.span_id]
                    text = span.raw_text
                    at = min(owner.place.offset, max(0, len(text) - 1))
                    cell = range_box(span, at, at + 1)
                    x = cell.x0 if owner.place.offset < len(text) else cell.x1
                    a = (int(x * ZOOM), int((cell.y1 + 1) * ZOOM))
                    cv2.line(image, a, (a[0] - 5, a[1] + 8), ORANGE, 2)
                    cv2.line(image, a, (a[0] + 5, a[1] + 8), ORANGE, 2)
                if owner.kind == "equation_unit":
                    unit = units[owner.unit_id]
                    cv2.putText(
                        image,
                        f"U{unit.anchor.reading_index}",
                        (int((box[0] - 22) * ZOOM), int(box[1] * ZOOM) + 16),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        GREEN,
                        2,
                    )
                    after = lines.get(unit.anchor.after_line_id)
                    if after is not None:
                        cv2.line(
                            image,
                            (int(after.bbox.x0 * ZOOM), int(after.bbox.y1 * ZOOM)),
                            (int(box[0] * ZOOM), int(box[1] * ZOOM)),
                            GREEN,
                            1,
                        )
            name = f"ownership_{book}_p{number}.png"
            cv2.imwrite(str(OUT / name), image)
            index.append(
                {
                    "book": book,
                    "page": number,
                    "shows": label,
                    "file": name,
                    "regions": len(record.regions),
                    "owners": sorted({r.owner.kind for r in record.regions}),
                    "equation_units": len(record.units),
                    "figures_converted": len(record.figure_conversions),
                    "figures_kept_with_math": len(record.figure_math),
                    "gold": len(gold.get(number, [])),
                }
            )
    path = OUT / "overlays.json"
    existing = json.loads(path.read_text("utf-8")) if path.exists() else []
    existing = [r for r in existing if not (r["book"] == book and r["page"] in pages)] + index
    path.write_text(json.dumps(existing, indent=1) + "\n", "utf-8")
    print(json.dumps(index, indent=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--pages", type=int, nargs="+", required=True)
    parser.add_argument("--labels", nargs="+")
    parser.add_argument("--before", action="store_true")
    args = parser.parse_args()
    main(args.book, args.pages, args.before, args.labels)
