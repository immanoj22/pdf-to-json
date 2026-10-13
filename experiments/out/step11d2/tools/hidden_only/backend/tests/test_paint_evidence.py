"""Opaque paint proofs preserve text and reject visible/unsupported controls."""

import hashlib
from pathlib import Path

import pymupdf
import pytest
from test_cache_keys import closure

from book_core import caching
from book_core.book_run import run_book
from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout.lines import build_lines
from book_core.objects.analysis import fingerprints
from book_core.paint.cache import page_paint, paint_fingerprint
from book_core.paint.device import inspect_page
from book_core.paint.proof import attribute
from book_core.run_context import source_session


def fixture(kind):
    doc = pymupdf.open()
    page = doc.new_page(width=240, height=300)
    page.insert_text((35, 75), "Ordinary text", fontsize=14)
    if kind == "repeated":
        page.insert_text((35, 75), "Ordinary text", fontsize=14)
    if kind in {"hidden", "partial", "semi"}:
        rect = (25, 45, 80 if kind == "partial" else 210, 90)
        page.draw_rect(rect, color=None, fill=(1, 1, 1), fill_opacity=0.5 if kind == "semi" else 1)
    if kind == "soft_mask":
        mask = doc.get_new_xref()
        doc.update_object(
            mask,
            "<< /Type /XObject /Subtype /Form /BBox [0 0 240 300] "
            "/Group << /S /Transparency /CS /DeviceGray >> /Resources << >> >>",
        )
        doc.update_stream(mask, b"0.5 g 0 0 240 300 re f")
        state = doc.get_new_xref()
        doc.update_object(
            state, f"<< /Type /ExtGState /SMask << /S /Luminosity /G {mask} 0 R >> >>"
        )
        resources = int(doc.xref_get_key(page.xref, "Resources")[1].split()[0])
        doc.xref_set_key(resources, "ExtGState", f"<< /AuditMask {state} 0 R >>")
        stream = doc.get_new_xref()
        doc.update_object(stream, "<< >>")
        doc.update_stream(stream, b"q /AuditMask gs 1 1 1 rg 25 210 185 45 re f Q")
        original = page.get_contents()
        doc.xref_set_key(
            page.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in [*original, stream]) + "]"
        )
    if kind == "clipped":
        stream = doc.get_new_xref()
        doc.update_object(stream, "<< >>")
        doc.update_stream(stream, b"q 25 210 40 45 re W n 1 1 1 rg 25 210 185 45 re f Q")
        original = page.get_contents()
        doc.xref_set_key(
            page.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in [*original, stream]) + "]"
        )
    data = doc.tobytes()
    doc.close()
    return pymupdf.open(stream=data), hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    "kind", ["visible", "hidden", "partial", "semi", "soft_mask", "repeated", "clipped"]
)
def test_visibility_proof_guards_and_lossless_store(kind, tmp_path):
    source = tmp_path / "fixture.pdf"
    with fixture(kind)[0] as document:
        document.save(source)
    extractor = PyMuPDFExtractor("cpu")
    with source_session(source):
        native = extractor.extract_object_page(source, 1)
        original = native.page.model_dump_json()
        _, analysis_key = fingerprints(native.page.source_sha256, extractor)
        evidence = page_paint(source, native.page, extractor, analysis_key, tmp_path / "cache")
        invisible = {s.span_id for s in evidence.spans if s.decision == "invisible"}
        assert len(invisible) == (1 if kind == "hidden" else 0)
        assert native.page.model_dump_json() == original
        assert (
            page_paint(source, native.page, extractor, analysis_key, tmp_path / "cache") == evidence
        )
        lines = build_lines(native, invisible)
        assert {sid for line in lines for sid in line.span_ids} == set(native.page.store.spans)
        assert {sid for line in lines if not line.visible for sid in line.span_ids} == invisible
        if kind == "soft_mask":
            assert evidence.spans and all(s.needs_review for s in evidence.spans)


def test_missing_paint_dependency_is_detected(monkeypatch):
    monkeypatch.setitem(caching.DEPENDENCIES, "layout", ("analysis",))
    missing = closure("layout/pipeline.py") - set(caching.coverage_files("layout"))
    assert "paint/cache.py" in missing and "paint/device.py" in missing


def test_unattributed_synthetic_nonspace_prevents_whole_span_hiding(tmp_path):
    source = tmp_path / "synthetic.pdf"
    with fixture("hidden")[0] as document:
        document.save(source)
    extractor = PyMuPDFExtractor("cpu")
    native = extractor.extract_object_page(source, 1)
    with pymupdf.open(source) as document:
        page = document[0]
        raw = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT, sort=False)
        raw["blocks"][0]["lines"][0]["spans"][0]["chars"][0]["synthetic"] = True
        matched, _ = attribute(native.page, raw, inspect_page(page))
        assert not matched


def test_paint_key_binds_configuration_and_upstream(monkeypatch):
    from book_core.paint import cache

    baseline = paint_fingerprint("a" * 64, "cpu")
    assert paint_fingerprint("b" * 64, "cpu") != baseline
    monkeypatch.setitem(cache.CONFIG, "render_scales", [3, 6])
    assert paint_fingerprint("a" * 64, "cpu") != baseline


def test_hidden_unit_and_proof_survive_final_archive(tmp_path):
    source = tmp_path / "hidden.pdf"
    with fixture("hidden")[0] as document:
        document[0].insert_text((35, 140), "Retained visible body text.")
        document.save(source)
    result = run_book(source, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    page = read_json(Path(result["output"]) / "page_000001.json.gz")
    proofs = page["visibility_evidence"]
    assert len(proofs) == 1 and proofs[0]["decision"] == "invisible"
    hidden = {proofs[0]["span_id"]}
    units = page["units"]["units"]
    retained = {
        sid
        for unit in units
        if unit["kind"] == "invisible"
        for lid in unit["line_ids"]
        for sid in page["line_spans"][lid]
    }
    assert hidden <= retained
    assert page["source"]["store"]["spans"][next(iter(hidden))]["raw_text"] == "Ordinary text"
    assert result["source_hashes"] == 1
