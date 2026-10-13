"""Audit the completed Step 11c evidence; no extraction, scoring or gold writes."""

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step11c"
sys.path.insert(0, str(ROOT / "backend/src"))

from step11c_identity import digest  # noqa: E402

from book_core.book_run import LOADED_FINAL_DIGEST  # noqa: E402
from book_core.cache_store import read_json  # noqa: E402
from book_core.extraction.fingerprints import stable_id  # noqa: E402

BOOKS = {
    "spanish_us_history": 758,
    "immigrant_children": 331,
    "art_therapy_index": 9,
    "medical_anatomy": 314,
}


def load(relative):
    return json.loads((OUT / relative).read_text("utf8"))


def files(path):
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in Path(path).iterdir()
        if p.is_file()
    }


def check_page_references(payload):
    lines = {line for unit in payload["units"]["units"] for line in unit["line_ids"]}
    assert set(payload["line_spans"]) == lines
    spans = payload["source"]["store"]["spans"]
    assert all(ids and all(span in spans for span in ids) for ids in payload["line_spans"].values())
    positions = {span: i for i, span in enumerate(spans)}
    for line, ids in payload["line_spans"].items():
        assert line == stable_id("visual_line", *sorted(ids))
        assert ids == sorted(ids, key=positions.__getitem__)


def main():
    identities = load("after/comparison.json")
    metrics = load("metrics_comparison.json")
    provenance = load("before/metrics_provenance.json")
    outputs = {}
    for book, pages in BOOKS.items():
        assert identities[book] == {"pages": True, "books": True}
        assert metrics[book]["identical"]
        baseline = OUT / "before" / f"{book}_metrics.json"
        assert (
            hashlib.sha256(baseline.read_bytes()).hexdigest() == provenance["books"][book]["sha256"]
        )
        migration = load(f"migration/{book}.json")
        assert set(migration) == {"native", "analysis", "layout", "reading_order"}
        assert all(row["pages_identical"] == pages for row in migration.values())
        serial = load(f"performance/{book}_workers1.json")
        after = load(f"after/{book}.json")
        for stage in (
            "native",
            "analysis",
            "layout",
            "reading_order",
            "furniture",
            "paragraphs",
            "structure_evidence",
        ):
            assert serial["cache_keys"][stage] == after["keys"][stage]
        assert serial["pages"] == pages and serial["source_hashes"] == 1
        archive = load(f"archive/{book}.json")
        assert archive["producer"] == LOADED_FINAL_DIGEST
        assert archive["pages"] == pages and archive["source_and_units_identical"]
        output = Path(archive["output"])
        assert output.name == stable_id(
            "final-book-1",
            LOADED_FINAL_DIGEST,
            after["source_sha256"],
            serial["cache_keys"]["lists"],
        )
        manifest = read_json(output / "manifest.json.gz")
        checksums = files(output)
        assert manifest["complete"] and manifest["pages"] == pages
        assert len(manifest["files"]) == pages + 1
        assert all(checksums[name] == checksum for name, checksum in manifest["files"].items())
        for number in range(1, pages + 1):
            payload = read_json(output / f"page_{number:06d}.json.gz")
            check_page_references(payload)
            assert digest(payload["source"]) == after["pages"][str(number)]["native_text"]
            assert digest(payload["units"]) == after["pages"][str(number)]["lists"]
        outputs[book] = {
            "pages": pages,
            "workers": serial["workers"],
            "manifest_sha256": checksums["manifest.json.gz"],
            "line_span_references_resolved": True,
        }
    (OUT / "four_book_outputs.json").write_text(json.dumps(outputs, indent=2) + "\n", "utf8")
    development = load("book300/development_workers1.json")
    production = load("book300/production_workers2.json")
    assert files(development["output"]) == files(production["output"])
    for path in Path(production["output"]).glob("page_*.json.gz"):
        check_page_references(read_json(path))
    assert development["workers"] == 1 and production["workers"] == 2
    assert development["source_hashes"] == production["source_hashes"] == 1
    assert not list(Path(production["output"]).parent.glob("book-core-*"))
    page_proof = load("book300/parallel_pages.json")
    for row in page_proof.values():
        assert row["byte_identical"] and row["pages"] == 300
        for relative, checksum in row["sha256"].items():
            path = ROOT / ".cache/step11c/book300/cache_development_1" / relative
            assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
    worker_comparison = {
        "fixture": "approved book 1, explicit 1–300 development excerpt",
        "workers": [1, 2],
        "cache_conditions": {"development": "resumed", "production": "cold temporary"},
        "final_byte_identical": True,
        "page_cache_byte_identical": {stage: row["pages"] for stage, row in page_proof.items()},
        "manifest_sha256": files(development["output"])["manifest.json.gz"],
    }
    (OUT / "workers_comparison.json").write_text(
        json.dumps(worker_comparison, indent=2) + "\n", "utf8"
    )
    test_counts = {}
    for name in ("core", "furniture", "parallel_payloads", "archive", "keys"):
        suite = ET.parse(OUT / f"pytest_{name}.xml").getroot().find("testsuite")
        assert suite is not None
        assert all(int(suite.attrib[field]) == 0 for field in ("failures", "errors", "skipped"))
        test_counts[name] = int(suite.attrib["tests"])
    full_book = load("gates/full_book.json")
    assert full_book["passing"] and full_book["node_token_count"] == 495751
    assert all(full_book["gate"].values())
    invariants = load("gates/invariants.json")
    assert invariants["every_line_once"] and all(n == 0 for n in invariants["totals"].values())
    crosscheck = load("gates/original_source_crosscheck.json")
    assert crosscheck["pages"] == 24 and crosscheck["missing"] == crosscheck["extra"] == 0
    for name in ("units_every_line_once", "lists_on_fixtures"):
        fixture = load(f"gates/{name}.json")
        assert fixture["pages"] == 24 and fixture["every_line_in_one_unit_and_ordered_once"]
    structure_fixture = load("gates/structure_on_fixtures.json")
    assert structure_fixture["pages"] == 24 and structure_fixture["ok"]
    result = {
        "passing": True,
        "books": BOOKS,
        "identity": identities,
        "metrics_identical": all(row["identical"] for row in metrics.values()),
        "workers_identical": True,
        "book300_final_identical": True,
        "book300_page_caches_identical": True,
        "book300_cache_conditions": {"development": "resumed", "production": "cold temporary"},
        "production_intermediates_removed": True,
        "test_counts": test_counts,
        "full_book_node_tokens": full_book["node_token_count"],
        "source_crosscheck": {k: crosscheck[k] for k in ("pages", "missing", "extra")},
        "fixture_coverage_and_order": True,
        "invariants": invariants["totals"],
        "sealed_intake_books_run": False,
    }
    (OUT / "verification.json").write_text(json.dumps(result, indent=2) + "\n", "utf8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
