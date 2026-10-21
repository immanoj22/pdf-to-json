"""Step 14a Task 4: effect of tables on units, from the final archive of a run.

Before: the lists-stage units (unchanged in their cache). After: the final view (units
without table lines, ``table_view``) plus one unit per table cell. Per book:

- paragraph metric (``evaluation.paragraphs.paragraph_scores``, per page) before and after;
- page by page: lines that moved from units into cells (by unit kind), and the change of
  boundary true positives, false positives and misses on that page;
- reference table tokens by owner kind after (cell, unit kind);
- order inside reference tables: pairs of located cells compared by our cell order
  (row-major, then token order) against the reference row-major order;
- display equation units read inside cells.

Usage: python step14a_effect.py --book NAME [--out final]
"""

# ruff: noqa: E402
import argparse
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
from step14a_bundles import token_owners

from book_core.cache_store import read_json
from book_core.evaluation.paragraphs import PARAGRAPH_KINDS, paragraph_scores
from book_core.ledger.tokenization import TOKEN_PATTERN
from book_core.lists.models import TEXT_KINDS
from book_core.model.spans import ExtractedPage

CELL_KIND = "table_cell"


def archive(book, out):
    run = common.read(common.OUT / out / f"performance/{book}.json")["run"]
    return Path(run["output"]), run


def cell_tokens(page, table, owners):
    """{ordinal: cell id} of one table (split spans: tokens assigned in piece order)."""
    spans = page["source"]["store"]["spans"]
    line_cell, pieces = {}, defaultdict(list)
    for cell in table["cells"]:
        for lid in cell["line_ids"]:
            line_cell[lid] = cell["id"]
        for ref in cell["span_refs"]:
            raw = spans[ref["span_id"]]["raw_text"]
            text = raw[ref["start"] : ref["end"]] if ref["start"] is not None else raw
            count = len(TOKEN_PATTERN.findall(unicodedata.normalize("NFKC", text)))
            pieces[ref["span_id"]].append((ref["start"] or 0, cell["id"], count))
    queue = {}
    for sid, parts in pieces.items():
        order = []
        for _, cid, count in sorted(parts):
            order += [cid] * count
        queue[sid] = order
    found = {}
    for ordinal, (line, span_ids) in enumerate(owners):
        if line in line_cell:
            found[ordinal] = line_cell[line]
            continue
        sid = next((s for s in span_ids if s in queue), None)
        if sid is not None and queue[sid]:
            found[ordinal] = queue[sid].pop(0) if len(queue[sid]) > 1 else queue[sid][0]
    return found


