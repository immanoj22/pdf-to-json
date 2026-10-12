"""Step 11b: single-item lists in the references, and how many our output misses.

Reference list items are those the list metric scores (``evaluation.lists.list_items``:
outside tables and off index pages; paragraphs inside lists for a dialect without list-item
units). A reference list with exactly one item is missed when the unit of ours holding most
of its tokens is not a list item. The marker glyph is the first character of the item's first
line in the PDF. Reads the token tables written by step11b_tokens.py.

Usage: python step11b_single_items.py --book medical_anatomy --tokens <file.pkl.gz>
"""

import argparse
import gzip
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
OUT = ROOT / "experiments/out/step11b/single_items"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--tokens", required=True)
    args = parser.parse_args()
    from book_core.evaluation.lists import list_items

    with gzip.open(args.tokens, "rb") as handle:
        data = pickle.load(handle)
    rows, units, lines = data["rows"], data["units"], data["lines"]
    token = {(r[0], r[1]): r for r in rows}
    index_pages = [p for p, k, _ in data["navigation"] if k == "index"]
    items = list_items(SimpleNamespace(units=list(data["gold"].values())), index_pages)
    by_list = defaultdict(list)
    for unit in items:
        by_list[unit["list"]["list"]].append(unit)
    singles = [members[0] for members in by_list.values() if len(members) == 1]
    missed, glyphs, examples = 0, Counter(), []
    for unit in singles:
        tokens = [token[(p, o)] for p, f, n in unit["pdf"] for o in range(f, f + n)
                  if (p, o) in token and token[(p, o)][6]]  # fmt: skip
        if not tokens:
            continue
        ours = Counter(t[6] for t in tokens).most_common(1)[0][0]
        if units[ours]["kind"] == "list_item":
            continue
        missed += 1
        first = tokens[0]
        text = lines[(first[0], first[3])]["text"].lstrip()
        glyph = text[:1]
        glyphs[glyph] += 1
        examples.append({"page": first[0], "glyph": glyph, "our_kind": units[ours]["kind"],
                         "stream": units[ours].get("stream"), "line": text[:80]})  # fmt: skip
    report = {
        "book": args.book,
        "reference_list_items": len(items),
        "reference_lists": len(by_list),
        "single_item_lists": len(singles),
        "single_item_lists_missed": missed,
        "missed_share_of_list_items": round(missed / len(items), 4) if items else None,
        "missed_glyphs": dict(glyphs.most_common()),
        "examples": examples,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.book}.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "examples"}, ensure_ascii=False
        )
    )
    for row in examples[:6]:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
