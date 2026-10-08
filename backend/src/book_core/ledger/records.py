"""Explicit token owners and the single discard policy permitted at this gate."""

from typing import Annotated, Literal

from pydantic import Field, PositiveInt

from book_core.model.common import BBox, CoreModel, Identifier

TRIMBOX_REASON = "Outside explicit PDF TrimBox; retained in raw evidence."


class DiscardRecord(CoreModel):
    id: Identifier
    line_id: Identifier
    page: PositiveInt
    bbox: BBox
    span_ids: list[Identifier]
    reason: Literal["Outside explicit PDF TrimBox; retained in raw evidence."] = TRIMBOX_REASON


class NodeAssignment(CoreModel):
    kind: Literal["node"] = "node"
    token_id: Identifier
    node_id: Identifier


class DiscardAssignment(CoreModel):
    kind: Literal["discard"] = "discard"
    token_id: Identifier
    discard_id: Identifier


Assignment = Annotated[NodeAssignment | DiscardAssignment, Field(discriminator="kind")]


class WordLedger(CoreModel):
    assignments: list[Assignment] = Field(default_factory=list)
    discards: list[DiscardRecord] = Field(default_factory=list)


class LedgerReport(CoreModel):
    source_line_count: int
    excluded_line_count: int
    retained_line_count: int
    source_token_count: int
    retained_token_count: int
    node_token_count: int
    discard_token_count: int
    missing_token_count: int
    extra_token_count: int
    retained_missing_token_count: int
    retained_extra_token_count: int
    expected_missing_token_count: int | None = None
    expected_extra_token_count: int | None = None
    ownership_errors: list[str] = Field(default_factory=list)

    @property
    def passing(self) -> bool:
        counts = (
            self.missing_token_count,
            self.extra_token_count,
            self.retained_missing_token_count,
            self.retained_extra_token_count,
            self.expected_missing_token_count,
            self.expected_extra_token_count,
        )
        return not any(counts) and not self.ownership_errors
