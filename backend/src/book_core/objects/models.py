"""Typed page evidence and roles, separate from semantic document nodes."""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import BBox, Confidence, CoreModel, Finite, Identifier, Provenance
from book_core.model.spans import ExtractedPage

ObjectKind = Literal[
    "text",
    "text_render",
    "image",
    "shading",
    "drawing",
    "clip",
    "group",
    "compound",
    "unmatched_paint",
]
AssetRole = Literal[
    "background",
    "container",
    "figure_part",
    "decorative",
    "scan_layer",
    "repeated_artifact",
    "content_image",
    "unknown",
]
RelationKind = Literal["drawn_above", "contains", "overlaps", "touches", "member_of"]


class PathItem(CoreModel):
    operator: str
    coordinates: list[float]
    orientation: int | None = None


class RenderGlyph(CoreModel):
    unicode: int
    glyph_id: int
    origin: tuple[float, float]
    bbox: BBox | None


class TextRenderInfo(CoreModel):
    seqno: int
    render_type: int
    opacity: float | None = None
    font: str
    size: float
    color: list[float]
    direction: tuple[float, float]
    writing_mode: int
    bidi_level: int | None = None
    layer: str | None = None
    glyphs: list[RenderGlyph] = Field(default_factory=list)


class PaintCommand(CoreModel):
    raw_bbox: list[float] = Field(default_factory=list)
    seqno: int
    operation: str
    bbox: BBox | None
    layer: str | None = None


class PageObject(CoreModel):
    id: Identifier
    kind: ObjectKind
    bbox: BBox | None
    native_bbox: BBox | None = None
    source_page: int
    source_spans: list[Identifier] = Field(default_factory=list)
    paint_sequences: list[int] = Field(default_factory=list)
    paint_run: int | None = None
    native_seqno: int | None = None
    opacity: float | None = None
    fill_opacity: float | None = None
    stroke_opacity: float | None = None
    fill: list[float] | None = None
    stroke: list[float] | None = None
    stroke_width: float | None = None
    path_items: list[PathItem] = Field(default_factory=list)
    clip_ids: list[Identifier] = Field(default_factory=list)
    clip_status: Literal["native_scissor", "unavailable", "context"] = "unavailable"
    blend_mode: str | None = None
    native_level: int | None = None
    image_digest: str | None = None
    image_xref: int | None = None
    image_transform: list[float] | None = None
    image_width: int | None = None
    image_height: int | None = None
    image_has_mask: bool | None = None
    render_info: list[TextRenderInfo] = Field(default_factory=list)
    evidence_notes: list[str] = Field(default_factory=list)
    provenance: Provenance

    @property
    def is_text(self) -> bool:
        return self.kind in {"text", "text_render"}


class CompoundVisual(PageObject):
    kind: Literal["compound"] = "compound"
    member_ids: list[Identifier]
    consolidation_reason: str = "Adjacent native primitives in the same uninterrupted paint run"


class SpanGeometry(CoreModel):
    """Native baseline evidence for one stored span; never a reading-order claim."""

    origin: tuple[Finite, Finite]
    direction: tuple[Finite, Finite]
    writing_mode: Literal["horizontal", "vertical"]
    ascender: Finite
    descender: Finite


class NativeObjectPage(CoreModel):
    page: ExtractedPage
    objects: list[PageObject]
    paint_commands: list[PaintCommand]
    span_geometry: dict[str, SpanGeometry] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_integrity(self):
        ids = [obj.id for obj in self.objects]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate native object ID")
        if {obj.id for obj in self.objects if obj.kind == "text"} != set(self.page.store.spans):
            raise ValueError("Every stored text span must have exactly one object")
        if self.span_geometry and set(self.span_geometry) != set(self.page.store.spans):
            raise ValueError("Span geometry must describe exactly the stored spans")
        if any(obj.source_page != self.page.geometry.page for obj in self.objects):
            raise ValueError("Mixed native object pages")
        return self


class ObjectRelation(CoreModel):
    source: Identifier
    target: Identifier
    kinds: list[RelationKind]


class RoleDecision(CoreModel):
    object_id: Identifier
    role: AssetRole
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    review_required: bool = False
    features: dict[str, float | int | str | bool | None] = Field(default_factory=dict)


class AssetLedger(CoreModel):
    records: list[RoleDecision]


class ObjectAnalysis(CoreModel):
    native: NativeObjectPage
    compounds: list[CompoundVisual] = Field(default_factory=list)
    relations: list[ObjectRelation] = Field(default_factory=list)
    asset_ledger: AssetLedger
    graph_complete: bool = True
    diagnostics: list[str] = Field(default_factory=list)
    candidate_pairs_checked: int = 0
    analysis_version: str = "1"

    def all_objects(self) -> list[PageObject]:
        return [*self.native.objects, *self.compounds]


class RepetitionRecord(CoreModel):
    page_numbers: list[int]
    stable_placement: bool


class ImageRepetition(CoreModel):
    source_sha256: str
    page_count: int
    images: dict[str, RepetitionRecord] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)
