"""Audit measured Step 11e outputs and freeze a manifest of the deliverable."""

# ruff: noqa: E402
import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step11c_identity import BOOKS
from step11e_diagnose import BASE, OUT, write
from step11e_run import differences, read


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparison_for(before, after, before_metrics, after_metrics):
    stages = set(next(iter(before["pages"].values())))
    assert all(
        set(page) == stages for version in (before, after) for page in version["pages"].values()
    )
    return {
        "changed_pages": {
            stage: [
                int(number)
                for number in before["pages"]
                if before["pages"][number][stage] != after["pages"][number][stage]
            ]
            for stage in stages
        },
        "book_changes": differences(before["books"], after["books"]),
        "key_changes": differences(before["keys"], after["keys"]),
        "metric_changes": differences(before_metrics, after_metrics),
    }


def archive_proof(book, after, run, archives):
    from book_core.cache_store import read_json
    from book_core.lists.keys import book_fingerprint

    proof = archives[book]
    assert all(
        proof[name] is True
        for name in (
            "source_and_unit_digests_match_all_pages",
            "line_span_references_resolve_all_pages",
            "all_file_checksums_match",
        )
    )
    output = Path(run["output"]).resolve()
    assert output.is_relative_to((ROOT / ".cache/step11e/final_books").resolve())
    manifest = read_json(output / "manifest.json.gz")
    assert proof["manifest"] == manifest
    assert manifest["complete"] is True
    assert manifest["source_sha256"] == after["source_sha256"]
    assert manifest["pages"] == run["pages"] == len(after["pages"])
    expected_keys = {name: key for name, key in after["keys"].items() if name != "lists"}
    expected_keys.update(
        text=after["keys"]["native"],
        structure=after["keys"]["lists"]["structure_decision_key"],
        lists=book_fingerprint(after["keys"]["lists"]),
    )
    assert manifest["keys"] == run["cache_keys"] == expected_keys
    assert set(manifest["files"]) == {
        "book.json.gz",
        *(f"page_{int(number):06d}.json.gz" for number in after["pages"]),
    }


