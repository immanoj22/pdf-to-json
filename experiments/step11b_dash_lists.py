"""Step 11b: dash lists and dialogue, with and without the set-off marker rule.

Runs the Step 11 lists stage of one book twice into a scratch cache (the producer cache is not
touched): "before" with ``lines.set_off_marker`` disabled, "after" with the current rule. For
every list whose items carry dash markers it reports the items, and flags dialogue or running
prose: an item text that opens with an opening question, exclamation or quotation mark, or
that holds a further dash followed by a lower-case word (a dialogue tag, "—¿Qué? —preguntó").

Usage: python step11b_dash_lists.py --book spanish_us_history --scratch <dir>
"""

import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import regex

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from step9_run import CACHE9
from step10_run import CACHE10, evidence_for, load_book

OUT = ROOT / "experiments/out/step11b/dash_lists"
_DIALOGUE = regex.compile(r"^\s*[¿¡«“\"'‘]|\s[—–]\s*\p{Ll}")


def dash_lists(result, cache, extractor, source, inputs):
    from book_core.lists.cache import load_page
    from book_core.paragraphs.text import unit_text

    lists = defaultdict(list)
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        layout, _ = inputs(page)
        built = load_page(result, number, cache)
        for unit in built.units:
            if unit.kind == "list_item" and unit.marker and unit.marker.type == "dash":
                text = unicodedata.normalize(
                    "NFKC", unit_text(page.store, layout, unit)
                )
                body = text.lstrip()[1:]
                lists[unit.list_id].append({"page": number, "text": text[:90],
                                            "dialogue": bool(_DIALOGUE.search(body))})  # fmt: skip
    rows = [{"items": len(v), "dialogue_items": sum(i["dialogue"] for i in v), "first": v[0]}
            for v in lists.values()]  # fmt: skip
    return {
        "dash_lists": len(rows),
        "dash_items": sum(r["items"] for r in rows),
        "lists_with_dialogue_items": sum(r["dialogue_items"] > 0 for r in rows),
        "dialogue_items": sum(r["dialogue_items"] for r in rows),
        "dialogue_examples": [i for v in lists.values() for i in v if i["dialogue"]][
            :10
        ],
        "examples": [r["first"] for r in rows[:10]],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--scratch", required=True)
    args = parser.parse_args()
    from book_core.lists import lines
    from book_core.lists.cache import analyze_book_lists
    from book_core.structure.cache import analyze_book_structure

    loaded = load_book(args.book)
    source, extractor, inputs, furniture, _, paragraphs, _, _ = loaded
    evidence, evidence_key, _ = evidence_for(args.book, loaded)
    structure, _ = analyze_book_structure(evidence, evidence_key, CACHE10)
    report = {"book": args.book}
    current = lines.set_off_marker
    for label, rule in (("before", lambda *a: None), ("after", current)):
        lines.set_off_marker = rule
        cache = Path(args.scratch) / f"{args.book}_{label}"
        result, _ = analyze_book_lists(
            lambda: extractor.extract_pages(source), inputs, paragraphs, CACHE9, structure,
            furniture, cache,
        )  # fmt: skip
        report[label] = dash_lists(result, cache, extractor, source, inputs)
    lines.set_off_marker = current
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.book}.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    for label in ("before", "after"):
        row = report[label]
        print(args.book, label, {k: row[k] for k in ("dash_lists", "dash_items",
                                                     "lists_with_dialogue_items",
                                                     "dialogue_items")})  # fmt: skip
        for example in row["dialogue_examples"][:3]:
            print("   ", json.dumps(example, ensure_ascii=False))


if __name__ == "__main__":
    main()
