"""Step 14a pre-run sweep: build and validate the table records of every page from bundles.

Runs ``tables.page.analyze`` and ``tables.records.records`` on each bundled page with the
page's lists-stage reading order and validates ``PageTables`` (grid coverage, overlapping
cells, line ownership), so a long book run cannot fail on a record. Book 1 uses its
candidate-page bundle (pages without a candidate hold no table).

Usage: python step14a_sweep.py [--book NAME]
"""

# ruff: noqa: E402
import argparse
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14a_dev as dev

from book_core.tables import records
from book_core.tables.models import PageTables
from book_core.tables.page import analyze


def sweep(book):
    bundle = dev.load(book, sub=book == "spanish_us_history")
    failures, counts = [], {"pages": 0, "tables": 0, "possible": 0}
    for number, page in sorted(bundle["pages"].items()):
        try:
            accepted, rejected = analyze(page["evidence"])
            order = common.list_page(book, number).order
            found, possible, refused, notes = records.records(
                accepted, rejected, page["evidence"], order, "0" * 64, number
            )
            PageTables(
                source_sha256="0" * 64,
                page=number,
                version="sweep",
                tables=found,
                possible_tables=possible,
                rejected=refused,
                figure_notes=notes,
            )
            counts["pages"] += 1
            counts["tables"] += len(found)
            counts["possible"] += len(possible)
        except Exception:  # noqa: BLE001 - every failure is collected and reported
            failures.append({"page": number, "error": traceback.format_exc(limit=3)[-600:]})
    print(book, counts, "failures", len(failures), flush=True)
    for failure in failures[:5]:
        print(failure, flush=True)
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    args = parser.parse_args()
    bad = sum(len(sweep(b)) for b in ([args.book] if args.book else common.BOOK_ORDER))
    sys.exit(1 if bad else 0)
