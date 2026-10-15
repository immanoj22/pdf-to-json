"""Step 13b manual samples for mixed expressions and text-set math (math book).

Populations are defined from input evidence, not from the regions being judged:

- ``mixed``: visual lines holding a drawn equation object (any region before the change) and
  a math operator character, an opening bracket glued to a single letter, or a relation in
  their text;
- ``text``: visual lines with no drawn equation object whose text holds a math operator
  character (Unicode Sm) or a single letter applied to a bracket (``f(``), outside words;
- ``new``: regions after the change that overlap no region before it (precision of the
  added detections).

Each tile shows the whole line: regions before (``--before KEY``) in red, after (current code
on the development bundles) in blue. A seeded draw over pages chooses the sample.

Usage: python step13b_line_samples.py --population mixed --n 40 --seed 101 --before KEY
"""

# ruff: noqa: E402
import argparse
import json
import random
import sys
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import regex

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step13_books import BOOKS, MATH_BOOK
from step13_equations import DEV
from step13b_bundles import book_evidence, load

from book_core.equations import detect
from book_core.equations.cache import CONFIG, load_page

OUT = ROOT / "experiments/out/step13b/samples"
APPLIED = regex.compile(r"(?<![\p{L}\p{N}])\p{L}\(")


def _box(b):
    return [b.x0, b.y0, b.x1, b.y1]


def _overlap(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def page_items(args):
    number, key, evidence, population = args
    bundle = load(MATH_BOOK, number)
    page, store = bundle["page"], bundle["page"].store
    before = load_page(DEV, key, number).regions
    after, _, _, _ = detect.detect_page(
        page, bundle["native"], bundle["layout"], bundle["units"], evidence["accepted"],
        bundle["math_fonts"], bundle["model_boxes"], evidence["book_size"], CONFIG,
        evidence["pitch"],
    )  # fmt: skip

    def text_of(region):
        return "".join(store.spans[r.span_id].raw_text[r.start : r.end] for r in region.span_refs)

    rows = [(_box(r.bbox), text_of(r), len(r.object_ids)) for r in before]
    news = [(_box(r.bbox), text_of(r), len(r.object_ids)) for r in after]
    items = []
    if population == "new":
        for box, text, objects in news:
            if not any(_overlap(box, b) for b, _, _ in rows):
                items.append({"page": number, "box": box, "text": text, "objects": objects})
        return items, rows, news
    drawn = [o.bbox for r in before for o in bundle["native"].objects if o.id in set(r.object_ids)]
    for line in bundle["layout"].lines:
        if line.blank or not line.inside_content or not line.horizontal:
            continue
        text = "".join(store.spans[s].raw_text for s in line.span_ids)
        lb = line.bbox
        holds_drawn = any(
            min(lb.y1, d.y1) - max(lb.y0, d.y0) > 0.5 * min(lb.y1 - lb.y0, d.y1 - d.y0)
            and d.x1 > lb.x0 - 20
            and d.x0 < lb.x1 + 20
            for d in drawn
        )
        operator = any(unicodedata.category(c) == "Sm" for c in text) or bool(APPLIED.search(text))
        if population == "mixed" and holds_drawn and operator:
            items.append({"page": number, "box": _box(lb), "text": text})
        if population == "text" and not holds_drawn and operator:
            items.append({"page": number, "box": _box(lb), "text": text})
    return items, rows, news


def main(population, n, seed, key):
    evidence = book_evidence(MATH_BOOK)
    evidence["pitch"] = json.loads(
        (ROOT / "experiments/out/step13b/dev/m2.json").read_text("utf-8")
    )["summary"]["pitch"]
    with ProcessPoolExecutor(7) as pool:
        results = list(
            pool.map(
                page_items,
                [(p, key, evidence, population) for p in range(1, evidence["pages"] + 1)],
                chunksize=4,
            )
        )
    everything = [item for items, _, _ in results for item in items]
    sample = random.Random(seed).sample(everything, min(n, len(everything)))
    target = OUT / f"{population}_seed{seed}"
    target.mkdir(parents=True, exist_ok=True)
    tiles, legend = [], []
    with pymupdf.open(reference_path(BOOKS[MATH_BOOK][0])) as document:
        for index, item in enumerate(sample):
            _, rows, news = results[item["page"] - 1]
            x0, y0, x1, y1 = item["box"]
            page = document[item["page"] - 1]
            clip = pymupdf.Rect(
                max(0, x0 - 30),
                max(0, y0 - 14),
                min(page.rect.x1, x1 + 30),
                min(page.rect.y1, y1 + 14),
            )
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip)
            image = (
                np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy()
            )

            def draw(b, colour, pad, image=image, clip=clip):
                cv2.rectangle(
                    image,
                    (int((b[0] - pad - clip.x0) * 2), int((b[1] - pad - clip.y0) * 2)),
                    (int((b[2] + pad - clip.x0) * 2), int((b[3] + pad - clip.y0) * 2)),
                    colour,
                    1 if pad else 2,
                )

            for b, _, _ in rows:
                if _overlap(b, [clip.x0, clip.y0, clip.x1, clip.y1]):
                    draw(b, (220, 0, 0), 2)
            for b, _, _ in news:
                if _overlap(b, [clip.x0, clip.y0, clip.x1, clip.y1]):
                    draw(b, (0, 60, 230), 0)
            scale = min(980 / image.shape[1], 110 / image.shape[0], 1)
            image = cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale)))
            canvas = np.full((128, 980, 3), 255, np.uint8)
            canvas[18 : 18 + image.shape[0], : image.shape[1]] = image
            cv2.putText(
                canvas,
                f"#{index} p{item['page']}",
                (4, 13),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (0, 0, 200),
                1,
            )
            tiles.append(canvas)
            box = item["box"]
            legend.append(
                {
                    "tile": index,
                    **item,
                    "before": [t for b, t, o in rows if _overlap(b, box)],
                    "after": [
                        t + (f" [+{o} drawn]" if o else "") for b, t, o in news if _overlap(b, box)
                    ],
                }
            )
    for start in range(0, len(tiles), 10):
        cv2.imwrite(
            str(target / f"sheet_{start // 10 + 1}.png"),
            cv2.cvtColor(np.vstack(tiles[start : start + 10]), cv2.COLOR_RGB2BGR),
        )
    record = {"population": population, "size": len(everything), "seed": seed, "tiles": legend}
    (target / "legend.json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    print(target, "population", len(everything))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", required=True, choices=["mixed", "text", "new"])
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--before", required=True)
    args = parser.parse_args()
    main(args.population, args.n, args.seed, args.before)
