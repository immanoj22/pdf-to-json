"""Equation MathML records (one per equation region) and the book's shape table.

A record holds the chosen MathML and LaTeX, every path's reading, the checks, the agreement
between paths, a confidence (a rule heuristic, not a calibrated probability), a review status
and what the default output uses. ``must_check`` equations keep their original text and
objects and carry an image fallback; their MathML (if any) is never presented as checked.
``sources`` traces each character of the chosen reading back to its evidence (a span
character ``span_id:offset`` or a drawn object id; None for a character a recognizer read).
"""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import Confidence, CoreModel, Digest, Identifier

PathName = Literal["text", "drawn", "image"]
ReviewStatus = Literal["paths_agree", "needs_review", "must_check"]
Output = Literal["text", "mathml", "mathml_parts", "image"]


class PathReading(CoreModel):
    path: PathName
    recognizer: str | None = None
    latex: str | None = None
    mathml: str | None = None
    problems: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    characters: int | None = None
    checks: dict[str, str | int | bool | None] = Field(default_factory=dict)


class FallbackImage(CoreModel):
    file_name: str
    dpi: int
    width: int
    height: int
    sha256: Digest
    bytes: int
    page_label: str | None = None
    label_source: str = "none"
    flags: list[str] = Field(default_factory=list)


class MathPart(CoreModel):
    """Reference style: the MathML of one drawn part of a mixed expression."""

    object_ids: list[Identifier] = Field(min_length=1)
    mathml: str
    latex: str


class EquationMath(CoreModel):
    equation_id: Identifier
    page: int = Field(gt=0)
    source: Literal["text", "vector", "image", "mixed"]
    presentation: Literal["inline", "display", "uncertain"]
    mathml: str | None = None
    latex: str | None = None
    path: PathName | None = None
    readings: list[PathReading] = Field(default_factory=list)
    agreement: Literal["agree", "disagree", "single", "none"]
    similarity: float | None = None
    confidence: Confidence
    review_status: ReviewStatus
    output: Output
    sources: list[str | None] = Field(default_factory=list)
    parts: list[MathPart] = Field(default_factory=list)
    fallback_image: FallbackImage | None = None
    flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self):
        if (self.mathml is None) != (self.path is None):
            raise ValueError("MathML and its path go together")
        if self.review_status == "paths_agree" and self.agreement != "agree":
            raise ValueError("Only agreeing paths are marked as agreeing")
        if self.review_status == "must_check" and self.output in {"mathml", "mathml_parts"}:
            raise ValueError("A must-check equation keeps its original evidence")
        if self.output == "mathml" and self.mathml is None:
            raise ValueError("A MathML output needs MathML")
        if self.output == "mathml_parts" and not self.parts:
            raise ValueError("A parts output needs its parts")
        return self


class PageMath(CoreModel):
    source_sha256: Digest
    page: int = Field(gt=0)
    version: str
    equations: list[EquationMath] = Field(default_factory=list)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique(self):
        ids = [e.equation_id for e in self.equations]
        if len(ids) != len(set(ids)):
            raise ValueError("One record per equation region")
        if any(
            e.review_status == "must_check" and e.fallback_image is None for e in self.equations
        ):
            raise ValueError("Every must-check equation carries its image fallback")
        names = [e.fallback_image.file_name for e in self.equations if e.fallback_image]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate equation image name")
        return self


class ShapeRecord(CoreModel):
    char: str | None
    italic: bool | None
    confidence: Confidence
    isolated: str | None = None
    isolated_latex: str | None = None
    votes: dict[str, dict[str, int]] = Field(default_factory=dict)
    by_position: dict[str, str] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    occurrences: int = Field(ge=0)
    unit_height: float | None = None
    descent: float | None = None


class BookMath(CoreModel):
    source_sha256: Digest
    pages: int = Field(gt=0)
    version: str
    config: dict
    settings: dict
    recognizers: dict[str, dict] = Field(default_factory=dict)
    equations: int = Field(ge=0)
    by_path: dict[str, int] = Field(default_factory=dict)
    by_review: dict[str, int] = Field(default_factory=dict)
    by_output: dict[str, int] = Field(default_factory=dict)
    by_agreement: dict[str, int] = Field(default_factory=dict)
    shapes: dict[str, ShapeRecord] = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)
