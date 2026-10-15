"""Step 13b evaluation on the math book: detection scores and inline placement.

1. Detection recall/precision on the verified gold with the unchanged Step 13a scorer
   (``step13_evaluate``), written under ``experiments/out/step13b/evaluation/<run>``.
2. Inline placement: for every verified inline gold equation whose drawn objects one region
   holds (>= 95%) and whose owner reads them inside a text unit, the place must lie after the
   reference token before the equation and no later than the token after it (the gold's own
   anchors, aligned by the unchanged reference aligner). Positions are compared in reading
   order: line index in the stream, then along the line; an anchor read in another stream
   (the main flow after a table or callout) is not compared. Pages, layout and order are
   read from the development bundles of the same caches (``step13b_bundles``).

Usage: python step13b_evaluate.py [--run final]
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
import step13_evaluate
from step13_books import MATH_BOOK
from step13_equations import DEV, stage_inputs
from step13b_bundles import load

from book_core.equations.cache import load_page
from book_core.equations.detect import range_box
from book_core.evaluation.math_gold import token_geometry

GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK
OUT = ROOT / "experiments/out/step13b/evaluation"
COMPLETE = 0.95


def _centre(box):
    return (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2


def _line_of(point, lines):
    x, y = point
    holding = [
        line
        for line in lines
        if line.bbox.x0 - 1 <= x <= line.bbox.x1 + 1 and line.bbox.y0 - 1 <= y <= line.bbox.y1 + 1
    ]
    if not holding:
        return None
    return min(
        holding, key=lambda line: (line.bbox.x1 - line.bbox.x0) * (line.bbox.y1 - line.bbox.y0)
    )


def placement(key, total):
    rows = {}
    with gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["status"] == "located" and row["verified"] and row["presentation"] == "inline":
                rows.setdefault(row["page"], []).append(row)
    counts, wrong = Counter(), []
    for number in range(1, total + 1):
        if number not in rows:
            continue
        bundle = load(MATH_BOOK, number)
        page, layout, order = bundle["page"], bundle["layout"], bundle["order"]
        lines = [line for line in layout.lines if not line.blank]
        rank = {}
        for s_index, stream in enumerate(order.streams):
            for l_index, lid in enumerate(stream.line_ids):
                rank[lid] = (s_index, l_index)
        boxes, _, _, _ = token_geometry(page)
        record = load_page(DEV, key, number)

        def position(point, lines=lines, rank=rank):
            line = _line_of(point, lines)
            if line is None or line.id not in rank:
                return None
            return (*rank[line.id], point[0])

        for row in rows[number]:
            objects = set(row["object_ids"])
            if not objects:
                continue
            holder = max(record.regions, key=lambda r: len(objects & set(r.object_ids)))
            if len(objects & set(holder.object_ids)) < COMPLETE * len(objects):
                counts["not_held_by_one_region"] += 1
                continue
            place = holder.owner.place
            if place is None:
                counts[f"owner_{holder.owner.kind}"] += 1
                continue
            span = page.store.spans[place.span_id]
            at = min(place.offset, len(span.raw_text) - 1)
            cell = range_box(span, at, at + 1, bundle["native"].span_geometry.get(span.id))
            x = cell.x0 if place.offset < len(span.raw_text) else cell.x1
            here = position((x, (cell.y0 + cell.y1) / 2))
            (_, before), (_, after) = row["anchors"]
            low = position(_centre(boxes[before])) if 0 <= before < len(boxes) else None
            high = position(_centre(boxes[after])) if 0 <= after < len(boxes) else None
            # Anchors read in another stream (the main flow after a table or callout) do
            # not order a place inside this stream.
            low = low if low is not None and here is not None and low[0] == here[0] else None
            high = high if high is not None and here is not None and high[0] == here[0] else None
            if here is None or (low is None and high is None):
                counts["not_comparable"] += 1
                continue
            right = (low is None or low < here) and (high is None or here <= high)
            counts["placed_between_anchors" if right else "placed_elsewhere"] += 1
            if not right and len(wrong) < 60:
                wrong.append(
                    {
                        "page": number,
                        "slot": row["slot"],
                        "leaf": row["leaf_text"],
                        "place": [place.span_id[:10], place.offset],
                        "here": here,
                        "before": low,
                        "after": high,
                    }
                )
    compared = counts["placed_between_anchors"] + counts["placed_elsewhere"]
    return {
        "counts": dict(counts),
        "agreement": round(counts["placed_between_anchors"] / compared, 4) if compared else None,
        "disagreements": wrong,
    }


def main(run):
    performance = json.loads(
        (ROOT / f"experiments/out/step13b/{run}/performance/{MATH_BOOK}.json").read_text("utf-8")
    )["run"]
    key = performance["cache_keys"]["equations"]
    step13_evaluate.OUT = ROOT / "experiments/out/step13b"
    step13_evaluate.stage_inputs = lambda book, _run: stage_inputs(book, "final")
    step13_evaluate.evaluate_math_book(f"{run}", key)
    result = placement(key, performance["pages"])
    target = OUT / run
    target.mkdir(parents=True, exist_ok=True)
    (target / "placement.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "disagreements"}, indent=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="final")
    args = parser.parse_args()
    main(args.run)
