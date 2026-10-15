"""Step 13b: per-label changes on the seeded boundary sample (200, seed 13) between two
record sets, with the region text of each change, for the strict and expression-level
scores.

``--before KEY`` and ``--after KEY`` read stage caches; ``--after-bundles`` detects with the
current code on the development bundles. Labels: the unchanged Step 13a classifier (drawn
objects decide). Each change to "merged" is listed with the other gold equations in the
region and the region's text, for a manual decision: one expression chained through text-set
operators on one line (expression-level complete) or two expressions joined (a regression).

Usage: python step13b_sample_changes.py --before KEY --after KEY --name final
"""

# ruff: noqa: E402
import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step13_books import MATH_BOOK
from step13_boundaries import classify
from step13_equations import DEV
from step13b_bundles import book_evidence, load

from book_core.equations import detect
from book_core.equations.cache import CONFIG, load_page

GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK
OUT = ROOT / "experiments/out/step13b/boundaries"


def main(before, after, after_bundles, name):
    rows = defaultdict(list)
    with gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["status"] == "located":
                rows[row["page"]].append(row)
    sample = {x["slot"] for x in json.loads((OUT / "sample.json").read_text("utf-8"))}
    evidence = book_evidence(MATH_BOOK)
    evidence["pitch"] = json.loads(
        (ROOT / "experiments/out/step13b/dev/m2.json").read_text("utf-8")
    )["summary"]["pitch"]
    transitions, changes, labels = Counter(), [], {}
    for page in sorted(rows):
        chosen = [r for r in rows[page] if r["verified"] and r["slot"] in sample]
        if not chosen:
            continue
        bundle = load(MATH_BOOK, page)
        store = bundle["page"].store
        old = load_page(DEV, before, page).regions
        if after_bundles:
            new, _, _, _ = detect.detect_page(
                bundle["page"], bundle["native"], bundle["layout"], bundle["units"],
                evidence["accepted"], bundle["math_fonts"], bundle["model_boxes"],
                evidence["book_size"], CONFIG, evidence["pitch"],
            )  # fmt: skip
        else:
            new = load_page(DEV, after, page).regions
        everything = {o for r in rows[page] for o in r["object_ids"]}
        for row in chosen:
            others = everything - set(row["object_ids"])
            was, _ = classify(row, old, others)
            now, used = classify(row, new, others)
            transitions[(was, now)] += 1
            labels[row["slot"]] = now
            if was == now:
                continue
            region = used[0] if used else None
            changes.append(
                {
                    "page": page,
                    "slot": row["slot"],
                    "gold": row["leaf_text"],
                    "before": was,
                    "after": now,
                    "region_text": " ".join(
                        store.spans[r.span_id].raw_text[r.start : r.end] for r in region.span_refs
                    )
                    if region
                    else "",
                    "region_objects": len(region.object_ids) if region else 0,
                    "other_gold_in_region": [
                        r["leaf_text"]
                        for r in rows[page]
                        if r is not row and region and set(r["object_ids"]) & set(region.object_ids)
                    ],
                }
            )
    result = {
        "before": before,
        "after": "bundles" if after_bundles else after,
        "labels": dict(sorted(Counter(labels.values()).items())),
        "transitions": {f"{a} -> {b}": n for (a, b), n in sorted(transitions.items()) if a != b},
        "changes": changes,
    }
    (OUT / f"sample_changes_{name}.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "changes"}, indent=1))
    for c in changes:
        print(
            c["page"],
            c["before"],
            "->",
            c["after"],
            "|",
            c["gold"][:30],
            "|",
            c["region_text"][:70],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after")
    parser.add_argument("--after-bundles", action="store_true")
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    main(args.before, args.after, args.after_bundles, args.name)