def audit():
    previous = read(ROOT / "experiments/out/step11d/manifest.json")
    assert all(
        sha(ROOT / name) == value
        for name, value in previous["files"].items()
        if name != ".gitattributes"
    )
    baseline_attributes = subprocess.check_output(
        ["git", "show", "90a544a:.gitattributes"], cwd=ROOT
    )
    assert hashlib.sha256(baseline_attributes).hexdigest() == previous["files"][".gitattributes"]
    attribute_extension = (
        b"# Step 11e measurements retain the exact bytes covered by their evidence manifest.\n"
        b"experiments/out/step11e/** -text "
        b"whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol\n"
    )
    assert (ROOT / ".gitattributes").read_bytes() == baseline_attributes + attribute_extension
    assert sha(ROOT / ".vscode/settings.json") == read(OUT / "baseline.json")["settings_sha256"]
    assert (
        sha(ROOT / "backend/src/book_core/layout/pipeline.py")
        == read(OUT / "isolated.json")["producer_sha256"]
    )
    comparison = read(OUT / "comparison.json")
    explanations = read(OUT / "metric_explanations.json")
    archives = read(OUT / "final_outputs.json")
    assert set(comparison) == set(explanations["changes"]) == set(archives) == set(BOOKS)
    assert explanations["accuracy_gate"] == "FAIL"
    assert explanations["no_noise_exception_applied"]
    producer = read(OUT / "producer_identity.json")
    from book_core.caching import SCOPES, code_digest, scope_files
    from book_core.layout.pipeline import layout_fingerprint

    assert code_digest("layout") == producer["layout_producer_digest"]
    assert set(producer["all_producer_scopes"]) == set(SCOPES)
    assert all(
        code_digest(scope) == values["after"]
        for scope, values in producer["all_producer_scopes"].items()
    )
    assert [
        scope
        for scope, values in producer["all_producer_scopes"].items()
        if values["before"] != values["after"]
    ] == ["layout"]
    assert all(
        sha(ROOT / "backend/src/book_core" / name) == digest
        for name, digest in producer["scope_files"].items()
    )
    assert (
        set(producer["scope_files"])
        == set(producer["scope_files_normalized_sha256"])
        == set(scope_files("layout"))
    )
    assert all(
        hashlib.sha256(
            (ROOT / "backend/src/book_core" / name).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        == digest
        for name, digest in producer["scope_files_normalized_sha256"].items()
    )
    assert sha(ROOT / "backend/src/book_core/layout/pipeline.py") == producer["pipeline_sha256"]
    books = {}
    inventory = read(OUT / "diagnosis/fallback_credits.json")
    from book_core.layout.models import PageLayout
    from book_core.objects.analysis import verified_read

    for book in BOOKS:
        after, before = read(OUT / f"after/{book}.json"), read(BASE / f"{book}.json")
        objects = read(OUT / f"after/{book}_objects.json")
        gates = read(OUT / f"after/{book}_full_gates.json")
        assert after["source_sha256"] == before["source_sha256"]
        assert objects == read(BASE / f"{book}_objects.json")
        assert (
            set(after["pages"])
            == set(before["pages"])
            == set(objects)
            == set(gates["invariants"])
            == set(gates["ownership"])
        )
        names = tuple(f"I{number}" for number in range(1, 8))
        assert all(set(row) == set(names) for row in gates["invariants"].values())
        totals = {
            name: sum(len(row[name]) for row in gates["invariants"].values()) for name in names
        }
        assert gates["invariant_totals"] == totals
        assert not any(gates["invariant_totals"].values())
        assert all(row["units_once"] and row["ordered_once"] for row in gates["ownership"].values())
        assert all(
            after["keys"][stage] == before["keys"][stage] for stage in ("native", "analysis")
        )
        assert layout_fingerprint(after["keys"]["analysis"], "cpu") == after["keys"]["layout"]
        metrics = read(OUT / f"metrics/{book}/summary.json")
        assert comparison[book] == comparison_for(
            before, after, read(BASE / f"metrics/{book}/summary.json"), metrics
        )
        metric_keys = metrics["cache_key_inputs"]
        assert metric_keys["paragraph_book_key"] == after["keys"]["paragraphs"]
        assert (
            metric_keys["structure_decision_key"]
            == after["keys"]["lists"]["structure_decision_key"]
        )
        assert comparison[book]["metric_changes"] == [
            {k: row[k] for k in ("path", "before", "after")}
            for row in explanations["changes"][book]
        ]
        if book != "spanish_us_history":
            assert not comparison[book]["book_changes"]
        # Any additional changed page requires diagnosis, never silent acceptance.
        for stage, numbers in comparison[book]["changed_pages"].items():
            assert set(numbers) <= (
                {324, 350, 361, 724} if book == "spanish_us_history" else set()
            ), (book, stage, numbers)
        preserved = 0
        for row in inventory["rows"]:
            if row["book"] != book:
                continue
            key = after["keys"]["layout"]
            layout = verified_read(
                ROOT / ".cache/step7/layout" / key / f"{row['page']}.json", PageLayout, key
            )
            region = next(region for region in layout.regions if row["line_id"] in region.line_ids)
            if row["checker_pass"]:
                assert region.type == "credit_candidate"
                preserved += 1
            else:
                assert region.type == "unknown" and region.review_required
        run = read(OUT / f"performance/{book}.json")["run"]
        assert run["source_hashes"] == 1 and run["workers"] == 1
        archive_proof(book, after, run, archives)
        books[book] = {
            "pages": len(after["pages"]),
            "invariant_totals": gates["invariant_totals"],
            "lines": sum(row["lines"] for row in gates["ownership"].values()),
            "every_line_assigned_and_ordered_once": True,
            "native_analysis_models_and_keys_identical": True,
            "passing_fallback_credits_preserved": preserved,
            "source_hashes": run["source_hashes"],
        }
    cases = []
    for name in ("pytest_core.xml", "pytest_furniture.xml"):
        tests = ET.parse(OUT / name).getroot()
        assert not any(tests.findall(".//" + tag) for tag in ("failure", "error", "skipped"))
        cases.extend(tests.findall(".//testcase"))
    assert len(cases) == 881
    names = {case.attrib["name"] for case in cases}
    assert {
        "test_workers_and_production_are_byte_identical_and_hash_pdf_once",
        "test_missing_upstream_dependency_is_detected",
        "test_i5_rotated_cells_build_structure_not_credits",
    } <= names
    crosscheck, ledger = read(OUT / "source_crosscheck.json"), read(OUT / "full_book.json")
    sample = read(BASE / "sample.json")
    assert crosscheck["sample"] == sample
    assert set(sample["pages"]) == set(BOOKS)
    assert all(len(numbers) == len(set(numbers)) == 6 for numbers in sample["pages"].values())
    expected_sample = {
        (book, page) for book, numbers in sample["pages"].items() for page in numbers
    }
    sample_rows = crosscheck["results"]
    assert len(sample_rows) == len(expected_sample) == 24
    assert {(row["book"], row["page"]) for row in sample_rows} == expected_sample
    assert all(row["missing"] == row["extra"] == 0 for row in sample_rows)
    assert crosscheck["pages"] == len(sample_rows)
    assert crosscheck["missing"] == sum(row["missing"] for row in sample_rows)
    assert crosscheck["extra"] == sum(row["extra"] for row in sample_rows)
    assert crosscheck["pages"] == 24 and crosscheck["missing"] == crosscheck["extra"] == 0
    assert set(crosscheck["final_archive_retained_tokens"]) == set(BOOKS)
    assert crosscheck["final_archive_retained_tokens"]["spanish_us_history"] == 495751
    assert ledger["node_token_count"] == 495751 and all(ledger["gate"].values())
    assert (
        read(OUT / "lint.json")["check_exit_code"]
        == read(OUT / "lint.json")["format_exit_code"]
        == 0
    )
    result = {
        "status": "FAILED-FOR-REVIEW",
        "accuracy_gate": explanations["accuracy_gate"],
        "all_other_required_checks_pass": True,
        "producer_identity_matches_measured_outputs": True,
        "final_archive_proofs_match_run_and_identity": True,
        "baseline_revision": "90a544a",
        "books": books,
        "full_book_pages": sum(row["pages"] for row in books.values()),
        "tests_passed": len(cases),
        "sample_pages": 24,
        "sample_missing": 0,
        "sample_extra": 0,
        "spanish_ledger_tokens": 495751,
        "old_evidence_unchanged": True,
        "attribute_extension": {
            "path": ".gitattributes",
            "original_bytes_match_step11d_manifest": True,
            "exact_append_only": True,
            "added_lines": attribute_extension.decode("utf8").splitlines(),
        },
        "settings_unchanged": True,
        "worker_equivalence": "one/two workers and production; fresh synthetic three-page fixture",
        "cache_closure_including_missing_dependency": "PASS",
        "step11d_resumed": False,
        "step12_started": False,
        "sealed_and_robustness_books_run": False,
    }
    assert result["full_book_pages"] == 1412
    write("verification.json", result)
    print(json.dumps(result, indent=2))
    return result


def manifest():
    files = [
        ROOT / "backend/src/book_core/layout/pipeline.py",
        ROOT / "backend/tests/test_layout_credit_fallback.py",
        ROOT / "docs/step11e_report.md",
        ROOT / "docs/decisions.md",
        *sorted((ROOT / "experiments").glob("step11e_*.py")),
        *sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "manifest.json"),
    ]
    attributes = ROOT / ".gitattributes"
    baseline_attributes = subprocess.check_output(
        ["git", "show", "90a544a:.gitattributes"], cwd=ROOT
    )
    if attributes.read_bytes().replace(b"\r\n", b"\n") != baseline_attributes.replace(
        b"\r\n", b"\n"
    ):
        files.append(attributes)
    write(
        "manifest.json",
        {
            "baseline_revision": "90a544a",
            "files": {p.relative_to(ROOT).as_posix(): sha(p) for p in files},
        },
    )


