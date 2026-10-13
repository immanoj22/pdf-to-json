"""Derived cache keys change whenever the code that produces the cached result changes."""

import ast
import shutil

import pytest

import book_core
from book_core import caching
from book_core.caching import (
    ENTRY_POINTS,
    SCOPES,
    code_digest,
    code_digest_at,
    coverage_files,
    scope_files,
)
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout import pipeline
from book_core.objects import analysis

PACKAGE = caching.PACKAGE


def closure(relative):
    """book_core modules imported, transitively, by one package-relative module."""
    seen, pending = set(), [relative]
    while pending:
        current = pending.pop()
        if current in seen or not (PACKAGE / current).exists():
            continue
        seen.add(current)
        tree = ast.parse((PACKAGE / current).read_text("utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                if not name.startswith("book_core."):
                    continue
                path = name.removeprefix("book_core.").replace(".", "/")
                for candidate in (f"{path}.py", f"{path}/__init__.py"):
                    if (PACKAGE / candidate).exists():
                        pending.append(candidate)
    return seen


@pytest.mark.parametrize("scope", sorted(SCOPES))
def test_scope_covers_the_import_closure(scope):
    covered = set(coverage_files(scope))
    for entry in ENTRY_POINTS[scope]:
        if not (PACKAGE / entry).exists():
            pytest.skip(f"{entry} not present")
        missing = closure(entry) - covered
        assert not missing, f"{scope} cache key ignores {sorted(missing)}"


@pytest.mark.parametrize("scope", sorted(SCOPES))
def test_editing_a_producing_source_changes_the_key(tmp_path, scope):
    copy = tmp_path / "book_core"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    assert code_digest_at(scope, copy) == code_digest(scope)
    for relative in scope_files(scope, copy):
        target = copy / relative
        original = target.read_bytes()
        target.write_bytes(original + b"\n# edited\n")
        assert code_digest_at(scope, copy) != code_digest(scope), relative
        target.write_bytes(original)
    # Line endings alone do not change the key (checkouts on other systems).
    first = copy / scope_files(scope, copy)[0]
    first.write_bytes(first.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert code_digest_at(scope, copy) == code_digest(scope)


def test_unrelated_source_does_not_change_layout_key(tmp_path):
    copy = tmp_path / "book_core"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    ledger = copy / "ledger" / "accounting.py"
    ledger.write_bytes(ledger.read_bytes() + b"\n# edited\n")
    assert code_digest_at("layout", copy) == code_digest("layout")


def test_cache_functions_use_the_code_digest(monkeypatch):
    extractor = PyMuPDFExtractor("cpu")
    native, derived = analysis.fingerprints("a" * 64, extractor)
    layout_key = pipeline.layout_fingerprint(derived, "cpu")
    monkeypatch.setattr(analysis, "code_digest", lambda scope: f"changed-{scope}")
    monkeypatch.setattr(pipeline, "code_digest", lambda scope: f"changed-{scope}")
    native2, derived2 = analysis.fingerprints("a" * 64, extractor)
    assert native2 != native and derived2 != derived
    assert pipeline.layout_fingerprint(derived, "cpu") != layout_key


def test_package_root_is_the_installed_package():
    assert PACKAGE == __import__("pathlib").Path(book_core.__file__).resolve().parent


def test_source_edit_changes_real_layout_key_in_same_process(tmp_path, monkeypatch):
    copy = tmp_path / "book_core"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(caching, "PACKAGE", copy)
    before = pipeline.layout_fingerprint("analysis-evidence", "cpu")
    producer = copy / "layout" / "regions.py"
    producer.write_bytes(producer.read_bytes() + b"\n# changed producer\n")
    assert pipeline.layout_fingerprint("analysis-evidence", "cpu") != before


def test_new_producer_file_changes_key(tmp_path):
    copy = tmp_path / "book_core"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    before = code_digest_at("layout", copy)
    (copy / "layout" / "new_producer.py").write_text("# new code\n", "utf8")
    assert code_digest_at("layout", copy) != before


def test_live_worker_refuses_to_derive_with_changed_sources(tmp_path, monkeypatch):
    copy = tmp_path / "book_core"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(caching, "PACKAGE", copy)
    source = copy / "layout" / "regions.py"
    source.write_bytes(source.read_bytes() + b"\n# deployed source\n")
    with pytest.raises(RuntimeError, match="restart the worker"):
        pipeline.analyze_layout("unused.pdf", 1, None)


def test_runtime_changes_native_and_derived_keys(monkeypatch):
    extractor = PyMuPDFExtractor("cpu")
    before = analysis.fingerprints("a" * 64, extractor)
    monkeypatch.setattr(analysis, "runtime_versions", lambda: {"unicode": "changed"})
    after = analysis.fingerprints("a" * 64, extractor)
    assert before[0] != after[0] and before[1] != after[1]
