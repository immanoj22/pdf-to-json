"""Typed layout proposals: visual lines, bands, lanes and regions. No reading order."""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import (
    BBox,
    Confidence,
    CoreModel,
    Digest,
    Finite,
    Identifier,
    Provenance,
    TextDirection,
)

WritingMode = Literal["horizontal", "vertical"]
LaneKind = Literal[
    "column", "sidebar", "figure", "callout", "table", "card", "caption", "margin", "unknown"
]
RegionType = Literal[
    "title_candidate",
    "heading_candidate",
    "main_text",
    "sidebar",
    "callout",
    "figure",
    "caption_candidate",
    "table_candidate",
    "footnote_candidate",
    "header_footer_candidate",
    "page_number_candidate",
    "credit_candidate",
    "artifact_candidate",
    "unknown",
]
BlockKind = Literal["figure", "callout", "table", "banner", "rule"]
Feature = float | int | str | bool | None


class VisualLine(CoreModel):
    """Spans sharing one baseline. Span IDs keep native order; text stays in the span store."""

    id: Identifier
    span_ids: list[Identifier] = Field(min_length=1)
    source_line_ids: list[Identifier] = Field(min_length=1)
    bbox: BBox
    baseline_start: tuple[Finite, Finite]
    baseline_end: tuple[Finite, Finite]
    direction: tuple[Finite, Finite]
    rotation: Finite
    writing_mode: WritingMode
    text_direction: TextDirection | None = None
    font_size: Finite
    visible: bool
    inside_content: bool
    blank: bool = False
    reasons: list[str] = Field(default_factory=list)

    @property
    def horizontal(self) -> bool:
        return self.writing_mode == "horizontal" and (self.rotation < 1.0 or self.rotation > 359.0)


class VisualBlock(CoreModel):
    """Non-text evidence that shapes layout: figures, callouts, tables, banners and rules."""

    id: Identifier
    kind: BlockKind
    bbox: BBox
    object_ids: list[Identifier] = Field(default_factory=list)
    line_ids: list[Identifier] = Field(default_factory=list)
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    features: dict[str, Feature] = Field(default_factory=dict)


class Scope(CoreModel):
    """The page content frame or the interior of a callout, analysed independently."""

    id: Identifier
    kind: Literal["page", "callout"]
    bbox: BBox
    parent_id: Identifier | None = None
    block_id: Identifier | None = None


class Gutter(CoreModel):
    x0: Finite
    x1: Finite
    y0: Finite
    y1: Finite
    inset_block_ids: list[Identifier] = Field(default_factory=list)
    rule_object_ids: list[Identifier] = Field(default_factory=list)
    left_items: int
    right_items: int
    ink_fraction: Confidence
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)


class Lane(CoreModel):
    index: int
    x0: Finite
    x1: Finite
    kind: LaneKind
    line_count: int
    block_ids: list[Identifier] = Field(default_factory=list)
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)


class Band(CoreModel):
    id: Identifier
    scope_id: Identifier
    bbox: BBox
    gutters: list[Gutter] = Field(default_factory=list)
    lanes: list[Lane] = Field(min_length=1)
    column_count: int
    inset_block_ids: list[Identifier] = Field(default_factory=list)
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    review_required: bool = False

    @model_validator(mode="after")
    def columns_are_column_lanes(self):
        if self.column_count != sum(lane.kind == "column" for lane in self.lanes):
            raise ValueError("Column count must equal the number of column lanes")
        if len(self.gutters) + 1 != len(self.lanes):
            raise ValueError("Lanes must be separated by exactly the band gutters")
        return self


class Region(CoreModel):
    """A typed proposal. Lines are direct members of exactly one region on the page."""

    id: Identifier
    type: RegionType
    bbox: BBox
    scope_id: Identifier
    band_id: Identifier | None = None
    lane_index: int | None = None
    line_ids: list[Identifier] = Field(default_factory=list)
    object_ids: list[Identifier] = Field(default_factory=list)
    child_region_ids: list[Identifier] = Field(default_factory=list)
    proposed_type: RegionType | None = None
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    evidence: dict[str, Feature] = Field(default_factory=dict)
    review_required: bool = False

    @model_validator(mode="after")
    def unknown_is_reviewed(self):
        if self.type == "unknown" and not self.review_required:
            raise ValueError("Unknown regions must remain under review")
        return self


class ReviewFlag(CoreModel):
    subject_id: Identifier
    subject_kind: Literal["visual_object", "line", "band", "region"]
    reason: str
    blocking: Literal[False] = False


class PageLayout(CoreModel):
    source_sha256: Digest
    page: int
    layout_version: str
    content_bbox: BBox
    lines: list[VisualLine]
    blocks: list[VisualBlock] = Field(default_factory=list)
    scopes: list[Scope] = Field(min_length=1)
    bands: list[Band] = Field(default_factory=list)
    regions: list[Region] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode="after")
    def references(self):
        line_ids = [line.id for line in self.lines]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("Duplicate visual line")
        scopes = {scope.id for scope in self.scopes}
        bands = {band.id for band in self.bands}
        regions = {region.id: region for region in self.regions}
        if len(regions) != len(self.regions):
            seen, repeated = set(), []
            for region in self.regions:
                if region.id in seen:
                    repeated.append(f"{region.id[:12]}:{region.type}")
                seen.add(region.id)
            raise ValueError(f"Duplicate region {repeated}")
        owned = [line for region in self.regions for line in region.line_ids]
        if sorted(owned) != sorted(line_ids):
            raise ValueError("Every visual line must be a direct member of exactly one region")
        for band in self.bands:
            if band.scope_id not in scopes:
                raise ValueError("Band references an unknown scope")
        for region in self.regions:
            if region.scope_id not in scopes:
                raise ValueError("Region references an unknown scope")
            if region.band_id is not None and region.band_id not in bands:
                raise ValueError("Region references an unknown band")
            if any(child not in regions for child in region.child_region_ids):
                raise ValueError("Region references an unknown child")
        return self
