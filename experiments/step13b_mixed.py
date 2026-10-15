"""Step 13b: mixed expressions, text-set math and clipped edges on the math book.

Regions come from a stage cache (``--key``) or are detected on the development bundles
(``--bundles``, the current code). Measured on every verified gold equation:

1. Mixed gold (drawn objects and PDF text tokens): exactly one complete region needs >= 95%
   of the drawn objects and every text token's centre inside one region's character boxes.
   Text-only gold: the same on tokens alone.
2. The boundary labels of all verified gold (Step 13a classifier on objects; tokens added for
   gold with tokens), with "merged" split into merged through text-set parts on one line
   (a mixed region whose other gold equations share its line band) and other merges.
3. Edges of every text and mixed region: (a) a region box that cuts an edge character (it
   holds < 50% of the first or last character's rendered glyph box, horizontally), (b) a
   character really excluded: the character right outside the range on the
   same line, with no space between, is an operand, operator or a bracket closing one opened
   in the range.

Usage: python step13b_mixed.py --name after --bundles
       python step13b_mixed.py --name before --key KEY
"""

# ruff: noqa: E402
import argparse
import gzip
import json
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step13_books import MATH_BOOK
from step13_boundaries import classify
from step13_equations import DEV
from step13b_bundles import book_evidence, load

from book_core.equations import detect
from book_core.equations.cache import CONFIG, load_page
from book_core.evaluation.math_gold import token_geometry

GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK
OUT = ROOT / "experiments/out/step13b/mixed"
COMPLETE = 0.95


def gold_rows():
    rows = {}
    with gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["status"] == "located":
                rows.setdefault(row["page"], []).append(row)
    return rows


def _inside(box, point):
    return box.x0 - 0.5 <= point[0] <= box.x1 + 0.5 and box.y0 - 0.5 <= point[1] <= box.y1 + 0.5


def _math_char(character):
    category = unicodedata.category(character)
    return category[0] in {"N", "S"} or category in {"Lu", "Ll", "Lo"} or character in "()[]{}|"


