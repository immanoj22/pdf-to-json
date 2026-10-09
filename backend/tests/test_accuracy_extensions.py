"""Optional accuracy contracts remain inert, source-referenced and cache-safe."""

import hashlib
import json
import shutil

import pytest
from pydantic import ValidationError

from book_core import caching
from book_core.accuracy import cache
from book_core.accuracy.adapters import (
    LanguageInput,
    MetadataLanguageDetector,
    MetadataOcrEngine,
    OcrInput,
    metadata_from_language,
)
from book_core.accuracy.interfaces import (
    AccuracyProvider,
    ContinuationScorer,
    FormulaRecognizer,
    HeadingClassifier,
    MathBuilder,
    MathConverter,
    PageReviewer,
    TableStructureRecognizer,
)
from book_core.accuracy.models import (
    AccuracyInput,
    ContinuationInput,
    EvidenceReference,
    ExtensionMetadata,
    FormulaInput,
    FormulaObservation,
    FormulaResult,
    GlyphEvidence,
    HeadingInput,
    MathBuildInput,
    MathBuildResult,
    MathConversionInput,
    PageReviewInput,
    PageReviewResult,
    ReviewFinding,
    RuleEvidence,
    SourceRegion,
    TableCellEvidence,
    TableStructureInput,
    TableStructureResult,
)
from book_core.accuracy.stubs import (
    UnavailableContinuationScorer,
    UnavailableFormulaRecognizer,
    UnavailableHeadingClassifier,
    UnavailableMathBuilder,
    UnavailableMathConverter,
    UnavailablePageReviewer,
    UnavailableTableStructureRecognizer,
)
from book_core.device import DeviceResolution
from book_core.document_analysis.language import (
    LanguageEvidence,
    LanguageScore,
    LanguageSegment,
)
from book_core.extraction.rasters import RasterPage
from book_core.model.common import BBox, Provenance, SpanRef
from book_core.model.math import MathTree
from book_core.model.spans import TextSpan

SOURCE = "a" * 64


@pytest.fixture
def regions():
    return [
        SourceRegion(
            id="source-first",
            page=3,
            bbox=BBox(x0=-20, y0=30, x1=70, y1=140),
            source_refs=[SpanRef(span_id="span-first", start=1, end=8)],
            languages=["ara", "eng"],
            script="Arab",
            text_direction="rtl",
        ),
        SourceRegion(
            id="source-second",
            page=4,
            source_refs=[SpanRef(span_id="span-second")],
            languages=["jpn"],
            script="Jpan",
            text_direction="ttb",
        ),
    ]


@pytest.fixture
def raster():
    return RasterPage(
        png=b"extractor-render",
        width=200,
        height=400,
        page_width=100,
        page_height=200,
    )


def tree():
    return MathTree(
        kind="fraction",
        children=[
            MathTree(kind="symbol", source_refs=[SpanRef(span_id="span-first", start=1, end=2)]),
            MathTree(kind="symbol", source_refs=[SpanRef(span_id="span-first", start=2, end=3)]),
        ],
    )


SLOTS = [
    (
        UnavailableTableStructureRecognizer,
        TableStructureRecognizer,
        TableStructureInput,
        "recognize",
    ),
    (UnavailableFormulaRecognizer, FormulaRecognizer, FormulaInput, "recognize"),
    (UnavailableMathBuilder, MathBuilder, MathBuildInput, "build"),
    (UnavailableMathConverter, MathConverter, MathConversionInput, "convert"),
    (UnavailableContinuationScorer, ContinuationScorer, ContinuationInput, "score"),
    (UnavailableHeadingClassifier, HeadingClassifier, HeadingInput, "classify"),
    (UnavailablePageReviewer, PageReviewer, PageReviewInput, "review"),
]


