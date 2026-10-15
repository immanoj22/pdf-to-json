"""Step 13b development loop on bundles: detection, boundaries, ownership on any page set.

Runs ``detect_page`` and the ownership pass on the bundled stage inputs of each page
(``step13b_bundles``), then labels every verified gold equation with the Step 13a boundary
classifier and scores recall with the Step 13a rule. Development only: final records come
from ``book_run``.

Usage: python step13b_dev.py --book statistics [--pages 100-120] [--workers 4] [--out name]
"""

# ruff: noqa: E402
import argparse
import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step13_books import MATH_BOOK
from step13_boundaries import classify
from step13b_bundles import book_evidence, load

from book_core.equations import detect, ownership
from book_core.equations.cache import CONFIG

GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK
OUT = ROOT / "experiments/out/step13b/dev"


def gold_rows():
    rows = defaultdict(list)
    with gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["status"] == "located":
                rows[row["page"]].append(row)
    return rows


def page_pitches(args):
    book, number = args
    bundle = load(book, number)
    return detect.line_pitches(bundle["layout"], bundle["units"])


def run_page(args):
    book, number, evidence, gold = args
    if evidence.get("no_clips"):  # ablation: proximity rules only, no drawing groups
        detect.drawing_groups = lambda *_args, **_kwargs: {}
    bundle = load(book, number)
    regions, _, diagnostics, _ = detect.detect_page(
        bundle["page"],
        bundle["native"],
        bundle["layout"],
        bundle["units"],
        evidence["accepted"],
        bundle["math_fonts"],
        bundle["model_boxes"],
        evidence["book_size"],
        CONFIG,
        evidence["pitch"],
    )
    built = SimpleLists(bundle["units"], bundle["order"])
    owned, units, conversions, kept, glyphs = ownership.own_page(
        bundle["page"],
        bundle["layout"],
        built,
        bundle["figures"],
        bundle["native"],
        regions,
        ownership.FigureContent(bundle["page"], bundle["layout"], bundle["native"]),
        lambda figure: figure.image.file_name if figure.image else None,
    )
    labels = []
    verified = [r for r in gold if r["verified"]]
    all_objects = {o for r in gold for o in r["object_ids"]}
    for row in verified:
        label, used = classify(row, owned, all_objects - set(row["object_ids"]))
        labels.append(
            {
                "slot": row["slot"],
                "page": number,
                "label": label,
                "presentation": row["presentation"],
                "bbox": row["bbox"],
                "regions": [[r.bbox.x0, r.bbox.y0, r.bbox.x1, r.bbox.y1] for r in used],
                "leaf_text": row["leaf_text"],
            }
        )
    return {
        "page": number,
        "regions": len(owned),
        "by_source": Counter(r.source for r in owned),
        "by_owner": Counter(r.owner.kind for r in owned),
        "units": len(units),
        "conversions": [c.model_dump(mode="json") for c in conversions],
        "kept": [k.model_dump(mode="json") for k in kept],
        "ownership": glyphs.model_dump(),
        "labels": labels,
        "diagnostics": diagnostics,
    }


class SimpleLists:
    def __init__(self, units, order):
        self.units, self.order = units, order


def main(book, pages, workers, out, no_clips=False):
    evidence = book_evidence(book)
    evidence["no_clips"] = no_clips
    gold = gold_rows() if book == MATH_BOOK else {}
    numbers = range(pages[0], pages[1] + 1) if pages else range(1, evidence["pages"] + 1)
    with ProcessPoolExecutor(workers) as pool:
        if "pitch" not in evidence:
            everything = range(1, evidence["pages"] + 1)
            found = [
                d for row in pool.map(page_pitches, [(book, n) for n in everything]) for d in row
            ]
            evidence["pitch"] = statistics.median(found) if found else None
        jobs = [(book, n, evidence, gold.get(n, [])) for n in numbers]
        results = list(pool.map(run_page, jobs, chunksize=4))
    labels = [label for r in results for label in r["labels"]]
    totals = Counter()
    for r in results:
        totals.update({f"owner_{k}": v for k, v in r["by_owner"].items()})
        totals.update({f"source_{k}": v for k, v in r["by_source"].items()})
        totals.update({f"glyphs_{k}": v for k, v in r["ownership"].items()})
        totals["regions"] += r["regions"]
        totals["units"] += r["units"]
        totals["figures_converted"] += len(r["conversions"])
        totals["figures_kept_with_math"] += len(r["kept"])
    summary = {
        "book": book,
        "pages": [numbers[0], numbers[-1]],
        "totals": dict(sorted(totals.items())),
        "labels": dict(sorted(Counter(x["label"] for x in labels).items())),
        "verified": len(labels),
        "pitch": evidence["pitch"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{out}.json").write_text(
        json.dumps(
            {"summary": summary, "pages": results},
            indent=1,
            ensure_ascii=False,
            default=dict,
        )
        + "\n",
        "utf-8",
    )
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", default=MATH_BOOK)
    parser.add_argument("--pages")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", default="latest")
    parser.add_argument("--no-clips", action="store_true")
    args = parser.parse_args()
    span = tuple(int(v) for v in args.pages.split("-")) if args.pages else None
    main(args.book, span, args.workers, args.out, args.no_clips)
