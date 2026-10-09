"""Read-only Step 6 rule audit; writes only its project-local JSON evidence report."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

from reference_paths import PROJECT_ROOT

from book_core.evaluation.derived_harness import DerivedGold

GIT = Path("C:/Program Files/Git/cmd/git.exe")
PROTECTED = [
    "backend/src/book_core/ledger",
    "backend/src/book_core/model",
    "backend/tests/gold",
    "backend/tests/gold_derived",
]
CONTRACTS = ["experiments/references.toml", "AGENTS.md", "CLAUDE.md"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unchanged(paths):
    environment = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    command = [str(GIT), "diff", "HEAD", "--ignore-space-at-eol", "--exit-code", "--", *paths]
    result = subprocess.run(
        command, cwd=PROJECT_ROOT, env=environment, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise AssertionError(f"Protected diff changed: {result.stdout} {result.stderr}")
    return {"paths": paths, "empty_diff": True, "ignore_space_at_eol": True}


def pdf_access():
    opens, mutators, outside = [], [], []
    for path in sorted((PROJECT_ROOT / "backend/src").rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text("utf8"))
        aliases, direct = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                aliases.update(
                    entry.asname or entry.name
                    for entry in node.names
                    if entry.name in {"pymupdf", "fitz"}
                )
            elif isinstance(node, ast.ImportFrom) and node.module in {"pymupdf", "fitz"}:
                direct.update(
                    entry.asname or entry.name for entry in node.names if entry.name == "open"
                )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            is_open = (
                isinstance(function, ast.Name)
                and function.id in direct
                or isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id in aliases
                and function.attr == "open"
            )
            if is_open:
                row = {"path": relative, "line": node.lineno}
                opens.append(row)
                if "/book_core/extraction/" not in relative:
                    outside.append(row)
            if (
                aliases
                and isinstance(function, ast.Attribute)
                and function.attr
                in {
                    "save",
                    "saveIncr",
                    "ez_save",
                    "insert_pdf",
                    "delete_page",
                    "delete_pages",
                    "set_toc",
                    "set_page_labels",
                    "insert_text",
                    "insert_image",
                }
            ):
                mutators.append({"path": relative, "line": node.lineno, "operation": function.attr})
    if outside or mutators:
        raise AssertionError({"outside_extraction": outside, "PDF_mutation_calls": mutators})
    return {
        "native_pdf_opens": opens,
        "opens_outside_extraction": outside,
        "pdf_mutation_calls": mutators,
    }


def boundary_gate():
    sys.path.insert(0, str(PROJECT_ROOT / "backend/tests"))
    source = PROJECT_ROOT / "backend/tests/test_boundaries.py"
    namespace = runpy.run_path(str(source), run_name="step6_boundary_audit")
    checks = [
        "test_no_adapter_imports_or_schema_tag_names",
        "test_package_initializers_are_docstrings_only",
    ]
    for name in checks:
        namespace[name]()
    return {"existing_test_sha256": digest(source), "unchanged_checks": checks, "passed": True}


def gold_integrity():
    rows = []
    for directory in sorted((PROJECT_ROOT / "backend/tests/gold_derived").iterdir()):
        if not directory.is_dir():
            continue
        gold = DerivedGold.load(directory)
        rows.append(
            {
                "book": gold.book,
                "units": len(gold.units),
                "human_approved": False,
                "manifest_sha256": digest(directory / "manifest.json"),
                "verified_files": gold.manifest["files"],
            }
        )
    return rows


def main():
    report = {
        "audit_script_sha256": digest(__file__),
        "protected_diff": unchanged(PROTECTED),
        "project_contract_diff": unchanged(CONTRACTS),
        "derived_gold": gold_integrity(),
        "schema_and_adapter_boundary": boundary_gate(),
        "pdf_access": pdf_access(),
        "old_projects_read_only": {
            "reviewed_step6_outputs": [
                "experiments/out/step6",
                ".cache/step6",
                "docs/licenses/step6",
                "docs/step6_report.md",
                "experiments/step6_language_sample.json",
            ],
            "external_source_mutation_calls_in_new_extraction_helpers": [],
            "audit_external_writes": False,
            "evidence": (
                "New extraction helpers only read source PDFs. Step 6 runner and audit "
                "write destinations were reviewed as project-local. No reference source, "
                "old-project environment or old-project cache is a write destination."
            ),
            "limitation": "Static/source review; no operating-system write trace was collected.",
        },
        "scope": "Rules and integrity only; no hold-out document analysis or gold modification",
    }
    output = PROJECT_ROOT / "experiments/out/step6/rule_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
    print(
        json.dumps(
            {
                "protected_diff_empty": True,
                "contracts_diff_empty": True,
                "gold_books_verified": len(report["derived_gold"]),
                "boundary_passed": True,
                "pdf_opens_outside_extraction": len(
                    report["pdf_access"]["opens_outside_extraction"]
                ),
                "pdf_mutation_calls": len(report["pdf_access"]["pdf_mutation_calls"]),
                "output": output.relative_to(PROJECT_ROOT).as_posix(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
