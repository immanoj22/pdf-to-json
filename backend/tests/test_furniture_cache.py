"""Step 8 cache identity: scope closure, producer edits and every book-key component."""

import shutil

import pytest
from test_cache_keys import closure

from book_core.caching import PACKAGE, coverage_files
from book_core.furniture.classify import FurnitureConfig, config_dict
from book_core.furniture.keys import (
    FURNITURE_ENTRY_POINTS,
    book_fingerprint,
    book_key_components,
    furniture_code_digest,
    furniture_scope_files,
)
from book_core.furniture.sequence import SequenceConfig
from book_core.settings import Settings


@pytest.mark.parametrize("entry", FURNITURE_ENTRY_POINTS)
def test_furniture_scope_covers_the_import_closure(entry):
    missing = closure(entry) - set(coverage_files("furniture"))
    assert not missing, f"Step 8 cache key ignores {sorted(missing)}"


def test_furniture_scope_is_own_producers_and_declares_upstream_inputs():
    files = set(furniture_scope_files())
    assert {"settings.py", "furniture/keys.py"} <= files
    assert "reading_order/builder.py" not in files
    assert "document_analysis/metadata.py" in coverage_files("furniture")


def test_editing_any_furniture_producer_changes_the_digest(tmp_path):
    copy = tmp_path / "book_core"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    original_digest = furniture_code_digest()
    assert furniture_code_digest(copy) == original_digest
    for relative in furniture_scope_files(copy):
        target = copy / relative
        original = target.read_bytes()
        target.write_bytes(original + b"\n# edited\n")
        assert furniture_code_digest(copy) != original_digest, relative
        target.write_bytes(original)
    (copy / "furniture" / "new_rule.py").write_text("X = 1\n", "utf-8")
    assert furniture_code_digest(copy) != original_digest


def _components(**changes):
    base = {
        "furniture": "f" * 64,
        "layout_key": "l" * 64,
        "order_key": "o" * 64,
        "vocabulary": {"casa": 3},
        "metadata": {"source_sha256": "s", "page_labels": [{"page": 1, "label": "i"}]},
        "settings": Settings(),
        "config": config_dict(FurnitureConfig(), SequenceConfig()),
        "version": "furniture-1",
    }
    base.update(changes)
    return book_key_components(**base)


@pytest.mark.parametrize(
    "change",
    [
        {"furniture": "g" * 64},
        {"layout_key": "m" * 64},
        {"order_key": "p" * 64},
        {"vocabulary": {"casa": 4}},
        {"metadata": {"source_sha256": "s", "page_labels": [{"page": 1, "label": "ii"}]}},
        {"settings": Settings(ocr_languages=["eng"])},
        {"config": config_dict(FurnitureConfig(min_pages=4), SequenceConfig())},
        {"version": "furniture-2"},
    ],
)
def test_every_book_key_component_changes_the_key(change):
    assert book_fingerprint(_components(**change)) != book_fingerprint(_components())


def test_book_key_names_its_components():
    assert set(_components()) == {
        "furniture_producer_sha256",
        "reading_order_producer_sha256",
        "layout_fingerprint",
        "order_fingerprint",
        "step6_evidence_sha256",
        "settings_sha256",
        "config_sha256",
        "furniture_version",
    }
