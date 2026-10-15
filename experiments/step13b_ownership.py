"""Step 13b Task 1/2: who holds drawn equation objects, before (Step 13a) and after (13b).

Before, an equation region was evidence beside unchanged units: its drawn objects were held
by no unit; those inside an exported Step 12 figure were held only as pixels of that image.
After, every region has an owner (text unit, display equation unit, real figure, review).

Per book: drawn objects of typeset equation regions by holder, regions by owner, display
units and their anchor confidence, figures converted / kept with math, images no longer
exported, and (math book) gold drawn objects held by no region (missed math). Step 13a
records are read as stored (their model predates owners).

Usage: python step13b_ownership.py [--books statistics,spanish_us_history,...]
"""

# ruff: noqa: E402
import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step13_books import BOOKS, MATH_BOOK
from step13_equations import DEV

from book_core.cache_store import read_json
from book_core.equations.cache import load_page
from book_core.figures.cache import load_page as figure_page

OUT = ROOT / "experiments/out/step13b/ownership"
GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK


def keys(step, book):
    path = ROOT / f"experiments/out/{step}/final/performance/{book}.json"
    run = json.loads(path.read_text("utf-8"))["run"]
    return run["cache_keys"], run["pages"]


def legacy_regions(key, number):
    """Step 13a page records as stored (no owners)."""
    entry = read_json(Path(DEV) / "equations" / key / f"{number}.json")
    return json.loads(entry["payload"]).get("regions", [])


def gold_objects():
    rows = {}
    with gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["status"] == "located" and row["verified"]:
                rows.setdefault(row["page"], set()).update(row["object_ids"])
    return rows


def measure(book):
    before_keys, total = keys("step13", book)
    after_keys, _ = keys("step13b", book)
    assert before_keys["figures"] == after_keys["figures"], "figures changed"
    before, after = Counter(), Counter()
    owners, anchors, kept_reasons = Counter(), Counter(), Counter()
    gold = gold_objects() if book == MATH_BOOK else {}
    converted_names, kept_names, examples = [], [], []
    for number in range(1, total + 1):
        figures = figure_page(DEV, after_keys["figures"], number).figures
        exported = {o for f in figures if f.image is not None for o in f.object_ids}
        for region in legacy_regions(before_keys["equations"], number):
            ids = region.get("object_ids", [])
            before["regions"] += 1
            before["objects"] += len(ids)
            inside = sum(o in exported for o in ids)
            before["objects_in_exported_figure_image_only"] += inside
            before["objects_held_by_nothing"] += len(ids) - inside
        record = load_page(DEV, after_keys["equations"], number)
        for name, value in record.ownership.model_dump().items():
            after[name] += value
        after["regions"] += len(record.regions)
        owners.update(r.owner.kind for r in record.regions)
        owners.update(f"{r.owner.kind}_{r.source}" for r in record.regions)
        for unit in record.units:
            anchors[f"confidence_{unit.anchor.confidence}"] += 1
            anchors["review_required"] += unit.anchor.review_required
            anchors["from_converted_figure"] += unit.converted_figure_id is not None
        after["units"] += len(record.units)
        after["figures_converted"] += len(record.figure_conversions)
        after["figures_kept_with_math"] += len(record.figure_math)
        converted_names += [c.figure_name for c in record.figure_conversions]
        for kept in record.figure_math:
            kept_reasons.update(
                " ".join(r.split()[1:]) if r[0].isdigit() else r for r in kept.reasons
            )
            kept_names.append(
                {"page": number, "figure": kept.figure_id[:12], "reasons": kept.reasons}
            )
        if number in gold:
            held = {o for r in record.regions for o in r.object_ids}
            after["gold_objects"] += len(gold[number])
            after["gold_objects_in_no_region"] += len(gold[number] - held)
            before_held = {
                o
                for r in legacy_regions(before_keys["equations"], number)
                for o in r.get("object_ids", [])
            }
            before["gold_objects"] += len(gold[number])
            before["gold_objects_in_no_region"] += len(gold[number] - before_held)
        for region in record.regions:
            if region.owner.kind == "review" and len(examples) < 20:
                examples.append(
                    {"page": number, "id": region.id[:12], "bbox": region.bbox.model_dump()}
                )
    book_record = read_json(Path(DEV) / "equations" / after_keys["equations"] / "book.json")
    summary = json.loads(book_record["payload"])
    result = {
        "book": book,
        "keys": {"before": before_keys["equations"], "after": after_keys["equations"]},
        "before_step13a": dict(before),
        "after_step13b": dict(after),
        "owners": dict(sorted(owners.items())),
        "display_unit_anchors": dict(sorted(anchors.items())),
        "kept_figure_reasons": dict(kept_reasons),
        "images_not_exported": summary.get("images_not_exported", []),
        "line_pitch": summary.get("line_pitch"),
        "converted_figures": converted_names,
        "kept_figures": kept_names,
        "review_examples": examples,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{book}.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"converted_figures", "kept_figures"}},
            indent=1,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--books", default=",".join(BOOKS))
    args = parser.parse_args()
    for name in args.books.split(","):
        measure(name)
