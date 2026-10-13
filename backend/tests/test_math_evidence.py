"""Synthetic source/presentation ambiguity and writing-frame math evidence gates."""

import unicodedata

import pytest
from pydantic import ValidationError
from test_cache_keys import closure

from book_core.accuracy.math_evidence import (
    MathEvidenceConfig,
    analyze_math_page,
    glyph_evidence,
    has_math_evidence,
)
from book_core.caching import coverage_files
from book_core.detection.models import DetectionResult, DetectorRegion
from book_core.device import DeviceResolution
from book_core.model.common import BBox, Provenance
from book_core.model.spans import (
    ExtractedPage,
    ExtractorIdentity,
    PageGeometry,
    SourceLine,
    SpanStore,
    TextSpan,
)
from book_core.objects.models import NativeObjectPage, PageObject, SpanGeometry

SOURCE = "a" * 64


def box(x0=0, y0=0, x1=100, y1=100):
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def native_page(parts=(), *, direction=(1.0, 0.0), images=(), content=None):
    spans = {}
    objects = []
    geometry = {}
    for index, (text, bounds) in enumerate(parts):
        sid = f"span-{index}"
        spans[sid] = TextSpan(
            id=sid,
            line_id="line",
            page=1,
            raw_text=text,
            text=unicodedata.normalize("NFKC", text),
            bbox=bounds,
            font="synthetic",
            size=10,
            color=0,
            flags=0,
            provenance=Provenance(source_sha256=SOURCE, method="native"),
        )
        objects.append(
            PageObject(
                id=sid,
                kind="text",
                bbox=bounds,
                source_page=1,
                source_spans=[sid],
                provenance=spans[sid].provenance,
            )
        )
        geometry[sid] = SpanGeometry(
            origin=(bounds.x0, bounds.y0),
            direction=direction,
            writing_mode="vertical" if direction[0] == 0 else "horizontal",
            ascender=1,
            descender=-0.2,
        )
    lines = []
    if spans:
        bounds = list(span.bbox for span in spans.values())
        lines = [
            SourceLine(
                id="line",
                page=1,
                span_ids=list(spans),
                bbox=box(
                    min(b.x0 for b in bounds),
                    min(b.y0 for b in bounds),
                    max(b.x1 for b in bounds),
                    max(b.y1 for b in bounds),
                ),
            )
        ]
    for index, bounds in enumerate(images):
        objects.append(
            PageObject(
                id=f"image-{index}",
                kind="image",
                bbox=bounds,
                source_page=1,
                provenance=Provenance(source_sha256=SOURCE, method="native"),
            )
        )
    page = ExtractedPage(
        source_sha256=SOURCE,
        extractor=ExtractorIdentity(name="synthetic", version="1", configuration={}),
        geometry=PageGeometry(
            page=1, width=100, height=100, rotation=0, content_bbox=content or box()
        ),
        store=SpanStore(spans=spans, lines=lines),
    )
    return NativeObjectPage(page=page, objects=objects, paint_commands=[], span_geometry=geometry)


def detection(bounds=()):
    return DetectionResult(
        source_sha256=SOURCE,
        page=1,
        detector="heron",
        repo_id="synthetic/heron",
        revision="b" * 40,
        threshold=0.5,
        regions=[
            DetectorRegion(
                id=f"region-{index}",
                type="unknown",
                bbox=bounds,
                raw_label="Formula",
                label_id=2,
                confidence=0.9,
                emission_index=index,
            )
            for index, bounds in enumerate(bounds)
        ],
        dependency_versions={},
        device=DeviceResolution(requested="cpu"),
        provenance=Provenance(source_sha256=SOURCE, method="derived"),
    )


def analyze(native, detected=None, **kwargs):
    return analyze_math_page(
        native,
        detected or detection(),
        render_sha256="c" * 64,
        model_sha256="d" * 64,
        **kwargs,
    )


def test_math_imports_are_covered_by_union_of_producer_scopes():
    covered = set(coverage_files("accuracy")) | set(coverage_files("detection"))
    assert closure("accuracy/math_evidence.py").issubset(covered)


@pytest.mark.parametrize("text", ["力=2", "س=٢", "x ≠ 2", "१२ + ३", "x²"])
def test_native_unicode_math_candidates_preserve_source(text):
    native = native_page([(text, box(0, 0, 80, 10))])
    before = native.model_dump_json()
    result = analyze(native)
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.source_type == "digital"
    assert candidate.source_refs[0].span_id == "span-0"
    assert candidate.detector_region_id is None
    assert candidate.basis == ["native_math_glyphs"]
    assert candidate.review_required
    assert text not in result.model_dump_json()
    assert native.model_dump_json() == before


