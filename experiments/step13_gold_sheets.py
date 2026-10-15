"""Step 13a: contact sheets of random located gold equations, for a manual precision check.

Each tile is a page crop with the gold region in green; the legend file lists each tile's
reference leaf text, presentation and method. Seeded and reproducible.

Usage: python step13_gold_sheets.py [--n 40] [--seed 13]
"""

# ruff: noqa: E402
import argparse
import gzip
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step13_books import BOOKS, MATH_BOOK

GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK
SHEETS = ROOT / "experiments/out/step13/gold/sheets"
TILE = (520, 140)


def tile(document, row, zoom=2.5):
    page = document[row["page"] - 1]
    x0, y0, x1, y1 = row["bbox"]
    clip = pymupdf.Rect(
        max(0, x0 - 60), max(0, y0 - 14), min(page.rect.x1, x1 + 60), min(page.rect.y1, y1 + 14)
    )
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip)
    image = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy()
    a = (int((x0 - clip.x0) * zoom), int((y0 - clip.y0) * zoom))
    b = (int((x1 - clip.x0) * zoom), int((y1 - clip.y0) * zoom))
    cv2.rectangle(image, a, b, (0, 170, 0), 2)
    scale = min(TILE[0] / image.shape[1], TILE[1] / image.shape[0], 1.0)
    image = cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale)))
    canvas = np.full((TILE[1] + 18, TILE[0], 3), 255, np.uint8)
    canvas[18 : 18 + image.shape[0], : image.shape[1]] = image
    cv2.putText(
        canvas,
        f"#{row['tile']} p{row['page']} slot {row['slot']}",
        (4, 13),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 0, 200),
        1,
    )
    return canvas


def main(n, seed):
    rows = [
        json.loads(line) for line in gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8")
    ]
    located = [r for r in rows if r["status"] == "located"]
    sample = random.Random(seed).sample(located, n)
    OUT = SHEETS / f"seed_{seed}"
    OUT.mkdir(parents=True, exist_ok=True)
    legend = []
    with pymupdf.open(reference_path(BOOKS[MATH_BOOK][0])) as document:
        tiles = []
        for index, row in enumerate(sample):
            row = {**row, "tile": index}
            tiles.append(tile(document, row))
            legend.append(
                {
                    "tile": index,
                    "page": row["page"],
                    "slot": row["slot"],
                    "leaf_text": row["leaf_text"],
                    "presentation": row["presentation"],
                    "method": row["method"],
                    "glyph_count_fits": row["glyph_count_fits"],
                }
            )
        per_sheet = 10
        for sheet in range(0, len(tiles), per_sheet):
            group = tiles[sheet : sheet + per_sheet]
            image = np.vstack(group)
            cv2.imwrite(
                str(OUT / f"sheet_{sheet // per_sheet + 1}.png"),
                cv2.cvtColor(image, cv2.COLOR_RGB2BGR),
            )
    (OUT / "legend.json").write_text(
        json.dumps({"seed": seed, "tiles": legend}, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()
    main(args.n, args.seed)