def committed():
    manifest_data = read(OUT / "manifest.json")
    for name, value in manifest_data["files"].items():
        data = subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT)
        assert hashlib.sha256(data).hexdigest() == value, name
    producer = read(OUT / "producer_identity.json")
    assert set(producer["scope_files_normalized_sha256"]) == set(producer["scope_files"])
    layout_digest = hashlib.sha256(b"layout")
    for name, value in sorted(producer["scope_files_normalized_sha256"].items()):
        data = subprocess.check_output(
            ["git", "show", "HEAD:backend/src/book_core/" + name], cwd=ROOT
        )
        if name == "layout/pipeline.py":
            assert hashlib.sha256(data).hexdigest() == producer["pipeline_sha256"], name
        normalized_digest = hashlib.sha256(data.replace(b"\r\n", b"\n"))
        assert normalized_digest.hexdigest() == value, name
        layout_digest.update(b"\0" + name.encode("utf8") + b"\0")
        layout_digest.update(normalized_digest.digest())
    assert layout_digest.hexdigest() == producer["layout_producer_digest"]
    print("All manifested bytes and canonical layout producer identity match the commit")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", action="store_true")
    parser.add_argument("--committed", action="store_true")
    args = parser.parse_args()
    if args.committed:
        committed()
    else:
        result = audit()
        if args.manifest:
            manifest()
        if result["accuracy_gate"] == "FAIL":
            raise SystemExit(1)
