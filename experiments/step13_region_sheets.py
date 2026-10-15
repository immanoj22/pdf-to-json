"""Step 13a: contact sheets of a seeded random sample of detected equation regions, for the
manual precision review (red box = region). A legend lists each tile's text and evidence.

Usage: python step13_region_sheets.py --book statistics --run before --n 40 --seed 21
                                      [--source vector|text|mixed] [--key KEY]
"""

# ruff: noqa: E402
import argparse
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
from step13_books import BOOKS
from step13_inspect import rows

OUT = ROOT / "experiments/out/step13/review"


def main(book, run, n, seed, source, key):
    found = list(rows(book, run, key, source))
    sample = random.Random(seed).sample(found, min(n, len(found)))
    target = OUT / f"{book}_{source or 'all'}_seed{seed}"
    target.mkdir(parents=True, exist_ok=True)
    tiles, legend = [], []
    with pymupdf.open(reference_path(BOOKS[book][0])) as document:
        for index, row in enumerate(sample):
            page = document[row["page"] - 1]
            x0, y0, x1, y1 = row["bbox"]
            clip = pymupdf.Rect(
                max(0, x0 - 90),
                max(0, y0 - 20),
                min(page.rect.x1, x1 + 90),
                min(page.rect.y1, y1 + 20),
            )
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip)
            image = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
            image = image.copy()
            cv2.rectangle(
                image,
                (int((x0 - clip.x0) * 2), int((y0 - clip.y0) * 2)),
                (int((x1 - clip.x0) * 2), int((y1 - clip.y0) * 2)),
                (220, 0, 0),
                2,
            )
            scale = min(500 / image.shape[1], 120 / image.shape[0], 1)
            image = cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale)))
            canvas = np.full((138, 500, 3), 255, np.uint8)
            canvas[18 : 18 + image.shape[0], : image.shape[1]] = image
            cv2.putText(
                canvas,
                f"#{index} p{row['page']} {row['source']} {row['presentation']}",
                (4, 13),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (0, 0, 200),
                1,
            )
            tiles.append(canvas)
            legend.append({"tile": index, **row})
    for start in range(0, len(tiles), 10):
        cv2.imwrite(
            str(target / f"sheet_{start // 10 + 1}.png"),
            cv2.cvtColor(np.vstack(tiles[start : start + 10]), cv2.COLOR_RGB2BGR),
        )
    (target / "legend.json").write_text(
        json.dumps(
            {"book": book, "seed": seed, "population": len(found), "tiles": legend},
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        "utf-8",
    )
    print(target, len(found))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--run", default="step12")
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--seed", type=int, default=21)
    parser.add_argument("--source")
    parser.add_argument("--key")
    args = parser.parse_args()
    main(args.book, args.run, args.n, args.seed, args.source, args.key)
