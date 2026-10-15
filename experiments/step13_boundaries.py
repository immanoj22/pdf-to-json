"""Step 13a region boundaries on the math book (final records).

1. Accounting of every region against the gold: a region overlapping a verified equation,
   a located-but-unverified equation, or no located equation (by source); fragments are the
   extra regions of an equation split over several.
2. Per verified equation: covered by exactly one complete region, complete but merged with
   other equations, complete with extra material, partial (one region holds part), split
   over several regions, or missed. Computed on every verified equation and reported for a
   seeded sample of 200; a seeded 40 of the sample is rendered for a manual check of the
   labels.

Drawn objects decide for vector equations; boxes decide for text-only equations.

Usage: python step13_boundaries.py --key KEY [--n 200 --seed 13]
"""

# ruff: noqa: E402
import argparse
import gzip
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step13_books import BOOKS, MATH_BOOK
from step13_equations import DEV

from book_core.equations.cache import load_page

GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK
OUT = ROOT / "experiments/out/step13/boundaries"
COMPLETE = 0.95  # share of the equation's objects one region must hold
EXTRA = 0.2  # share of a region's objects outside the equation that counts as extra


def _inter(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _area(a):
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def _box(b):
    return [b.x0, b.y0, b.x1, b.y1]


def classify(row, regions, other_objects):
    """Label of one verified equation against the page's regions."""
    objects = set(row["object_ids"])
    if not objects:  # text-only equation: boxes
        hits = [r for r in regions if _inter(_box(r.bbox), row["bbox"]) > 0]
        covering = [
            r for r in hits if _inter(_box(r.bbox), row["bbox"]) >= COMPLETE * _area(row["bbox"])
        ]
        if not hits:
            return "missed", []
        if len(hits) > 1 and not covering:
            return "split", hits
        region = covering[0] if covering else hits[0]
        if not covering:
            return "partial", [region]
        extra = _area(_box(region.bbox)) - _inter(_box(region.bbox), row["bbox"])
        return (
            "complete_with_extra" if extra > EXTRA * _area(_box(region.bbox)) else "complete"
        ), [region]
    hits = [r for r in regions if objects & set(r.object_ids)]
    if not hits:
        return "missed", []
    best = max(hits, key=lambda r: len(objects & set(r.object_ids)))
    share = len(objects & set(best.object_ids)) / len(objects)
    if len(hits) > 1 and share < COMPLETE:
        return "split", hits
    if share < COMPLETE:
        return "partial", [best]
    outside = set(best.object_ids) - objects
    if outside & other_objects:
        return "merged_with_other_equations", [best]
    if len(outside) > EXTRA * len(best.object_ids):
        return "complete_with_extra", [best]
    return "complete", [best]


def main(key, n, seed):
    with gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    located = defaultdict(list)
    for row in rows:
        if row["status"] == "located":
            located[row["page"]].append(row)
    labels, accounting, details = {}, Counter(), []
    for number in range(1, 872):
        regions = load_page(DEV, key, number).regions
        page_rows = located.get(number, [])
        verified = [r for r in page_rows if r["verified"]]
        all_objects = {o for r in page_rows for o in r["object_ids"]}
        for row in verified:
            others = all_objects - set(row["object_ids"])
            label, used = classify(row, regions, others)
            labels[row["slot"]] = label
            details.append(
                {
                    "slot": row["slot"],
                    "page": number,
                    "label": label,
                    "presentation": row["presentation"],
                    "bbox": row["bbox"],
                    "regions": [_box(r.bbox) for r in used],
                    "leaf_text": row["leaf_text"],
                }
            )
        # Region accounting.
        verified_objects = {o for r in verified for o in r["object_ids"]}
        unverified_objects = {o for r in page_rows if not r["verified"] for o in r["object_ids"]}
        first_region = {}
        for index, region in enumerate(regions):
            owned = set(region.object_ids)
            box = _box(region.bbox)
            on_verified = (owned & verified_objects) or any(
                not r["object_ids"] and _inter(box, r["bbox"]) > 0 for r in verified
            )
            if on_verified:
                slots = [
                    r["slot"]
                    for r in verified
                    if owned & set(r["object_ids"])
                    or (not r["object_ids"] and _inter(box, r["bbox"]) > 0)
                ]
                fragment = any(s in first_region for s in slots)
                for s in slots:
                    first_region.setdefault(s, index)
                accounting[
                    "on_verified_equation_fragment" if fragment else "on_verified_equation"
                ] += 1
            elif owned & unverified_objects or any(
                not r["verified"] and _inter(box, r["bbox"]) > 0 for r in page_rows
            ):
                accounting["on_located_unverified_equation"] += 1
            else:
                accounting[f"no_located_equation_{region.source}"] += 1
    everything = Counter(labels.values())
    sample = random.Random(seed).sample(sorted(labels), min(n, len(labels)))
    sampled = Counter(labels[s] for s in sample)
    by_presentation = defaultdict(Counter)
    for row in details:
        if row["slot"] in set(sample):
            by_presentation[row["presentation"]][row["label"]] += 1
    result = {
        "key": key,
        "regions": sum(accounting.values()),
        "verified_gold": len(labels),
        "region_accounting": dict(sorted(accounting.items())),
        "labels_all_verified": dict(sorted(everything.items())),
        "sample": {
            "seed": seed,
            "n": len(sample),
            "labels": dict(sorted(sampled.items())),
            "by_presentation": {k: dict(v) for k, v in by_presentation.items()},
        },
        "definitions": {
            "complete": f"one region holds >= {COMPLETE:.0%} of the equation and little else",
            "complete_with_extra": f"as complete; > {EXTRA:.0%} of the region is other material",
            "merged_with_other_equations": "one region also holds another located equation",
            "partial": "one region holds part of the equation",
            "split": "several regions each hold part of the equation",
            "missed": "no region touches the equation",
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "boundaries.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    (OUT / "sample.json").write_text(
        json.dumps(
            [d for d in details if d["slot"] in set(sample)],
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        "utf-8",
    )
    # Seeded 40 of the sample rendered for a manual check of the labels.
    check = random.Random(seed + 1).sample(sample, 40)
    tiles = []
    by_slot = {d["slot"]: d for d in details}
    with pymupdf.open(reference_path(BOOKS[MATH_BOOK][0])) as document:
        for index, slot in enumerate(check):
            row = by_slot[slot]
            page = document[row["page"] - 1]
            boxes = [row["bbox"], *row["regions"]]
            clip = pymupdf.Rect(
                max(0, min(b[0] for b in boxes) - 40),
                max(0, min(b[1] for b in boxes) - 12),
                min(page.rect.x1, max(b[2] for b in boxes) + 40),
                min(page.rect.y1, max(b[3] for b in boxes) + 12),
            )
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip)
            image = (
                np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy()
            )

            def draw(b, colour, width, image=image, clip=clip):
                cv2.rectangle(
                    image,
                    (int((b[0] - clip.x0) * 2), int((b[1] - clip.y0) * 2)),
                    (int((b[2] - clip.x0) * 2), int((b[3] - clip.y0) * 2)),
                    colour,
                    width,
                )

            for b in row["regions"]:
                draw(b, (220, 0, 0), 2)
            draw(
                [
                    row["bbox"][0] - 2,
                    row["bbox"][1] - 2,
                    row["bbox"][2] + 2,
                    row["bbox"][3] + 2,
                ],
                (0, 160, 0),
                1,
            )
            scale = min(500 / image.shape[1], 120 / image.shape[0], 1)
            image = cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale)))
            canvas = np.full((138, 500, 3), 255, np.uint8)
            canvas[18 : 18 + image.shape[0], : image.shape[1]] = image
            cv2.putText(
                canvas,
                f"#{index} p{row['page']} {row['label']}",
                (4, 13),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (0, 0, 200),
                1,
            )
            tiles.append(canvas)
    for start in range(0, len(tiles), 10):
        cv2.imwrite(
            str(OUT / f"check_{start // 10 + 1}.png"),
            cv2.cvtColor(np.vstack(tiles[start : start + 10]), cv2.COLOR_RGB2BGR),
        )
    (OUT / "check_legend.json").write_text(
        json.dumps(
            [{"tile": i, **by_slot[s]} for i, s in enumerate(check)],
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        "utf-8",
    )
    print(json.dumps({k: v for k, v in result.items() if k != "definitions"}, indent=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()
    main(args.key, args.n, args.seed)
