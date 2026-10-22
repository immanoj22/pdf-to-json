"""Conservative OCR eligibility from immutable native extraction evidence.

This is a screen, not a claim that valid Unicode matches the printed glyphs.  The latter
needs an independent render comparison.  Isolated unknown glyphs (including mathematical
symbols and private-use bullets) never turn an otherwise usable digital page into a scan.
No source span, visibility decision, ownership or native ledger is modified here.
"""

import unicodedata
from collections.abc import Sequence
from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import BBox, CoreModel, Digest, Identifier
from book_core.objects.models import NativeObjectPage

VERSION = "ocr-eligibility-1"
Action = Literal["ocr", "compare_only", "review"]


class RenderTextCheck(CoreModel):
    """Independent visual evidence, never an OCR confidence or a Unicode heuristic.

    ``mismatch`` must be an adjudicated render comparison.  A reader disagreement alone
    is ``unresolved``: it cannot establish which reader is wrong.  References name saved
    render/comparison artifacts so the decision remains reviewable.
    """

    bbox: BBox
    outcome: Literal["matches", "mismatch", "unresolved", "no_text", "text_present"]
    method: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    native_span_ids: list[Identifier] = Field(default_factory=list)
    excluded_figure_boxes: list[BBox] = Field(default_factory=list)


class OcrRegionEligibility(CoreModel):
    bbox: BBox
    action: Action
    reasons: list[str] = Field(min_length=1)
    image_ids: list[Identifier] = Field(default_factory=list)
    native_span_ids: list[Identifier] = Field(default_factory=list)
    excluded_figure_boxes: list[BBox] = Field(default_factory=list)
    retain_native: Literal[True] = True


class OcrEligibility(CoreModel):
    source_sha256: Digest
    page: int = Field(gt=0)
    version: str = VERSION
    decision: Literal["native", "ocr", "compare_only", "review"]
    regions: list[OcrRegionEligibility] = Field(default_factory=list)
    native_characters: int = Field(ge=0)
    unusable_characters: int = Field(ge=0)
    unusable_span_ids: list[Identifier] = Field(default_factory=list)
    invisible_glyphs: int = Field(ge=0)
    missing_unicode_glyphs: int = Field(ge=0)
    raster_coverage: float = Field(ge=0, le=1)
    excluded_figure_image_ids: list[Identifier] = Field(default_factory=list)
    render_checks: list[RenderTextCheck] = Field(default_factory=list)
    unmeasured_checks: list[str] = Field(default_factory=list)
    native_retained: Literal[True] = True

    @model_validator(mode="after")
    def decision_matches_regions(self):
        actions = {r.action for r in self.regions}
        expected = next((a for a in ("ocr", "compare_only", "review") if a in actions), "native")
        if self.decision != expected:
            raise ValueError("OCR page decision must agree with its region actions")
        if self.unusable_characters > self.native_characters:
            raise ValueError("Unusable character count exceeds the source count")
        return self


def _area(box):
    return (box.x1 - box.x0) * (box.y1 - box.y0)


def _intersection(a, b):
    x0, y0 = max(a.x0, b.x0), max(a.y0, b.y0)
    x1, y1 = min(a.x1, b.x1), min(a.y1, b.y1)
    if x1 <= x0 or y1 <= y0:
        return None
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _union_area(boxes):
    """Exact rectangle union; overlapping rasters cannot inflate page coverage."""
    edges = sorted({x for b in boxes for x in (b.x0, b.x1)})
    area = 0.0
    for left, right in zip(edges, edges[1:], strict=False):
        intervals = sorted((b.y0, b.y1) for b in boxes if b.x0 < right and b.x1 > left)
        end, covered = float("-inf"), 0.0
        for start, stop in intervals:
            covered += max(0, stop - max(start, end))
            end = max(end, stop)
        area += (right - left) * covered
    return area


def _covers(outer, inner):
    overlap = _intersection(outer, inner)
    return overlap is not None and _area(overlap) / max(_area(inner), 1e-12) >= 0.90


def unusable_codepoint(codepoint: int) -> bool:
    """Language-independent missing mappings; combining and RTL controls stay valid."""
    if not 0 <= codepoint <= 0x10FFFF:
        return True
    character = chr(codepoint)
    return codepoint in {0, 0xFFFD} or unicodedata.category(character) in {"Co", "Cs"}


