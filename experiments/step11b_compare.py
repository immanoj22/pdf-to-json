"""Step 11b: per-book metric table of Step 11b variants next to the Step 11 summaries.

Reads experiments/out/step11/<book>/summary.json ("step11") and
experiments/out/step11b/<label>/<book>/summary.json for each label given, and writes
experiments/out/step11b/compare.json (and prints a compact table).

Usage: python step11b_compare.py r1_navigation r2_markers ...
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step11b"
BOOKS = [
    "spanish_us_history",
    "immigrant_children",
    "art_therapy_index",
    "medical_anatomy",
]


def get(summary, *path):
    value = summary
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def metrics(summary):
    p = get(summary, "paragraphs", "step11_per_page") or {}
    lm = get(summary, "list_metrics", "step11") or {}
    items = lm.get("list_items") or {}
    index = lm.get("index") or {}
    levels = get(summary, "headings", "levels", "all") or {}
    return {
        "paragraph_f1": p.get("boundary_f1"),
        "paragraph_precision": p.get("boundary_precision"),
        "paragraph_recall": p.get("boundary_recall"),
        "paragraph_exact": p.get("exact_unit_match"),
        "merges": p.get("merge_errors"),
        "splits": p.get("split_errors"),
        "list_items": items.get("reference_items"),
        "list_items_exact": items.get("exact_match"),
        "list_item_f1": items.get("item_boundary_f1"),
        "list_boundary_f1": get(items, "list_boundary", "f1"),
        "index_exact": index.get("exact_match"),
        "index_entries": index.get("reference_entries"),
        "sub_entry_level": index.get("sub_entry_level_accuracy"),
        "bibliography_exact": get(lm, "bibliography", "exact_unit_match"),
        "definition_terms_exact": get(lm, "definitions", "definition_term", "exact"),
        "headings_precision": get(summary, "headings", "precision"),
        "headings_recall": get(summary, "headings", "recall"),
        "levels_exact": levels.get("exact"),
        "levels_within_one": levels.get("within_one"),
        "zones_pages": get(summary, "zones", "page_accuracy"),
        "main_flow": get(summary, "reading_order", "step11", "main_flow"),
        "float_anchors": get(summary, "reading_order", "step11", "float_anchors"),
        "index_pages": get(summary, "lists", "index_pages"),
        "glossary_pages": len(get(summary, "lists", "glossary_pages") or []),
        "lists": get(summary, "lists", "count"),
        "lines_problems": len(get(summary, "gates", "invariant_problems") or {}),
    }


def main():
    labels = ["step11", *sys.argv[1:]]
    table = {}
    for book in BOOKS:
        table[book] = {}
        for label in labels:
            base = ROOT / "experiments/out/step11" if label == "step11" else OUT / label
            path = base / book / "summary.json"
            if path.exists():
                table[book][label] = metrics(json.loads(path.read_text("utf-8")))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "compare.json").write_text(json.dumps(table, indent=1) + "\n", "utf-8")
    for book, rows in table.items():
        print(f"== {book}")
        keys = list(next(iter(rows.values()), {}).keys())
        for key in keys:
            values = [
                rows[label].get(key) if label in rows else "-" for label in labels
            ]
            if len({json.dumps(v) for v in values}) == 1:
                continue
            shown = [f"{v:.4f}" if isinstance(v, float) else str(v) for v in values]
            print(f"  {key:22s} " + "  ".join(f"{s:>9s}" for s in shown))


if __name__ == "__main__":
    main()
