"""Step 8 gates: 24-page source gate, I1-I7, every line ordered once (with furniture roles
applied), and the full-book ledger. Reuses the Step 7 gate functions; writes to out/step8.

The 24 measured pages are single-page fixtures, so their furniture decision is a one-page
book (no folio run can form); the whole-book every-line-once gate for all pages of the three
books is checked by step8_run.py. Usage: python step8_gates.py [--skip-full-book]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

import step7_gates  # noqa: E402

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor  # noqa: E402

OUT = ROOT / "experiments/out/step8"


def furniture_once(extractor):
    from book_core.furniture.apply import apply_page
    from book_core.furniture.cache import decide_book
    from book_core.furniture.features import page_features
    from book_core.reading_order.cache import analyze_reading_order
    from book_core.reading_order.graph import check

    rows = []
    for page in step7_gates.measured_pages():
        order, layout, analysis = analyze_reading_order(
            page["path"], 1, extractor, cache_dir=step7_gates.CACHE
        )
        native = analysis.native.page
        decisions = decide_book({1: page_features(native, layout, order)}, {}, layout.source_sha256)
        result = apply_page(native, layout, order, decisions.roles[1], decisions.book.markers[0])
        ordered = [lid for s in result.order.streams for lid in s.line_ids]
        rows.append(
            {
                "page": page["id"],
                "lines": len(layout.lines),
                "lines_ordered_once": len(ordered) == len(set(ordered))
                and set(ordered) == {line.id for line in layout.lines},
                "order_problems": check(result.order, None),
                "roles": sorted({r.role for r in result.roles}),
            }
        )
    return {
        "pages": len(rows),
        "every_line_once": all(r["lines_ordered_once"] and not r["order_problems"] for r in rows),
        "results": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-full-book", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    extractor = PyMuPDFExtractor("cpu")
    reports = {
        "original_source_crosscheck": step7_gates.crosscheck(extractor),
        "invariants": step7_gates.invariants(extractor),
        "furniture_every_line_once": furniture_once(extractor),
    }
    if not args.skip_full_book:
        reports["full_book"] = step7_gates.full_book()
    for name, report in reports.items():
        (OUT / f"{name}.json").write_text(
            json.dumps(report, indent=1, ensure_ascii=False) + "\n", "utf8"
        )
    cross, inv = reports["original_source_crosscheck"], reports["invariants"]
    once = reports["furniture_every_line_once"]
    print("24 pages missing/extra:", cross["missing"], cross["extra"])
    print("I1-I7:", inv["totals"], "every line once:", inv["every_line_once"], once["every_line_once"])
    if "full_book" in reports:
        book = reports["full_book"]
        print("full book:", book["node_token_count"], book["gate"])
    failed = cross["missing"] or cross["extra"] or any(inv["totals"].values())
    failed = failed or not inv["every_line_once"] or not once["every_line_once"]
    failed = failed or ("full_book" in reports and not all(reports["full_book"]["gate"].values()))
    if failed:
        raise SystemExit("Step 8 gate FAILED")


if __name__ == "__main__":
    main()
