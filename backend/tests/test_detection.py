"""Detector contracts tested without model downloads or optional imports."""

import builtins
import importlib
import sys

import pytest
from pydantic import ValidationError

from book_core.detection import (
    DetectionInput,
    HeronDetector,
    PPDocLayoutV3Detector,
    RegionDetector,
)
from book_core.detection.models import DetectionResult, DetectorRegion
from book_core.detection.transformers import observations, region_type
from book_core.device import DeviceResolution
from book_core.extraction.rasters import RasterPage
from book_core.model.common import BBox

DIGEST = "a" * 64


class Value:
    def __init__(self, value):
        self.value = value

    def item(self):
        return self.value

    def tolist(self):
        return self.value


def page():
    return DetectionInput(
        source_sha256=DIGEST,
        page=1,
        raster=RasterPage(png=b"render", width=200, height=300, page_width=100, page_height=100),
        page_bbox=BBox(x0=10, y0=20, x1=110, y1=120),
    )


def test_import_keeps_optional_dependencies_lazy(monkeypatch):
    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "torchvision", "transformers", "PIL"}:
            raise AssertionError(f"Optional import on default path: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    importlib.reload(sys.modules["book_core.detection"])
    detector = HeronDetector(device="cpu")
    assert isinstance(detector, RegionDetector)
    assert detector.device.resolved == "cpu"


def test_transform_uses_both_axes_and_nonzero_render_origin_preserves_emission():
    processed = {
        "scores": [Value(0.8), Value(0.9)],
        "labels": [Value(6), Value(9)],
        "boxes": [Value([100, 150, 200, 300]), Value([0, 0, 80, 90])],
        "polygon_points": [
            Value([[100, 150], [200, 150], [200, 300], [100, 300]]),
            Value([[0, 0], [80, 0], [80, 90], [0, 90]]),
        ],
    }
    regions = observations(
        page(), processed, {6: "picture", 9: "text"}, "heron", HeronDetector.default_revision
    )
    assert regions[0].bbox == BBox(x0=60, y0=70, x1=110, y1=120)
    assert regions[1].bbox == BBox(x0=10, y0=20, x1=50, y1=50)
    assert regions[0].polygon == [(60, 70), (110, 70), (110, 120), (60, 120)]
    assert [region.emission_index for region in regions] == [0, 1]
    assert [region.type for region in regions] == ["figure", "main_text"]
    assert len({region.id for region in regions}) == 2


def test_labels_are_proposals_and_unsupported_classes_remain_unknown():
    assert region_type("Section-header") == "heading_candidate"
    assert region_type("aside_text") == "sidebar"
    assert region_type("header") == "header_footer_candidate"
    assert region_type("table") == "table_candidate"
    assert region_type("number") == "unknown"
    assert region_type("formula") == "unknown"
    assert region_type("unfamiliar_label") == "unknown"


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_threshold_rejected(threshold):
    with pytest.raises(ValueError, match="threshold"):
        HeronDetector(threshold=threshold)


def test_immutable_revision_required():
    with pytest.raises(ValueError, match="immutable"):
        HeronDetector(revision="main")


def test_gpu_failure_retries_whole_detection_on_cpu_and_records_device(monkeypatch):
    detector = HeronDetector(device="auto")
    detector._device = DeviceResolution(requested="auto", resolved="cuda")
    attempted = []

    def infer(render, device):
        attempted.append(device)
        if device == "cuda":
            detector._model = object()  # Simulates weights left in a failed GPU context.
            raise RuntimeError("simulated failed kernel")
        assert detector._model is None
        return []

    monkeypatch.setattr(detector, "_infer", infer)
    result = detector.detect(page())
    assert attempted == ["cuda", "cpu"]
    assert result.device == DeviceResolution(
        requested="auto", fallback_reason="GPU operation failed (RuntimeError)"
    )
    assert result.provenance.execution_device == "cpu"
    assert result.provenance.resolved_device == "cpu"
    assert detector.device.resolved == "cpu"
    assert any("device_fallback:" in note for note in result.provenance.notes)


def test_cpu_failure_is_not_hidden(monkeypatch):
    detector = PPDocLayoutV3Detector(device="cpu")

    def infer(render, device):
        raise RuntimeError("failed CPU inference")

    monkeypatch.setattr(detector, "_infer", infer)
    with pytest.raises(RuntimeError, match="failed CPU"):
        detector.detect(page())


def test_result_has_no_text_or_ownership_and_preserves_source():
    result = HeronDetector(device="cpu")
    result._infer = lambda render, device: []
    evidence = result.detect(page()).model_dump()
    assert not {"text", "spans", "line_ids", "reading_order", "bands"} & set(evidence)
    assert not {"text", "span_ids", "line_ids", "reading_order"} & set(DetectorRegion.model_fields)
    assert evidence["source_sha256"] == DIGEST
    assert evidence["revision"] == HeronDetector.default_revision
    assert evidence["threshold"] == 0.5
    assert DetectionResult.model_validate(evidence) == result.detect(page())


def test_nonpositive_input_frame_rejected():
    bad = page().model_dump()
    bad["page_bbox"] = {"x0": 10, "y0": 20, "x1": 10, "y1": 120}
    with pytest.raises(ValidationError, match="positive page frame"):
        DetectionInput.model_validate(bad)


def test_extractor_crop_frame_convenience():
    raster = page().raster
    assert DetectionInput.from_raster(DIGEST, 1, raster).page_bbox == BBox(
        x0=0, y0=0, x1=100, y1=100
    )


def evidence(regions):
    result = HeronDetector(device="cpu")
    result._infer = lambda render, device: regions
    return result.detect(page())


def detection_region(identifier, *, bbox=None, score=0.8, label=9):
    return DetectorRegion(
        id=identifier,
        type="main_text" if label == 9 else "figure",
        bbox=bbox or BBox(x0=0, y0=0, x1=100, y1=100),
        raw_label="text" if label == 9 else "picture",
        label_id=label,
        confidence=score,
        emission_index=0,
    )


def test_tolerant_comparison_ignores_emission_order_and_small_device_variation():
    from book_core.detection.comparison import compare

    left = detection_region("left", bbox=BBox(x0=0, y0=0, x1=40, y1=50))
    right = detection_region("right", bbox=BBox(x0=60, y0=0, x1=100, y1=50))
    changed_right = right.model_copy(
        update={"id": "new-right", "bbox": BBox(x0=60.1, y0=0, x1=100.1, y1=50), "confidence": 0.81}
    )
    comparison = compare(evidence([left, right]), evidence([changed_right, left]))
    assert comparison.passed
    assert len(comparison.matches) == 2
    assert comparison.matches[1].iou < 1


def test_tolerant_comparison_flags_high_confidence_loss_and_changed_type():
    from book_core.detection.comparison import compare

    region = detection_region("retained")
    comparison = compare(evidence([region]), evidence([]))
    assert not comparison.passed
    assert comparison.expected_only == ["retained"]
    changed = detection_region("figure", label=6)
    comparison = compare(evidence([region]), evidence([changed]))
    assert not comparison.passed
    assert comparison.actual_only == ["figure"]


def test_tolerant_comparison_reports_threshold_edge_without_failing():
    from book_core.detection.comparison import compare

    edge = detection_region("edge", score=0.51)
    comparison = compare(evidence([edge]), evidence([]))
    assert comparison.passed
    assert comparison.boundary_expected_only == ["edge"]
    assert not comparison.expected_only


def test_tolerant_comparison_uses_maximum_cardinality_instead_of_greedy():
    from book_core.detection.comparison import DetectionTolerance, compare

    # A overlaps both candidates, while B can only match C; greedy A->C loses a match.
    a = detection_region("A", bbox=BBox(x0=1, y0=0, x1=11, y1=10))
    b = detection_region("B", bbox=BBox(x0=0, y0=0, x1=10, y1=10))
    c = detection_region("C", bbox=BBox(x0=0.5, y0=0, x1=10.5, y1=10))
    d = detection_region("D", bbox=BBox(x0=1.5, y0=0, x1=11.5, y1=10))
    comparison = compare(evidence([a, b]), evidence([c, d]), DetectionTolerance(minimum_iou=0.85))
    assert comparison.passed
    assert {(m.expected_id, m.actual_id) for m in comparison.matches} == {("A", "D"), ("B", "C")}


def test_tolerant_comparison_rejects_different_model_revision():
    from book_core.detection.comparison import compare

    base = evidence([])
    with pytest.raises(ValueError, match="same page, model"):
        compare(base, base.model_copy(update={"revision": "b" * 40}))
