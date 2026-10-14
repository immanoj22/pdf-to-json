"""Step 12: suspect (surplus) figures of a book with their "model disagrees" flag.

A figure is a suspect when its page holds more of our figures than reference figures (by
PDF page). Contact sheets show each suspect (figure box red when flagged, blue when not),
numbered as in the JSON list, for manual classification.

Usage: STEP12_OUT=final python step12_false_figures.py --book spanish_us_history
"""

# ruff: noqa: E402
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import cv2
import numpy as np
from reference_paths import reference_path
from step7_layouts import BOOKS
from step12_evaluate import reference_view

from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.figures.evidence import MODEL_DISAGREES
from book_core.figures.imaging import decode_png

RUN = ROOT / "experiments/out/step12" / os.environ.get("STEP12_OUT", "run")
TILE = 300


def main(book):
    run = json.loads((RUN / f"performance/{book}.json").read_text("utf-8"))["run"]
    output = Path(run["output"])
    _, ref_pages, _ = reference_view(book)
    suspects = []
    for number in range(1, run["pages"] + 1):
        figures = read_json(output / f"page_{number:06d}.json.gz")["figures"]["figures"]
        if len(figures) <= ref_pages.get(number, 0):
            continue
        for f in figures:
            suspects.append(
                {
                    "page": number,
                    "reference_on_page": ref_pages.get(number, 0),
                    "ours_on_page": len(figures),
                    "name": f["name"],
                    "bbox": f["bbox"],
                    "flagged": MODEL_DISAGREES in f["review_flags"],
                    "model_support": f["model_support"],
                    "area_share": f["content_area_share"],
                }
            )
    out = RUN / "false_figures"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{book}.json").write_text(json.dumps(suspects, indent=1) + "\n", "utf-8")
    extractor = PyMuPDFExtractor("cpu")
    source = reference_path(BOOKS[book][0])
    tiles = []
    for i, s in enumerate(suspects):
        raster = extractor.render_page(source, s["page"], 50)
        image = cv2.cvtColor(decode_png(raster.png), cv2.COLOR_RGB2BGR)
        k = raster.width / raster.page_width
        b = s["bbox"]
        colour = (40, 40, 220) if s["flagged"] else (200, 90, 20)
        cv2.rectangle(image, (int(b["x0"] * k), int(b["y0"] * k)),
                      (int(b["x1"] * k), int(b["y1"] * k)), colour, 3)  # fmt: skip
        scale = TILE / max(image.shape[:2])
        image = cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale)))
        canvas = np.full((TILE + 22, TILE, 3), 255, np.uint8)
        canvas[22 : 22 + image.shape[0], : image.shape[1]] = image
        label = f"{i} p{s['page']} {'FLAG' if s['flagged'] else 'ok'} r{s['reference_on_page']}"
        cv2.putText(canvas, label, (3, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        tiles.append(canvas)
    for start in range(0, len(tiles), 30):
        chunk = tiles[start : start + 30]
        while len(chunk) % 6:
            chunk.append(np.full_like(tiles[0], 255))
        grid = cv2.vconcat([cv2.hconcat(chunk[i : i + 6]) for i in range(0, len(chunk), 6)])
        cv2.imwrite(
            str(out / f"{book}_{start // 30:02d}.jpg"), grid, [cv2.IMWRITE_JPEG_QUALITY, 80]
        )
    print(len(suspects), "suspects;", sum(s["flagged"] for s in suspects), "flagged")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    main(parser.parse_args().book)
