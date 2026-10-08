"""Tolerance-based detector repeat/device gates; emission order is immaterial."""

from pydantic import Field, computed_field

from book_core.detection.models import DetectionResult
from book_core.model.common import Confidence, CoreModel


class DetectionTolerance(CoreModel):
    minimum_iou: Confidence = 0.95
    maximum_score_delta: Confidence = 0.02
    threshold_boundary_margin: Confidence = 0.02


class RegionMatch(CoreModel):
    expected_id: str
    actual_id: str
    iou: Confidence
    score_delta: Confidence


class DetectionComparison(CoreModel):
    tolerance: DetectionTolerance
    matches: list[RegionMatch] = Field(default_factory=list)
    expected_only: list[str] = Field(default_factory=list)
    actual_only: list[str] = Field(default_factory=list)
    boundary_expected_only: list[str] = Field(default_factory=list)
    boundary_actual_only: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def passed(self) -> bool:
        return not self.expected_only and not self.actual_only


def iou(a, b):
    area_a = (a.x1 - a.x0) * (a.y1 - a.y0)
    area_b = (b.x1 - b.x0) * (b.y1 - b.y0)
    intersection = max(0, min(a.x1, b.x1) - max(a.x0, b.x0)) * max(
        0, min(a.y1, b.y1) - max(a.y0, b.y0)
    )
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def compare(
    expected: DetectionResult,
    actual: DetectionResult,
    tolerance: DetectionTolerance | None = None,
) -> DetectionComparison:
    """Maximum-cardinality compatible matching, with explicit threshold-edge allowance.

    This comparison permits small device/numeric variation in boxes and probabilities.
    It never compares emission positions or text. Unmatched regions whose confidence
    lies within the configured margin above the threshold are reported separately and
    tolerated; other unmatched regions fail. Different jobs/models/revisions/thresholds
    cannot be compared as repeats.
    """
    import networkx as nx

    identity = ("source_sha256", "page", "detector", "repo_id", "revision", "threshold")
    if any(getattr(expected, field) != getattr(actual, field) for field in identity):
        raise ValueError(
            "Detector comparisons require the same page, model, revision and threshold"
        )
    tolerance = tolerance or DetectionTolerance()
    graph = nx.Graph()
    metrics = {}
    for i, region_a in enumerate(expected.regions):
        for j, region_b in enumerate(actual.regions):
            if (
                region_a.label_id != region_b.label_id
                or region_a.raw_label != region_b.raw_label
                or region_a.type != region_b.type
            ):
                continue
            overlap = iou(region_a.bbox, region_b.bbox)
            delta = abs(region_a.confidence - region_b.confidence)
            if overlap >= tolerance.minimum_iou and delta <= tolerance.maximum_score_delta:
                graph.add_edge(("expected", i), ("actual", j), weight=overlap - delta)
                metrics[i, j] = overlap, delta
    chosen = nx.max_weight_matching(graph, maxcardinality=True)
    pairs = []
    for first, second in chosen:
        if first[0] == "actual":
            first, second = second, first
        pairs.append((first[1], second[1]))
    pairs.sort()  # Stable diagnostics only; this is not spatial or semantic order.
    matches = [
        RegionMatch(
            expected_id=expected.regions[i].id,
            actual_id=actual.regions[j].id,
            iou=metrics[i, j][0],
            score_delta=metrics[i, j][1],
        )
        for i, j in pairs
    ]
    matched_expected, matched_actual = {i for i, _ in pairs}, {j for _, j in pairs}
    required, boundary = [], []
    for result, matched in ((expected, matched_expected), (actual, matched_actual)):
        missing, near_threshold = [], []
        for i, region in enumerate(result.regions):
            if i in matched:
                continue
            if region.confidence <= result.threshold + tolerance.threshold_boundary_margin:
                near_threshold.append(region.id)
            else:
                missing.append(region.id)
        required.append(missing)
        boundary.append(near_threshold)
    return DetectionComparison(
        tolerance=tolerance,
        matches=matches,
        expected_only=required[0],
        actual_only=required[1],
        boundary_expected_only=boundary[0],
        boundary_actual_only=boundary[1],
    )
