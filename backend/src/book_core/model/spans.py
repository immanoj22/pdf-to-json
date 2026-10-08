"""Single source-text authority; geometry lines are evidence, not paragraphs."""

import unicodedata
from collections.abc import Iterable
from typing import Annotated, Literal

from pydantic import Field, PositiveInt, model_validator

from book_core.model.common import (
    BBox,
    CoreModel,
    Digest,
    Identifier,
    Provenance,
    SpanRef,
    TextDirection,
)

NORMALIZATION = "NFKC"


class TextSpan(CoreModel):
    id: Identifier
    line_id: Identifier
    page: PositiveInt
    raw_text: str
    text: str
    bbox: BBox
    font: str
    size: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    color: Annotated[int, Field(ge=0, le=0xFFFFFF)]
    flags: Annotated[int, Field(ge=0)]
    language: str = "und"
    script: str | None = None
    text_direction: TextDirection | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def normalized(self) -> "TextSpan":
        if self.text != unicodedata.normalize(NORMALIZATION, self.raw_text):
            raise ValueError("Normalized span text must agree exactly with original source text")
        return self


class SourceLine(CoreModel):
    id: Identifier
    page: PositiveInt
    bbox: BBox
    span_ids: list[Identifier]


class SpanStore(CoreModel):
    spans: dict[str, TextSpan] = Field(default_factory=dict)
    lines: list[SourceLine] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self) -> "SpanStore":
        seen_lines: set[str] = set()
        seen_spans: set[str] = set()
        for line in self.lines:
            if line.id in seen_lines:
                raise ValueError("Duplicate source line identifier")
            seen_lines.add(line.id)
            for sid in line.span_ids:
                if sid in seen_spans or sid not in self.spans:
                    raise ValueError("Every span must occur exactly once in source line evidence")
                seen_spans.add(sid)
                span = self.spans[sid]
                if span.id != sid or span.line_id != line.id or span.page != line.page:
                    raise ValueError("Span and line provenance disagree")
        if seen_spans != set(self.spans):
            raise ValueError("Orphan span in store")
        return self

    def raw_line_text(self, line: SourceLine) -> str:
        return "".join(self.spans[sid].raw_text for sid in line.span_ids)

    def resolve_content(self, refs: Iterable[SpanRef]) -> str:
        """Resolve original order; line boundaries remain token separators."""
        parts: list[str] = []
        previous_line: str | None = None
        for ref in refs:
            span = self.spans[ref.span_id]
            if previous_line is not None and previous_line != span.line_id:
                parts.append("\n")
            if ref.end is not None and ref.end > len(span.raw_text):
                raise ValueError("Character range exceeds source span")
            parts.append(span.raw_text[ref.start : ref.end])
            previous_line = span.line_id
        return unicodedata.normalize(NORMALIZATION, "".join(parts))


class PageGeometry(CoreModel):
    page: PositiveInt
    width: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    height: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    rotation: int
    content_bbox: BBox
    coordinate_system: Literal["unrotated_cropbox"] = "unrotated_cropbox"


class ExtractorIdentity(CoreModel):
    name: Identifier
    version: Identifier
    configuration: dict[str, str | int | bool]


class ExtractedPage(CoreModel):
    source_sha256: Digest
    extractor: ExtractorIdentity
    geometry: PageGeometry
    store: SpanStore

    @model_validator(mode="after")
    def one_page(self) -> "ExtractedPage":
        if any(line.page != self.geometry.page for line in self.store.lines):
            raise ValueError("Page extraction contains evidence from a different page")
        for span in self.store.spans.values():
            if span.provenance.source_sha256 != self.source_sha256:
                raise ValueError("Span evidence belongs to another source")
        return self