def request_for(request_type, regions):
    fields = {"source_sha256": SOURCE, "regions": regions}
    if request_type in {FormulaInput, MathBuildInput}:
        fields["source_kind"] = "digital"
    if request_type is MathConversionInput:
        fields.update(tree=tree(), target_format="latex")
    if request_type is ContinuationInput:
        fields.update(first_region_id=regions[0].id, second_region_id=regions[1].id)
    if request_type is HeadingInput:
        fields["candidate_region_id"] = regions[0].id
    if request_type is PageReviewInput:
        fields.update(regions=[regions[0]], page=regions[0].page)
    return request_type(**fields)


@pytest.mark.parametrize("provider_type,protocol,request_type,method", SLOTS)
@pytest.mark.parametrize("device", ["cpu", "auto", "cuda"])
def test_each_slot_is_explicitly_unavailable(
    provider_type, protocol, request_type, method, device, regions, monkeypatch
):
    def forbidden_probe(*args, **kwargs):
        raise AssertionError("Unavailable providers must not probe optional GPU libraries")

    monkeypatch.setattr("book_core.device.cuda_ready", forbidden_probe)
    provider = provider_type(device=device)
    request = request_for(request_type, regions)
    snapshot = request.model_dump_json()
    result = getattr(provider, method)(request)
    assert isinstance(provider, protocol)
    assert isinstance(provider, AccuracyProvider)
    assert result.status == "unavailable"
    assert result.reason == "provider_not_configured"
    assert result.confidence is None
    assert result.metadata.device.requested == device
    assert result.metadata.device.resolved == "cpu"
    assert result.provenance.source_sha256 == SOURCE
    assert result.provenance.execution_device == "cpu"
    assert request.model_dump_json() == snapshot
    assert type(result).model_validate_json(result.model_dump_json()) == result
    cache.validate_result(request, provider, result)
    for name in (
        "row_count",
        "column_count",
        "cells",
        "observations",
        "tree",
        "generated_value",
        "continuation_score",
        "heading_likelihood",
        "label",
        "level",
        "findings",
    ):
        if hasattr(result, name):
            assert getattr(result, name) in (None, [])


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "different-provider"),
        ("version", "2"),
        ("configuration", {"threshold": 0.8}),
        ("producer_source_sha256", "b" * 64),
        ("model_sha256", "c" * 64),
        ("dependency_versions", {"provider-runtime": "2"}),
        ("device", DeviceResolution(requested="cpu")),
    ],
)
def test_provider_identity_invalidates_key(regions, field, value):
    provider = UnavailableTableStructureRecognizer(configuration={"threshold": 0.7})
    request = request_for(TableStructureInput, regions)
    original = cache.accuracy_fingerprint(request, provider)
    provider._metadata = provider.metadata.model_copy(update={field: value})
    assert cache.accuracy_fingerprint(request, provider) != original


@pytest.mark.parametrize("field", ["source", "page", "range", "geometry", "direction", "feature"])
def test_input_evidence_invalidates_key(regions, field):
    provider = UnavailableTableStructureRecognizer()
    request = request_for(TableStructureInput, regions)
    original = cache.accuracy_fingerprint(request, provider)
    data = request.model_dump(mode="json")
    if field == "source":
        data["source_sha256"] = "b" * 64
    elif field == "page":
        data["regions"][0]["page"] += 1
    elif field == "range":
        data["regions"][0]["source_refs"][0]["end"] -= 1
    elif field == "geometry":
        data["regions"][0]["bbox"]["x0"] -= 1
    elif field == "direction":
        data["regions"][0]["text_direction"] = "ttb"
    else:
        data["features"]["spacing_ratio"] = 0.25
    assert (
        cache.accuracy_fingerprint(TableStructureInput.model_validate(data), provider) != original
    )


