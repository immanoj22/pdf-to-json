"""Step 9 gates: 24-page source gate, I1-I7, every line in exactly one unit and ordered once,
and the full-book ledger. Reuses the Step 7/8 gate functions; writes to out/step9.

The 24 measured pages are single-page fixtures (a one-page book for furniture and
paragraphs); the whole-book unit gate for all pages of the three books is in step9_run.py.
Usage: python step9_gates.py [--skip-full-book]
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

OUT = ROOT / "experiments/out/step9"


def units_once(extractor):
    from book_core.furniture.apply import apply_page
    from book_core.furniture.cache import decide_book
    from book_core.furniture.features import page_features
    from book_core.paragraphs.lexicon import Profile
    from book_core.paragraphs.page import build_page
    from book_core.reading_order.cache import analyze_reading_order
    from book_core.reading_order.graph import check

    rows = []
    for page in step7_gates.measured_pages():
        order, layout, analysis = analyze_reading_order(
            page["path"], 1, extractor, cache_dir=step7_gates.CACHE
        )
        native = analysis.native.page
        decisions = decide_book({1: page_features(native, layout, order)}, {}, layout.source_sha256)
        furniture = apply_page(native, layout, order, decisions.roles[1], decisions.book.markers[0])
        profile = Profile()
        profile.add_page(native, layout, furniture.order)
        result = build_page(native, layout, furniture, profile.freeze())
        lines = [lid for unit in result.units for lid in unit.line_ids]
        ordered = [lid for s in result.order.streams for lid in s.line_ids]
        expected = {line.id for line in layout.lines}
        rows.append(
            {
                "page": page["id"],
                "lines": len(layout.lines),
                "units": len(result.units),
                "every_line_in_one_unit": len(lines) == len(set(lines)) and set(lines) == expected,
                "ordered_once": len(ordered) == len(set(ordered)) and set(ordered) == expected,
                "order_problems": check(result.order, None),
            }
        )
    ok = all(r["every_line_in_one_unit"] and r["ordered_once"] and not r["order_problems"]
             for r in rows)  # fmt: skip
    return {"pages": len(rows), "every_line_in_one_unit_and_ordered_once": ok, "results": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-full-book", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    extractor = PyMuPDFExtractor("cpu")
    reports = {
        "original_source_crosscheck": step7_gates.crosscheck(extractor),
        "invariants": step7_gates.invariants(extractor),
        "units_every_line_once": units_once(extractor),
    }
    if not args.skip_full_book:
        reports["full_book"] = step7_gates.full_book()
    for name, report in reports.items():
        (OUT / f"{name}.json").write_text(
            json.dumps(report, indent=1, ensure_ascii=False) + "\n", "utf8"
        )
    cross, inv = reports["original_source_crosscheck"], reports["invariants"]
    units = reports["units_every_line_once"]
    print("24 pages missing/extra:", cross["missing"], cross["extra"])
    print("I1-I7:", inv["totals"], "every line once:", inv["every_line_once"],
          units["every_line_in_one_unit_and_ordered_once"])  # fmt: skip
    if "full_book" in reports:
        print("full book:", reports["full_book"]["node_token_count"], reports["full_book"]["gate"])
    failed = cross["missing"] or cross["extra"] or any(inv["totals"].values())
    failed = failed or not inv["every_line_once"]
    failed = failed or not units["every_line_in_one_unit_and_ordered_once"]
    failed = failed or ("full_book" in reports and not all(reports["full_book"]["gate"].values()))
    if failed:
        raise SystemExit("Step 9 gate FAILED")


if __name__ == "__main__":
    main()
