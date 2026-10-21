"""Step 14b Task 2: where TableFormer helps our table structure, measured per book.

On every text-owning table that matches a reference segment (``step14b_dev.pipeline``
without the TableFormer uses), TableFormer (accurate) reads the table as the stage does
(``tables.opinion``: the page rendered through the Extractor, the region cut out and turned
upright; readings cached per image). Its cells take tokens by token-box centre. Policies scored with
the table gold (structure and full TEDS, adjacency, header rows):

- ``geometry``: our grid (production);
- ``weak_<criterion>`` / ``weak_any``: TableFormer's grid where our evidence is weak —
  ``lists`` (list items or bulleted lines in cells), ``empty`` (at least 30% of body cells
  empty), ``organizer`` (a ruled lattice whose cells hold long text, 8+ tokens on average),
  ``spans`` (spans split at column boundaries or overlapping merged areas);
- ``header_all`` / ``header_none``: our grid with TableFormer's header rows (always, or only
  where our grid found no header evidence);
- ``second_opinion``: our grid, flagged for review where the two structures disagree
  (structure TEDS between them below 0.8); scored as flag precision/recall against our
  tables with structure TEDS below 0.9.

Usage: python step14b_tableformer.py [--book NAME] [--label final]
"""

# ruff: noqa: E402
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14a_methods as methods
import step14b_common as c14b
import step14b_dev as dev

from book_core.evaluation import table_scoring as ts

CRITERIA = ("lists", "empty", "organizer", "spans")
EMPTY_SHARE = 0.3
ORGANIZER_TOKENS = 8
DISAGREE = 0.8
WRONG = 0.9
KEYS = ("structure_scored", "teds_structure_mean", "teds_full_mean", "adjacency_f1",
        "header_rows_exact", "header_token_accuracy")  # fmt: skip


def weak(table, grid):
    """{criterion: bool} of one record (see the module)."""
    body = [(c, cell) for c, cell in zip(table.cells, grid["cells"], strict=True) if not c.header]
    empty = sum(not cell[5] for _, cell in body)
    filled = [cell for _, cell in body if cell[5]]
    tokens = sum(len(cell[5]) for cell in filled) / max(1, len(filled))
    flags = " ".join(table.review_flags)
    return {
        "lists": any(i.kind == "list_item" for c in table.cells for i in c.content),
        "empty": bool(body) and empty >= EMPTY_SHARE * len(body),
        "organizer": table.structure_method.startswith("rules+ruled")
        and tokens >= ORGANIZER_TOKENS,
        "spans": "split at a column boundary" in flags or "overlapping merged" in flags,
    }


def with_header(grid, rows):
    cells = [(r, c, rs, cs, r < rows, t) for r, c, rs, cs, _, t in grid["cells"]]
    return {"cells": cells, "header_rows": rows}


def run(book, label):
    started = time.perf_counter()
    titled, _, owners, spans, _, _ = dev.pipeline(book, second=False)
    recs = {(n, i): t for n, tables in titled.items() for i, t in enumerate(tables)}
    ours = {k: dev.record_grid(k[0], t, owners[k[0]], spans[k[0]], None) for k, t in recs.items()}
    gold = ts.gold_segments(common.gold_tables(book))
    matches = ts.match(gold, ours)
    tf, rows, seconds, boxes = {}, [], 0.0, {}
    for gkey, okey, _ in matches:
        gkey, okey = tuple(gkey), tuple(okey)
        table, number = recs[okey], okey[0]
        begun = time.perf_counter()
        cells, header_rows = dev.reader(book)(number, [table])[table.id]
        seconds += time.perf_counter() - begun
        if number not in boxes:
            boxes = {number: methods.token_boxes(book, number)}
        grid = methods.grid_from_cells(number, cells, boxes[number], header_rows)
        if not grid["cells"]:
            grid = {"cells": [(0, 0, 1, 1, False, frozenset())], "header_rows": 0}
        tf[okey] = grid
        g = gold[gkey]
        rows.append({
            "page": number, "table": gkey[0], **weak(table, ours[okey]),
            "teds_ours": round(ts.teds(g, ours[okey]), 4), "teds_tf": round(ts.teds(g, grid), 4),
            "agreement": round(ts.teds(grid, ours[okey]), 4),
            "header_ours": table.header_rows, "header_tf": header_rows,
            "header_gold": g["header_rows"],
            "header_evidence": table.structure_evidence.get("header"),
        })  # fmt: skip
    by_key = {(r["page"], r["table"]): r for r in rows}
    policy = {"geometry": {tuple(m[1]): ours[tuple(m[1])] for m in matches}}

    def keyed(choose):
        out = {}
        for gkey, okey, _ in matches:
            okey = tuple(okey)
            out[okey] = choose(by_key[(okey[0], gkey[0])], okey)
        return out

    for criterion in (*CRITERIA, "any"):

        def pick(row, okey, criterion=criterion):
            hit = any(row[c] for c in CRITERIA) if criterion == "any" else row[criterion]
            return tf[okey] if hit else ours[okey]

        policy[f"weak_{criterion}"] = keyed(pick)
    policy["header_all"] = keyed(lambda row, k: with_header(ours[k], row["header_tf"]))
    policy["header_none"] = keyed(
        lambda row, k: with_header(ours[k], row["header_tf"])
        if row["header_evidence"] == "no header evidence" else ours[k]
    )  # fmt: skip
    policy["tableformer"] = keyed(lambda row, k: tf[k])
    scores = {}
    for name, grids in policy.items():
        result = ts.score(gold, grids)
        scores[name] = {k: result[k] for k in KEYS}
        if name.startswith("weak_"):
            criterion = name[5:]
            scores[name]["tables_switched"] = sum(
                (any(r[c] for c in CRITERIA) if criterion == "any" else r[criterion]) for r in rows
            )  # fmt: skip
    flagged = [r for r in rows if r["agreement"] < DISAGREE]
    wrong = [r for r in rows if r["teds_ours"] < WRONG]
    caught = [r for r in flagged if r["teds_ours"] < WRONG]
    scores["second_opinion"] = {
        "tables": len(rows), "flagged": len(flagged), "our_wrong": len(wrong),
        "caught": len(caught),
        "flag_precision": round(len(caught) / len(flagged), 4) if flagged else None,
        "flag_recall": round(len(caught) / len(wrong), 4) if wrong else None,
        "base_rate": round(len(wrong) / len(rows), 4) if rows else None,
    }  # fmt: skip
    result = {"scores": scores, "tables": rows, "tableformer_seconds": round(seconds, 1),
              "seconds": round(time.perf_counter() - started, 1)}  # fmt: skip
    common.write(c14b.OUT / "tableformer" / label / f"{book}.json", result)
    for name, row in scores.items():
        print(book, name, row, flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--label", default="try")
    args = parser.parse_args()
    for name in [args.book] if args.book else common.BOOK_ORDER:
        if name != "art_therapy_index":
            run(name, args.label)
