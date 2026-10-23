"""Consolidate required Step 17 evidence; missing evidence fails the gate."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
from book_core.caching import code_digest

FINAL = ROOT / "experiments/out/step17/final"
BOOKS = ("spanish_us_history", "immigrant_children", "art_therapy_index",
         "medical_anatomy", "statistics")


def read(name):
    return json.loads((FINAL / name).read_text("utf-8"))


def main():
    report = read("report_data.json")
    contract = read("contract_check.json")
    assembly_producer = code_digest("assembly")
    rows = {}
    for book in BOOKS:
        data = report[book]
        proof = read(f"after/{book}_full_gates.json")
        invariants = proof["invariant_totals"]
        expected = {f"I{n}": int(book == "statistics" and n == 7) for n in range(1, 8)}
        parity = read(f"parity/{book}.json")
        lossless = data["lossless"]
        document = json.loads((Path(data["book_json_folder"]) / "book.json").read_text("utf-8"))
        rows[book] = {
            "pages": data["pages"],
            "schema_and_round_trip": data["schema_errors"] == 0 and data["round_trip_identical"],
            "lossless": all(lossless.get(k, 0) == 0 for k in
                            ("missing", "extra", "discard_missing", "discard_extra")),
            "invariants": invariants, "invariants_expected": invariants == expected,
            "ownership": len(proof["ownership"]) == data["pages"] and all(
                r["units_once"] and r["ordered_once"] for r in proof["ownership"].values()),
            "parity": parity["continuity"]["identical"] and parity["assembly"]["identical"]
                      and not parity["tables"]["differ"],
            "json_identity_and_links": not contract[book]["defects"]
                                       and not contract[book]["unresolved_review_unit_ids_by_kind"],
            "current_assembly_producer": document["metadata"]["converter"]["producer"]
                                         == assembly_producer,
        }
    source = read("source_crosscheck.json")
    worker = read("workers_book3.json")
    ledger = read("full_book.json")
    validation = read("validation_record.json")
    cover_audit = read("book2_change_audit.json")
    statistics_disk = read("performance/statistics.json")["assembly_refresh"]["disk"]
    checks = {
        "five_books": all(all(row[k] for k in (
            "schema_and_round_trip", "lossless", "invariants_expected", "ownership", "parity",
            "json_identity_and_links", "current_assembly_producer")) for row in rows.values()),
        "30_source_pages": source["pages"] == 30 and source["missing"] == source["extra"] == 0,
        "spanish_ledger": report["spanish_us_history"]["lossless"]["ledger_retained"] == 495751
                          and ledger["node_token_count"] == 495751 and all(ledger["gate"].values()),
        "worker_and_production_bytes": worker["one_vs_two_workers_identical"]
                                       and worker["production_vs_development_identical"]
                                       and worker["assembly_producer"] == assembly_producer,
        "non_ocr_changes_explained": not cover_audit["unexpected_non_ocr_page_changes"]
                                     and cover_audit["non_ocr_heading_changes_explained"],
        "tests_and_lint": validation["full_suite"]["passed"]
                          and validation["full_suite"]["assembly_producer"] == assembly_producer
                          and validation["cache_closure_after_cleanup"]["passed"]
                          and validation["ruff"]["passed"]
                          and validation["wheel_assets"]["passed"],
        "approved_cleanup_plan_unchanged": hashlib.sha256(
            (FINAL.parent / "cache_prune_dry_run.json").read_bytes()).hexdigest()
            == "f7956e2fead2ff25601019908304b3d6de0ecf29811e358bc05870c15d21d793",
        "statistics_publication_reserve": statistics_disk["reserve_bytes"] == 5_000_000_000
                                          and statistics_disk["free_before"]
                                          - statistics_disk["estimated_write_bytes"] >= 5_000_000_000
                                          and statistics_disk["free_after"] >= 5_000_000_000,
    }
    files = [p for p in FINAL.rglob("*.json")
             if p.name != "gate_summary.json" and "run_history" not in p.parts]
    result = {"passed": all(checks.values()), "checks": checks, "books": rows,
              "free_bytes": shutil.disk_usage(ROOT).free,
              "evidence_sha256": {p.relative_to(FINAL).as_posix(): hashlib.sha256(p.read_bytes())
                                    .hexdigest() for p in files}}
    (FINAL / "gate_summary.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    print(json.dumps({"passed": result["passed"], "checks": checks, "books": rows}, indent=1))
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
