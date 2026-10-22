"""Step 15 join precision per book and kind, from the manual verdicts (with the counts).

Reads the check set (``step15_manual``) and the hand-recorded ``verdicts.json``
({join id: [verdict, method, note]}, verdict ``correct`` / ``wrong`` / ``unclear``) and
writes, per book and kind (paragraph, column, list, entry, table):

- **new joins** (decided by the continuity stage; for tables: continuations kept after the
  title checks): correct / checked, wrong ids, unclear ids;
- **kept joins** (Step 9 joins and lists-stage links the stage keeps), where checked;
- **seeded random samples** (books 1 and 2): correct / checked over all joins;
- the reference-scored link verdicts of ``measure/after`` beside them (where gold exists).

Every join of the check set must have a verdict. Usage: python step15_precision.py
"""

# ruff: noqa: E402
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common

OUT = ROOT / "experiments/out/step15"
KINDS = ("paragraph", "column", "list", "entry", "table")


def main():
    check = common.read(OUT / "manual" / "check_set.json")
    verdicts = common.read(OUT / "manual" / "verdicts.json")
    missing = sorted(set(check["joins"]) - set(verdicts))
    if missing:
        raise SystemExit(f"{len(missing)} joins without a verdict, e.g. {missing[:5]}")
    cells = defaultdict(lambda: {"correct": 0, "checked": 0, "wrong": [], "unclear": []})
    for rid, row in check["joins"].items():
        verdict, method, _ = verdicts[rid]
        # Table chains are new in Step 15 (one logical table over its per-page records).
        group = "new" if row["source"] in {"continuity", "tables"} else "kept"
        keys = [(row["book"], row["kind"], group)]
        if any(w.startswith("random") for w in row["why_checked"]):
            keys.append((row["book"], "all", "random"))
        for key in keys:
            cell = cells[key]
            if verdict == "unclear":
                cell["unclear"].append(rid)
                continue
            cell["checked"] += 1
            cell["correct"] += verdict == "correct"
            if verdict == "wrong":
                cell["wrong"].append(rid)
    table = []
    for (book, kind, group), cell in sorted(cells.items()):
        n, c = cell["checked"], cell["correct"]
        table.append({"book": book, "kind": kind, "joins": group, "correct": c, "checked": n,
                      "precision": round(c / n, 4) if n else None, "wrong": cell["wrong"],
                      "unclear": cell["unclear"]})  # fmt: skip
    gold = {}
    for book in common.BOOK_ORDER:
        path = OUT / "measure" / "after" / f"{book}.json"
        if path.exists():
            row = common.read(path)
            gold[book] = {"links": row.get("our_links", {}).get("by_kind"),
                          "tables": {k: v for k, v in row["tables"]["our_links"].items()
                                     if k != "wrong_examples"}}  # fmt: skip
    common.write(OUT / "manual" / "precision.json", {"rows": table, "gold_scored": gold})
    for r in table:
        print(f"{r['book']:20s} {r['kind']:9s} {r['joins']:6s} {r['correct']}/{r['checked']} "
              f"= {r['precision']} wrong {r['wrong']} unclear {r['unclear']}")  # fmt: skip


if __name__ == "__main__":
    main()
