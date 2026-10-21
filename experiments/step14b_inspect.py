"""Step 14b inspection: our grid next to the reference grid for one page (development aid).

Prints each table of the page (rows x columns, header rows, method) with its cells' text and
spans, and the reference segments on the page with theirs, plus the units around the table.

Usage: python step14b_inspect.py --book NAME --page N [--text 40]
"""

# ruff: noqa: E402
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common as c14b

from book_core.evaluation import table_scoring
from book_core.tables.page import analyze


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=common.BOOK_ORDER)
    parser.add_argument("--page", required=True, type=int)
    parser.add_argument("--text", type=int, default=40)
    args = parser.parse_args()
    bundle = c14b.load(args.book, pages={args.page})
    page = bundle["pages"][args.page]
    ev = page["evidence"]
    tables, rejected = analyze(ev)
    width = args.text
    for index, draft in enumerate(tables):
        g = draft.grid
        shape = f"{len(g.rows)}x{len(g.columns)} header={g.header_rows}"
        print(f"TABLE {index} strong={draft.strong} rot={draft.rotation} {shape} {g.method}",
              g.evidence, g.flags)  # fmt: skip
        print("  columns", [round(a, 1) for a, _ in g.columns], round(g.columns[-1][1], 1))
        for cell in g.cells:
            text = " ".join(a.text.strip() for a in cell.atoms)[:width]
            if text or cell.row_span > 1 or cell.column_span > 1:
                print(f"  r{cell.row} c{cell.column} {cell.row_span}x{cell.column_span}"
                      f"{' H' if cell.header else ''} {text!r}")  # fmt: skip
    for r in rejected:
        print("REJECTED", r.kind, r.reasons)
    gold = table_scoring.gold_segments(common.gold_tables(args.book))
    texts = {(args.page, i): t for i, t in enumerate(c14b.token_texts(args.book, args.page))}
    for key, g in gold.items():
        if key[1] != args.page:
            continue
        print(f"GOLD {key} {g['rows']}x{g['columns']} header={g['header_rows']} {g['problems']}")
        for row, col, rs, cs, header, tokens in sorted(g["cells"]):
            text = " ".join(texts.get(t, "?") for t in sorted(tokens))[:width]
            if text or rs > 1 or cs > 1:
                print(f"  r{row} c{col} {rs}x{cs}{' H' if header else ''} {text!r}")


if __name__ == "__main__":
    main()
