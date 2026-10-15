"""Step 13b: equation regions of a book (development bundles) with their source text,
compared with the Step 13a inventory of the same book: regions added, removed and changed
(same page, overlapping box, different text or objects). Text is resolved for review only.

Usage: python step13b_inventory.py --book immigrant_children --dev-run immigrant_children_m1
"""

# ruff: noqa: E402
import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step13b_bundles import book_evidence, load

from book_core.equations import detect
from book_core.equations.cache import CONFIG

BEFORE = ROOT / "experiments/out/step13/evaluation/step12"
OUT = ROOT / "experiments/out/step13b/inventory"


def page_rows(args):
    book, number, evidence = args
    bundle = load(book, number)
    store = bundle["page"].store
    regions, _, _, _ = detect.detect_page(
        bundle["page"], bundle["native"], bundle["layout"], bundle["units"],
        evidence["accepted"], bundle["math_fonts"], bundle["model_boxes"],
        evidence["book_size"], CONFIG, evidence["pitch"],
    )  # fmt: skip
    return [
        {
            "page": number,
            "text": "".join(
                store.spans[r.span_id].raw_text[r.start : r.end] for r in region.span_refs
            ),
            "source": region.source,
            "presentation": region.presentation,
            "rules": region.rules,
            "objects": len(region.object_ids),
            "bbox": [
                round(v, 1)
                for v in (region.bbox.x0, region.bbox.y0, region.bbox.x1, region.bbox.y1)
            ],
        }
        for region in regions
    ]


def _overlap(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def main(book, dev_run):
    evidence = book_evidence(book)
    dev = json.loads((ROOT / f"experiments/out/step13b/dev/{dev_run}.json").read_text("utf-8"))
    evidence["pitch"] = dev["summary"]["pitch"]
    with ProcessPoolExecutor(6) as pool:
        after = [
            row
            for rows in pool.map(
                page_rows,
                [(book, n, evidence) for n in range(1, evidence["pages"] + 1)],
                chunksize=4,
            )
            for row in rows
        ]
    before_path = BEFORE / f"{book}_inventory.json"
    before = json.loads(before_path.read_text("utf-8"))["regions"] if before_path.exists() else []
    same, changed, added = [], [], []
    matched = set()
    for row in after:
        hits = [
            i
            for i, old in enumerate(before)
            if old["page"] == row["page"] and _overlap(old["bbox"], row["bbox"])
        ]
        exact = [
            i
            for i in hits
            if before[i]["text"] == row["text"] and before[i]["objects"] == row["objects"]
        ]
        if exact:
            same.append(row)
            matched.add(exact[0])
        elif hits:
            changed.append({"after": row, "before": [before[i] for i in hits]})
            matched.update(hits)
        else:
            added.append(row)
    removed = [old for i, old in enumerate(before) if i not in matched]
    result = {
        "book": book,
        "regions_before": len(before),
        "regions_after": len(after),
        "unchanged": len(same),
        "changed": changed,
        "added": added,
        "removed": removed,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{book}.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    print(book, {k: (len(v) if isinstance(v, list) else v) for k, v in result.items()})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--dev-run", required=True)
    args = parser.parse_args()
    main(args.book, args.dev_run)
