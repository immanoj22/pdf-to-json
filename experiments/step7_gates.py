"""Step 7 gates: 24-page source text gate, I1-I7 and every-line-once, full-book ledger.

Writes experiments/out/step7/{original_source_crosscheck,invariants,full_book}.json and refuses
to report success on any failure. Usage: python step7_gates.py [--skip-full-book]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402
from step4b_run import configured_source, retained_counter  # noqa: E402

from book_core.extraction.fingerprints import source_digest  # noqa: E402
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor  # noqa: E402

OUT = ROOT / "experiments/out/step7"
CACHE = ROOT / ".cache/objects"


def measured_pages():
    gold = json.loads((ROOT / "experiments/out/fixtures_manifest.json").read_text("utf8"))
    unseen = json.loads((ROOT / "experiments/out/step4av/fixtures_manifest.json").read_text("utf8"))
    rows = [{**row, "path": ROOT / "experiments/fixtures" / f"{row['id']}.pdf"} for row in gold]
    rows += [{**row, "path": ROOT / row["fixture"]} for row in unseen]
    return rows


def crosscheck(extractor):
    rows = []
    for original in measured_pages():
        source = configured_source(original["source_key"])
        if source_digest(source) != original["source_sha256"]:
            raise ValueError(f"{original['id']}: original source digest changed")
        expected = retained_counter(
            extractor.extract_object_page(source, original["physical_page"]).page
        )
        actual = retained_counter(extractor.extract_object_page(original["path"], 1).page)
        rows.append(
            {
                "page": original["id"],
                "source_key": original["source_key"],
                "physical_page": original["physical_page"],
                "retained_tokens": actual.total(),
                "missing": (expected - actual).total(),
                "extra": (actual - expected).total(),
            }
        )
        print(original["id"], rows[-1]["missing"], rows[-1]["extra"], flush=True)
    return {
        "pages": len(rows),
        "missing": sum(r["missing"] for r in rows),
        "extra": sum(r["extra"] for r in rows),
        "results": rows,
        "method": "Original source vs fixture through Extractor; TrimBox-centre NFKC Counter",
    }


def invariants(extractor):
    from book_core.layout.invariants import check as layout_check
    from book_core.reading_order.cache import analyze_reading_order
    from book_core.reading_order.graph import check as order_check

    rows = []
    for page in measured_pages():
        order, layout, analysis = analyze_reading_order(page["path"], 1, extractor, cache_dir=CACHE)
        violations = layout_check(layout, analysis)
        ordered = [lid for s in order.streams for lid in s.line_ids]
        rows.append(
            {
                "page": page["id"],
                **{key: len(value) for key, value in sorted(violations.items())},
                "lines": len(layout.lines),
                "lines_ordered": len(ordered),
                "lines_ordered_once": len(ordered) == len(set(ordered))
                and set(ordered) == {line.id for line in layout.lines},
                "order_problems": order_check(order, layout),
            }
        )
    keys = [f"I{i}" for i in range(1, 8)]
    return {
        "pages": len(rows),
        "totals": {key: sum(r.get(key, 0) for r in rows) for key in keys},
        "every_line_once": all(r["lines_ordered_once"] and not r["order_problems"] for r in rows),
        "results": rows,
    }


def full_book():
    from book_core.cli import ledger_check
    from book_core.evaluation.cached_benchmark import CachedBenchmark
    from book_core.extraction.cache import CachedExtractor

    extractor = CachedExtractor(PyMuPDFExtractor(), ROOT / "experiments/out/step2/page_cache")
    result = ledger_check(
        reference_path("spanish_pdf"), extractor, CachedBenchmark(reference_path("spanish_cache"))
    )
    expected = {
        "pages": 758,
        "node_token_count": 495751,
        "source_line_count": 92228,
        "excluded_line_count": 7194,
        "retained_line_count": 85034,
    }
    result["gate"] = {key: result[key] == value for key, value in expected.items()}
    result["gate"]["passing"] = result["passing"]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-full-book", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    extractor = PyMuPDFExtractor("cpu")
    reports = {
        "original_source_crosscheck": crosscheck(extractor),
        "invariants": invariants(extractor),
    }
    if not args.skip_full_book:
        reports["full_book"] = full_book()
    for name, report in reports.items():
        (OUT / f"{name}.json").write_text(
            json.dumps(report, indent=1, ensure_ascii=False) + "\n", "utf8"
        )
    cross, inv = reports["original_source_crosscheck"], reports["invariants"]
    print("24 pages missing/extra:", cross["missing"], cross["extra"])
    print("I1-I7:", inv["totals"], "every line once:", inv["every_line_once"])
    if "full_book" in reports:
        book = reports["full_book"]
        print("full book:", book["node_token_count"], book["gate"])
    failed = cross["missing"] or cross["extra"] or any(inv["totals"].values())
    failed = failed or not inv["every_line_once"]
    failed = failed or ("full_book" in reports and not all(reports["full_book"]["gate"].values()))
    if failed:
        raise SystemExit("Step 7 gate FAILED")


if __name__ == "__main__":
    main()