def evaluate(book, out):
    root, run = archive(book, out)
    gold = common.derived_gold(book) if book != common.MATH_BOOK else None
    tables_gold = common.gold_tables(book)
    in_gold_cells = {(p, o): (t["table"], i) for t in tables_gold
                     for i, c in enumerate(t["cells"]) for p, o in c["tokens"]}  # fmt: skip
    before, after = {}, {}
    kinds_after = Counter()
    per_page = {}
    moved_total = Counter()
    order = Counter()
    equations_in_cells = 0
    for number in range(1, run["pages"] + 1):
        payload = read_json(root / f"page_{number:06d}.json.gz")
        page = ExtractedPage.model_validate(payload["source"])
        layout = common.layout_page(book, number)
        owners = token_owners(page, layout)
        units = payload["units"]["units"]
        view = payload["table_view"]
        removed = set(view["removed"])
        final = [u for u in units if u["id"] not in removed] + view["added"]
        tables = payload["tables"]["tables"]
        unit_of = {lid: u for u in units for lid in u["line_ids"]}
        final_of = {lid: u for u in final for lid in u["line_ids"]}
        cells = {}
        cell_order = {}
        cell_units = {c["id"]: set(c["unit_ids"]) for t in payload["tables"]["tables"]
                      for c in t["cells"]}  # fmt: skip
        for table in tables:
            found = cell_tokens(payload, table, owners)
            cells.update(found)
            rank = {c["id"]: k for k, c in enumerate(
                sorted(table["cells"], key=lambda c: (c["row"], c["column"])))}  # fmt: skip
            for ordinal, cid in found.items():
                cell_order[ordinal] = (table["id"], rank[cid], ordinal)
            equations_in_cells += sum(len(c["equation_unit_ids"]) for c in table["cells"])
        moved = Counter()
        for table in tables:
            for lid in table["line_ids"]:
                moved[unit_of[lid]["kind"] if lid in unit_of else "none"] += 1
        moved_total.update(moved)
        page_before, page_after = {}, {}
        for ordinal, (line, _) in enumerate(owners):
            unit = unit_of.get(line)
            if unit is not None and unit["kind"] in TEXT_KINDS:
                page_before[(number, ordinal)] = unit["id"]
            if ordinal in cells:
                # A unit lying wholly in its cell (a list item in a cell) stays a unit there.
                unit = unit_of.get(line)
                inside = unit is not None and unit["id"] in cell_units.get(cells[ordinal], ())
                page_after[(number, ordinal)] = unit["id"] if inside else cells[ordinal]
                kind = CELL_KIND
            else:
                unit = final_of.get(line)
                kind = unit["kind"] if unit else "none"
                if unit is not None and unit["kind"] in TEXT_KINDS:
                    page_after[(number, ordinal)] = unit["id"]
            if (number, ordinal) in in_gold_cells:
                kinds_after[kind] += 1
        before.update(page_before)
        after.update(page_after)
        if tables:
            per_page[number] = {"tables": len(tables), "lines_moved_from": dict(moved)}
        # Order inside reference tables on this page: first token of each located cell.
        for t in tables_gold:
            if number not in t["pages"]:
                continue
            firsts = []
            for c in sorted(t["cells"], key=lambda c: (c["row"], c["column"])):
                refs = [o for p, o in c["tokens"] if p == number]
                if refs and refs[0] in cell_order:
                    firsts.append(cell_order[refs[0]])
            for i in range(len(firsts)):
                for j in range(i + 1, len(firsts)):
                    if firsts[i][0] != firsts[j][0]:
                        continue
                    order["pairs"] += 1
                    order["agree"] += firsts[i] <= firsts[j]
    result = {
        "book": book,
        "tables": sum(v["tables"] for v in per_page.values()),
        "lines_moved_into_tables_by_unit_kind": dict(moved_total.most_common()),
        "reference_cell_tokens_by_owner_after": dict(kinds_after.most_common()),
        "cell_order_in_reference_tables": {
            "pairs": order["pairs"],
            "agreement": round(order["agree"] / order["pairs"], 4) if order["pairs"] else None,
        },
        "display_equation_units_in_cells": equations_in_cells,
    }
    if gold is not None:
        sb = paragraph_scores(gold, before)
        sa = paragraph_scores(gold, after)
        result["paragraphs"] = {"before": sb, "after": sa}
        # Page by page: boundary changes where tables moved lines.
        sequence = [
            (p, o, u["unit"])
            for u in gold.units
            if u["kind"] in PARAGRAPH_KINDS
            for p, first, n in u["pdf"]
            for o in range(first, first + n)
        ]
        changes = defaultdict(Counter)
        for name, logical in (("before", before), ("after", after)):
            scored = [(p, o, u) for p, o, u in sequence if (p, o) in logical]
            for (p1, o1, u1), (p2, o2, u2) in zip(scored, scored[1:], strict=False):
                ref, ours = u1 != u2, logical[(p1, o1)] != logical[(p2, o2)]
                changes[p1][f"{name}_tp"] += ref and ours
                changes[p1][f"{name}_fp"] += ours and not ref
                changes[p1][f"{name}_fn"] += ref and not ours
        for number, row in changes.items():
            delta = {k: row[f"after_{k}"] - row[f"before_{k}"] for k in ("tp", "fp", "fn")}
            if any(delta.values()):
                per_page.setdefault(number, {"tables": 0, "lines_moved_from": {}})
                per_page[number]["boundary_change"] = delta
        unexplained = [n for n, row in per_page.items() if "boundary_change" in row and
                       not row["tables"]]  # fmt: skip
        result["pages_with_boundary_changes"] = sum(
            "boundary_change" in r for r in per_page.values()
        )
        result["boundary_changes_without_a_table"] = unexplained
    result["pages"] = {str(k): v for k, v in sorted(per_page.items())}
    common.write(common.OUT / out / "effect" / f"{book}.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=common.BOOK_ORDER)
    parser.add_argument("--out", default="final")
    args = parser.parse_args()
    r = evaluate(args.book, args.out)
    short = {k: v for k, v in r.items() if k not in {"pages", "paragraphs"}}
    if "paragraphs" in r:
        for side in ("before", "after"):
            s = r["paragraphs"][side]
            short[side] = {k: s[k] for k in ("boundary_precision", "boundary_recall",
                                             "boundary_f1", "exact_unit_match")}  # fmt: skip
    print(short)


if __name__ == "__main__":
    main()