def detect_ocr_regions(
    native: NativeObjectPage,
    *,
    figure_boxes: Sequence[BBox] = (),
    render_checks: Sequence[RenderTextCheck] = (),
    large_raster_share: float = 0.70,
) -> OcrEligibility:
    """Screen a page without opening a source or invoking an OCR reader.

    The 70% screen reuses the existing scan-layer geometric screen.  It is not a learned
    confidence.  A large raster without text remains a *review candidate* until visual
    evidence identifies printed text: a full-page photo must never be silently OCRed.
    Small raster text and explicit figure boxes are excluded.  An invisible native layer
    over a large raster is compare-only, even if its Unicode is unusable.
    """
    if not 0 < large_raster_share <= 1:
        raise ValueError("Large raster share must be in (0, 1]")
    page = native.page
    frame = page.geometry.content_bbox
    if not _area(frame):
        raise ValueError("OCR requires a nonempty content frame")
    spans = [s for s in page.store.spans.values() if frame.contains_center(s.bbox)]
    source_ids = set(page.store.spans)
    for check in render_checks:
        if not set(check.native_span_ids) <= source_ids:
            raise ValueError("Render check names unknown native spans")
        if _intersection(check.bbox, frame) is None:
            raise ValueError("Render check does not intersect the content frame")
    figure_boxes = tuple(figure_boxes) + tuple(
        box for check in render_checks for box in check.excluded_figure_boxes
    )
    visible_characters = {s.id: [c for c in s.raw_text if not c.isspace()] for s in spans}
    characters = sum(len(chars) for chars in visible_characters.values())
    bad_counts = {
        sid: sum(unusable_codepoint(ord(c)) for c in chars)
        for sid, chars in visible_characters.items()
    }
    bad = sum(bad_counts.values())
    traces = {}
    for obj in native.objects:
        for info in obj.render_info:
            traces[info.seqno] = info  # one trace can be assigned to several span objects
    glyphs = [
        g for t in traces.values() for g in t.glyphs if g.bbox and frame.contains_center(g.bbox)
    ]
    invisible = [
        g
        for t in traces.values()
        if t.render_type == 3
        for g in t.glyphs
        if g.bbox and frame.contains_center(g.bbox)
    ]
    images, excluded = [], []
    for obj in native.objects:
        if obj.kind != "image" or obj.bbox is None:
            continue
        box = _intersection(obj.bbox, frame)
        if box is None:
            continue
        if any(_covers(figure, box) for figure in figure_boxes):
            excluded.append(obj.id)
        else:
            images.append((obj.id, box))
    coverage = min(1.0, _union_area([b for _, b in images]) / _area(frame))
    regions = []
    large_images = [
        (oid, box) for oid, box in images if _area(box) / _area(frame) >= large_raster_share
    ]
    # Tiled scans qualify as a page-size raster area without assuming one image per page.
    if not large_images and coverage >= large_raster_share:
        large_images = [(None, frame)]
    for oid, box in large_images:
        inside = [s for s in spans if box.contains_center(s.bbox)]
        count = sum(len(visible_characters[s.id]) for s in inside)
        invalid = sum(bad_counts[s.id] for s in inside)
        ignored = [g for g in invisible if box.contains_center(g.bbox)]
        reason = None
        action = "review"
        if ignored:
            action = "compare_only"
            reason = "invisible_native_text_over_large_raster_compare_never_replace"
        elif count == 0:
            reason = "large_raster_without_native_text_scan_or_figure_requires_visual_check"
        elif invalid == count:
            reason = "large_raster_without_usable_unicode_requires_visual_check"
        if reason:
            regions.append(
                OcrRegionEligibility(
                    bbox=box,
                    action=action,
                    reasons=[reason],
                    image_ids=[oid] if oid else [i for i, _ in images],
                    native_span_ids=[s.id for s in inside],
                    excluded_figure_boxes=[
                        f for f in figure_boxes if _intersection(f, box) is not None
                    ],
                )
            )
    if characters and bad == characters and not regions:
        regions.append(
            OcrRegionEligibility(
                bbox=frame,
                action="review",
                reasons=["native_text_has_no_usable_unicode_mapping"],
                native_span_ids=[s.id for s in spans],
            )
        )
    for check in render_checks:
        if any(_covers(figure, check.bbox) for figure in figure_boxes):
            continue
        if check.outcome in {"no_text", "matches"}:
            regions = [
                r for r in regions if r.action != "review" or not _covers(check.bbox, r.bbox)
            ]
        if check.outcome not in {"mismatch", "text_present"}:
            continue
        checked_spans = [s for s in spans if check.bbox.contains_center(s.bbox)]
        if check.outcome == "text_present" and any(
            bad_counts[s.id] < len(visible_characters[s.id]) for s in checked_spans
        ):
            # Visual text presence is not evidence that usable native text is wrong.
            continue
        regions = [r for r in regions if r.action != "review" or not _covers(check.bbox, r.bbox)]
        compare = any(check.bbox.contains_center(g.bbox) for g in invisible)
        regions.append(
            OcrRegionEligibility(
                bbox=check.bbox,
                action="compare_only" if compare else "ocr",
                reasons=[
                    "adjudicated_render_text_mismatch"
                    if check.outcome == "mismatch"
                    else "adjudicated_raster_text_without_usable_native_text"
                ],
                native_span_ids=list(
                    dict.fromkeys([*check.native_span_ids, *(s.id for s in checked_spans)])
                ),
                excluded_figure_boxes=[
                    f for f in figure_boxes if _intersection(f, check.bbox) is not None
                ],
            )
        )
    checked_boxes = [
        c.bbox for c in render_checks if c.outcome in {"matches", "mismatch", "no_text"}
    ]
    unchecked = [s for s in spans if not any(b.contains_center(s.bbox) for b in checked_boxes)]
    unmeasured = []
    if unchecked:
        unmeasured.append("native_unicode_vs_render_not_independently_verified_for_all_spans")
    if any(r.action == "review" and r.image_ids for r in regions):
        unmeasured.append("raster_text_vs_figure_content_not_visually_adjudicated")
    actions = {r.action for r in regions}
    decision = next((a for a in ("ocr", "compare_only", "review") if a in actions), "native")
    return OcrEligibility(
        source_sha256=page.source_sha256,
        page=page.geometry.page,
        decision=decision,
        regions=regions,
        native_characters=characters,
        unusable_characters=bad,
        unusable_span_ids=[sid for sid, count in bad_counts.items() if count],
        invisible_glyphs=len(invisible),
        missing_unicode_glyphs=sum(unusable_codepoint(g.unicode) for g in glyphs),
        raster_coverage=coverage,
        excluded_figure_image_ids=excluded,
        render_checks=list(render_checks),
        unmeasured_checks=unmeasured,
    )
