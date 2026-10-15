"""Step 13a evaluation: equation detection against the math gold (math book) and review
inventories for books 1-4 (no math in their references).

Math book, per located gold equation:
- recall: the equation is found when one region holds at least half of its drawn objects
  (vector) or overlaps at least half of its box (text);
- precision: a region is correct when at least half of its drawn objects belong to gold
  equations (vector), or half of its box lies on a gold equation (text);
- object level: drawn objects in regions vs drawn objects of gold equations;
- presentation agreement, splits (one equation over several regions) and merges;
- the same scores for layout-model formula boxes alone (Heron, PP-DocLayoutV3, either).

Books 1-4: every region and every model-only formula box with its text, for manual review.

Usage: python step13_evaluate.py --book statistics --run before [--key KEY]
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
from step13_equations import DEV, OUT, stage_inputs
from step13_inspect import region_text

from book_core.equations.cache import load_page
from book_core.equations.evidence import formula_label

GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK
SHARE = 0.5


def _area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _box(b):
    return [b.x0, b.y0, b.x1, b.y1]


def gold_equations():
    rows = defaultdict(list)
    with gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["status"] == "located" and row["verified"]:
                rows[row["page"]].append(row)
    return rows


def _found(gold, region_boxes, region_objects):
    """Index of the region that holds the gold equation, else None."""
    objects = set(gold["object_ids"])
    for index, (box, owned) in enumerate(zip(region_boxes, region_objects, strict=True)):
        if objects and len(objects & owned) >= SHARE * len(objects):
            return index
        if not objects and _inter(box, gold["bbox"]) >= SHARE * _area(gold["bbox"]):
            return index
    return None


def score(pairs):
    tp = sum(1 for p in pairs["regions"] if p)
    precision = tp / len(pairs["regions"]) if pairs["regions"] else None
    recall = sum(pairs["gold"]) / len(pairs["gold"]) if pairs["gold"] else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    return {
        "regions": len(pairs["regions"]),
        "regions_correct": tp,
        "gold": len(pairs["gold"]),
        "gold_found": sum(pairs["gold"]),
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
    }


def evaluate_math_book(run, key):
    inputs = stage_inputs(MATH_BOOK, run)
    gold = gold_equations()
    ours = {"regions": [], "gold": []}
    models = {name: {"regions": [], "gold": []} for name in ("heron", "pp", "either", "both")}
    by_kind = defaultdict(lambda: {"regions": [], "gold": []})
    objects = Counter()
    presentation = Counter()
    split_merge = Counter()
    misses, false = [], []
    from step13_equations import formulas

    detector = formulas(inputs["source"], inputs["extractor"])
    for number in range(1, inputs["total"] + 1):
        record = load_page(DEV, key, number)
        rows = gold.get(number, [])
        boxes = [_box(r.bbox) for r in record.regions]
        owned = [set(r.object_ids) for r in record.regions]
        gold_objects = {o for row in rows for o in row["object_ids"]}
        found_by = defaultdict(list)
        for row in rows:
            index = _found(row, boxes, owned)
            ours["gold"].append(index is not None)
            by_kind[row["presentation"]]["gold"].append(index is not None)
            if index is None:
                misses.append(
                    {
                        "page": number,
                        "slot": row["slot"],
                        "leaf": row["leaf_text"],
                        "presentation": row["presentation"],
                        "bbox": row["bbox"],
                    }
                )
                continue
            found_by[index].append(row)
            region = record.regions[index]
            presentation[(row["presentation"], region.presentation)] += 1
        for index, region in enumerate(record.regions):
            if region.object_ids:
                correct = len(owned[index] & gold_objects) >= SHARE * len(owned[index])
            else:
                correct = any(
                    _inter(boxes[index], row["bbox"]) >= SHARE * _area(boxes[index]) for row in rows
                )
            ours["regions"].append(correct)
            by_kind[region.presentation]["regions"].append(correct)
            if not correct:
                false.append(
                    {
                        "page": number,
                        "id": region.id[:12],
                        "bbox": boxes[index],
                        "source": region.source,
                        "presentation": region.presentation,
                        "objects": len(region.object_ids),
                        "rules": region.rules,
                        "host": region.host.unit_kind,
                        "figure_region": region.signals.get("figure_region"),
                    }
                )
            if len(found_by.get(index, [])) > 1:
                split_merge["regions_holding_several_equations"] += 1
        for row in rows:
            hit = [i for i in range(len(owned)) if set(row["object_ids"]) & owned[i]]
            if len(hit) > 1:
                split_merge["equations_split_over_regions"] += 1
        objects["gold_objects"] += len(gold_objects)
        objects["region_objects"] += sum(len(o) for o in owned)
        objects["region_objects_in_gold"] += sum(len(o & gold_objects) for o in owned)
        # Layout-model formula boxes alone.
        boxes_by_model = {
            name: [_box(b) for b, label in found if formula_label(label)]
            for name, found in detector(number).items()
        }
        boxes_by_model["either"] = boxes_by_model["heron"] + boxes_by_model["pp"]
        boxes_by_model["both"] = [
            b
            for b in boxes_by_model["heron"]
            if any(_inter(b, o) >= SHARE * min(_area(b), _area(o)) for o in boxes_by_model["pp"])
        ]
        for name, model_boxes in boxes_by_model.items():
            for row in rows:
                models[name]["gold"].append(
                    any(_inter(b, row["bbox"]) >= SHARE * _area(row["bbox"]) for b in model_boxes)
                )
            for b in model_boxes:
                models[name]["regions"].append(
                    any(
                        _inter(b, row["bbox"]) >= SHARE * min(_area(b), _area(row["bbox"]))
                        for row in rows
                    )
                )
    result = {
        "book": MATH_BOOK,
        "key": key,
        "detection": score(ours),
        "by_presentation": {k: score(v) for k, v in by_kind.items()},
        "objects": {
            **objects,
            "precision": round(
                objects["region_objects_in_gold"] / max(1, objects["region_objects"]), 4
            ),
            "recall": round(objects["region_objects_in_gold"] / max(1, objects["gold_objects"]), 4),
        },
        "presentation_confusion": {f"{g}->{o}": n for (g, o), n in sorted(presentation.items())},
        "split_merge": dict(split_merge),
        "layout_models_alone": {k: score(v) for k, v in models.items()},
    }
    target = OUT / "evaluation" / run
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{MATH_BOOK}.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    (target / f"{MATH_BOOK}_misses.json").write_text(json.dumps(misses, indent=1) + "\n", "utf-8")
    (target / f"{MATH_BOOK}_false.json").write_text(json.dumps(false, indent=1) + "\n", "utf-8")
    print(json.dumps(result, indent=1))


def inventory(book, run, key):
    """Every region and model-only box of a book without math gold, for manual review."""
    inputs = stage_inputs(book, run)
    regions, model_only = [], []
    for page in inputs["pages"]():
        number = page.geometry.page
        record = load_page(DEV, key, number)
        for region in record.regions:
            regions.append({
                "page": number, "id": region.id[:12], "text": region_text(page.store, region),
                "source": region.source, "presentation": region.presentation,
                "rules": region.rules, "host": region.host.unit_kind,
                "objects": len(region.object_ids), "bbox": [round(v, 1) for v in _box(region.bbox)],
                "models": [m for m, v in (("heron", region.model_support.heron),
                                          ("pp", region.model_support.pp_doclayoutv3)) if v],
            })  # fmt: skip
        for box in record.model_only:
            lines = [
                line
                for line in inputs["layout_of"](page).lines
                if _inter(_box(line.bbox), _box(box.bbox)) > 0.5 * _area(_box(line.bbox))
            ]
            text = " / ".join(
                "".join(page.store.spans[s].raw_text for s in line.span_ids) for line in lines
            )
            model_only.append(
                {
                    "page": number,
                    "models": box.models,
                    "labels": box.labels,
                    "bbox": [round(v, 1) for v in _box(box.bbox)],
                    "text": text[:200],
                }
            )
    target = OUT / "evaluation" / run
    target.mkdir(parents=True, exist_ok=True)
    row = {
        "book": book,
        "key": key,
        "regions": regions,
        "model_only": model_only,
        "counts": {
            "regions": len(regions),
            "model_only": len(model_only),
            "by_source": dict(Counter(r["source"] for r in regions)),
            "by_presentation": dict(Counter(r["presentation"] for r in regions)),
            "by_host": dict(Counter(r["host"] for r in regions)),
        },
    }
    (target / f"{book}_inventory.json").write_text(
        json.dumps(row, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    print(json.dumps(row["counts"], indent=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--run", default="step12")
    parser.add_argument("--key")
    args = parser.parse_args()
    key = args.key or json.loads((OUT / "equations_dev" / f"{args.book}.json").read_text())["key"]
    if args.book == MATH_BOOK:
        evaluate_math_book(args.run, key)
    else:
        inventory(args.book, args.run, key)
