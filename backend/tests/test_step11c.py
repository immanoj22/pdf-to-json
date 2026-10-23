"""Performance changes must preserve content, integrity and interruption safety."""

import hashlib
import json
import shutil
from pathlib import Path

import pymupdf
import pytest
from test_cache_keys import closure

from book_core import caching
from book_core.book_run import default_workers, run_book
from book_core.cache_admin import apply_plan, cache_lock, disk_check, prune_plan, register, report
from book_core.cache_store import read_json, read_model, validated_reads, write_model
from book_core.extraction.fingerprints import source_digest
from book_core.model.common import BBox
from book_core.run_context import source_session


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "sample.pdf"
    with pymupdf.open() as document:
        for number in range(3):
            page = document.new_page(width=420, height=500)
            page.insert_text((30, 40), f"Chapter {number + 1}", fontsize=18)
            page.insert_text((30, 80), "Ordinary source text stays lossless.")
            page.insert_text((30, 105), "1. First item")
            page.insert_text((30, 125), "2. Second item")
        document.save(path)
    return path


def final_files(result):
    output = Path(result["output"])
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}


def test_workers_and_production_are_byte_identical_and_hash_pdf_once(source, tmp_path):
    serial = run_book(source, tmp_path / "one_out", tmp_path / "one", workers=1, device="cpu")
    parallel = run_book(source, tmp_path / "two_out", tmp_path / "two", workers=2, device="cpu")
    production = run_book(
        source, tmp_path / "prod_out", tmp_path / "prod", mode="production", workers=2, device="cpu"
    )
    assert final_files(serial) == final_files(parallel) == final_files(production)
    for path in Path(production["output"]).glob("page_*.json.gz"):
        page = read_json(path)
        unit_lines = {line for unit in page["units"]["units"] for line in unit["line_ids"]}
        assert set(page["line_spans"]) == unit_lines
        spans = page["source"]["store"]["spans"]
        assert all(span in spans for line in page["line_spans"].values() for span in line)
        assert all(page["line_spans"][line] for line in unit_lines)

    # Parallel scheduling must preserve intermediate evidence as well as final units.
    def payloads(root):
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*.json")
        }

    assert payloads(tmp_path / "one") == payloads(tmp_path / "two")
    assert all(row["source_hashes"] == 1 for row in (serial, parallel, production))
    assert not [
        p for p in (tmp_path / "prod_out").iterdir() if p.name.startswith(("book-core-", ".final-"))
    ]
    assert not (tmp_path / "prod" / "native").exists()
    assert serial["stages"]["analysis"]["cache_bytes"] > 0
    assert production["stages"]["analysis"]["cache_bytes"] > 0


