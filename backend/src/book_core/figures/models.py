"""Neutral figure records: one per figure region, over Step 4 regions and Step 11 units.

A figure references its regions, native objects, units and lines by id; no source text is
copied. Captions, credits and figure-internal text stay units of the page (every line is in
exactly one unit); the figure lists their ids with the rule that linked them. The exported
image is named by the configured pattern; the alt-text slot is empty and needs review unless
a human supplies text. A model draft is never verified. Confidence is a rule heuristic, not
a calibrated probability.
"""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import BBox, Confidence, CoreModel, Digest, Identifier, Provenance

Feature = float | int | str | bool | None
FigureKind = Literal["photo", "drawing"]
ImageFormat = Literal["jpg", "png"]
SourceType = Literal["raster", "vector", "mixed"]
LabelSource = Literal["printed", "metadata", "inferred", "none"]
AltStatus = Literal["needs_review", "verified"]
AltSource = Literal["none", "model_draft", "human"]


class AltText(CoreModel):
    """Image description slot. Empty by default; drafts are English and always reviewed."""

    text: str = ""
    status: AltStatus = "needs_review"
    source: AltSource = "none"
    language: str | None = None
    model: str | None = None  # model id and immutable revision of a draft

    @model_validator(mode="after")
    def drafts_are_reviewed(self):
        if self.source == "model_draft" and self.status != "needs_review":
            raise ValueError("A model draft is never verified")
        if self.source == "none" and (self.text or self.status != "needs_review"):
            raise ValueError("An empty slot has no text and needs review")
        if self.status == "verified" and self.source != "human":
            raise ValueError("Only a human description is verified")
        return self


class FigureAnchor(CoreModel):
    """Where the figure is read: its float stream's anchor in the page's main flow."""

    stream_id: Identifier
    after_line_id: Identifier | None = None
    position: int = Field(ge=-1)
    order: int = Field(ge=0)
    reading_index: int = Field(ge=1)  # 1-based position among the page's figures


class Link(CoreModel):
    """A caption, credit or internal-text unit linked to the figure, with its rule."""

    unit_id: Identifier
    line_ids: list[Identifier] = Field(min_length=1)
    rule: str
    confidence: Confidence
    review_required: bool = False


class ImageEvidence(CoreModel):
    """Measured crop statistics behind the photo/drawing and JPG/PNG decision."""

    source_type: SourceType
    raster_share: Confidence
    vector_objects: int = Field(ge=0)
    raster_objects: int = Field(ge=0)
    colour_count_ratio: Confidence  # distinct quantized colours per pixel
    dominant_colour_share: Confidence  # pixels in the 16 most frequent quantized colours
    dominant_tone_share: Confidence  # pixels in the 16 most frequent 8-bit grey levels
    flat_share: Confidence  # pixels whose neighbourhood has no visible gradient
    decision_rule: str


class ExportedImage(CoreModel):
    file_name: str
    format: ImageFormat
    dpi: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    sha256: Digest
    bytes: int = Field(gt=0)


class FigureRecord(CoreModel):
    id: Identifier
    page: int = Field(ge=1)
    pages: list[int] = Field(min_length=1)  # a spread lists both pages; the first names it
    region_ids: list[Identifier] = Field(min_length=1)
    block_ids: list[Identifier] = Field(default_factory=list)
    object_ids: list[Identifier] = Field(default_factory=list)
    bbox: BBox
    content_area_share: Confidence  # figure box / content box
    small_artwork: bool = False  # below the client-profile small-figure share
    page_label: str | None = None
    label_source: LabelSource = "none"
    label_inferred: bool = False
    name: str
    kind: FigureKind
    kind_confidence: Confidence
    image: ExportedImage | None = None
    evidence: ImageEvidence
    captions: list[Link] = Field(default_factory=list)
    credits: list[Link] = Field(default_factory=list)
    internal_text: list[Link] = Field(default_factory=list)
    anchor: FigureAnchor
    alt_text: AltText = Field(default_factory=AltText)
    spread_partner_id: Identifier | None = None
    model_support: dict[str, bool] = Field(default_factory=dict)  # layout model -> finds it
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    review_flags: list[str] = Field(default_factory=list)

    @property
    def review_required(self) -> bool:
        return bool(self.review_flags) or self.alt_text.status == "needs_review"


class UnlinkedCaption(CoreModel):
    unit_id: Identifier
    line_ids: list[Identifier] = Field(min_length=1)
    reason: str


class PageCredit(CoreModel):
    """A credit or source line of the page. Whether it credits a picture or quoted text is not
    decidable from layout alone, so it is not linked to a figure; the figures its rule would
    link are kept as a proposal for review."""

    unit_id: Identifier
    line_ids: list[Identifier] = Field(min_length=1)
    proposed_figure_ids: list[Identifier] = Field(default_factory=list)
    rule: str
    confidence: Confidence  # of the proposal (the proposing rule's), not of a link
    reason: str
    review_required: Literal[True] = True


class PageFigures(CoreModel):
    source_sha256: Digest
    page: int = Field(ge=1)
    figures_version: str
    figures: list[FigureRecord] = Field(default_factory=list)
    unlinked_captions: list[UnlinkedCaption] = Field(default_factory=list)
    page_credits: list[PageCredit] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance

    @model_validator(mode="after")
    def units_once(self):
        ids = [f.id for f in self.figures]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate figure id")
        owned = [link.unit_id for f in self.figures for link in (*f.captions, *f.internal_text)]
        if len(owned) != len(set(owned)):
            raise ValueError("A caption or label unit is linked to more than one figure")
        credits = set()
        for f in self.figures:
            ids = [link.unit_id for link in f.credits]
            if len(ids) != len(set(ids)):
                raise ValueError("A credit unit is linked twice to one figure")
            credits.update(ids)
        if credits & set(owned):
            raise ValueError("A credit unit cannot also be a caption or label")
        if {c.unit_id for c in self.unlinked_captions} & (set(owned) | credits):
            raise ValueError("An unlinked caption cannot also be linked")
        page_credits = [c.unit_id for c in self.page_credits]
        if len(page_credits) != len(set(page_credits)) or set(page_credits) & (
            set(owned) | credits
        ):
            raise ValueError("A page credit is listed once and is not also linked")
        if sorted(f.anchor.reading_index for f in self.figures if f.page == self.page) != list(
            range(1, sum(f.page == self.page for f in self.figures) + 1)
        ):
            raise ValueError("Figure reading indexes must number the page's figures")
        return self


class Spread(CoreModel):
    figure_ids: list[Identifier] = Field(min_length=2, max_length=2)
    pages: list[int] = Field(min_length=2, max_length=2)
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    evidence: dict[str, Feature] = Field(default_factory=dict)


class BookFigures(CoreModel):
    source_sha256: Digest
    figures_version: str
    pages: int
    spreads: list[Spread] = Field(default_factory=list)
    names: dict[str, Identifier] = Field(default_factory=dict)  # file stem -> figure id
    profile: dict[str, Feature | list | dict] = Field(default_factory=dict)
    config: dict[str, Feature | list | dict] = Field(default_factory=dict)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance
