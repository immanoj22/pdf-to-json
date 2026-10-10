"""Neutral structure data: printed-navigation kinds, headings with levels and roles, book parts.

Records reference unit ids, line ids and span ranges only; no source text is stored. Levels
are neutral integers (1 = outermost) and roles are neutral names; neither is a schema tag.
Confidence is a rule heuristic, not a calibrated probability; below REVIEW_BELOW a decision is
flagged for review.
"""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import Confidence, CoreModel, Digest, Identifier, Provenance, SpanRef

Feature = float | int | str | bool | None
REVIEW_BELOW = 0.6
NavigationKind = Literal["table_of_contents", "index", "glossary", "bibliography", "other_list"]
HeadingRole = Literal[
    "book_title",
    "part",
    "unit",
    "chapter",
    "lesson",
    "section",
    "subsection",
    "sidebar_title",
    "feature_title",
    "front_section_title",
    "rear_section_title",
]
STRUCTURAL_ROLES = frozenset(
    {"part", "unit", "chapter", "lesson", "section", "subsection", "front_section_title",
     "rear_section_title", "book_title"}
)  # fmt: skip
LevelMethod = Literal["navigation", "numbering", "style_rank", "zone", "attached", "nesting"]
Zone = Literal["front", "body", "rear"]
SectionKind = Literal[
    "cover",
    "title_page",
    "copyright",
    "dedication",
    "table_of_contents",
    "preface",
    "other_list",
    "front_other",
    "part",
    "unit",
    "chapter",
    "appendix",
    "glossary",
    "index",
    "bibliography",
    "credits",
    "rear_other",
]


class Decision(CoreModel):
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    evidence: dict[str, Feature] = Field(default_factory=dict)
    review_required: bool = False


class NavigationPage(Decision):
    """One page of printed navigation and what kind of list it is."""

    page: int = Field(ge=1)
    kind: NavigationKind
    entries: int = Field(ge=0)


class TocLink(Decision):
    """A table-of-contents entry resolved to a physical page and to units on that page."""

    entry_id: Identifier
    source_page: int | None = None  # None for a document-outline entry
    target_label: str | None = None
    target_page: int | None = None
    unit_ids: list[Identifier] = Field(default_factory=list)
    match_score: float | None = None
    level: int | None = None  # level evidence from the list itself (indent/style rank)


class Heading(Decision):
    id: Identifier
    page: int = Field(ge=1)
    unit_ids: list[Identifier] = Field(min_length=1)
    run_in: list[SpanRef] = Field(default_factory=list)  # heading text inside a paragraph
    level: int = Field(ge=1)
    level_method: LevelMethod
    role: HeadingRole
    style_group: str | None = None
    navigation_entry_ids: list[Identifier] = Field(default_factory=list)
    section_id: Identifier | None = None


StyledRole = Literal["display_title", "label"]


class StyledText(Decision):
    """A styled unit that is not a heading: a display title inside a section's running text,
    or a label of a box or of the text. It keeps its style evidence (adapters may render it)."""

    id: Identifier
    page: int = Field(ge=1)
    unit_ids: list[Identifier] = Field(min_length=1)
    role: StyledRole
    style_group: str | None = None


class RejectedCandidate(CoreModel):
    """A heading-like unit decided not to be a heading, with why (review evidence)."""

    unit_id: Identifier
    page: int
    score: float
    reasons: list[str] = Field(min_length=1)


class Section(Decision):
    """A contiguous run of pages with one zone and section kind."""

    id: Identifier
    zone: Zone
    kind: SectionKind
    first_page: int = Field(ge=1)
    last_page: int = Field(ge=1)
    heading_id: Identifier | None = None
    logical_index: int = Field(ge=0)  # book order (navigation order, else physical order)


class PageZone(Decision):
    page: int = Field(ge=1)
    zone: Zone
    section_id: Identifier
    section_kind: SectionKind


class BookStructure(CoreModel):
    source_sha256: Digest
    structure_version: str
    pages: int
    body_style: dict[str, Feature] = Field(default_factory=dict)
    style_groups: list[dict[str, Feature]] = Field(default_factory=list)
    navigation_pages: list[NavigationPage] = Field(default_factory=list)
    toc_links: list[TocLink] = Field(default_factory=list)
    headings: list[Heading] = Field(default_factory=list)  # book order
    styled: list[StyledText] = Field(default_factory=list)  # non-heading styled units
    rejected: list[RejectedCandidate] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    page_zones: list[PageZone] = Field(default_factory=list)
    profile: dict[str, Feature | list | dict] = Field(default_factory=dict)
    config: dict[str, Feature | list | dict] = Field(default_factory=dict)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance

    @model_validator(mode="after")
    def consistent(self):
        units = [u for h in self.headings for u in h.unit_ids if not h.run_in]
        units += [u for s in self.styled for u in s.unit_ids]
        if len(units) != len(set(units)):
            raise ValueError("A unit belongs to more than one heading or styled text")
        ids = [h.id for h in self.headings]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate heading id")
        depth = 0
        for heading in self.headings:
            if heading.role in STRUCTURAL_ROLES:
                if heading.level > depth + 1:
                    raise ValueError("A heading level skips when going down")
                depth = heading.level
            elif heading.level > depth + 1:
                raise ValueError("An attached title is deeper than its section allows")
        if self.page_zones and [z.page for z in self.page_zones] != list(range(1, self.pages + 1)):
            raise ValueError("Exactly one zone per physical page, in page order")
        sections = {s.id for s in self.sections}
        if any(z.section_id not in sections for z in self.page_zones):
            raise ValueError("A page zone names an unknown section")
        return self
