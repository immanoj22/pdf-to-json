"""Step 14b pre-run sweep: build and validate every development page's table records.

For each page of ``step14b_bundles`` this runs what the stage runs (analysis, records with
roles, content and header references, ``PageTables`` validation, title/note candidates over
the final unit view), collecting failures page by page; then the book-level links
(continuation, titles and notes, the TableFormer uses) re-validate every record, so a long
book run cannot fail on a record.

Usage: python step14b_sweep.py [--book NAME]
"""

# ruff: noqa: E402
import argparse
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14b_common as c14b
import step14b_dev as dev

from book_core.tables import captions, opinion, records
from book_core.tables.models import PageTables
from book_core.tables.page import analyze
from book_core.tables.view import ownership, unit_view


def sweep(book):
    failures, pages, cands, claims, contents = [], {}, {}, {}, {}
    counts = {"pages": 0, "tables": 0, "possible": 0}
    for number, pg in c14b.pages(book):
        try:
            ev, built = pg["evidence"], pg["built"]
            accepted, rejected = analyze(ev)
            found, possible, refused, notes = records.records(
                accepted, rejected, ev, built.order, dev.DIGEST, number
            )
            PageTables(source_sha256=dev.DIGEST, page=number, version="sweep", tables=found,
                       possible_tables=possible, rejected=refused, figure_notes=notes)  # fmt: skip
            final, _, _ = unit_view(built.units, found)
            problems = ownership([line.id for line in ev.lines], final, found)
            if problems:
                raise ValueError(f"ownership: {problems[:3]}")
            cands[number] = captions.candidates(ev, found, final)
            claims[number] = captions.figure_claims(ev, found)
            contents[number] = ev.content
            pages[number] = found
            counts["pages"] += 1
            counts["tables"] += len(found)
            counts["possible"] += len(possible)
        except Exception:  # noqa: BLE001 - every failure is collected and reported
            failures.append({"page": number, "error": traceback.format_exc(limit=3)[-600:]})
    try:
        linked, _ = records.link(pages, contents)
        linked, _ = captions.link(linked, cands, claims, dev.figure_labels(book))
        for number, tables in linked.items():
            readings = dev.reader(book)(number, tables)
            for table in tables:
                update, _ = opinion.apply(table, *readings[table.id])
                if update:
                    captions._validated(table, update)
    except Exception:  # noqa: BLE001
        failures.append({"page": "book", "error": traceback.format_exc(limit=4)[-800:]})
    print(book, counts, "failures", len(failures), flush=True)
    for failure in failures[:5]:
        print(failure, flush=True)
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=c14b.common.BOOK_ORDER)
    args = parser.parse_args()
    names = [args.book] if args.book else c14b.common.BOOK_ORDER
    bad = sum(len(sweep(name)) for name in names)
    sys.exit(1 if bad else 0)
