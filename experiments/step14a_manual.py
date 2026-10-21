"""Step 14a Task 4: seeded manual check of 30 tables and overlays of 8 tables.

From the final archives (text-owning tables of the five books), ``draw`` takes 30 tables by
a seeded random draw and renders each page crop with its grid (cells red, header cells
purple, spanning cells thick) beside the reference table box (green) for a manual verdict;
``overlays`` draws 8 tables by a second seeded draw, constrained to include a rotated
table, a table with merged cells and a table without ruling lines. Verdicts are written by
hand into ``experiments/out/step14a/manual/verdicts.json``.

Usage: python step14a_manual.py draw | overlays
"""

# ruff: noqa: E402
import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common

from book_core.cache_store import read_json

SEED_CHECK = 1414
SEED_OVERLAY = 1415
OUT = common.OUT / "manual"


def tables(out="final"):
    found = []
    for book in common.BOOK_ORDER:
        run = common.read(common.OUT / out / f"performance/{book}.json")["run"]
        root = Path(run["output"])
        for number in range(1, run["pages"] + 1):
            page = read_json(root / f"page_{number:06d}.json.gz")
            for table in page["tables"]["tables"]:
                found.append((book, number, table))
    return found


def gold_box(book, number):
    boxes = []
    for t in common.gold_tables(book):
        b = t.get("boxes", {}).get(str(number), {}).get("cells")
        if b:
            boxes.append((b, (0, 170, 0), 2, f"ref {t['table']}"))
    return boxes


def render(book, number, table, path):
    b = table["bbox"]
    pad = 30
    crop = (b["x0"] - pad, b["y0"] - pad, b["x1"] + pad, b["y1"] + pad)
    boxes = gold_box(book, number)
    for cell in table["cells"]:
        cb = cell["bbox"]
        spanning = cell["row_span"] > 1 or cell["column_span"] > 1
        colour = (170, 0, 200) if cell["header"] else (230, 0, 0)
        boxes.append(([cb["x0"], cb["y0"], cb["x1"], cb["y1"]], colour, 3 if spanning else 1, ""))
    label = (
        f"{len(table['rows'])}x{len(table['columns'])} h{table['header_rows']} "
        f"rot{table['rotation']} {table['structure_method']}"
    )
    boxes.append(([b["x0"], b["y0"], b["x1"], b["y1"]], (230, 0, 0), 2, label))
    return common.render(book, number, boxes, path, dpi=110, crop=crop)


def ruled(table):
    return "rules" in table["structure_method"]


def draw():
    found = tables()
    rng = random.Random(SEED_CHECK)
    sample = rng.sample(found, min(30, len(found)))
    rows = []
    for k, (book, number, table) in enumerate(sample, 1):
        path = OUT / "check" / f"{k:02d}_{book}_p{number}.png"
        render(book, number, table, path)
        rows.append({"n": k, "book": book, "page": number, "table": table["id"],
                     "rows": len(table["rows"]), "columns": len(table["columns"]),
                     "header_rows": table["header_rows"], "image": path.name})  # fmt: skip
    common.write(OUT / "check_sample.json", {"seed": SEED_CHECK, "population": len(found),
                                             "sample": rows})  # fmt: skip
    print(len(found), "tables;", len(rows), "drawn")


def overlays():
    found = tables()
    rng = random.Random(SEED_OVERLAY)
    order = rng.sample(found, len(found))
    picks = []
    for need in (
        lambda t: t["rotation"] != 0,
        lambda t: any(c["row_span"] > 1 or c["column_span"] > 1 for c in t["cells"]),
        lambda t: not ruled(t),
    ):
        choice = next((x for x in order if need(x[2]) and x not in picks), None)
        if choice is not None:
            picks.append(choice)
    for x in order:
        if len(picks) >= 8:
            break
        if x not in picks:
            picks.append(x)
    rows = []
    for k, (book, number, table) in enumerate(picks, 1):
        path = OUT.parent / "overlays" / f"table_{book}_p{number}_{k}.png"
        render(book, number, table, path)
        rows.append({"n": k, "book": book, "page": number, "rotation": table["rotation"],
                     "merged_cells": any(c["row_span"] > 1 or c["column_span"] > 1
                                         for c in table["cells"]),
                     "ruled": ruled(table), "image": path.name})  # fmt: skip
    common.write(OUT.parent / "overlays" / "overlays.json", {"seed": SEED_OVERLAY, "tables": rows})
    print(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["draw", "overlays"])
    {"draw": draw, "overlays": overlays}[parser.parse_args().action]()
