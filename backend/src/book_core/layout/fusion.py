"""Learned regions are corroborating evidence, never layout or text ownership.

The original geometry, types, memberships and structure are protected. Detector
regions live beside the copied own layout, including disagreements and fragments.
Only confidence and review annotations on own regions may change. Text retention
is outside this module: no ledger, span store or model reading order is accepted.
"""

from collections.abc import Iterable
from typing import Literal

from pydantic import Field
from shapely.geometry import box
from shapely.ops import unary_union

from book_core.detection.models import DetectionResult, DetectorRegion
from book_core.layout.models import PageLayout, Region, RegionType, ReviewFlag
from book_core.model.common import BBox, Confidence, CoreModel, Identifier

ComparisonStatus = Literal[
    "agreement",
    "type_disagreement",
    "geometry_disagreement",
    "own_only",
    "model_only",
    "fragmented_figure",
]

# Models do not all distinguish page titles from section headings, or folios from
# running furniture. These two coarse pairs are compatible; other types are exact.
COMPATIBLE_TYPES = (
    frozenset({"title_candidate", "heading_candidate"}),
    frozenset({"header_footer_candidate", "page_number_candidate"}),
)


class FusionComparison(CoreModel):
    detector: str
    own_region_ids: list[Identifier] = Field(default_factory=list)
    model_region_ids: list[Identifier] = Field(default_factory=list)
    status: ComparisonStatus
    iou: Confidence = 0.0
    type_compatible: bool = False
    reason: str
    review_required: bool


class FusionResult(CoreModel):
    """Both sources retained; ``layout`` has annotation changes only."""

    layout: PageLayout
    detections: list[DetectionResult]
    comparisons: list[FusionComparison]
    iou_threshold: Confidence
    agreement_gain: Confidence
    invariants_checked: bool = False

    @property
    def disagreements(self) -> list[FusionComparison]:
        return [item for item in self.comparisons if item.review_required]


def type_compatible(own: RegionType, model: RegionType) -> bool:
    """Unknown proposals cannot corroborate a type, even another unknown."""
    if "unknown" in {own, model}:
        return False
    return own == model or any({own, model} <= family for family in COMPATIBLE_TYPES)


def bbox_iou(a: BBox, b: BBox) -> float:
    """Dimensionless box IoU. Degenerate regions provide no overlap evidence."""
    intersection = _intersection(a, b)
    union = _area(a) + _area(b) - intersection
    return intersection / union if union > 0 else 0.0


def _area(bbox: BBox) -> float:
    return (bbox.x1 - bbox.x0) * (bbox.y1 - bbox.y0)


def _intersection(a: BBox, b: BBox) -> float:
    return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0)) * max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))


def _fragments(own: Region, candidates: list[DetectorRegion], threshold: float):
    """Several mostly-contained figure boxes may describe one composite figure.

    This is a review disagreement, not permission to split the own figure. Union
    coverage avoids double-counting duplicate or overlapping model boxes.
    """
    if own.type != "figure":
        return [], 0.0
    fragments = [
        item
        for item in candidates
        if item.type == "figure"
        and 0 < _area(item.bbox) < _area(own.bbox)
        and _intersection(own.bbox, item.bbox) / _area(item.bbox) >= threshold
    ]
    if len(fragments) < 2:
        return [], 0.0
    combined = unary_union(
        [box(item.bbox.x0, item.bbox.y0, item.bbox.x1, item.bbox.y1) for item in fragments]
    )
    own_box = box(own.bbox.x0, own.bbox.y0, own.bbox.x1, own.bbox.y1)
    union_area = own_box.union(combined).area
    overlap = own_box.intersection(combined).area / union_area if union_area > 0 else 0.0
    return (fragments, overlap) if overlap >= threshold else ([], 0.0)


