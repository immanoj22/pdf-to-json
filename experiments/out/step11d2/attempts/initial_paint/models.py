"""Visibility proof references; source text remains exclusively in its span store."""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import Confidence, CoreModel, Digest, Identifier


class RenderComparison(CoreModel):
    dpi: int = Field(gt=0)
    changed_pixels: int = Field(ge=0)
    pixels: int = Field(gt=0)
    before_sha256: Digest
    after_sha256: Digest
    suppressed_glyph_items: int = Field(gt=0)
    passthrough_matches_standard_renderer: Literal[True]


class SpanVisibility(CoreModel):
    span_id: Identifier
    line_id: Identifier
    decision: Literal["invisible", "review", "already_trimbox_excluded"]
    confidence: Confidence
    reason: str
    needs_review: bool
    text_paint_seqnos: list[int]
    cover_paint_seqnos: list[int]
    renders: list[RenderComparison] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_proof(self):
        if self.decision == "invisible":
            if (
                self.needs_review
                or len(self.renders) < 2
                or any(r.changed_pixels or r.before_sha256 != r.after_sha256 for r in self.renders)
            ):
                raise ValueError("Invisible spans require independent zero-change render proofs")
        return self


class PagePaintEvidence(CoreModel):
    source_sha256: Digest
    page: int = Field(gt=0)
    version: str
    spans: list[SpanVisibility] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_spans(self):
        ids = [s.span_id for s in self.spans]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate span visibility decision")
        return self
