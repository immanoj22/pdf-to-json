"""Step 13b review: every real figure kept with math (dev bundles), its figure box (purple)
and the equation regions it owns (red), for a manual check that each region is math drawn
inside the figure and not text-flow math under an over-extended figure region.

Usage: python step13b_figure_sheets.py --book statistics --dev-run all11
"""

# ruff: noqa: E402
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step13_books import BOOKS
from step13b_bundles import book_evidence, load

from book_core.equations import detect, ownership
from book_core.equations.cache import CONFIG

OUT = ROOT / "experiments/out/step13b/review"


def main(book, dev_run):
    evidence = book_evidence(book)
    # The book line pitch measured by the development loop over the same bundles.
    dev = ROOT / f"experiments/out/step13b/dev/{dev_run}.json"
    evidence["pitch"] = json.loads(dev.read_text("utf-8"))["summary"]["pitch"]
    tiles, legend = [], []
    with pymupdf.open(reference_path(BOOKS[book][0])) as document:
        for number in range(1, evidence["pages"] + 1):
            bundle = load(book, number)
            regions, _, _, _ = detect.detect_page(
                bundle["page"], bundle["native"], bundle["layout"], bundle["units"],
                evidence["accepted"], bundle["math_fonts"], bundle["model_boxes"],
                evidence["book_size"], CONFIG, evidence.get("pitch"),
            )  # fmt: skip
            owned, _, _, kept, _ = ownership.own_page(
                bundle["page"], bundle["layout"], _Lists(bundle), bundle["figures"],
                bundle["native"], regions,
                ownership.FigureContent(bundle["page"], bundle["layout"], bundle["native"]),
                lambda f: None,
            )  # fmt: skip
            figures = {f.id: f for f in bundle["figures"].figures}
            for record in kept:
                figure = figures[record.figure_id]
                box = figure.bbox
                page = document[number - 1]
                clip = pymupdf.Rect(box.x0 - 10, box.y0 - 10, box.x1 + 10, box.y1 + 10)
                clip &= page.rect
                pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), clip=clip)
                image = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)
                image = image[:, :, :3].copy()

                def draw(b, colour, image=image, clip=clip):
                    cv2.rectangle(
                        image,
                        (int((b.x0 - clip.x0) * 1.5), int((b.y0 - clip.y0) * 1.5)),
                        (int((b.x1 - clip.x0) * 1.5), int((b.y1 - clip.y0) * 1.5)),
                        colour,
                        2,
                    )

                draw(box, (160, 40, 160))
                for region in owned:
                    if region.id in record.equation_ids:
                        draw(region.bbox, (220, 0, 0))
                scale = min(480 / image.shape[1], 220 / image.shape[0], 1)
                image = cv2.resize(
                    image, (int(image.shape[1] * scale), int(image.shape[0] * scale))
                )
                canvas = np.full((240, 480, 3), 255, np.uint8)
                canvas[18 : 18 + image.shape[0], : image.shape[1]] = image
                index = len(tiles)
                cv2.putText(
                    canvas, f"#{index} p{number} {figure.name}", (4, 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 200), 1,
                )  # fmt: skip
                tiles.append(canvas)
                legend.append(
                    {"tile": index, "page": number, "figure": figure.name,
                     "equations": len(record.equation_ids), "reasons": record.reasons}
                )  # fmt: skip
    target = OUT / f"{book}_kept_figures"
    target.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(tiles), 10):
        block = tiles[start : start + 10]
        rows = [np.hstack(block[i : i + 2]) if i + 1 < len(block) else
                np.hstack([block[i], np.full_like(block[i], 255)])
                for i in range(0, len(block), 2)]  # fmt: skip
        cv2.imwrite(
            str(target / f"sheet_{start // 10 + 1}.png"),
            cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR),
        )
    (target / "legend.json").write_text(json.dumps(legend, indent=1) + "\n", "utf-8")
    print(target, len(tiles))


class _Lists:
    def __init__(self, bundle):
        self.units, self.order = bundle["units"], bundle["order"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", default="statistics")
    parser.add_argument("--dev-run", default="latest")
    args = parser.parse_args()
    main(args.book, args.dev_run)