def _compare(layout: PageLayout, result: DetectionResult, threshold: float):
    own = {item.id: item for item in layout.regions}
    models = {item.id: item for item in result.regions}
    comparisons = []
    linked_own, linked_model = set(), set()

    def add(own_ids, model_ids, status, iou, compatible, reason):
        comparisons.append(
            FusionComparison(
                detector=result.detector,
                own_region_ids=own_ids,
                model_region_ids=model_ids,
                status=status,
                iou=iou,
                type_compatible=compatible,
                reason=reason,
                review_required=status != "agreement",
            )
        )
        linked_own.update(own_ids)
        linked_model.update(model_ids)

    # Fragmentation is kept visible even when two halves individually reach IoU .5.
    # It is not independent corroboration of the own region's complete extent.
    for item in own.values():
        fragments, iou = _fragments(
            item, [model for model in models.values() if model.id not in linked_model], threshold
        )
        if fragments:
            add(
                [item.id],
                [model.id for model in fragments],
                "fragmented_figure",
                iou,
                True,
                "Model splits a composite figure; single own figure and all model boxes retained",
            )

    scores = [(bbox_iou(a.bbox, b.bbox), a.id, b.id) for a in own.values() for b in models.values()]
    fragmented_own, fragmented_model = set(linked_own), set(linked_model)
    for iou, aid, bid in scores:
        if iou < threshold or iou == 0 or aid in fragmented_own or bid in fragmented_model:
            continue
        compatible = type_compatible(own[aid].type, models[bid].type)
        model_box, content = models[bid].bbox, layout.content_bbox
        outside_frame = own[aid].type == "figure" and (
            model_box.x0 < content.x0
            or model_box.y0 < content.y0
            or model_box.x1 > content.x1
            or model_box.y1 > content.y1
        )
        if outside_frame:
            status = "geometry_disagreement"
            reason = "Model figure geometry leaves content frame; own geometry retained (I4)"
        elif compatible:
            status = "agreement"
            reason = "Compatible type and box overlap; own geometry and type retained"
        else:
            status = "type_disagreement"
            reason = f"Own {own[aid].type} vs model {models[bid].type}; both sources retained"
        add([aid], [bid], status, iou, compatible, reason)

    # Below-threshold overlaps are geometry disagreements. Greedy pairing by IoU
    # makes diagnostics deterministic without imposing coordinate/text order.
    for iou, aid, bid in sorted(scores, key=lambda item: (-item[0], item[1], item[2])):
        if iou <= 0 or aid in linked_own or bid in linked_model:
            continue
        compatible = type_compatible(own[aid].type, models[bid].type)
        add(
            [aid],
            [bid],
            "geometry_disagreement",
            iou,
            compatible,
            f"Box IoU below {threshold:g}; own geometry retained"
            + ("; types also disagree" if not compatible else ""),
        )
    for aid in sorted(own.keys() - linked_own):
        add([aid], [], "own_only", 0.0, False, "No corresponding model region; own region retained")
    for bid in sorted(models.keys() - linked_model):
        add(
            [],
            [bid],
            "model_only",
            0.0,
            False,
            "No corresponding own region; model evidence retained",
        )
    return comparisons


def _protected(layout: PageLayout):
    """Only annotation fields are excluded from the exact protection gate."""
    data = layout.model_dump(mode="json")
    data.pop("review_flags")
    for region in data["regions"]:
        for field in ("confidence", "reasons", "evidence", "review_required"):
            region.pop(field)
    return data


def fuse_regions(
    layout: PageLayout,
    detections: Iterable[DetectionResult],
    *,
    iou_threshold: float = 0.5,
    agreement_gain: float = 0.1,
    analysis=None,
) -> FusionResult:
    """Attach independent model evidence, keeping all own protected fields exact.

    Confidence rises once per agreeing detector, bounded by its confidence and IoU.
    The gain is an explicit heuristic, not a calibrated probability. Disagreement
    never lowers existing confidence, deletes a region or transfers text. Optional
    ``analysis`` is used only by the existing read-only I1-I7 checker.
    """
    if not 0 < iou_threshold <= 1:
        raise ValueError("iou_threshold must be in (0, 1]")
    if not 0 <= agreement_gain <= 1:
        raise ValueError("agreement_gain must be in [0, 1]")
    sources = list(detections)
    for result in sources:
        if result.source_sha256 != layout.source_sha256 or result.page != layout.page:
            raise ValueError("Detector evidence belongs to another source or page")
    if len({result.detector for result in sources}) != len(sources):
        raise ValueError("At most one result per detector is allowed")
    comparisons = [item for result in sources for item in _compare(layout, result, iou_threshold)]
    lookup = {
        (result.detector, region.id): region for result in sources for region in result.regions
    }
    by_own = {}
    for item in comparisons:
        for rid in item.own_region_ids:
            by_own.setdefault(rid, []).append(item)
    regions, flags = [], list(layout.review_flags)
    for region in layout.regions:
        evidence = by_own.get(region.id, [])
        if not evidence:
            regions.append(region.model_copy(deep=True))
            continue
        support = {}
        disagreements = [item for item in evidence if item.review_required]
        for item in evidence:
            if item.status == "agreement":
                strength = item.iou * max(
                    lookup[(item.detector, rid)].confidence for rid in item.model_region_ids
                )
                support[item.detector] = max(support.get(item.detector, 0.0), strength)
        confidence = region.confidence
        for detector in sorted(support):
            confidence += (1.0 - confidence) * agreement_gain * support[detector]
        annotations = {
            **region.evidence,
            "model_agreements": len(support),
            "model_disagreements": len(disagreements),
            "fusion_iou_threshold": iou_threshold,
        }
        reasons = list(region.reasons)
        if support:
            reasons.append("Compatible learned evidence: " + ", ".join(sorted(support)))
        if disagreements:
            reasons.append("Learned region disagreement; own geometry and type retained for review")
            flags.append(
                ReviewFlag(subject_id=region.id, subject_kind="region", reason=reasons[-1])
            )
        regions.append(
            region.model_copy(
                deep=True,
                update={
                    "confidence": confidence,
                    "evidence": annotations,
                    "reasons": reasons,
                    "review_required": region.review_required or bool(disagreements),
                },
            )
        )
    data = layout.model_dump()
    data.update(regions=regions, review_flags=flags)
    fused = PageLayout.model_validate(data)
    if _protected(fused) != _protected(layout):
        raise AssertionError("Fusion changed a protected own layout field")
    if analysis is not None:
        from book_core.layout.invariants import check

        if check(fused, analysis) != check(layout, analysis):
            raise AssertionError("Fusion changed I1-I7 invariant results")
    return FusionResult(
        layout=fused,
        detections=sources,
        comparisons=comparisons,
        iou_threshold=iou_threshold,
        agreement_gain=agreement_gain,
        invariants_checked=analysis is not None,
    )
