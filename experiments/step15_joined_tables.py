"""Step 15 Task 4: tables over several pages scored as one logical table.

For every located reference table on two or more pages, our table chain holding most of its
cell tokens (the continuity record's table chains of a final archive) is turned into one
grid: its members' grids (``step14b_dev.record_grid``) stacked in order, each continuation
without the leading rows the record names as repeated header rows. Scores against the whole
reference grid: structure TEDS and full TEDS of the joined table, the same with repeated
header rows kept (duplicates), header rows exact, and header duplicates removed. Reference
tables whose parts are not all in one chain of ours are counted, with the reason.

Usage: python step15_joined_tables.py [--book NAME] [--out final]
"""

# ruff: noqa: E402
import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common  # noqa: F401
import step14b_dev as dev
from step14a_bundles import token_owners

from book_core.cache_store import read_json
from book_core.evaluation import table_scoring
from book_core.model.spans import ExtractedPage
from book_core.tables.models import TableRecord

OUT = ROOT / "experiments/out/step15"


def gold_grid(t):
    return {"cells": [(c["row"], c["column"], c["row_span"], c["column_span"], c["header"],
                       frozenset((p, o) for p, o in c["tokens"])) for c in t["cells"]],
            "header_rows": t["header_rows"]}  # fmt: skip


def stacked(grids, repeated):
    """One grid from per-page grids; ``repeated[k]``: leading rows of part k to drop."""
    cells, offset = [], 0
    for k, grid in enumerate(grids):
        drop = repeated[k] if k else 0
        rows = 0
        for row, column, rs, cs, header, tokens in grid["cells"]:
            rows = max(rows, row + rs)
            if row < drop:
                continue
            cells.append((row - drop + offset, column, rs, cs, header and k == 0, tokens))
        offset += rows - drop
    return {"cells": cells, "header_rows": grids[0]["header_rows"]}


def check(book, out):
    run = common.read(OUT / out / "performance" / f"{book}.json")["run"]
    root = Path(run["output"])
    archive = read_json(root / "book.json.gz")
    chains = [c for c in archive["continuity"]["chains"] if c["kind"] == "table"]
    member_of = {m: c for c in chains for m in c["members"]}
    gold = [t for t in common.gold_tables(book) if t["located"] and len(t["pages"]) > 1
            and not t["problems"]]  # fmt: skip
    grids, records = {}, {}
    pages = sorted({p for t in gold for p in t["pages"]}
                   | {p for c in chains for p in c["pages"]})  # fmt: skip
    for number in pages:
        payload = read_json(root / f"page_{number:06d}.json.gz")
        page = ExtractedPage.model_validate(payload["source"])
        owners = token_owners(page, common.layout_page(book, number))
        spans = {sid: span.raw_text for sid, span in page.store.spans.items()}
        for row in payload["tables"]["tables"]:
            record = TableRecord.model_validate(row)
            records[record.id] = (number, record)
            grids[record.id] = dev.record_grid(number, record, owners, spans, None)
    rows, totals = [], Counter()
    for t in gold:
        reference = gold_grid(t)
        tokens = {tok for cell in reference["cells"] for tok in cell[5]}
        votes = Counter()
        for tid, grid in grids.items():
            held = sum(len(tokens & cell[5]) for cell in grid["cells"])
            if held:
                votes[tid] = held
        chain_votes = Counter()
        for tid, n in votes.items():
            chain_votes[member_of[tid]["id"] if tid in member_of else tid] += n
        if not chain_votes:
            totals["not_detected"] += 1
            rows.append({"table": t["table"], "pages": t["pages"], "joined": None,
                         "reason": "no table of ours"})  # fmt: skip
            continue
        best = chain_votes.most_common(1)[0][0]
        chain = next((c for c in chains if c["id"] == best), None)
        members = chain["members"] if chain else [best]
        repeated = [0] + [b["repeated_header_rows"] for b in chain["breaks"]] if chain else [0]
        parts = [grids[m] for m in members]
        joined = stacked(parts, repeated)
        kept = stacked(parts, [0] * len(parts))
        covered = {records[m][0] for m in members}
        whole = covered >= set(t["pages"])
        totals["whole" if whole else "partial"] += 1
        totals["header_duplicates_removed"] += sum(repeated)
        rows.append({
            "table": t["table"], "pages": t["pages"], "ours_pages": sorted(covered),
            "whole": whole, "members": len(members),
            "teds": round(table_scoring.teds(reference, joined), 4),
            "teds_full": round(table_scoring.teds(reference, joined, content=True), 4),
            "teds_duplicates_kept": round(table_scoring.teds(reference, kept), 4),
            "header_rows": [t["header_rows"], joined["header_rows"]],
            "repeated_header_rows": repeated[1:],
        })  # fmt: skip
    scored = [r for r in rows if r.get("teds") is not None]
    whole = [r for r in scored if r["whole"]]

    def mean(key, rows_):
        return round(sum(r[key] for r in rows_) / len(rows_), 4) if rows_ else None

    result = {
        "book": book, "reference_multi_page_tables": len(gold), **totals,
        "teds_joined": mean("teds", scored), "teds_full_joined": mean("teds_full", scored),
        "teds_duplicates_kept": mean("teds_duplicates_kept", scored),
        "teds_joined_whole_only": mean("teds", whole),
        "header_rows_exact": round(sum(r["header_rows"][0] == r["header_rows"][1]
                                       for r in scored) / len(scored), 4) if scored else None,
        "tables": rows,
    }  # fmt: skip
    common.write(OUT / out / "joined_tables" / f"{book}.json", result)
    print(book, {k: v for k, v in result.items() if k != "tables"}, flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=["medical_anatomy", common.MATH_BOOK])
    parser.add_argument("--out", default="final")
    args = parser.parse_args()
    for name in [args.book] if args.book else ["medical_anatomy", common.MATH_BOOK]:
        check(name, args.out)
