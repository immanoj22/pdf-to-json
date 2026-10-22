"""Content continued across page breaks: chains of per-page units and tables, by reference.

The model keeps logical paragraphs, list items, entries and tables as **linked per-page
pieces** (owner decision, Step 10): a chain lists its members (final-view unit ids, or table
ids) in reading order, and each page break between two members is recorded where it falls
(the last line before it, the first line after it, the printed label of the page that
begins), so an adapter can emit the joined unit with the page marker inside it or split it
there. Nothing is merged and no text is copied.

- A **column break** continues a unit into the next column of the same page where the
  paragraph stage did not join them (same evidence as across pages; no page marker).
- A **unit break** carries the line join across the break (``LineJoin`` of kind ``page``,
  with its hyphen or split-word decision); floats and set-apart units skipped at the page
  edges and whole pages skipped between the halves (a full-page table or figure) are named.
- An **entry link** (index, glossary, bibliography) continues an entry on the next page; it
  is a link like the others, never a prose join (owner decision, Step 11).
- A **table break** maps the continuation's columns onto the first part's, names the
  continuation's leading rows that repeat the header rows (``repeated_header_rows``: kept
  in the record, not repeated in the logical table) and the continuation marks next to the
  table ("Contd..." lines, repeated titles), by reference.
- **Candidates** that were examined and not joined keep their reasons (review evidence);
  a close call or a table whose columns do not map is flagged for review.

Confidence is a rule heuristic, not a calibrated probability.
"""

from typing import Literal

from pydantic import Field, model_validator

from book_core.furniture.models import LabelSource
from book_core.model.common import Confidence, CoreModel, Digest, Identifier, Provenance
from book_core.paragraphs.models import LineJoin

Feature = float | int | str | bool | None
ChainKind = Literal["paragraph", "list_item", "entry", "table"]
Source = Literal["paragraphs", "lists", "continuity", "tables"]
REVIEW_BELOW = 0.6


class ContinuationMark(CoreModel):
    """Text next to a continued table that marks the continuation ("Contd...", a repeated
    numbered title), by reference."""

    page: int = Field(ge=1)
    unit_id: Identifier | None = None
    line_ids: list[Identifier] = Field(min_length=1)
    position: Literal["below", "above", "title"]
    reasons: list[str] = Field(min_length=1)


class PageBreak(CoreModel):
    """One break inside a chain: between member ``from_id`` (ending page ``from_page`` with
    line ``from_line_id``) and member ``to_id`` (beginning page ``to_page``). A ``column``
    break continues a unit into the next column of the same page (no page marker)."""

    kind: Literal["page", "column"] = "page"
    from_page: int = Field(ge=1)
    from_id: Identifier
    from_line_id: Identifier
    to_page: int = Field(ge=1)
    to_id: Identifier
    to_line_id: Identifier
    page_label: str | None = None  # printed label of ``to_page`` (the page marker)
    label_source: LabelSource = "none"
    skipped_pages: list[int] = Field(default_factory=list)  # float-only pages between
    skipped_ids: list[Identifier] = Field(default_factory=list)  # floats at the edges
    join: LineJoin | None = None  # unit breaks: the line join across the break
    repeated_header_rows: int = Field(default=0, ge=0)  # table breaks
    column_map: list[int] = Field(default_factory=list)  # table breaks: to column -> from
    marks: list[ContinuationMark] = Field(default_factory=list)
    source: Source
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    review_required: bool = False

    @model_validator(mode="after")
    def ordered(self):
        if self.kind == "column":
            if self.to_page != self.from_page or self.page_label is not None:
                raise ValueError("A column break stays on its page, without a page marker")
        elif self.to_page <= self.from_page:
            raise ValueError("A page break goes forward")
        if self.skipped_pages != list(range(self.from_page + 1, self.to_page)):
            raise ValueError("Pages between the halves are the skipped pages")
        if self.join is not None and (
            self.join.previous_line_id != self.from_line_id
            or self.join.next_line_id != self.to_line_id
            or self.join.kind != self.kind
        ):
            raise ValueError("A break's join links its two lines across the page")
        return self


class Chain(CoreModel):
    """A logical unit or table over several pages: members in order, one break between
    each two."""

    id: Identifier
    kind: ChainKind
    members: list[Identifier] = Field(min_length=2)
    pages: list[int] = Field(min_length=2)
    breaks: list[PageBreak] = Field(min_length=1)
    review_required: bool = False

    @model_validator(mode="after")
    def connected(self):
        if len(set(self.members)) != len(self.members):
            raise ValueError("A chain member appears once")
        if len(self.breaks) != len(self.members) - 1 or len(self.pages) != len(self.members):
            raise ValueError("A chain has one break between each two members")
        for k, brk in enumerate(self.breaks):
            if (brk.from_id, brk.to_id) != (self.members[k], self.members[k + 1]):
                raise ValueError("Chain breaks must connect consecutive members")
            if (brk.from_page, brk.to_page) != (self.pages[k], self.pages[k + 1]):
                raise ValueError("Chain pages must match its breaks")
        if (self.kind == "table") != all(b.source == "tables" for b in self.breaks):
            raise ValueError("Table chains, and only they, come from the tables stage")
        return self


class Candidate(CoreModel):
    """A page break examined and not joined, with the reasons (review evidence)."""

    kind: ChainKind
    from_page: int = Field(ge=1)
    from_id: Identifier | None = None
    to_page: int = Field(ge=1)
    to_id: Identifier | None = None
    reasons: list[str] = Field(min_length=1)
    evidence: dict[str, Feature] = Field(default_factory=dict)
    review_required: bool = False


class BookContinuity(CoreModel):
    source_sha256: Digest
    pages: int = Field(gt=0)
    version: str
    chains: list[Chain] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    dropped_links: list[dict[str, Feature]] = Field(default_factory=list)
    profile: dict[str, Feature | list | dict] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance

    @model_validator(mode="after")
    def links_once(self):
        starts, ends = set(), set()
        for chain in self.chains:
            for brk in chain.breaks:
                if brk.from_id in starts or brk.to_id in ends:
                    raise ValueError("A member continues to (and from) at most one other")
                starts.add(brk.from_id)
                ends.add(brk.to_id)
        return self

    def links(self, number):
        """{member id on page ``number``: (continues from, continues to)} of unit chains."""
        out = {}
        for chain in self.chains:
            if chain.kind == "table":
                continue
            for brk in chain.breaks:
                if brk.from_page == number:
                    out.setdefault(brk.from_id, [None, None])[1] = brk.to_id
                if brk.to_page == number:
                    out.setdefault(brk.to_id, [None, None])[0] = brk.from_id
        return {k: tuple(v) for k, v in out.items()}

    def page_breaks(self, number):
        """The breaks that end or begin on page ``number`` (with their chain id and kind)."""
        return [
            {"chain_id": chain.id, "chain_kind": chain.kind, **brk.model_dump(mode="json")}
            for chain in self.chains
            for brk in chain.breaks
            if number in {brk.from_page, brk.to_page}
        ]