@pytest.mark.parametrize("direction", [(1.0, 0.0), (-1.0, 0.0)])
def test_inline_native_fragment_uses_supplied_horizontal_baseline(direction):
    native = native_page(
        [
            ("before", box(0, 0, 30, 10)),
            ("x = 2", box(40, 0, 60, 10)),
            ("بعد", box(70, 0, 100, 10)),
        ],
        direction=direction,
    )
    candidate = analyze(native).candidates[0]
    assert candidate.presentation == "inline"
    assert candidate.context_refs != candidate.source_refs


def test_vertical_native_fragment_uses_supplied_baseline():
    native = native_page(
        [
            ("文章", box(0, 0, 10, 30)),
            ("力=2", box(0, 40, 10, 60)),
            ("続き", box(0, 70, 10, 100)),
        ],
        direction=(0.0, 1.0),
    )
    assert analyze(native).candidates[0].presentation == "inline"


def test_formula_detector_and_native_candidate_are_deduplicated():
    native = native_page([("x = 2", box(10, 10, 50, 20))])
    result = analyze(native, detection([box(5, 5, 55, 25)]))
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.detector_region_id == "region-0"
    assert candidate.presentation == "display"
    assert candidate.confidence == 0.9


@pytest.mark.parametrize("source_type", ["image", "mixed", "uncertain"])
def test_raster_source_is_evidence_not_assumed_from_missing_text(source_type):
    bounds = box(10, 10, 60, 30)
    native = native_page(
        [("x = 2", bounds)] if source_type == "mixed" else [],
        images=[bounds] if source_type != "uncertain" else [],
    )
    candidate = analyze(native, detection([bounds])).candidates[0]
    assert candidate.source_type == source_type
    assert bool(candidate.source_refs) == (source_type == "mixed")
    assert bool(candidate.image_object_ids) == (source_type != "uncertain")
    if source_type == "uncertain":
        assert candidate.source_confidence is None
        assert candidate.presentation_confidence is None


@pytest.mark.parametrize(
    "text", ["Some ordinary prose", "123 456", "مرحبا بالعالم", "日本語の文章"]
)
def test_prose_and_numeric_rows_are_not_native_math(text):
    assert not has_math_evidence(glyph_evidence(text))
    assert analyze(native_page([(text, box(0, 0, 80, 10))])).candidates == []


def test_presentation_remains_uncertain_without_supported_geometry():
    native = native_page([("The value x = unknown", box(0, 0, 100, 10))])
    assert analyze(native).candidates[0].presentation == "uncertain"


def test_trimbox_exclusions_do_not_edit_native_text():
    native = native_page([("x = 2", box(70, 0, 100, 10))], content=box(0, 0, 50, 100))
    before = native.model_dump_json()
    result = analyze(native, detection([box(70, 0, 100, 10)]))
    assert result.candidates == []
    assert result.retained_line_count == 0
    assert native.model_dump_json() == before


def test_source_page_mismatch_is_rejected():
    native = native_page([("x = 2", box(0, 0, 80, 10))])
    other = detection().model_copy(update={"source_sha256": "b" * 64})
    with pytest.raises(ValueError, match="different source pages"):
        analyze(native, other)


def test_all_producing_input_digests_and_configuration_change_key():
    native = native_page([("x = 2", box(0, 0, 80, 10))])
    original = analyze(native)
    changed = analyze_math_page(native, detection(), render_sha256="e" * 64, model_sha256="d" * 64)
    assert changed.cache_key != original.cache_key
    changed = analyze_math_page(native, detection(), render_sha256="c" * 64, model_sha256="e" * 64)
    assert changed.cache_key != original.cache_key
    changed = analyze(native, config=MathEvidenceConfig(display_symbol_fraction=0.7))
    assert changed.cache_key != original.cache_key
    assert type(original).model_validate_json(original.model_dump_json()) == original


@pytest.mark.parametrize(
    "configuration",
    [
        {"image_overlap_fraction": 0},
        {"inline_extent_fraction": 1},
        {"display_symbol_fraction": -0.1},
    ],
)
def test_degenerate_math_evidence_configuration_rejected(configuration):
    with pytest.raises(ValidationError):
        MathEvidenceConfig(**configuration)
