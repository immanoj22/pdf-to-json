"""Step 14b Task 6: seeded manual checks (30 tables, 20 title/note links per book) and 8
overlays, from the Step 14b final archives.

- ``draw``: 30 text-owning tables of the five books (seed 1424), each page crop with its grid
  (column headers purple, row headers cyan, section rows orange, data cells red; spanning
  cells thick), title (blue) and notes (orange) and the reference table box (green).
- ``links``: per book, up to 20 linked titles and notes (seed 1426); a book with fewer links
  gets all of them plus a draw of its unlinked candidates (grey) up to 20.
- ``overlays``: 8 tables (seed 1425), constrained to include a rotated table, merged cells,
  a table without ruled columns, a table with a linked title and one with notes.

Verdicts are written by hand into ``experiments/out/step14b/manual/verdicts.json``.

Usage: python step14b_manual.py draw | links | overlays
"""

# ruff: noqa: E402
import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common as c14b
from step14a_manual import gold_box

from book_core.cache_store import read_json

SEED_CHECK, SEED_OVERLAY, SEED_LINKS = 1424, 1425, 1426
OUT = c14b.OUT / "manual"
COLOURS = {"column_header": (170, 0, 200), "row_header": (0, 160, 200), "section": (240, 140, 0),
           "data": (230, 0, 0)}  # fmt: skip


def tables():
    found = []
    for book in common.BOOK_ORDER:
        run = common.read(c14b.FINAL / f"performance/{book}.json")["run"]
        root = Path(run["output"])
        for number in range(1, run["pages"] + 1):
            page = read_json(root / f"page_{number:06d}.json.gz")
            for table in page["tables"]["tables"]:
                found.append((book, number, table))
    return found


def _lines_box(book, number, line_ids):
    lines = {line.id: line.bbox for line in common.layout_page(book, number).lines}
    boxes = [lines[lid] for lid in line_ids if lid in lines]
    return [min(b.x0 for b in boxes), min(b.y0 for b in boxes),
            max(b.x1 for b in boxes), max(b.y1 for b in boxes)]  # fmt: skip


def render(book, number, table, path, unlinked=False):
    b = table["bbox"]
    texts = [(t, (0, 90, 230), "title") for t in [table["title"]] if t]
    texts += [(n, (240, 140, 0), "note") for n in table["notes"]]
    if unlinked:
        texts += [(u, (128, 128, 128), "unlinked") for u in table["unlinked_texts"]]
    extent = [b["x0"], b["y0"], b["x1"], b["y1"]]
    shapes = []
    for text, colour, name in texts:
        box = _lines_box(book, number, text["line_ids"])
        shapes.append((box, colour, 2, name))
        extent = [min(extent[0], box[0]), min(extent[1], box[1]),
                  max(extent[2], box[2]), max(extent[3], box[3])]  # fmt: skip
    pad = 24
    crop = (extent[0] - pad, extent[1] - pad, extent[2] + pad, extent[3] + pad)
    boxes = gold_box(book, number)
    for cell in table["cells"]:
        cb = cell["bbox"]
        spanning = cell["row_span"] > 1 or cell["column_span"] > 1
        boxes.append(([cb["x0"], cb["y0"], cb["x1"], cb["y1"]], COLOURS[cell["role"]],
                      3 if spanning else 1, ""))  # fmt: skip
    label = (f"{len(table['rows'])}x{len(table['columns'])} h{table['header_rows']} "
             f"stub{table['row_header_columns']} rot{table['rotation']}")  # fmt: skip
    boxes.append(([b["x0"], b["y0"], b["x1"], b["y1"]], (230, 0, 0), 2, label))
    return common.render(book, number, boxes + shapes, path, dpi=110, crop=crop)


def ruled_columns(table):
    return table["structure_method"].startswith("rules")


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


def links():
    found = tables()
    rng = random.Random(SEED_LINKS)
    out = {}
    for book in common.BOOK_ORDER:
        items, unlinked = [], []
        for _, number, table in (x for x in found if x[0] == book):
            items += [(number, table, "title", table["title"])] if table["title"] else []
            items += [(number, table, "note", n) for n in table["notes"]]
            unlinked += [(number, table, "unlinked", u) for u in table["unlinked_texts"]]
        picked = rng.sample(items, min(20, len(items)))
        if len(picked) < 20:
            picked += rng.sample(unlinked, min(20 - len(picked), len(unlinked)))
        rows = []
        for k, (number, table, kind, text) in enumerate(picked, 1):
            path = OUT / "links" / f"{book}_{k:02d}_p{number}_{kind}.png"
            render(book, number, table, path, unlinked=kind == "unlinked")
            rows.append({"n": k, "page": number, "table": table["id"], "kind": kind,
                         "rule": text.get("rule") or text.get("reason"),
                         "image": path.name})  # fmt: skip
        out[book] = {"links": len(items), "unlinked": len(unlinked), "sample": rows}
        print(book, len(items), "links,", len(unlinked), "unlinked;", len(rows), "drawn")
    common.write(OUT / "links_sample.json", {"seed": SEED_LINKS, "books": out})


def overlays():
    found = tables()
    rng = random.Random(SEED_OVERLAY)
    order = rng.sample(found, len(found))
    picks = []
    for need in (
        lambda t: t["rotation"] != 0,
        lambda t: any(c["row_span"] > 1 or c["column_span"] > 1 for c in t["cells"]),
        lambda t: not ruled_columns(t),
        lambda t: t["title"] is not None,
        lambda t: bool(t["notes"]),
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
        path = c14b.OUT / "overlays" / f"table_{book}_p{number}_{k}.png"
        render(book, number, table, path)
        rows.append({"n": k, "book": book, "page": number, "rotation": table["rotation"],
                     "merged_cells": any(c["row_span"] > 1 or c["column_span"] > 1
                                         for c in table["cells"]),
                     "ruled_columns": ruled_columns(table), "title": table["title"] is not None,
                     "notes": len(table["notes"]), "image": path.name})  # fmt: skip
    common.write(c14b.OUT / "overlays" / "overlays.json", {"seed": SEED_OVERLAY, "tables": rows})
    print(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["draw", "links", "overlays"])
    {"draw": draw, "links": links, "overlays": overlays}[parser.parse_args().action]()
