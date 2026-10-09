"""Typed reading order over Step 4 lines: a main flow, float streams and side streams.

Order is a graph with typed edges (see ``reading_order.graph``); this model is its serialised
form. Every visual line of the page is in exactly one stream. Lines keep their span references;
no text is copied. Confidence is a rule heuristic, not a calibrated probability.
"""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import Confidence, CoreModel, Digest, Identifier, Provenance

EdgeKind = Literal[
    "next_in_lane",
    "next_lane_in_band",
    "next_band",
    "continues_across_column",
    "continues_across_page",
    "next_in_stream",
    "belongs_to_figure",
    "belongs_to_table",
    "caption_of",
    "anchored_after",
]
SEQUENCE_EDGES = frozenset(
    {"next_in_lane", "next_lane_in_band", "next_band", "continues_across_column", "next_in_stream"}
)
StreamKind = Literal[
    "main",
    "sidebar",
    "callout",
    "figure",
    "table",
    "card",
    "credit",
    "note",
    "furniture",
    "artifact",
    "invisible",
]
FLOAT_KINDS = frozenset({"sidebar", "callout", "figure", "table", "card", "credit", "note"})
AnchorMode = Literal["in_lane", "inset", "lane_order", "band", "scope", "page_start"]
DecisionKind = Literal[
    "direction",
    "lane_transition",
    "band_transition",
    "column_flow",
    "float_anchor",
    "caption_link",
    "credit_link",
    "row",
    "lane_assignment",
    "scope_boundary",
    "unplaced",
]
Feature = float | int | str | bool | None
PAGE_START = "page_start"
REVIEW_BELOW = 0.6


class Anchor(CoreModel):
    """Where a float is read in the main flow: after a main line, or before the first one."""

    after_line_id: Identifier | None = None
    position: int = Field(ge=-1)  # index of after_line_id in the main flow; -1 = page start
    order: int = Field(ge=0)  # among floats sharing this anchor
    mode: AnchorMode
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    review_required: bool = False


class Stream(CoreModel):
    id: Identifier
    kind: StreamKind
    line_ids: list[Identifier] = Field(default_factory=list)
    region_ids: list[Identifier] = Field(default_factory=list)
    scope_id: Identifier | None = None
    anchor: Anchor | None = None
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    review_required: bool = False

    @model_validator(mode="after")
    def floats_are_anchored(self):
        if (self.kind in FLOAT_KINDS) != (self.anchor is not None):
            raise ValueError(f"{self.kind} stream: floats, and only floats, carry an anchor")
        return self


class OrderEdge(CoreModel):
    source: Identifier
    target: Identifier
    kind: EdgeKind
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    evidence: dict[str, Feature] = Field(default_factory=dict)


class OrderDecision(CoreModel):
    kind: DecisionKind
    subject_ids: list[Identifier] = Field(min_length=1)
    choice: str
    alternatives: list[str] = Field(default_factory=list)
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    evidence: dict[str, Feature] = Field(default_factory=dict)
    review_required: bool = False


class PageReadingOrder(CoreModel):
    source_sha256: Digest
    page: int
    order_version: str
    layout_version: str
    streams: list[Stream]
    edges: list[OrderEdge] = Field(default_factory=list)
    decisions: list[OrderDecision] = Field(default_factory=list)
    provenance: Provenance

    @property
    def main(self) -> Stream:
        return next(stream for stream in self.streams if stream.kind == "main")

    def stream_of(self) -> dict[str, str]:
        return {line: stream.id for stream in self.streams for line in stream.line_ids}

    @model_validator(mode="after")
    def every_line_once(self):
        if sum(stream.kind == "main" for stream in self.streams) != 1:
            raise ValueError("Exactly one main stream")
        ids = [stream.id for stream in self.streams]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate stream")
        lines = [line for stream in self.streams for line in stream.line_ids]
        if len(lines) != len(set(lines)):
            raise ValueError("A line is ordered more than once")
        main = self.main.line_ids
        for stream in self.streams:
            anchor = stream.anchor
            if anchor is None:
                continue
            expected = main.index(anchor.after_line_id) if anchor.after_line_id in main else None
            if anchor.after_line_id is None and anchor.position != -1:
                raise ValueError("A page-start anchor has position -1")
            if anchor.after_line_id is not None and expected != anchor.position:
                raise ValueError(f"Float {stream.id[:12]} anchors outside the main flow")
        return self
