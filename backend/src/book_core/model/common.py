"""Shared schema-independent geometry, evidence and visual style."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Identifier = Annotated[str, Field(min_length=1)]
TextDirection = Literal["ltr", "rtl", "ttb"]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CoreModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BBox(CoreModel):
    x0: Finite
    y0: Finite
    x1: Finite
    y1: Finite

    @model_validator(mode="after")
    def ordered(self) -> "BBox":
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("Inverted geometry is not a visible bounding box")
        return self

    def contains_center(self, other: "BBox") -> bool:
        return (
            self.x0 <= (other.x0 + other.x1) / 2 <= self.x1
            and self.y0 <= (other.y0 + other.y1) / 2 <= self.y1
        )


class SpanRef(CoreModel):
    span_id: Identifier


class VisualStyle(CoreModel):
    font: str | None = None
    size: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    color: Annotated[int, Field(ge=0, le=0xFFFFFF)] | None = None
    flags: Annotated[int, Field(ge=0)] | None = None
    bold: bool | None = None
    italic: bool | None = None
    superscript: bool | None = None
    subscript: bool | None = None


class SemanticRole(StrEnum):
    UNKNOWN = "unknown"
    CHAPTER = "chapter"
    SECTION = "section"
    BODY_TEXT = "body_text"
    TERM = "term"
    DEFINITION = "definition"
    EMPHASIS = "emphasis"
    STRONG_EMPHASIS = "strong_emphasis"
    MARGINAL = "marginal"
    PRIMARY = "primary"
    SECONDARY = "secondary"


class Relationship(CoreModel):
    kind: Literal["continues", "caption_of", "note_for", "refers_to", "part_of", "precedes"]
    target_id: Identifier


class Provenance(CoreModel):
    source_sha256: Digest | None = None
    engine: str | None = None
    engine_version: str | None = None
    method: Literal["native", "ocr", "derived", "unknown"] = "unknown"
    notes: list[str] = Field(default_factory=list)


class ExternalDescription(CoreModel):
    """Required figure information supplied externally, never invented from source text."""

    text: str | None = None
    source: Literal["external"] = "external"
    required: Literal[True] = True
    review_required: bool = True

    @model_validator(mode="after")
    def unresolved_requires_review(self) -> "ExternalDescription":
        if not self.text or not self.text.strip():
            if not self.review_required:
                raise ValueError("A missing required external description must remain under review")
        return self
