"""Step 10 gates: 24-page source gate, I1-I7, every line in exactly one unit and ordered once
(the Step 9 one-page check, re-run), the structure stage on each one-page fixture (decides
without error; every heading and styled unit is a unit of the page), and the full-book
ledger. Writes to out/step10. The whole-book unit gate for the three books is in
step10_run.py (page-by-page identity with the frozen Step 9 run).

Usage: python step10_gates.py [--skip-full-book]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

import step7_gates  # noqa: E402
import step9_gates  # noqa: E402

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor  # noqa: E402

OUT = ROOT / "experiments/out/step10"


def structure_on_fixtures(extractor):
    from book_core.furniture.apply import apply_page
    from book_core.furniture.cache import decide_book as decide_furniture
    from book_core.furniture.features import page_features
    from book_core.paragraphs.lexicon import Profile
    from book_core.paragraphs.page import build_page
    from book_core.reading_order.cache import analyze_reading_order
    from book_core.structure.decide import DEFAULT_CONFIG, decide_book
    from book_core.structure.evidence import token_owners
    from book_core.structure.features import page_evidence

    rows = []
    for page in step7_gates.measured_pages():
        order, layout, analysis = analyze_reading_order(
            page["path"], 1, extractor, cache_dir=step7_gates.CACHE
        )
        native = analysis.native.page
        decisions = decide_furniture({1: page_features(native, layout, order)}, {},
                                     layout.source_sha256)  # fmt: skip
        furniture = apply_page(native, layout, order, decisions.roles[1],
                               decisions.book.markers[0])  # fmt: skip
        profile = Profile()
        profile.add_page(native, layout, furniture.order)
        result = build_page(native, layout, furniture, profile.freeze())
        evidence = {
            "source_sha256": layout.source_sha256,
            "pages": [page_evidence(native, layout, result, furniture,
                                    token_owners(native, layout))],
            "runs": [], "bookmarks": [], "toc_pages": [], "cache_key_inputs": {},
        }  # fmt: skip
        decided = decide_book(evidence, DEFAULT_CONFIG)
        units = {u.id for u in result.units}
        named = [u for h in decided["headings"] for u in h.unit_ids]
        named += [u for s in decided["styled"] for u in s.unit_ids]
        rows.append({
            "page": page["id"], "units": len(units), "headings": len(decided["headings"]),
            "styled": len(decided["styled"]), "zone": decided["page_zones"][0].zone,
            "unknown_units": sorted(set(named) - units),
        })  # fmt: skip
    return {"pages": len(rows), "ok": all(not r["unknown_units"] for r in rows), "results": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-full-book", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    extractor = PyMuPDFExtractor("cpu")
    reports = {
        "original_source_crosscheck": step7_gates.crosscheck(extractor),
        "invariants": step7_gates.invariants(extractor),
        "units_every_line_once": step9_gates.units_once(extractor),
        "structure_on_fixtures": structure_on_fixtures(extractor),
    }
    if not args.skip_full_book:
        reports["full_book"] = step7_gates.full_book()
    for name, report in reports.items():
        (OUT / f"{name}.json").write_text(
            json.dumps(report, indent=1, ensure_ascii=False) + "\n", "utf8"
        )
    cross, inv = reports["original_source_crosscheck"], reports["invariants"]
    units, structure = reports["units_every_line_once"], reports["structure_on_fixtures"]
    print("24 pages missing/extra:", cross["missing"], cross["extra"])
    print("I1-I7:", inv["totals"], "every line once:", inv["every_line_once"])
    print("units once:", units["every_line_in_one_unit_and_ordered_once"],
          "structure:", structure["ok"])  # fmt: skip
    if "full_book" in reports:
        print("full book:", reports["full_book"]["node_token_count"], reports["full_book"]["gate"])
    failed = cross["missing"] or cross["extra"] or any(inv["totals"].values())
    failed = failed or not inv["every_line_once"] or not structure["ok"]
    failed = failed or not units["every_line_in_one_unit_and_ordered_once"]
    failed = failed or ("full_book" in reports and not all(reports["full_book"]["gate"].values()))
    if failed:
        raise SystemExit("Step 10 gate FAILED")


if __name__ == "__main__":
    main()