def test_interrupted_development_resumes_and_production_cleans_temporary_files(source, tmp_path):
    def interrupt(stage, completed, total):
        if completed == 2:
            raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_book(
            source,
            tmp_path / "out",
            tmp_path / "cache",
            workers=1,
            device="cpu",
            progress=interrupt,
        )
    assert len(list((tmp_path / "cache/native").glob("*/*.json"))) == 2
    assert not list((tmp_path / "out").glob("*/manifest.json.gz"))
    resumed = run_book(source, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    assert resumed["stages"]["native"]["source_reads"] == 1
    clean = run_book(source, tmp_path / "clean_out", tmp_path / "clean", workers=1, device="cpu")
    assert final_files(resumed) == final_files(clean)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_book(
            source,
            tmp_path / "prod_out",
            tmp_path / "prod",
            workers=1,
            mode="production",
            device="cpu",
            progress=interrupt,
        )
    assert not list((tmp_path / "prod_out").iterdir())


def test_lists_resume_retains_completed_page_builds(source, tmp_path, monkeypatch):
    from book_core.lists import cache

    original = cache.build_page_lists
    calls = []

    def interrupted(page, *args, **kwargs):
        calls.append(page.geometry.page)
        if len(calls) == 2:
            raise RuntimeError("lists interruption")
        return original(page, *args, **kwargs)

    monkeypatch.setattr(cache, "build_page_lists", interrupted)
    with pytest.raises(RuntimeError, match="lists interruption"):
        run_book(source, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    assert len(list((tmp_path / "cache/lists/page").glob("*/*.json"))) == 1
    assert not list((tmp_path / "cache/lists/book").glob("*.json"))
    calls.clear()

    def counted(page, *args, **kwargs):
        calls.append(page.geometry.page)
        return original(page, *args, **kwargs)

    monkeypatch.setattr(cache, "build_page_lists", counted)
    resumed = run_book(source, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    assert calls == [2, 3]
    monkeypatch.setattr(cache, "build_page_lists", original)
    fresh = run_book(source, tmp_path / "fresh_out", tmp_path / "fresh", workers=1, device="cpu")
    assert final_files(resumed) == final_files(fresh)


def test_run_scoped_digest_is_not_a_stale_process_global(source):
    first = source_digest(source)
    with pytest.raises(ValueError, match="Source changed"):
        with source_session(source) as snapshot:
            assert source_digest(source) == snapshot.digest == first
            source.write_bytes(source.read_bytes() + b"\n")
            with pytest.raises(ValueError, match="Source changed"):
                source_digest(source)
    assert source_digest(source) != first


def test_source_session_rejects_changes_at_exit(source):
    with pytest.raises(ValueError, match="Source changed"):
        with source_session(source):
            source.write_bytes(source.read_bytes() + b"\n")
    assert source_digest(source) != ""


def test_registry_edits_and_unrelated_producers_do_not_rekey_stages(tmp_path):
    root = tmp_path / "book_core"
    shutil.copytree(caching.PACKAGE, root, ignore=shutil.ignore_patterns("__pycache__"))
    before = {stage: caching.code_digest_at(stage, root) for stage in caching.SCOPES}
    registry = root / "caching.py"
    registry.write_bytes(registry.read_bytes() + b"\n# register another stage\n")
    assert {stage: caching.code_digest_at(stage, root) for stage in caching.SCOPES} == before
    rule = root / "lists/lines.py"
    rule.write_bytes(rule.read_bytes() + b"\n# change lists producer\n")
    changed = {
        stage for stage in caching.SCOPES if caching.code_digest_at(stage, root) != before[stage]
    }
    assert changed == {"lists"}
    rule = root / "layout/regions.py"
    rule.write_bytes(rule.read_bytes() + b"\n# change layout producer\n")
    assert caching.code_digest_at("reading_order", root) == before["reading_order"]
    assert caching.code_digest_at("layout", root) != before["layout"]


def test_missing_upstream_dependency_is_detected(monkeypatch):
    monkeypatch.setitem(caching.DEPENDENCIES, "layout", ())
    missing = closure("layout/pipeline.py") - set(caching.coverage_files("layout"))
    assert "objects/analysis.py" in missing


def test_compressed_cache_versions_corruption_and_bounded_validation_reuse(tmp_path, monkeypatch):
    path = tmp_path / "value.json"
    value = BBox(x0=0, y0=0, x1=2, y1=3)
    write_model(path, value, "key")
    assert path.read_bytes().startswith(b"\x1f\x8b")
    original = BBox.model_validate_json
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(BBox, "model_validate_json", counted)
    with validated_reads(budget_bytes=1000):
        assert read_model(path, BBox, "key") == value
        assert read_model(path, BBox, "key") == value
    assert len(calls) == 1
    with validated_reads(budget_bytes=1):
        read_model(path, BBox, "key")
        read_model(path, BBox, "key")
    assert len(calls) == 3
    entry = read_json(path)
    entry["format_version"] = 999
    path.write_text(json.dumps(entry), "utf8")
    with pytest.raises(ValueError, match="version"):
        read_model(path, BBox, "key")
    write_model(path, value, "key")
    data = bytearray(path.read_bytes())
    data[-5] ^= 1
    path.write_bytes(data)
    with pytest.raises(ValueError, match="Corrupt"):
        read_model(path, BBox, "key")


def test_prune_requires_unchanged_plan_and_keeps_current_unknown_and_same_producer(tmp_path):
    root = tmp_path / "cache"
    root.mkdir()
    paths = {}
    for name in ("old", "same", "current"):
        key = hashlib.sha256(name.encode()).hexdigest()
        path = root / "layout" / key / "1.json"
        path.parent.mkdir(parents=True)
        path.write_text("payload")
        paths[name] = path
        register(
            root,
            "book",
            "layout",
            key,
            [path],
            producer="old-code" if name == "old" else "current-code",
        )
    (root / "unknown.json").write_text("payload")
    plan = prune_plan(root, budget_bytes=1)
    assert set(plan["files"]) == {paths["old"].relative_to(root).as_posix()}
    assert not plan["budget_satisfied"]
    paths["old"].write_text("changed")
    with pytest.raises(ValueError, match="changed since dry-run"):
        apply_plan(root, plan)
    assert paths["old"].exists()
    with cache_lock(root):
        with pytest.raises(RuntimeError, match="in use"):
            with cache_lock(root):
                pass
        result = apply_plan(root, prune_plan(root))
    assert result["deleted_files"] == 1
    assert paths["same"].exists() and paths["current"].exists() and (root / "unknown.json").exists()
    assert report(root)["superseded_bytes"] == 0
    with pytest.raises((ValueError, OSError)):
        register(root, "book", "layout", "escape", [tmp_path / "outside.json"], producer="x")
    gold = root / "backend/tests/gold/columns.json"
    gold.parent.mkdir(parents=True)
    gold.write_text("protected")
    with pytest.raises(ValueError, match="not a stage cache"):
        register(root, "book", "layout", "a" * 64, [gold], producer="x")


def test_disk_check_fails_clearly_and_records_low_disk_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(20, 15, 5))
    with pytest.raises(OSError, match="Insufficient disk space: estimated"):
        disk_check(tmp_path, 100)
    assert (tmp_path / "disk_cleanup_dry_run.json").exists()


def test_worker_default_is_memory_safe(monkeypatch):
    import book_core.book_run as runner

    monkeypatch.setattr(runner, "available_memory", lambda: 8 * 1024**3)
    assert default_workers() == 1


def _stage_files(root, stage, key, count):
    """Files laid out as the stage writes them."""
    if stage == "structure_evidence":
        path = root / "structure" / "evidence" / f"{key}.json.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x" * 1000)
        return [path]
    if stage == "continuity":
        path = root / "continuity" / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x" * 1000)
        return [path]
    paged = {"native", "analysis", "paint", "characters", "figures", "equations", "mathml",
             "tables", "layout", "reading_order", "text", "assembly_evidence"}  # fmt: skip
    folder = root / stage / key if stage in paged else root / stage / "page" / key
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for number in range(1, count + 1):
        path = folder / f"{number}.json"
        path.write_text("x" * 1000)
        paths.append(path)
    return paths


def test_disk_need_is_the_full_estimate_on_an_empty_cache(tmp_path):
    from book_core.cache_admin import disk_need

    need = disk_need(tmp_path, "book", 10, 12 * 1024**2, {})
    assert need["estimated_bytes"] == need["full_estimate_bytes"] == 10 * 12 * 1024**2
    assert need["cached_stages"] == []


def test_disk_need_counts_only_stages_not_cached_and_the_final_archive(tmp_path):
    from book_core.cache_admin import RUN_STAGES, disk_need

    producers = {stage: f"producer-{stage}" for stage in RUN_STAGES}
    for stage in RUN_STAGES:
        files = _stage_files(tmp_path, stage, "a" * 64, 3)
        register(tmp_path, "book", stage, "a" * 64, files, producer=producers[stage])
    full = 3 * 12 * 1024**2
    cached = disk_need(tmp_path, "book", 3, 12 * 1024**2, producers)
    assert cached["missing_stages"] == ["final"]
    assert cached["estimated_bytes"] < full / 10
    # A changed producer makes that stage (and only it) needed again.
    changed = disk_need(tmp_path, "book", 3, 12 * 1024**2, {**producers, "equations": "new"})
    assert changed["missing_stages"] == ["equations", "final"]
    assert cached["estimated_bytes"] < changed["estimated_bytes"] < full
    # Another book has nothing cached: its need is the full estimate.
    other = disk_need(tmp_path, "other", 3, 12 * 1024**2, producers)
    assert other["estimated_bytes"] == full
