"""Step 12: contact sheets of sampled caption/credit links for manual review.

One sheet per rule and book: each tile is the page region around the figure (blue) and the
linked unit (green), rendered through the Extractor, numbered as in the sample list.

Usage: python step12_link_sheets.py --book medical_anatomy [--links links]
"""

# ruff: noqa: E402
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import cv2
import numpy as np
from reference_paths import reference_path
from step7_layouts import BOOKS

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.figures.imaging import decode_png

DPI = 60
TILE = 360


def tile(extractor, source, row, index):
    raster = extractor.render_page(source, row["page"], DPI)
    image = cv2.cvtColor(decode_png(raster.png), cv2.COLOR_RGB2BGR)
    s = raster.width / raster.page_width
    f, u = row["figure_bbox"], row["unit_bbox"]
    for box, colour in ((f, (200, 90, 20)), (u, (40, 170, 40))):
        cv2.rectangle(image, (int(box[0] * s), int(box[1] * s)), (int(box[2] * s), int(box[3] * s)),
                      colour, 2)  # fmt: skip
    x0 = max(0, int(min(f[0], u[0]) * s) - 15)
    y0 = max(0, int(min(f[1], u[1]) * s) - 15)
    x1 = min(image.shape[1], int(max(f[2], u[2]) * s) + 15)
    y1 = min(image.shape[0], int(max(f[3], u[3]) * s) + 15)
    crop = image[y0:y1, x0:x1]
    scale = TILE / max(crop.shape[:2])
    crop = cv2.resize(
        crop, (max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale)))
    )
    canvas = np.full((TILE + 24, TILE, 3), 255, np.uint8)
    canvas[24 : 24 + crop.shape[0], : crop.shape[1]] = crop
    cv2.putText(canvas, f"{index} p{row['page']} {row['reference_tag']}", (4, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)  # fmt: skip
    return canvas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--links", default="links")
    args = parser.parse_args()
    data = json.loads(
        (ROOT / f"experiments/out/step12/{args.links}/{args.book}.json").read_text("utf-8")
    )
    source = reference_path(BOOKS[args.book][0])
    extractor = PyMuPDFExtractor("cpu")
    out = ROOT / f"experiments/out/step12/{args.links}/sheets"
    out.mkdir(parents=True, exist_ok=True)
    for rule, rows in data["samples"].items():
        tiles = [tile(extractor, source, row, i) for i, row in enumerate(rows)]
        while len(tiles) % 5:
            tiles.append(np.full_like(tiles[0], 255))
        grid = cv2.vconcat([cv2.hconcat(tiles[i : i + 5]) for i in range(0, len(tiles), 5)])
        slug = re.sub(r"[^a-z]+", "_", rule.lower())[:40].strip("_")
        cv2.imwrite(str(out / f"{args.book}_{slug}.jpg"), grid, [cv2.IMWRITE_JPEG_QUALITY, 80])
        print(out / f"{args.book}_{slug}.jpg")


if __name__ == "__main__":
    main()
