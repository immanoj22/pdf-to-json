"""Audit the frozen diagnostic checkpoint; exit nonzero for any failed gate."""

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from step11c_identity import BOOKS  # noqa: E402

OUT = ROOT / "experiments/out/step11d"


def read(path):
    return json.loads(path.read_text("utf8"))


def metric_content(value):
    if isinstance(value, dict):
        return {k: metric_content(v) for k, v in value.items() if k not in {"seconds", "cache_hit"}}
    if isinstance(value, list):
        return [metric_content(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def audit():
    assert read(OUT / "before/complete.json")["complete"]
    books = {}
    for book in BOOKS:
        frozen = read(OUT / "before" / f"{book}.json")
        old = read(ROOT / "experiments/out/step11c/after" / f"{book}.json")
        objects = read(OUT / "before" / f"{book}_objects.json")
        old_objects = read(ROOT / "experiments/out/step11c/before" / f"{book}_objects.json")
        gates = read(OUT / "before" / f"{book}_full_gates.json")
        metrics = metric_content(read(OUT / "before/metrics" / book / "summary.json"))
        old_metrics = metric_content(
            read(ROOT / "experiments/out/step11c/metrics" / book / "summary.json")
        )
        identical = all(frozen[field] == old[field] for field in ("pages", "books", "keys"))
        assert identical and objects == old_objects and metrics == old_metrics, book
        assert len(gates["ownership"]) == len(frozen["pages"])
        assert all(r["units_once"] and r["ordered_once"] for r in gates["ownership"].values())
        books[book] = {
            "pages": len(frozen["pages"]),
            "stages": sorted(next(iter(frozen["pages"].values()))),
            "page_and_book_identities_match_step11c": identical,
            "cache_keys_match_step11c": frozen["keys"] == old["keys"],
            "exact_native_analysis_digests_match": objects == old_objects,
            "reported_metrics_match_step11c": metrics == old_metrics,
            "metric_content_sha256": digest(metrics),
            "invariant_totals": gates["invariant_totals"],
            "violations": {p: r for p, r in gates["invariants"].items() if any(r.values())},
            "every_visual_line_assigned_and_ordered_once": True,
        }
    crosscheck = read(OUT / "before/source_crosscheck.json")
    assert crosscheck["pages"] == 24 and crosscheck["missing"] == crosscheck["extra"] == 0
    ledger = read(OUT / "before/full_book.json")
    assert ledger["node_token_count"] == 495751 and all(ledger["gate"].values())
    tests = ET.parse(OUT / "pytest_baseline.xml").getroot()
    cases = tests.findall(".//testcase")
    assert len(cases) == 869
    assert not tests.findall(".//failure") and not tests.findall(".//error")
    names = {c.attrib["name"] for c in cases}
    required = (
        "test_workers_and_production_are_byte_identical_and_hash_pdf_once",
        "test_missing_upstream_dependency_is_detected",
    )
    assert set(required) <= names
    integrity = True
    invariant_pass = not any(any(r["invariant_totals"].values()) for r in books.values())
    result = {
        "status": "PASS" if invariant_pass else "FAIL",
        "baseline_integrity_pass": integrity,
        "full_book_invariants_pass": invariant_pass,
        "books": books,
        "source_crosscheck": {k: crosscheck[k] for k in ("pages", "missing", "extra")},
        "spanish_ledger_tokens": ledger["node_token_count"],
        "tests_passed": len(cases),
        "worker_equivalence_scope": "fresh three-page synthetic fixture; all-book rerun unverified",
        "cache_closure_including_missing_dependency": "PASS in existing full test suite",
        "hidden_only_variant": "unverified: not implemented or run",
        "repair_only_variant": "unverified: not implemented or run",
        "combined_variant": "unverified: not implemented or run",
        "implementation_held_at_baseline_gate": not invariant_pass,
        "step12_started": False,
    }
    (OUT / "verification.json").write_text(json.dumps(result, indent=2) + "\n", "utf8")
    print(json.dumps(result, indent=2))
    return invariant_pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", action="store_true", help="check file hashes without rewriting"
    )
    args = parser.parse_args()
    if args.manifest:
        manifest = read(OUT / "manifest.json")
        for relative, expected in manifest["files"].items():
            path = (ROOT / relative).resolve()
            assert path.is_relative_to(ROOT)
            assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, relative
        print(f"Manifest PASS: {len(manifest['files'])} files")
    else:
        raise SystemExit(0 if audit() else 1)
