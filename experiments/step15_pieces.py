"""Step 15 Part 0 development check: figures that are drawing fragments of a table and its
numbered title (``tables.captions.title_pieces``), on every book.

Runs the table stage's page and book passes on the Step 14b development evidence
(``step14b_bundles``): records, title/note candidates, continuation, title/note links, then
the title-piece rule. Per book: tables whose title was flagged as lying inside a figure
region before and after, the figures absorbed (page, figure, table), and figures that hold
a linked title but stay figures, with the failing test. ``--render N`` draws N seeded pieces
(figure blue, table red).

Usage: python step15_pieces.py [--book NAME] [--render 6]
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
import step14b_dev as dev

from book_core.tables import captions, records
from book_core.tables.page import analyze
from book_core.tables.view import unit_view

OUT = ROOT / "experiments/out/step15/pieces"


def check(book, render=0):
    pages, cands, claims, contents, pieces, figures = {}, {}, {}, {}, {}, {}
    for number, pg in c14b.pages(book):
        ev, built = pg["evidence"], pg["built"]
        accepted, rejected = analyze(ev)
        found, _, _, _ = records.records(accepted, rejected, ev, built.order, dev.DIGEST, number)
        cands[number] = captions.candidates(ev, found, unit_view(built.units, found)[0])
        claims[number] = captions.figure_claims(ev, found)
        pieces[number] = captions.piece_candidates(ev, found)
        figures[number] = {f["id"]: f for f in ev.figures}
        contents[number] = ev.content
        pages[number] = found
    linked, _ = records.link(pages, contents)
    linked, _ = captions.link(linked, cands, claims, dev.figure_labels(book))
    flagged_before = sum(captions.INSIDE_FIGURE in t.review_flags
                         for ts in linked.values() for t in ts)  # fmt: skip
    after, notes, count = captions.title_pieces(linked, pieces)
    flagged_after = [
        {"page": n, "table": t.id, "title_unit": t.title.unit_id}
        for n, ts in after.items() for t in ts if captions.INSIDE_FIGURE in t.review_flags
    ]  # fmt: skip
    absorbed = [{"page": n, "figure": note.figure_id, "table": note.table_id,
                 "name": figures[n][note.figure_id].get("name")}
                for n, found in notes.items() for note in found]  # fmt: skip
    row = {"book": book, "titles_inside_figure_regions_before": flagged_before,
           "title_pieces": count, "flagged_after": flagged_after, "absorbed": absorbed}  # fmt: skip
    common.write(OUT / f"{book}.json", row)
    print(book, flagged_before, "->", len(flagged_after), "pieces", count, flush=True)
    for item in random.Random(1500).sample(absorbed, min(render, len(absorbed))):
        number = item["page"]
        table = next(t for t in after[number] if t.id == item["table"])
        figure = figures[number][item["figure"]]
        boxes = [([table.bbox.x0, table.bbox.y0, table.bbox.x1, table.bbox.y1], (220, 0, 0), 2,
                  "table"),
                 ([figure["bbox"].x0, figure["bbox"].y0, figure["bbox"].x1, figure["bbox"].y1],
                  (0, 0, 220), 2, "piece")]  # fmt: skip
        common.render(book, number, boxes, OUT / f"{book}_p{number}.png", dpi=90)
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--render", type=int, default=0)
    args = parser.parse_args()
    for name in [args.book] if args.book else common.BOOK_ORDER:
        check(name, args.render)