def page_result(args):
    number, key, evidence, rows = args
    bundle = load(MATH_BOOK, number)
    page, native = bundle["page"], bundle["native"]
    store = page.store
    if key:
        regions = load_page(DEV, key, number).regions
    else:
        regions, _, _, _ = detect.detect_page(
            page, native, bundle["layout"], bundle["units"], evidence["accepted"],
            bundle["math_fonts"], bundle["model_boxes"], evidence["book_size"], CONFIG,
            evidence["pitch"],
        )  # fmt: skip
    cells = detect.char_boxes(native, store)
    geometry = native.span_geometry
    boxes, _, _, _ = token_geometry(page)

    def region_cells(region):
        return [
            detect.range_box(
                store.spans[r.span_id], o, o + 1, geometry.get(r.span_id), cells.get(r.span_id)
            )
            for r in region.span_refs
            for o in range(r.start, r.end)
            if not store.spans[r.span_id].raw_text[o].isspace()
        ]

    counts, labels, examples = Counter(), [], []
    verified = [r for r in rows if r["verified"]]
    all_objects = {o for r in rows for o in r["object_ids"]}
    region_atoms = [(region, region_cells(region)) for region in regions]
    for row in verified:
        objects = set(row["object_ids"])
        tokens = [boxes[t] for t in row["token_ordinals"] if 0 <= t < len(boxes)]
        centres = [((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2) for b in tokens]
        kind = "mixed" if objects and tokens else "text" if tokens else "drawn"
        if kind == "drawn":
            label, used = classify(row, regions, all_objects - objects)
        else:
            label = "missed"
            for region, atoms in region_atoms:
                held = len(objects & set(region.object_ids)) / len(objects) if objects else 1.0
                covered = sum(any(_inside(a, c) for a in atoms) for c in centres)
                if held >= COMPLETE and covered == len(centres):
                    label = "complete"
                    break
                if held > 0 or covered > 0:
                    label = "partial"
            used = []
        if label == "merged_with_other_equations":
            region = used[0]
            others = [
                r for r in rows if r is not row and set(r["object_ids"]) & set(region.object_ids)
            ]
            band = (row["bbox"][1] + row["bbox"][3]) / 2
            same_line = all(r["bbox"][1] - 2 <= band <= r["bbox"][3] + 2 for r in others)
            if region.span_refs and same_line:
                label = "merged_through_text_on_one_line"
        labels.append({"slot": row["slot"], "page": number, "kind": kind, "label": label})
    # Edges of text and mixed regions.
    for region, _atoms in region_atoms:
        if not region.span_refs:
            continue
        counts["text_regions"] += 1
        first, last = region.span_refs[0], region.span_refs[-1]
        for ref, offset, outward in ((first, first.start, -1), (last, last.end - 1, 1)):
            span = store.spans[ref.span_id]
            glyphs = cells.get(ref.span_id)
            if glyphs is not None:
                glyph, box = glyphs[offset], region.bbox
                width = max(1e-6, glyph.x1 - glyph.x0)
                share = max(0.0, min(box.x1, glyph.x1) - max(box.x0, glyph.x0)) / width
                counts["edge_glyphs_checked"] += 1
                if share < 0.5:
                    counts["edge_glyph_cut_by_region_box"] += 1
            neighbour = offset + outward
            if 0 <= neighbour < len(span.raw_text):
                character = span.raw_text[neighbour]
                text = (
                    span.raw_text[first.start : last.end] if first.span_id == last.span_id else ""
                )
                closing = character in ")]}" and text.count("(") > text.count(")")
                if not character.isspace() and (
                    closing or (_math_char(character) and character not in ")]}")
                ):
                    word = (
                        outward < 0
                        and neighbour > 0
                        and span.raw_text[neighbour - 1].isalpha()
                        and character.isalpha()
                    ) or (
                        outward > 0
                        and neighbour + 1 < len(span.raw_text)
                        and span.raw_text[neighbour + 1].isalpha()
                        and character.isalpha()
                    )
                    if not word:
                        counts["edge_character_outside_range"] += 1
                        if len(examples) < 40:
                            examples.append(
                                {
                                    "page": number,
                                    "region": "".join(
                                        store.spans[r.span_id].raw_text[r.start : r.end]
                                        for r in region.span_refs
                                    ),
                                    "outside": character,
                                    "side": "start" if outward < 0 else "end",
                                }
                            )
    return {"labels": labels, "counts": counts, "examples": examples, "regions": len(regions)}


def main(name, key, bundles):
    evidence = book_evidence(MATH_BOOK)
    evidence["pitch"] = json.loads(
        (ROOT / "experiments/out/step13b/dev/m2.json").read_text("utf-8")
    )["summary"]["pitch"]
    rows = gold_rows()
    jobs = [(n, None if bundles else key, evidence, rows.get(n, [])) for n in range(1, 872)]
    with ProcessPoolExecutor(7) as pool:
        results = list(pool.map(page_result, jobs, chunksize=4))
    labels = [x for r in results for x in r["labels"]]
    counts = Counter()
    for r in results:
        counts.update(r["counts"])
    by_kind = {
        kind: dict(Counter(x["label"] for x in labels if x["kind"] == kind))
        for kind in ("drawn", "mixed", "text")
    }
    result = {
        "name": name,
        "key": key,
        "regions": sum(r["regions"] for r in results),
        "verified": len(labels),
        "labels_all": dict(sorted(Counter(x["label"] for x in labels).items())),
        "labels_by_gold_kind": by_kind,
        "edges": dict(counts),
        "edge_examples": [e for r in results for e in r["examples"]][:60],
        "labels": labels,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"labels", "edge_examples"}}, indent=1
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--key")
    parser.add_argument("--bundles", action="store_true")
    args = parser.parse_args()
    main(args.name, args.key, args.bundles)
