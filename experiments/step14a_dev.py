"""Step 14a development scoring: run the table page analysis on bundles and score it.

Loads ``.cache/step14a/bundles/<book>.pkl.gz`` (``step14a_bundles.py``), attaches the
learned detectors' table boxes (``step14a_models.py`` output), runs ``tables.page.analyze``
on every page and scores against the table gold (``evaluation.table_scoring``): detection
P/R/F1 per page segment, structure-only TEDS, cell adjacency F1, header accuracy. Writes
``experiments/out/step14a/dev/<label>/<book>.json`` with per-segment details.

Usage: python step14a_dev.py --book NAME [--label try1] [--models heron,pp,tatr]
"""

# ruff: noqa: E402
import argparse
import gzip
import pickle
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
from step14a_bundles import BUNDLES

from book_core.evaluation import table_scoring
from book_core.model.common import BBox
from book_core.tables.page import analyze


def load(book, models=("heron", "pp", "tatr"), sub=False):
    """The book's bundle; ``sub``: only pages with a gold table or a table candidate (a
    development shortcut; pages without candidates never hold a table)."""
    with gzip.open(BUNDLES / f"{book}{'_sub' if sub else ''}.pkl.gz", "rb") as stream:
        bundle = pickle.load(stream)
    detections = common.OUT / "models" / f"{book}.json"
    found = common.read(detections)["pages"] if detections.exists() else {}
    navigation = common.navigation(book)
    for number, page in bundle["pages"].items():
        page["evidence"].navigation = navigation.get(number)
        # Rules and fills are recomputed from the bundled drawings with the current code.
        if "drawings" in page:
            from book_core.tables.rulings import page_rules

            ev = page["evidence"]
            ev.rules, ev.fills = page_rules(page["drawings"], ev.font)
            from book_core.tables.rulings import freeform

            ev.freeform = freeform(page["drawings"])
        row = found.get(str(number), {})
        page["evidence"].models = {
            name: [
                (BBox(x0=b[0], y0=b[1], x1=b[2], y1=b[3]), b[4], b[5]) for b in row.get(name, [])
            ]
            for name in models
            if name in row
        }
    return bundle


def our_grid(number, draft, owners):
    """Scoring grid of one draft: cells with their (page, ordinal) tokens."""
    import unicodedata

    from book_core.ledger.tokenization import TOKEN_PATTERN

    pieces = {}  # span -> [(start, cell, token count)]
    for index, cell in enumerate(draft.grid.cells):
        for atom in cell.atoms:
            count = len(TOKEN_PATTERN.findall(unicodedata.normalize("NFKC", atom.text)))
            pieces.setdefault(atom.span_id, []).append((atom.start or 0, index, count))
    queue = {}
    for sid, parts in pieces.items():
        order = []
        for _, index, count in sorted(parts):
            order += [index] * count
        queue[sid] = order
    tokens = {i: set() for i in range(len(draft.grid.cells))}
    for ordinal, (_, spans) in enumerate(owners):
        sid = next((s for s in spans if s in queue), None)
        if sid is None:
            continue
        order = queue[sid]
        index = order.pop(0) if len(order) > 1 else (order[0] if order else None)
        if index is not None:
            tokens[index].add((number, ordinal))
    return {
        "cells": [
            (c.row, c.column, c.row_span, c.column_span, c.header, frozenset(tokens[i]))
            for i, c in enumerate(draft.grid.cells)
        ],
        "header_rows": draft.grid.header_rows,
    }


def run(book, label, models, sub=False):
    started = time.perf_counter()
    bundle = load(book, models, sub)
    ours, details, rejected = {}, {}, Counter()
    for number, page in sorted(bundle["pages"].items()):
        tables, refused = analyze(page["evidence"])
        for r in refused:
            rejected[r.kind] += 1
        for index, draft in enumerate(tables):
            key = (number, index)
            ours[key] = our_grid(number, draft, page["tokens"])
            details[key] = {
                "bbox": [
                    round(v, 1)
                    for v in (draft.bbox.x0, draft.bbox.y0, draft.bbox.x1, draft.bbox.y1)
                ],
                "rotation": draft.rotation,
                "families": draft.families,
                "sources": sorted(draft.sources),
                "rows": len(draft.grid.rows),
                "columns": len(draft.grid.columns),
                "header_rows": draft.grid.header_rows,
                "method": draft.grid.method,
                "strong": draft.strong,
            }
    gold = table_scoring.gold_segments(common.gold_tables(book))
    everything = table_scoring.score(gold, ours)
    possible = {k for k, v in details.items() if not v["strong"]}
    result = table_scoring.score(gold, {k: v for k, v in ours.items() if k not in possible})
    matched_any = {tuple(m[1]) for m in everything["matches"]}
    result["all_candidates"] = {
        k: everything[k]
        for k in ("our_tables", "matched", "detection_precision", "detection_recall")
    }
    result["possible_tables"] = {
        "count": len(possible),
        "matching_a_reference_table": len(possible & matched_any),
    }
    matched_ours = {tuple(m[1]) for m in result["matches"]}
    matched_gold = {tuple(m[0]) for m in result["matches"]}
    result["unmatched_ours"] = [
        {"page": k[0], **details[k]}
        for k in sorted(ours)
        if k not in matched_ours and details[k]["strong"]
    ]
    result["missed_gold"] = [
        {"table": k[0], "page": k[1], "rows": g["rows"], "columns": g["columns"]}
        for k, g in sorted(gold.items())
        if k not in matched_gold and table_scoring.tokens_of(g)
    ]
    per = []
    for gkey, okey, _ in result["matches"]:
        g, o = gold[tuple(gkey)], ours[tuple(okey)]
        per.append(
            {
                "table": gkey[0],
                "page": gkey[1],
                "gold_rows": g["rows"],
                "gold_columns": g["columns"],
                "gold_header": g["header_rows"],
                **details[tuple(okey)],
                "teds": round(table_scoring.teds(g, o), 4),
                "adjacency": table_scoring.adjacency(g, o),
            }
        )
    result["matched_detail"] = per
    result["rejected"] = dict(rejected)
    result["seconds"] = round(time.perf_counter() - started, 1)
    common.write(common.OUT / "dev" / label / f"{book}.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--label", default="try")
    parser.add_argument("--models", default="heron,pp,tatr")
    parser.add_argument("--sub", action="store_true", help="candidate pages only (book 1)")
    args = parser.parse_args()
    models = tuple(m for m in args.models.split(",") if m)
    for book in [args.book] if args.book else common.BOOK_ORDER:
        r = run(book, args.label, models, args.sub)
        print(
            book,
            {
                k: r[k]
                for k in (
                    "reference_segments",
                    "our_tables",
                    "matched",
                    "detection_precision",
                    "detection_recall",
                    "teds_structure_mean",
                    "teds_exact_share",
                    "adjacency_f1",
                    "header_rows_exact",
                    "header_token_accuracy",
                    "possible_tables",
                    "rejected",
                    "seconds",
                )
            },  # fmt: skip
            flush=True,
        )


if __name__ == "__main__":
    main()
