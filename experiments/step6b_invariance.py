"""Step 6b byte invariance and the unchanged 24-page source gate.

This runner writes only new Step 6b evidence. It never restores changed evidence,
modifies gold, or runs whole-book hold-out analysis. Before/after modes compare exact
working-tree bytes with Git HEAD; crosscheck reads the existing explicit 24-page fixture
manifest and original configured sources through the Extractor interface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from reference_paths import PROJECT_ROOT
from step4b_run import configured_source, retained_counter

from book_core.caching import code_digest, runtime_versions
from book_core.evaluation.derived_harness import DerivedGold
from book_core.extraction.cache import atomic_json, payload_digest
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

OUT = PROJECT_ROOT / "experiments/out/step6b"
DEFAULT_GIT = Path("C:/Program Files/Git/cmd/git.exe")
ALLOWED_TEST = "backend/tests/test_document_language.py"


def _git(git: Path, *arguments: str) -> bytes:
    return subprocess.check_output([str(git), "-C", str(PROJECT_ROOT), *arguments])


def _head_files(git: Path) -> dict[str, str]:
    records = _git(
        git,
        "ls-tree",
        "-r",
        "-z",
        "HEAD",
        "--",
        "experiments/out",
        "backend/tests",
        "backend/src/book_core/ledger",
    ).split(b"\0")
    files = {}
    for record in filter(None, records):
        details, raw_path = record.split(b"\t", 1)
        _, kind, oid = details.decode().split()
        name = raw_path.decode("utf-8")
        if kind == "blob" and not name.startswith("experiments/out/step6b/"):
            files[name] = oid
    return files


def _head_sha256(git: Path, objects: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Hash exact and LF-normalized Git bytes without working-tree conversion."""
    digests, normalized_digests = {}, {}
    with subprocess.Popen(
        [str(git), "-C", str(PROJECT_ROOT), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ) as process:
        assert process.stdin is not None and process.stdout is not None
        for oid in dict.fromkeys(objects.values()):
            process.stdin.write(oid.encode() + b"\n")
            process.stdin.flush()
            returned, kind, raw_size = process.stdout.readline().split()
            if returned.decode() != oid or kind != b"blob":
                raise ValueError("Git did not return the expected blob")
            remaining = int(raw_size)
            digest, normalized_digest = hashlib.sha256(), hashlib.sha256()
            pending = b""
            while remaining:
                block = process.stdout.read(min(remaining, 1024 * 1024))
                if not block:
                    raise ValueError("Truncated Git blob")
                digest.update(block)
                remaining -= len(block)
                normalized = pending + block
                pending = b"\r" if normalized.endswith(b"\r") else b""
                if pending:
                    normalized = normalized[:-1]
                normalized_digest.update(normalized.replace(b"\r\n", b"\n"))
            normalized_digest.update(pending)
            if process.stdout.read(1) != b"\n":
                raise ValueError("Invalid Git batch blob terminator")
            digests[oid] = digest.hexdigest()
            normalized_digests[oid] = normalized_digest.hexdigest()
        process.stdin.close()
        if process.wait() != 0:
            raise ValueError("Git blob hash process failed")
    return (
        {path: digests[oid] for path, oid in objects.items()},
        {path: normalized_digests[oid] for path, oid in objects.items()},
    )


def _groups(name: str) -> list[str]:
    if name.startswith("experiments/out/"):
        return ["earlier_outputs"]
    if name.startswith(("backend/tests/gold/", "backend/tests/gold_derived/")):
        return ["gold"]
    if name.startswith("backend/src/book_core/ledger/"):
        return ["ledger_code"]
    if name == ALLOWED_TEST:
        return ["permitted_language_test"]
    if name.startswith("backend/tests/"):
        return ["earlier_tests_and_fixtures"]
    return []


def snapshot(git: Path) -> dict:
    objects = {name: oid for name, oid in _head_files(git).items() if _groups(name)}
    expected, expected_normalized = _head_sha256(git, objects)
    groups = {}
    for name in objects:
        path = PROJECT_ROOT / name
        actual = source_digest(path) if path.is_file() else None
        normalized = (
            hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            if path.is_file()
            else None
        )
        row = {
            "path": name,
            "head_sha256": expected[name],
            "head_lf_normalized_sha256": expected_normalized[name],
            "working_sha256": actual,
            "lf_normalized_sha256": normalized,
        }
        for group in _groups(name):
            groups.setdefault(group, []).append(row)
    summaries = {}
    for group, rows in groups.items():
        changed = [row["path"] for row in rows if row["head_sha256"] != row["working_sha256"]]
        summaries[group] = {
            "files": len(rows),
            "changed_from_head": changed,
            "all_exact_bytes": not changed,
            "all_lf_normalized_head_equivalent": all(
                row["head_sha256"] == row["working_sha256"]
                or row["head_lf_normalized_sha256"] == row["lf_normalized_sha256"]
                for row in rows
            ),
            "crlf_only_differences": sum(
                row["head_sha256"] != row["working_sha256"]
                and row["head_lf_normalized_sha256"] == row["lf_normalized_sha256"]
                for row in rows
            ),
            "files_sha256": payload_digest({"files": rows}),
            "records": rows,
        }
    gold = []
    for directory in sorted((PROJECT_ROOT / "backend/tests/gold_derived").iterdir()):
        if directory.is_dir():
            verified = DerivedGold.load(directory)
            gold.append(
                {
                    "book": verified.book,
                    "manifest_checksums": "verified",
                    "human_approved": verified.manifest["human_approved"],
                    "manifest_files": len(verified.manifest["files"]),
                }
            )
    return {
        "utc": datetime.now(UTC).isoformat(),
        "head": _git(git, "rev-parse", "HEAD").decode().strip(),
        "runner_sha256": source_digest(Path(__file__)),
        "groups": summaries,
        "derived_gold": gold,
        "immutable_groups_pass": all(
            value["all_exact_bytes"]
            for key, value in summaries.items()
            if key != "permitted_language_test"
        ),
        "immutable_groups_head_equivalent": all(
            value["all_lf_normalized_head_equivalent"]
            for key, value in summaries.items()
            if key != "permitted_language_test"
        ),
        "permitted_test_change": (
            "Only the earlier default-all language test now supplies explicit ar/he/ja; "
            "all its multilingual assertions remain"
        ),
    }


def crosscheck() -> dict:
    old_path = PROJECT_ROOT / "experiments/out/step6/original_source_crosscheck.json"
    old = json.loads(old_path.read_text("utf-8"))
    sources = json.loads(
        (PROJECT_ROOT / "experiments/out/fixtures_manifest.json").read_text("utf-8")
    )
    sources += json.loads(
        (PROJECT_ROOT / "experiments/out/step4av/fixtures_manifest.json").read_text("utf-8")
    )
    metadata = {row["id"]: row for row in sources}
    manifest_path = PROJECT_ROOT / "experiments/out/step4b/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    extractor = PyMuPDFExtractor("cpu")
    rows, source_hashes, fixtures, native_payloads = [], {}, {}, {}
    producer_before = code_digest("extraction")
    for measured in manifest["pages"]:
        name = measured["page"]
        original = metadata[name]
        source = configured_source(original["source_key"])
        digest = source_digest(source)
        if digest != original["source_sha256"]:
            raise ValueError(f"{name}: original source digest changed")
        source_hashes[original["source_key"]] = digest
        original_page = extractor.extract_object_page(source, original["physical_page"]).page
        fixture = PROJECT_ROOT / measured["source"]
        fixtures[measured["source"]] = source_digest(fixture)
        fixture_page = extractor.extract_object_page(fixture, 1).page
        native_payloads[name] = {
            "original_page_sha256": payload_digest(original_page.model_dump(mode="json")),
            "fixture_page_sha256": payload_digest(fixture_page.model_dump(mode="json")),
        }
        expected, actual = retained_counter(original_page), retained_counter(fixture_page)
        row = {
            "page": name,
            "source_key": original["source_key"],
            "physical_page": original["physical_page"],
            "retained_tokens": actual.total(),
            "missing": (expected - actual).total(),
            "extra": (actual - expected).total(),
        }
        rows.append(row)
        print(name, row["missing"], row["extra"], flush=True)
    report = {
        "pages": len(rows),
        "missing": sum(r["missing"] for r in rows),
        "extra": sum(r["extra"] for r in rows),
        "results": rows,
        "method": old["method"],
    }
    producer_after = code_digest("extraction")
    result = {
        **report,
        "same_as_step6_results": report == old,
        "passing": producer_before == producer_after
        and len(rows) == 24
        and not report["missing"]
        and not report["extra"]
        and report == old,
        "provenance": {
            "runner_sha256": source_digest(Path(__file__)),
            "old_step6_sha256": source_digest(old_path),
            "fixture_manifest_sha256": source_digest(manifest_path),
            "configured_source_sha256": source_hashes,
            "fixture_sha256": fixtures,
            "extractor": extractor.identity.model_dump(mode="json"),
            "extraction_producer_sha256_before": producer_before,
            "extraction_producer_sha256_after": producer_after,
            "producer_unchanged": producer_before == producer_after,
            "runtime": runtime_versions(),
            "native_page_payloads": native_payloads,
            "scope": "existing 24 explicit fixture pages only; no whole-book hold-out analysis",
        },
    }
    atomic_json(OUT / "original_source_crosscheck.json", result)
    return result


def finalize(git: Path) -> dict:
    before = json.loads((OUT / "invariance.before.json").read_text("utf-8"))
    after = snapshot(git)
    comparisons = {}
    for group, initial in before["groups"].items():
        current = after["groups"][group]
        comparisons[group] = {
            "files": current["files"],
            "unchanged_since_before": [
                {key: row[key] for key in ("path", "head_sha256", "working_sha256")}
                for row in initial["records"]
            ]
            == [
                {key: row[key] for key in ("path", "head_sha256", "working_sha256")}
                for row in current["records"]
            ],
            "all_exact_head_bytes_after": current["all_exact_bytes"],
            "lf_normalized_head_equivalent_after": current["all_lf_normalized_head_equivalent"],
            "preexisting_crlf_only_differences": current["crlf_only_differences"],
            "changed_from_head": current["changed_from_head"],
        }
    source = json.loads((OUT / "original_source_crosscheck.json").read_text("utf-8"))
    full_path = PROJECT_ROOT / "experiments/out/step4a/full_book.json"
    full = json.loads(full_path.read_text("utf-8"))
    full_pass = (
        full["passing"]
        and full["pages"] == 758
        and full["node_token_count"] == 495751
        and full["expected_missing_token_count"] == full["expected_extra_token_count"] == 0
    )
    xml_path = OUT / "pytest.xml"
    suites = ElementTree.parse(xml_path).getroot()
    leaves = [node for node in suites.iter("testsuite") if not node.findall("testsuite")]
    tests = {
        key: sum(int(node.attrib.get(key, 0)) for node in leaves)
        for key in ("tests", "failures", "errors", "skipped")
    }
    tests["passing"] = tests["tests"] > 0 and not any(
        tests[key] for key in ("failures", "errors", "skipped")
    )
    full_check = {
        "passing": full_pass,
        "retained_tokens": full["node_token_count"],
        "source_sha256": source_digest(full_path),
        "result": full,
    }
    report = {
        "phase": "after_tests",
        "before": before,
        "after": after,
        "before_after": comparisons,
        "source_crosscheck": source,
        "full_book": full_check,
        "pytest": tests,
        "same_head": before["head"] == after["head"],
        "strict_head_bytes_pass": before["immutable_groups_pass"]
        and after["immutable_groups_pass"],
        "preexisting_line_ending_policy": (
            "Preserve exact pre-test working bytes; compare HEAD using separate LF-normalized "
            "hashes. Pre-existing CRLF differences are reported, never rewritten or hidden."
        ),
        "passing": after["immutable_groups_head_equivalent"]
        and after["groups"]["gold"]["all_exact_bytes"]
        and before["head"] == after["head"]
        and source["passing"]
        and full_pass
        and tests["passing"]
        and all(value["unchanged_since_before"] for value in comparisons.values()),
    }
    atomic_json(OUT / "invariance.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git", type=Path, default=DEFAULT_GIT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--before-tests", action="store_true")
    mode.add_argument("--crosscheck", action="store_true")
    mode.add_argument("--after-tests", action="store_true")
    args = parser.parse_args(argv)
    if args.before_tests:
        target = OUT / "invariance.before.json"
        if target.exists():
            raise ValueError("Refusing to replace the pre-test byte snapshot")
        result = snapshot(args.git)
        atomic_json(target, result)
        atomic_json(OUT / "invariance.json", {"phase": "before_tests", "before": result})
        print(
            json.dumps(
                {
                    group: {k: v for k, v in row.items() if k != "records"}
                    for group, row in result["groups"].items()
                },
                indent=1,
            )
        )
        if not result["immutable_groups_pass"]:
            raise SystemExit("Earlier tracked evidence/code/test bytes already differ from HEAD")
    elif args.crosscheck:
        result = crosscheck()
        print(json.dumps({key: result[key] for key in ("pages", "missing", "extra", "passing")}))
        if not result["passing"]:
            raise SystemExit("24-page original-source gate differs or failed")
    else:
        result = finalize(args.git)
        print(
            json.dumps(
                {
                    "passing": result["passing"],
                    "pytest": result["pytest"],
                    "source_pages": result["source_crosscheck"]["pages"],
                }
            )
        )
        if not result["passing"]:
            raise SystemExit("Step 6b invariance/gate checks failed; see invariance.json")


if __name__ == "__main__":
    main()
