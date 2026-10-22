"""Step 15 development: table continuation marks before and after the title checks.

Runs the table stage's page and book passes on the Step 14b development evidence
(``step14b_dev.pipeline`` without TableFormer, which never changes continuation), then
``records.title_checks``. Each continuation mark is scored
against the reference tables: correct when both tables hold most of their reference cell
tokens from the same reference table, wrong when from different ones, else unscored.

Usage: python step15_tables.py [--book NAME]
"""

# ruff: noqa: E402
import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_dev as dev

from book_core.tables import records

OUT = ROOT / "experiments/out/step15/tables"


def reference_of(book):
    out = {}
    for t in common.gold_tables(book):
        for c in t["cells"]:
            for p, o in c["tokens"]:
                out[(p, o)] = t["table"]
    return out


def score(pages, owners, spans, gold_of):
    out, rows = Counter(), []
    for number, tables in pages.items():
        for table in tables:
            to = table.continues_to
            if to is None or to.page not in pages:
                continue
            following = next(t for t in pages[to.page] if t.id == to.table_id)
            sides = []
            for page, record in ((number, table), (to.page, following)):
                grid = dev.record_grid(page, record, owners[page], spans[page], None)
                votes = Counter(gold_of.get(tok) for cell in grid["cells"] for tok in cell[5])
                votes.pop(None, None)
                sides.append(votes.most_common(1)[0][0] if votes else None)
            verdict = "unscored" if None in sides else (
                "correct" if sides[0] == sides[1] else "wrong")  # fmt: skip
            out[verdict] += 1
            rows.append({"pages": [number, to.page], "gold": sides, "verdict": verdict})
    return dict(out), rows


def check(book):
    titled, _, owners, spans, stats, _ = dev.pipeline(book, second=False)
    gold_of = reference_of(book)
    before, rows_before = score(titled, owners, spans, gold_of)
    after_pages, withdrawn = records.title_checks(titled)
    after, rows_after = score(after_pages, owners, spans, gold_of)
    kept = {tuple(r["pages"]) for r in rows_after}
    removed = [r for r in rows_before if tuple(r["pages"]) not in kept]
    row = {"book": book, "title_side": stats.get("title_side"), "before": before,
           "after": after, "withdrawn": withdrawn, "withdrawn_rows": removed,
           "wrong_after": [r for r in rows_after if r["verdict"] == "wrong"]}  # fmt: skip
    common.write(OUT / f"{book}.json", row)
    print(book, row["title_side"], "before", before, "after", after, "withdrawn",
          Counter(r["verdict"] for r in removed), flush=True)  # fmt: skip
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    args = parser.parse_args()
    for name in (
        [args.book]
        if args.book
        else ["medical_anatomy", common.MATH_BOOK, "immigrant_children", "spanish_us_history"]
    ):
        check(name)
