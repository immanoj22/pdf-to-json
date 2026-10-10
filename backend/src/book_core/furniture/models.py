"""Neutral furniture data: line roles, page markers and the whole-book folio sequence.

Nothing is removed. Furniture is a role on a retained line, read in its own stream and still
counted by the ledger. Records reference line ids; no source text is copied (a page label is a
derived value, like a navigation target label). Confidence is a rule heuristic, not a
calibrated probability; anything below ``REVIEW_BELOW`` is flagged for review.
"""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import Confidence, CoreModel, Digest, Identifier, Provenance
from book_core.reading_order.models import PageReadingOrder

FurnitureRole = Literal[
    "running_head", "running_foot", "folio", "production_mark", "repeated_box", "content"
]
FURNITURE_ROLES = frozenset({"running_head", "running_foot", "folio", "production_mark"})
LabelKind = Literal["arabic", "roman", "prefixed", "other", "none"]
LabelSource = Literal["printed", "metadata", "inferred", "none"]
Feature = float | int | str | bool | None
REVIEW_BELOW = 0.6


class LineRole(CoreModel):
    line_id: Identifier
    role: FurnitureRole
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    group_id: Identifier | None = None  # the book-level slot or repeated group
    evidence: dict[str, Feature] = Field(default_factory=dict)
    review_required: bool = False


class PageMarker(CoreModel):
    """The printed page label of one physical page (or none), with where it came from."""

    page: int = Field(ge=1)
    label: str | None = None
    kind: LabelKind
    source: LabelSource
    confidence: Confidence
    folio_line_ids: list[Identifier] = Field(default_factory=list)
    run_index: int | None = None
    metadata_label: str | None = None
    reasons: list[str] = Field(min_length=1)
    review_required: bool = False

    @model_validator(mode="after")
    def consistent(self):
        if (self.label is None) != (self.source == "none"):
            raise ValueError("A page marker has a label exactly when it has a source")
        if self.source == "printed" and not self.folio_line_ids:
            raise ValueError("A printed label needs its folio line")
        if self.source in {"inferred", "none"} and self.folio_line_ids:
            raise ValueError("Inferred or missing labels reference no folio line")
        return self


class FolioRun(CoreModel):
    """Consecutive physical pages whose printed labels share one series and offset."""

    index: int = Field(ge=0)
    kind: LabelKind
    prefix: str = ""
    uppercase: bool = False
    offset: int  # physical page minus label value
    first_page: int
    last_page: int
    first_label: str
    last_label: str
    printed_pages: int
    inferred_pages: list[int] = Field(default_factory=list)
    style: list[Feature] = Field(default_factory=list)


class FurnitureGroup(CoreModel):
    """A book-level slot (edge position and style) or repeated text group, by line ids."""

    id: Identifier
    role: FurnitureRole
    edge: str | None = None
    pages: list[int]
    line_ids: list[Identifier]
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    evidence: dict[str, Feature] = Field(default_factory=dict)


class PageFurniture(CoreModel):
    source_sha256: Digest
    page: int
    furniture_version: str
    roles: list[LineRole]
    marker: PageMarker
    order: PageReadingOrder  # Step 7 order rebuilt with these roles; furniture streams by role
    furniture_streams: dict[str, Identifier] = Field(default_factory=dict)
    provenance: Provenance

    @model_validator(mode="after")
    def one_role_per_line(self):
        ids = [role.line_id for role in self.roles]
        if len(ids) != len(set(ids)):
            raise ValueError("A line has more than one furniture role")
        ordered = {line for stream in self.order.streams for line in stream.line_ids}
        if set(ids) != ordered:
            raise ValueError("Every ordered line needs exactly one role")
        if self.marker.page != self.page or self.order.page != self.page:
            raise ValueError("Page furniture mixes pages")
        streams = {stream.id: stream for stream in self.order.streams}
        role_of = {role.line_id: role.role for role in self.roles}
        for role, stream_id in self.furniture_streams.items():
            stream = streams.get(stream_id)
            if stream is None or any(role_of[line] != role for line in stream.line_ids):
                raise ValueError(f"The {role} stream must hold only {role} lines")
        return self


class BookFurniture(CoreModel):
    source_sha256: Digest
    furniture_version: str
    pages: int
    body_style: list[Feature]
    runs: list[FolioRun]
    groups: list[FurnitureGroup]
    markers: list[PageMarker]
    metadata_comparison: dict[str, Feature | list[int]] = Field(default_factory=dict)
    config: dict[str, Feature] = Field(default_factory=dict)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)  # see furniture.keys
    provenance: Provenance

    @model_validator(mode="after")
    def one_marker_per_page(self):
        if [m.page for m in self.markers] != list(range(1, self.pages + 1)):
            raise ValueError("Exactly one page marker per physical page, in page order")
        return self
