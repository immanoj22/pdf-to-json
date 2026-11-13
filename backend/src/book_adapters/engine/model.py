"""The adapter document tree: book.json arranged as a delivery outline, with no output
format in it. Writers turn it into files. Text is never copied: every text is a
:class:`TextRef` into book.json."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .text import TextRef


@dataclass
class PageMark:
    """A physical page starts here."""

    page: int
    label: str | None
    zone: str | None
    anchor_id: str = ""
    role: str | None = None  # first | last (set by the outline)
    keep: bool = True


Inline = TextRef | PageMark


@dataclass
class Para:
    parts: list[Inline]
    kind: str = "body"  # book.json paragraph role, or caption/footnote/subchapter
    unit_ids: list[str] = field(default_factory=list)
    role_override: str | None = None


@dataclass
class Item:
    parts: list[Inline]
    children: list[Block] = field(default_factory=list)
    marker: dict | None = None
    marker_ref: TextRef | None = None  # marker written as text (bibliography abbrev)
    item_role: str | None = None
    level: int | None = None
    locators: list[dict] = field(default_factory=list)
    unit_id: str = ""
    merged_ids: list[str] = field(default_factory=list)  # item pieces joined into this one


@dataclass
class ListBlock:
    list_type: str
    marker_type: str | None
    items: list[Item]
    start: int | None = None
    glyph: str | None = None
    unit_ids: list[str] = field(default_factory=list)
    continues: bool = False  # continues the numbering of the list before it


@dataclass
class Figure:
    unit: dict
    captions: list[TextRef] = field(default_factory=list)
    texts: list[TextRef] = field(default_factory=list)
    credits: list[TextRef] = field(default_factory=list)
    formal: bool = False
    kind: str | None = None  # profile figure kind name
    num: str | None = None  # printed number
    label_ref: TextRef | None = None  # caption text that became the label attribute
    verbatim_label: bool = False  # the printed label names several figures: written as printed
    continued: bool = False
    image: dict | None = None
    page: int = 0
    page_label: str | None = None
    zone: str | None = None
    # set by the writer's numbering pass
    id: str | None = None
    label: str | None = None
    title_role: str | None = None
    file: str | None = None


@dataclass
class Table:
    unit: dict
    parts: list[dict] = field(default_factory=list)  # joined continued table units
    title: TextRef | None = None
    label_ref: TextRef | None = None
    num: str | None = None
    notes: list[TextRef] = field(default_factory=list)
    id: str | None = None
    label: str | None = None
    title_role: str | None = None
    cells_blocks: dict[str, list[Block]] = field(default_factory=dict)  # cell id -> blocks
    rows: list[list[dict]] = field(default_factory=list)  # joined rows of cells
    columns: int = 0
    header_rows: int = 0
    trailing_marks: list[PageMark] = field(default_factory=list)  # pages begun inside it


@dataclass
class Sidebar:
    unit: dict | None
    title: TextRef | None = None
    label_ref: TextRef | None = None
    num: str | None = None
    children: list[Block] = field(default_factory=list)
    id: str | None = None
    label: str | None = None
    title_role: str | None = None


@dataclass
class Equation:
    unit: dict
    content: TextRef | None = None


@dataclass
class BibEntry:
    parts: list[Inline]
    marker_ref: TextRef | None = None
    marker_text: str | None = None
    unit_id: str = ""
    id: str | None = None


@dataclass
class Bibliography:
    title: TextRef | None
    entries: list[BibEntry]
    lead: list[Block] = field(default_factory=list)  # blocks between title and entries
    as_chapter: bool = False


@dataclass
class IndexEntry:
    level: int
    item: Item


@dataclass
class IndexDiv:
    title: TextRef | None
    title_text: str | None  # generated letter when the index prints none
    entries: list[IndexEntry]
    lead: list[Block] = field(default_factory=list)


@dataclass
class QandaSet:
    title: TextRef | None
    items: list[Item]


@dataclass
class QuestionEntry:
    """A numbered stem, its lettered options and its printed answer (Stage 1 question entry).
    ``question`` holds the blocks of the question in reading order (the stem list first, the
    options list last); ``answer`` the answer line and the explanation."""

    number: int | None
    question: list[Block] = field(default_factory=list)
    answer: list[Block] = field(default_factory=list)
    key: str | None = None


@dataclass
class QuestionSet:
    entries: list[QuestionEntry]

    def blocks(self) -> list:
        return [b for e in self.entries for b in (*e.question, *e.answer)]


@dataclass
class Section:
    title: TextRef | None
    depth: int
    children: list[Node] = field(default_factory=list)
    heading: dict | None = None
    id: str | None = None
    title_role: str | None = None
    subchapter: bool = False


Block = (Para | ListBlock | Figure | Table | Sidebar | Equation | Bibliography | QandaSet
         | QuestionSet | PageMark)  # fmt: skip
Node = Block | Section


@dataclass
class Division:
    """A part, chapter, preface, dedication, appendix, glossary or index."""

    kind: str
    title: list[TextRef] = field(default_factory=list)
    title_text: str | None = None  # generated (profile default) title
    label_ref: TextRef | None = None  # printed label word consumed into the label attribute
    number_ref: TextRef | None = None
    number: int | None = None
    chosen_number: int | None = None  # the number a reviewer set on the heading
    printed_number: int | None = None  # the number printed with the heading, as its label
    intro: list[Node] = field(default_factory=list)  # part intro
    children: list[Any] = field(default_factory=list)  # nodes, or chapters in a part
    first_page: int | None = None
    last_page: int | None = None
    opener_title: TextRef | None = None
    index_divs: list[IndexDiv] = field(default_factory=list)
    id: str | None = None
    label: str | None = None
    title_page_mark: list[PageMark] = field(default_factory=list)
    evidence: str = "heading"  # heading | opener | toc (opener/toc: adapter-inferred)
    title_evidence: str = "heading"  # heading | opener | toc | none


@dataclass
class BookInfo:
    title_ref: TextRef | None = None
    legal: list[Block] = field(default_factory=list)
    legal_after: list[Block] = field(default_factory=list)
    page_marks: list[PageMark] = field(default_factory=list)
    authors: list = field(default_factory=list)  # author groups read from the title page


@dataclass
class Omission:
    addr: str
    ranges: list[tuple[int, int]]
    reason: str
    content: dict | None = None


@dataclass
class ReviewEntry:
    kind: str
    message: str
    unit: str | None = None
    page: int | None = None
    rule: str | None = None
    severity: str | None = None  # must_check | needs_review (None: by kind, see review_list)

    def as_dict(self) -> dict:
        out = {
            "kind": self.kind,
            "message": self.message,
            "unit": self.unit,
            "page": self.page,
            "rule": self.rule,
        }
        if self.severity:
            out["severity"] = self.severity
        return out


@dataclass
class Document:
    bookinfo: BookInfo
    front: list[Division]
    body: list[Division]
    back: list[Division]
    omissions: list[Omission] = field(default_factory=list)
    reviews: list[ReviewEntry] = field(default_factory=list)
    order: dict[str, int] = field(default_factory=dict)  # addr -> book.json order
    records: dict[str, dict] = field(default_factory=dict)  # addr -> text record
    pages: list[dict] = field(default_factory=list)
    marker_addrs: set[str] = field(default_factory=set)
    structure_markers: set[str] = field(default_factory=set)  # markers shown by numbering
    after: list[Division] = field(default_factory=list)  # body divisions after back matter
