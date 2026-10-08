"""Evidence fusion protects structure and text; model boxes have no ownership."""

import pytest
from conftest import ROOT

from book_core.detection.models import DetectionResult, DetectorRegion
from book_core.device import DeviceResolution
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.layout.fusion import bbox_iou, fuse_regions, type_compatible
from book_core.layout.invariants import check as invariant_check
from book_core.layout.models import Band, Lane, PageLayout, Region, Scope, VisualLine
from book_core.layout.pipeline import analyze_layout
from book_core.ledger.accounting import check as ledger_check
from book_core.model.common import BBox, Provenance


def bbox(x0=10, y0=10, x1=100, y1=100):
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def own_layout(kind="main_text", *, direction="rtl", rotation=0.0):
    frame = bbox(0, 0, 120, 120)
    line = VisualLine(
        id="line",
        span_ids=["span"],
        source_line_ids=["native-line"],
        bbox=bbox(),
        baseline_start=(100, 20),
        baseline_end=(10, 20),
        direction=(-1.0, 0.0),
        rotation=rotation,
        writing_mode="vertical" if direction == "ttb" else "horizontal",
        text_direction=direction,
        font_size=10,
        visible=True,
        inside_content=True,
    )
    band = Band(
        id="band",
        scope_id="page",
        bbox=bbox(),
        column_count=1,
        confidence=0.8,
        reasons=["Own structure"],
        lanes=[
            Lane(
                index=0,
                x0=10,
                x1=100,
                kind="column",
                line_count=1,
                confidence=0.8,
                reasons=["Own lane"],
            )
        ],
    )
    region = Region(
        id="own",
        type=kind,
        bbox=bbox(),
        scope_id="page",
        band_id="band",
        lane_index=0,
        line_ids=["line"],
        object_ids=["object"],
        confidence=0.8,
        reasons=["Own evidence"],
    )
    return PageLayout(
        source_sha256="c" * 64,
        page=1,
        layout_version="test",
        content_bbox=frame,
        lines=[line],
        scopes=[Scope(id="page", kind="page", bbox=frame)],
        bands=[band],
        regions=[region],
        provenance=Provenance(source_sha256="c" * 64),
    )


def model_region(rid="model", kind="main_text", geometry=None, confidence=0.9, index=0):
    return DetectorRegion(
        id=rid,
        type=kind,
        bbox=geometry or bbox(),
        raw_label="native label",
        label_id=0,
        confidence=confidence,
        polygon=[(10, 10), (100, 10), (100, 100), (10, 100)],
        emission_index=index,
    )


def detection(regions, name="test-detector", digest="c" * 64, page=1):
    return DetectionResult(
        source_sha256=digest,
        page=page,
        detector=name,
        repo_id="test/repository",
        revision="a" * 40,
        threshold=0.5,
        regions=regions,
        dependency_versions={"test": "1"},
        device=DeviceResolution(requested="cpu"),
        provenance=Provenance(source_sha256=digest),
    )


def protected(layout):
    data = layout.model_dump(mode="json")
    data.pop("review_flags")
    for region in data["regions"]:
        for field in ("confidence", "reasons", "evidence", "review_required"):
            region.pop(field)
    return data


@pytest.mark.parametrize("direction,rotation", [("ltr", 0), ("rtl", 0), ("ttb", 90)])
def test_agreement_changes_only_annotations_and_confidence(direction, rotation):
    own = own_layout(direction=direction, rotation=rotation)
    model = detection([model_region()])
    original_own, original_model = own.model_dump_json(), model.model_dump_json()
    result = fuse_regions(own, [model])
    assert result.layout.regions[0].confidence == pytest.approx(0.818)
    assert result.layout.regions[0].evidence["model_agreements"] == 1
    assert result.comparisons[0].status == "agreement"
    assert not result.disagreements
    assert protected(own) == protected(result.layout)
    assert own.model_dump_json() == original_own
    assert model.model_dump_json() == original_model == result.detections[0].model_dump_json()
    assert result.layout.lines[0].text_direction == direction
    assert "text" not in Region.model_fields


def test_type_disagreement_keeps_both_sources_and_own_type():
    own = own_layout()
    result = fuse_regions(own, [detection([model_region(kind="table_candidate")])])
    assert result.disagreements[0].status == "type_disagreement"
    assert result.layout.regions[0].type == "main_text"
    assert result.layout.regions[0].confidence == own.regions[0].confidence
    assert result.layout.regions[0].review_required
    assert result.layout.review_flags[-1].subject_id == "own"
    assert result.detections[0].regions[0].type == "table_candidate"
    assert protected(own) == protected(result.layout)