def test_pixels_frame_runtime_and_execution_device_invalidate_key(regions, raster, monkeypatch):
    provider = UnavailableTableStructureRecognizer()
    request = TableStructureInput(
        source_sha256=SOURCE,
        regions=[regions[0]],
        raster=raster,
        raster_page=regions[0].page,
        raster_bbox=BBox(x0=-30, y0=0, x1=70, y1=200),
    )
    original = cache.accuracy_fingerprint(request, provider)
    altered = request.model_copy(update={"raster": raster.model_copy(update={"png": b"changed"})})
    assert cache.accuracy_fingerprint(altered, provider) != original
    altered = request.model_copy(update={"raster_bbox": BBox(x0=-40, y0=0, x1=60, y1=200)})
    assert cache.accuracy_fingerprint(altered, provider) != original
    assert cache.accuracy_fingerprint(request, provider, resolved_device="cuda") != original
    monkeypatch.setattr(cache, "runtime_versions", lambda: {"python": "changed"})
    assert cache.accuracy_fingerprint(request, provider) != original


def test_fallback_diagnostics_do_not_change_actual_cpu_key(regions):
    provider = UnavailableTableStructureRecognizer()
    request = request_for(TableStructureInput, regions)
    result = provider.recognize(request)
    changed = result.metadata.device.model_copy(update={"fallback_reason": "GPU failure"})
    result = result.model_copy(
        update={"metadata": result.metadata.model_copy(update={"device": changed})}
    )
    cache.validate_result(request, provider, result)


