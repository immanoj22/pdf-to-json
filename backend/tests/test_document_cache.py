"""Source/configuration/producer-keyed document artifacts and corruption refusal."""

import json
from dataclasses import replace

import pytest

from book_core.cache_store import read_json
from book_core.document_analysis import cache
from book_core.document_analysis.cache import DocumentConfig, analyze_book_cached, fingerprint


def inputs(make_page):
    pages = [make_page()]
    metadata = {"source_sha256": "a" * 64, "page_count": 1, "page_labels": [], "bookmarks": []}
    blocks = [{"page": 1, "block": 0, "line_ids": ["line"]}]
    return pages, metadata, blocks


def test_cache_hit_preserves_source_and_refuses_corruption(make_page, tmp_path, monkeypatch):
    pages, metadata, blocks = inputs(make_page)
    before = pages[0].model_dump_json()
    monkeypatch.setattr(cache, "LinguaLanguageDetector", lambda *a, **k: object())
    monkeypatch.setattr(cache, "language_evidence", lambda *a: {"blocks": []})
    payload, path, hit = analyze_book_cached(pages, metadata, blocks, tmp_path)
    assert not hit and payload["decisions"] == {
        "heading_levels": None,
        "furniture_removal": None,
        "zones": None,
    }
    repeated, same_path, hit = analyze_book_cached(pages, metadata, blocks, tmp_path)
    assert hit and same_path == path and repeated == payload
    assert pages[0].model_dump_json() == before
    entry = json.loads(path.read_text("utf8"))
    entry["payload"]["style"]["body_style_key"] = "tampered"
    path.write_text(json.dumps(entry), "utf8")
    with pytest.raises(ValueError, match="Corrupt"):
        analyze_book_cached(pages, metadata, blocks, tmp_path)


def test_each_input_configuration_and_library_version_changes_key(make_page, monkeypatch):
    pages, metadata, blocks = inputs(make_page)
    config = DocumentConfig()
    first, _ = fingerprint(pages, metadata, blocks, config)
    other, _ = fingerprint(
        pages, metadata, blocks, replace(config, language_candidates=("es", "en"))
    )
    assert first != other
    assert (
        first
        != fingerprint(pages, {**metadata, "bookmarks": [{"title": "new"}]}, blocks, config)[0]
    )
    assert first != fingerprint(pages, metadata, [], config)[0]
    monkeypatch.setattr(cache, "version", lambda name: "changed")
    assert first != fingerprint(pages, metadata, blocks, config)[0]


def test_cache_refuses_changed_loaded_producer(make_page, tmp_path, monkeypatch):
    pages, metadata, blocks = inputs(make_page)
    monkeypatch.setattr(cache, "LOADED_DIGEST", "old")
    with pytest.raises(RuntimeError, match="restart"):
        analyze_book_cached(pages, metadata, blocks, tmp_path)


def test_cache_rejects_mixed_or_missing_pages(make_page):
    pages, metadata, blocks = inputs(make_page)
    with pytest.raises(ValueError, match="nonempty"):
        fingerprint([], metadata, blocks, DocumentConfig())
    with pytest.raises(ValueError, match="incomplete"):
        fingerprint(pages * 2, metadata, blocks, DocumentConfig())
    with pytest.raises(ValueError, match="different sources"):
        fingerprint(pages, {**metadata, "source_sha256": "b" * 64}, blocks, DocumentConfig())


def test_holdout_guard_precedes_any_source_read(monkeypatch, tmp_path):
    import step6_run

    def forbidden(*args):
        raise AssertionError("Hold-out source accessed before authorization guard")

    monkeypatch.setattr(step6_run, "reference_path", forbidden)
    monkeypatch.setattr(step6_run, "OUT", tmp_path)
    with pytest.raises(SystemExit) as error:
        step6_run.main(["--book", "immigrant_children"])
    assert error.value.code == 2
    (tmp_path / "holdout_runs.jsonl").write_text(
        json.dumps({"book": "immigrant_children", "action": "started"}) + "\n", "utf8"
    )
    with pytest.raises(SystemExit) as error:
        step6_run.main(["--book", "immigrant_children", "--holdout"])
    assert error.value.code == 2


def test_native_metadata_cache_source_model_and_corruption(tmp_path, make_page):
    from book_core.document_analysis.metadata import cached_metadata
    from book_core.extraction.fingerprints import source_digest

    source = tmp_path / "source.pdf"
    source.write_bytes(b"synthetic source")

    class Native:
        identity = make_page().extractor
        calls = 0

        def extract_navigation(self, path):
            self.calls += 1
            return {
                "source_sha256": source_digest(path),
                "extractor": self.identity.model_dump(mode="json"),
                "page_count": 1,
                "native_blocks": [],
                "page_labels": [],
                "bookmarks": [],
            }

    native = Native()
    directory = tmp_path / "metadata"
    first = cached_metadata(source, native, directory)
    assert first == cached_metadata(source, native, directory) and native.calls == 1
    entry_path = next(directory.glob("*.json"))
    entry = read_json(entry_path)
    entry["payload"]["page_count"] = 99
    entry_path.write_text(json.dumps(entry), "utf8")
    with pytest.raises(ValueError, match="Corrupt"):
        cached_metadata(source, native, directory)
    source.write_bytes(b"changed source")
    assert cached_metadata(source, native, directory)["source_sha256"] != first["source_sha256"]
    assert native.calls == 2
