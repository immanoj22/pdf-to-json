"""Character review evidence. Flags reference spans; source text stays in the span store."""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import Confidence, CoreModel, Digest, Identifier

CharacterReason = Literal[
    "glyph_name_disagrees_with_unicode",
    "unnamed_or_mismatched_glyph_repeated_as_marker",
]


class GlyphEvidence(CoreModel):
    """One painted glyph occurrence: its offset in the span's original text and its codes."""

    offset: int = Field(ge=0)
    glyph_id: int
    glyph_name: str | None = None
    name_codepoint: int | None = None  # strict glyph-list reading of the name, if any
    decoded_codepoints: list[int] = Field(min_length=1)  # what the PDF maps the glyph to
    font: str
    marker_candidate: bool = False
    name_disagrees: bool = False


class CharacterFlag(CoreModel):
    span_id: Identifier
    line_id: Identifier
    reasons: list[CharacterReason] = Field(min_length=1)
    confidence: Confidence
    needs_review: Literal[True] = True
    glyphs: list[GlyphEvidence] = Field(min_length=1)


class PageCharacterEvidence(CoreModel):
    source_sha256: Digest
    page: int = Field(gt=0)
    version: str
    # Glyphs that meet a page-level test, by span; repetition is decided across the book.
    candidates: dict[Identifier, list[GlyphEvidence]] = Field(default_factory=dict)
    flags: list[CharacterFlag] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_flags(self):
        ids = [f.span_id for f in self.flags]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate character flag")
        return self