def test_source_edit_changes_key_and_stale_worker_refuses(regions, tmp_path, monkeypatch):
    package = tmp_path / "book_core"
    shutil.copytree(caching.PACKAGE, package, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(caching, "PACKAGE", package)
    provider = UnavailableTableStructureRecognizer()
    request = request_for(TableStructureInput, regions)
    original = cache.accuracy_fingerprint(request, provider)
    source = package / "accuracy" / "stubs.py"
    source.write_bytes(source.read_bytes() + b"\n# changed provider\n")
    assert cache.accuracy_fingerprint(request, provider) != original
    with pytest.raises(RuntimeError, match="restart"):
        provider.recognize(request)


@pytest.mark.parametrize(
    "update",
    [
        {"source_sha256": "b" * 64},
        {"request_sha256": "b" * 64},
        {"cache_key": "b" * 64},
    ],
)
def test_result_identity_mismatch_is_rejected(regions, update):
    provider = UnavailableTableStructureRecognizer()
    request = request_for(TableStructureInput, regions)
    result = provider.recognize(request).model_copy(update=update)
    with pytest.raises(ValueError, match="source|cache key"):
        cache.validate_result(request, provider, result)


def test_model_identity_requires_actual_model_digest():
    with pytest.raises(ValidationError, match="content digest"):
        ExtensionMetadata(
            name="test", version="1", producer_source_sha256="a" * 64, model_repository="models/x"
        )


def test_invalid_image_and_reference_requests_are_rejected(regions, raster):
    with pytest.raises(ValidationError, match="coordinate frame"):
        AccuracyInput(source_sha256=SOURCE, regions=regions, raster=raster)
    with pytest.raises(ValidationError, match="extractor pixels"):
        FormulaInput(source_sha256=SOURCE, regions=regions, source_kind="image")
    with pytest.raises(ValidationError, match="unknown"):
        HeadingInput(source_sha256=SOURCE, regions=regions, candidate_region_id="missing")
    with pytest.raises(ValidationError, match="distinct"):
        ContinuationInput(
            source_sha256=SOURCE,
            regions=regions,
            first_region_id=regions[0].id,
            second_region_id=regions[0].id,
        )
    with pytest.raises(ValidationError, match="mix source pages"):
        PageReviewInput(source_sha256=SOURCE, regions=regions, page=3)


def test_unavailable_results_cannot_invent_scores_or_content(regions):
    provider = UnavailableTableStructureRecognizer()
    request = request_for(TableStructureInput, regions)
    base = provider.recognize(request).model_dump(exclude={"row_count", "column_count", "cells"})
    for result_type, fields in [
        (TableStructureResult, {"row_count": 2}),
        (
            FormulaResult,
            {
                "observations": [
                    FormulaObservation(
                        id="formula",
                        region_id=regions[0].id,
                        source_kind="digital",
                        source_refs=regions[0].source_refs,
                    )
                ]
            },
        ),
        (MathBuildResult, {"tree": tree()}),
        (PageReviewResult, {"findings": [ReviewFinding(id="finding", kind="uncertain")]}),
    ]:
        with pytest.raises(ValidationError):
            result_type(**base, **fields)
    base["confidence"] = 0.8
    with pytest.raises(ValidationError, match="no confidence"):
        TableStructureResult(**base)


def test_evidence_source_ranges_and_review_findings_are_checked(regions):
    provider = UnavailableTableStructureRecognizer()
    request = request_for(TableStructureInput, regions)
    base = provider.recognize(request).model_dump(exclude={"row_count", "column_count", "cells"})
    base.update(status="evidence")
    result = TableStructureResult(
        **base,
        row_count=1,
        column_count=1,
        cells=[
            TableCellEvidence(
                row=0, column=0, source_refs=[SpanRef(span_id="span-first", start=2, end=3)]
            )
        ],
    )
    cache.validate_result(request, provider, result)
    result = result.model_copy(
        update={
            "cells": [
                TableCellEvidence(row=0, column=0, source_refs=[SpanRef(span_id="span-first")])
            ]
        }
    )
    with pytest.raises(ValueError, match="source range"):
        cache.validate_result(request, provider, result)
    reviewer = UnavailablePageReviewer()
    review_request = request_for(PageReviewInput, regions)
    review_base = reviewer.review(review_request).model_dump(exclude={"findings"})
    review_base["status"] = "evidence"
    result = PageReviewResult(
        **review_base,
        findings=[ReviewFinding(id="finding", kind="uncertain", region_ids=["missing"])],
    )
    with pytest.raises(ValueError, match="unknown source region"):
        cache.validate_result(review_request, reviewer, result)


def test_digital_formula_and_math_never_copy_generated_values(regions):
    with pytest.raises(ValidationError, match="source references"):
        FormulaObservation(
            id="formula",
            region_id=regions[0].id,
            source_kind="digital",
            source_refs=regions[0].source_refs,
            recognized_latex="x",
        )
    provider = UnavailableMathBuilder()
    request = request_for(MathBuildInput, regions)
    result = provider.build(request)
    result = result.model_copy(
        update={"status": "evidence", "tree": MathTree(kind="symbol", derived_value="x")}
    )
    with pytest.raises(ValueError, match="preserve source references"):
        cache.validate_result(request, provider, result)


class FakeLanguage:
    identity = {
        "name": "test-language",
        "version": "1",
        "configuration": {"languages": ["ara", "eng"]},
    }

    def __init__(self):
        self.last = None
        self.evidence = LanguageEvidence(
            language="und",
            confidence=0.8,
            candidates=(LanguageScore("ar", 0.8), LanguageScore("en", 0.6)),
            segments=(LanguageSegment(0, 5, "ar", 0.8), LanguageSegment(6, 11, "en", 0.9)),
            mixed=True,
            reason="mixed_language_evidence",
        )

    def detect(self, text):
        self.last = text
        return self.evidence


def explicit_metadata():
    return ExtensionMetadata(
        name="test-provider",
        version="1",
        configuration={"languages": ["ara", "eng"]},
        producer_source_sha256="c" * 64,
        model_sha256="d" * 64,
        device=DeviceResolution(requested="cpu"),
    )


def test_language_legacy_delegate_and_opt_in_context_are_lossless(regions):
    detector = FakeLanguage()
    wrapper = MetadataLanguageDetector(detector, explicit_metadata())
    text = "مرحبا hello"
    assert wrapper.detect(text) is detector.evidence
    assert wrapper.identity is detector.identity
    request = LanguageInput(
        source_sha256=SOURCE,
        regions=[regions[0]],
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    result = wrapper.detect_with_context(text, request)
    assert result.evidence == detector.evidence
    assert detector.last == text
    assert result.source_sha256 == SOURCE
    assert result.provenance.execution_device == "cpu"
    assert text not in result.model_dump_json()
    cache.validate_result(request, wrapper, result)
    with pytest.raises(ValueError, match="Transient"):
        wrapper.detect_with_context("different", request)
    with pytest.raises(ValueError, match="explicit extension metadata"):
        metadata_from_language(detector)


def test_lingua_bridge_records_model_and_resolved_configuration():
    detector = FakeLanguage()
    detector.identity = {
        "name": "lingua-language-detector",
        "version": "test",
        "configuration": {"languages": ["ar", "en"], "minimum_letters": 10},
        "model": {"sha256": "b" * 64},
    }
    metadata = metadata_from_language(detector)
    assert metadata.model_sha256 == "b" * 64
    assert metadata.configuration == detector.identity["configuration"]
    assert metadata.device.resolved == "cpu"
    detector.identity["configuration"] = {"languages": ["ar"], "minimum_letters": 20}
    assert metadata_from_language(detector).configuration != metadata.configuration


class FakeOcr:
    def __init__(self, span):
        self.span = span
        self.arguments = None
        self.iterator = iter([span])

    def recognize(self, image, *, languages):
        self.arguments = (image, languages)
        return self.iterator


def test_ocr_bridge_is_explicit_and_preserves_legacy_iterator(regions, raster):
    span = TextSpan(
        id="recognized",
        line_id="recognized-line",
        page=3,
        raw_text="مرحبا",
        text="مرحبا",
        bbox=BBox(x0=0, y0=0, x1=20, y1=10),
        font="",
        size=0,
        color=0,
        flags=0,
        text_direction="rtl",
        provenance=Provenance(source_sha256=SOURCE, method="ocr"),
    )
    engine = FakeOcr(span)
    wrapper = MetadataOcrEngine(engine, explicit_metadata())
    assert wrapper.recognize(raster.png, languages=["ara", "eng"]) is engine.iterator
    engine.iterator = iter([span])
    request = OcrInput(
        source_sha256=SOURCE,
        regions=[regions[0]],
        raster=raster,
        raster_page=regions[0].page,
        raster_bbox=BBox(x0=0, y0=0, x1=100, y1=200),
        languages=["ara", "eng"],
    )
    spans, result = wrapper.recognize_with_context(request)
    assert spans == (span,)
    assert engine.arguments == (raster.png, ["ara", "eng"])
    assert result.source_refs == [SpanRef(span_id=span.id)]
    assert result.provenance.method == "ocr"
    assert span.raw_text not in result.model_dump_json()
    assert json.loads(result.model_dump_json())["metadata"]["model_sha256"] == "d" * 64
    engine.iterator = iter([span.model_copy(update={"page": 9})])
    with pytest.raises(ValueError, match="requested source"):
        wrapper.recognize_with_context(request)


def test_math_conversion_accepts_tree_or_provenanced_derived_latex(regions):
    common = {"source_sha256": SOURCE, "regions": regions, "target_format": "mathml"}
    request = MathConversionInput(
        **common,
        recognized_latex=r"\frac{x}{2}",
        input_source="image",
        input_provenance=Provenance(source_sha256=SOURCE, method="derived"),
    )
    provider = UnavailableMathConverter()
    result = provider.convert(request)
    assert result.status == "unavailable"
    assert result.generated_value is None
    cache.validate_result(request, provider, result)
    assert MathConversionInput(**common, tree=tree()).tree is not None
    for fields in (
        {},
        {"tree": tree(), "recognized_latex": "x"},
        {"recognized_latex": "x"},
        {
            "recognized_latex": " ",
            "input_source": "image",
            "input_provenance": Provenance(source_sha256=SOURCE, method="derived"),
        },
        {
            "recognized_latex": "x",
            "input_source": "digital",
            "input_provenance": Provenance(source_sha256="b" * 64, method="derived"),
        },
    ):
        with pytest.raises(ValidationError):
            MathConversionInput(**common, **fields)


def test_heading_contract_keeps_label_level_and_confidence_unavailable(regions):
    provider = UnavailableHeadingClassifier()
    result = provider.classify(request_for(HeadingInput, regions))
    assert result.label is None and result.level is None and result.confidence is None
    with pytest.raises(ValidationError, match="no label or level"):
        type(result).model_validate({**result.model_dump(), "label": "heading", "level": 2})
    with pytest.raises(ValidationError, match="Only a heading"):
        type(result).model_validate(
            {**result.model_dump(), "status": "evidence", "label": "not_heading", "level": 2}
        )
    available = type(result).model_validate(
        {
            **result.model_dump(),
            "status": "evidence",
            "label": "heading",
            "level": 2,
            "confidence": 0.7,
        }
    )
    assert available.label == "heading" and available.level == 2


def test_result_operation_and_provenance_cannot_be_forged(regions):
    provider = UnavailableTableStructureRecognizer()
    request = request_for(TableStructureInput, regions)
    result = provider.recognize(request)
    base = result.model_dump(exclude={"row_count", "column_count", "cells"})
    with pytest.raises(ValueError, match="request operation"):
        cache.validate_result(request, provider, FormulaResult(**base))
    for update in ({"engine": "other"}, {"engine_version": "other"}):
        bad = result.model_copy(update={"provenance": result.provenance.model_copy(update=update)})
        with pytest.raises(ValueError, match="provenance identity"):
            cache.validate_result(request, provider, bad)


def test_cpu_policy_cannot_claim_cuda_but_cuda_can_recover_on_cpu(regions):
    request = request_for(TableStructureInput, regions)
    cpu = UnavailableTableStructureRecognizer(device="cpu")
    result = cpu.recognize(request)
    forged = result.model_copy(
        update={
            "metadata": result.metadata.model_copy(
                update={"device": DeviceResolution(requested="cpu", resolved="cuda")}
            ),
            "provenance": result.provenance.model_copy(
                update={
                    "resolved_device": "cuda",
                    "execution_device": "cuda",
                }
            ),
        }
    )
    with pytest.raises(ValueError, match="CPU device policy"):
        cache.validate_result(request, cpu, forged)
    for requested in ("auto", "cuda"):
        provider = UnavailableTableStructureRecognizer(device=requested)
        recovered = provider.recognize(request)
        provider._metadata = provider.metadata.model_copy(
            update={"device": DeviceResolution(requested=requested, resolved="cuda")}
        )
        cache.validate_result(request, provider, recovered)


@pytest.mark.parametrize("device", ["", False, 0])
def test_false_execution_device_is_rejected(regions, device):
    provider = UnavailableTableStructureRecognizer()
    with pytest.raises(ValueError, match="Unsupported execution device"):
        cache.accuracy_fingerprint(
            request_for(TableStructureInput, regions), provider, resolved_device=device
        )


def test_nonfinite_configuration_is_not_a_json_cache_identity(regions):
    provider = UnavailableTableStructureRecognizer(configuration={"threshold": float("nan")})
    with pytest.raises(ValueError):
        cache.accuracy_fingerprint(request_for(TableStructureInput, regions), provider)


def test_formula_observations_bind_source_kind_and_own_region(regions):
    provider = UnavailableFormulaRecognizer()
    request = request_for(FormulaInput, regions)
    base = provider.recognize(request).model_dump(exclude={"observations"})
    base["status"] = "evidence"
    mismatched_kind = FormulaObservation(
        id="formula",
        region_id=regions[0].id,
        source_kind="image",
        recognized_latex="x",
        source_refs=regions[1].source_refs,
    )
    with pytest.raises(ValueError, match="source kind"):
        cache.validate_result(
            request, provider, FormulaResult(**base, observations=[mismatched_kind])
        )
    mismatched_region = FormulaObservation(
        id="formula",
        region_id=regions[0].id,
        source_kind="digital",
        source_refs=regions[1].source_refs,
    )
    with pytest.raises(ValueError, match="another source region"):
        cache.validate_result(
            request, provider, FormulaResult(**base, observations=[mismatched_region])
        )
    correct = mismatched_region.model_copy(update={"source_refs": regions[0].source_refs})
    cache.validate_result(request, provider, FormulaResult(**base, observations=[correct]))


def test_one_raster_requires_explicit_single_source_page(regions, raster):
    common = {
        "source_sha256": SOURCE,
        "raster": raster,
        "raster_bbox": BBox(x0=0, y0=0, x1=100, y1=200),
    }
    with pytest.raises(ValidationError, match="explicit source page"):
        TableStructureInput(**common, regions=[regions[0]])
    with pytest.raises(ValidationError, match="cross source pages"):
        TableStructureInput(**common, regions=regions, raster_page=regions[0].page)
    with pytest.raises(ValidationError, match="cross source pages"):
        TableStructureInput(**common, regions=[regions[0]], raster_page=regions[1].page)
    request = TableStructureInput(**common, regions=[regions[0]], raster_page=regions[0].page)
    binary = request.model_copy(
        update={"raster": raster.model_copy(update={"png": b"\x89PNG\xff"})}
    )
    assert TableStructureInput.model_validate_json(binary.model_dump_json()) == binary


def test_native_glyph_and_rule_contract_binds_artifacts_and_regions(regions):
    region = regions[0].model_copy(update={"native_object_ids": ["native-rule"]})
    artifact = EvidenceReference(id="native-artifact", sha256="b" * 64, kind="native_objects")
    glyph = GlyphEvidence(
        id="native-glyph",
        region_id=region.id,
        native_evidence_id=artifact.id,
        source_ref=SpanRef(span_id="span-first", start=1, end=3),
        bbox=region.bbox,
        origin=(-10, 40),
        writing_vector=(-1, 0),
    )
    rule = RuleEvidence(
        region_id=region.id,
        native_evidence_id=artifact.id,
        object_id="native-rule",
        start=(-10, 50),
        end=(40, 50),
        stroke_width=0,
    )
    fields = {
        "source_sha256": SOURCE,
        "regions": [region, regions[1]],
        "source_kind": "digital",
        "evidence_refs": [artifact],
        "glyphs": [glyph],
        "rules": [rule],
    }
    request = MathBuildInput(**fields)
    assert request.glyphs[0].source_ref.end - request.glyphs[0].source_ref.start == 2
    assert MathBuildInput.model_validate_json(request.model_dump_json()) == request
    provider = UnavailableMathBuilder()
    result = provider.build(request)
    cache.validate_result(request, provider, result)
    for update, message in (
        ({"evidence_refs": []}, "artifact digest"),
        (
            {"glyphs": [glyph.model_copy(update={"region_id": regions[1].id})]},
            "another source region",
        ),
        (
            {"rules": [rule.model_copy(update={"region_id": regions[1].id})]},
            "another source region",
        ),
    ):
        with pytest.raises(ValidationError, match=message):
            MathBuildInput.model_validate({**request.model_dump(), **update})
    with pytest.raises(ValidationError, match="explicit original character range"):
        GlyphEvidence.model_validate(
            {**glyph.model_dump(), "source_ref": SpanRef(span_id="span-first")}
        )
    with pytest.raises(ValidationError, match="nonzero writing vector"):
        GlyphEvidence.model_validate({**glyph.model_dump(), "writing_vector": (0, 0)})
    with pytest.raises(ValidationError, match="distinct endpoints"):
        RuleEvidence.model_validate({**rule.model_dump(), "end": rule.start})


def test_converter_output_format_is_bound_to_request(regions):
    request = MathConversionInput(
        source_sha256=SOURCE, regions=regions, tree=tree(), target_format="mathml"
    )
    provider = UnavailableMathConverter()
    result = provider.convert(request).model_copy(update={"target_format": "latex"})
    with pytest.raises(ValueError, match="output format"):
        cache.validate_result(request, provider, result)