@pytest.mark.parametrize("pieces", [2, 3])
def test_composite_figure_is_never_split_by_model_fragments(pieces):
    own = own_layout("figure")
    fragments = [
        model_region(
            str(index),
            "figure",
            bbox(10 + 90 * index / pieces, 10, 10 + 90 * (index + 1) / pieces, 100),
            index=index,
        )
        for index in range(pieces)
    ]
    result = fuse_regions(own, [detection(fragments)])
    assert len(result.layout.regions) == 1
    assert result.layout.regions[0].bbox == own.regions[0].bbox
    assert result.layout.regions[0].line_ids == ["line"]
    assert result.layout.regions[0].confidence == own.regions[0].confidence
    assert len(result.detections[0].regions) == pieces
    assert result.disagreements[0].status == "fragmented_figure"
    assert len(result.disagreements[0].model_region_ids) == pieces
    assert result.disagreements[0].iou == pytest.approx(1.0)


def test_detector_geometry_outside_content_frame_is_flagged_not_adopted():
    own = own_layout("figure")
    model = detection([model_region(kind="figure", geometry=bbox(-5, 10, 100, 100))])
    result = fuse_regions(own, [model])
    assert result.disagreements[0].status == "geometry_disagreement"
    assert "I4" in result.disagreements[0].reason
    assert protected(own) == protected(result.layout)
    assert result.layout.regions[0].confidence == own.regions[0].confidence


def test_model_misses_and_new_regions_remain_explicit_review_evidence():
    own = own_layout()
    distant = model_region(geometry=bbox(105, 105, 115, 115))
    result = fuse_regions(own, [detection([distant])])
    assert {item.status for item in result.disagreements} == {"own_only", "model_only"}
    assert result.layout.regions[0].line_ids == ["line"]
    assert result.detections[0].regions == [distant]


def test_iou_threshold_is_configurable_without_changing_own_geometry():
    own = own_layout()
    model = detection([model_region(geometry=bbox(40, 10, 100, 100))])
    at_half = fuse_regions(own, [model])
    at_four_fifths = fuse_regions(own, [model], iou_threshold=0.8)
    assert at_half.comparisons[0].status == "agreement"
    assert at_four_fifths.disagreements[0].status == "geometry_disagreement"
    assert protected(own) == protected(at_half.layout) == protected(at_four_fifths.layout)


def test_duplicate_regions_do_not_multiply_detector_confidence_gain():
    own = own_layout()
    result = fuse_regions(own, [detection([model_region("a"), model_region("b")])])
    assert len(result.comparisons) == 2
    assert result.layout.regions[0].confidence == pytest.approx(0.818)
    assert result.layout.regions[0].evidence["model_agreements"] == 1
    assert fuse_regions(own, []).layout == own


@pytest.mark.parametrize("threshold,gain", [(0, 0.1), (1.01, 0.1), (0.5, -0.1), (0.5, 1.1)])
def test_invalid_fusion_settings_are_rejected(threshold, gain):
    with pytest.raises(ValueError):
        fuse_regions(own_layout(), [], iou_threshold=threshold, agreement_gain=gain)


def test_cross_source_or_duplicate_detector_evidence_is_rejected():
    own = own_layout()
    with pytest.raises(ValueError, match="another source"):
        fuse_regions(own, [detection([], digest="d" * 64)])
    with pytest.raises(ValueError, match="another source"):
        fuse_regions(own, [detection([], page=2)])
    with pytest.raises(ValueError, match="one result per detector"):
        fuse_regions(own, [detection([]), detection([])])


def test_compatibility_is_conservative_and_unknown_cannot_corroborate():
    assert type_compatible("title_candidate", "heading_candidate")
    assert type_compatible("page_number_candidate", "header_footer_candidate")
    assert not type_compatible("unknown", "unknown")
    assert not type_compatible("sidebar", "main_text")
    assert not type_compatible("callout", "table_candidate")
    assert bbox_iou(bbox(), bbox()) == 1.0
    assert bbox_iou(bbox(), bbox(100, 100, 110, 110)) == 0.0


def test_invariants_and_text_ledger_remain_exact_with_contradictory_model_evidence():
    source = ROOT / "experiments/fixtures/science_fission.pdf"
    own, analysis = analyze_layout(
        source, 1, PyMuPDFExtractor(device="cpu"), cache_dir=ROOT / ".cache/objects"
    )
    before_analysis = analysis.model_dump_json()
    document, ledger = provision_page(analysis.native.page)
    before_document, before_ledger = document.model_dump_json(), ledger.model_dump_json()
    reports = invariant_check(own, analysis)
    assert all(not failures for failures in reports.values())
    contradicting = detection(
        [
            model_region(str(index), "table_candidate", region.bbox, index=index)
            for index, region in enumerate(own.regions)
            if region.bbox.x0 < region.bbox.x1 and region.bbox.y0 < region.bbox.y1
        ],
        digest=own.source_sha256,
    )
    result = fuse_regions(own, [contradicting], analysis=analysis)
    assert result.invariants_checked
    assert protected(result.layout) == protected(own)
    assert invariant_check(result.layout, analysis) == reports
    assert analysis.model_dump_json() == before_analysis
    assert document.model_dump_json() == before_document
    assert ledger.model_dump_json() == before_ledger
    report = ledger_check(document, ledger)
    assert report.passing and report.missing_token_count == report.extra_token_count == 0
