"""Step 14a: collect the final evidence into one summary for the report.

Reads the final run records (time, memory), the detection/structure scores (``dev/final``),
the method comparison (``methods/final``), the unit effect (``final/effect``), the gates
(proofs, source cross-check, ledger, archives), the 13c review-status change, the gold
coverage, today's measurements and the manual check. Writes
``experiments/out/step14a/final/summary.json``.
"""

# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common

OUT = common.OUT


def maybe(path):
    return common.read(path) if Path(path).exists() else None


def main():
    books = {}
    for book in common.BOOK_ORDER:
        run = common.read(OUT / f"final/performance/{book}.json")["run"]
        stages = run["stages"]
        gates = maybe(OUT / f"final/after/{book}_full_gates.json")
        books[book] = {
            "pages": run["pages"],
            "time_seconds": {
                "total": round(run["total"]["wall_seconds"]),
                "tables_stage": round(stages["tables"]["wall_seconds"]),
                "mathml_stage": round(stages["mathml"]["wall_seconds"]),
            },
            "peak_memory_gb": {
                "run": round(run["peak_tree_rss_bytes"] / 2**30, 2),
                "tables_stage": round(stages["tables"]["peak_rss_bytes"] / 2**30, 2),
            },
            "source_hashes": run["source_hashes"],
            "warnings": run["warnings"],
            "invariants": gates and gates["invariant_totals"],
            "lines_owned_and_ordered_once": gates
            and all(v["units_once"] and v["ordered_once"] for v in gates["ownership"].values()),
            "detection_structure": maybe(OUT / f"dev/final/{book}.json"),
            "methods": maybe(OUT / f"methods/final/{book}.json"),
            "effect": maybe(OUT / f"final/effect/{book}.json"),
            "measured_before": maybe(OUT / f"measure/before/{book}.json"),
        }
        for key in ("detection_structure",):
            if books[book][key]:
                books[book][key] = {
                    k: v
                    for k, v in books[book][key].items()
                    if k not in {"matches", "matched_detail"}
                }
    summary = {
        "books": books,
        "gold_coverage": maybe(OUT / "gold/coverage.json"),
        "source_crosscheck": {
            k: v
            for k, v in (maybe(OUT / "final/source_crosscheck.json") or {}).items()
            if k != "results"
        },
        "archives": maybe(OUT / "final/final_outputs.json"),
        "mathml_13c_fix": maybe(OUT / "final/mathml_13c_fix.json"),
        "manual_check": (maybe(OUT / "manual/verdicts.json") or {}).get("summary"),
        "overlays": maybe(OUT / "overlays/overlays.json"),
    }
    common.write(OUT / "final/summary.json", summary)
    for book, row in books.items():
        print(book, row["time_seconds"], row["peak_memory_gb"], row["invariants"])


if __name__ == "__main__":
    main()
