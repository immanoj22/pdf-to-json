"""Decisions at page breaks: which unit of one page continues on the next.

**Book profile** (pass 1): the body style (the style of most characters of main-flow
paragraphs) and whether the book indents its paragraphs (the share of body paragraphs of
three or more lines whose first line is indented).

**Edges**: the unit ending page p (``A``) is the last body unit of its main flow, skipping
floats and set-apart units after it; the unit beginning the next page (``B``) is the first
body unit there, skipping floats and set-apart units before it. A structure-stage heading
on the way ends the search (a continuation never crosses a real heading or section start).
A page whose main flow holds only floats (a full-page table or figure) is skipped, at most
``MAX_SKIPPED`` pages.

**Units** (A, B both body text in one style):

- A paragraph or list item continues into B when B opens no new item (no list marker, no
  enumerator such as "13 ." or "a." that the lists stage did not read as a marker, no new
  entry), B's first line is not indented (when measurable), the two have the same
  column width (when measurable), and the text says so:
  - A ends with a break hyphen, or ends open (no sentence end) and B opens lowercase or
    with a digit: the sentence goes on (confidence 0.9; 0.85 after a hyphen);
  - A ends open, B opens with a capital, and A's last line fills its column: 0.75;
  - A ends a sentence on a full last line, B's first line is not indented, and the book
    indents its paragraphs: a new sentence of the same paragraph (0.7).
  A list item continued by unmarked text continues as that item, only when its last line
  fills its column (items often end without punctuation).
- An index or bibliography entry continues into B (same entry kind) when B is an indented
  line without an open entry (lists stage), or A ends open and B opens lowercase: an
  entry link, never a prose join. Glossary and definition entries are not linked by rule
  (measured: their rows end without punctuation).

Earlier links are kept: Step 9 page joins the lists stage kept (with their line join),
lists-stage entry links and items continued at the top of a page. A link whose unit no
longer exists in the final view (its lines went into a table) is dropped with the reason.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from book_core.continuity.edges import (
    ENTRY_KINDS,
    LINKED_ENTRIES,
    _text,
    end_kind,
    same_style,
    start_kind,
    unit_style,
)
from book_core.continuity.models import REVIEW_BELOW, Candidate, PageBreak
from book_core.lists.joins import new_join
from book_core.paragraphs.geometry import frame

INDENT = 0.8  # font sizes: a first-line indent
FULL = 1.5  # font sizes: a last line ending at most this short of its column is full
WIDTH = 0.12  # relative difference of column widths that still match
INDENTED_BOOK = 0.6  # share of body paragraphs with a first-line indent
MAX_SKIPPED = 2  # float-only pages between two halves
RUNNING = frozenset({"paragraph", "list_item", "list_item_candidate"})
CONTINUING = frozenset({"paragraph", "list_item_candidate"})
CONFIG = {"indent": INDENT, "full": FULL, "width": WIDTH, "indented_book": INDENTED_BOOK,
          "max_skipped": MAX_SKIPPED}  # fmt: skip


@dataclass
class BookProfile:
    styles: Counter = field(default_factory=Counter)
    pending: list = field(default_factory=list)  # (style, indented) of long paragraphs
    indented: int = 0
    paragraphs: int = 0
    body: tuple | None = None

    def add_page(self, store, layout, units, order):
        lines = {line.id: line for line in layout.lines}
        main = {lid for s in order.streams if s.kind == "main" for lid in s.line_ids}
        for unit in units:
            if unit.kind != "paragraph" or unit.line_ids[0] not in main:
                continue
            members = [lines[lid] for lid in unit.line_ids if lid in lines]
            style = unit_style(store, members)
            self.styles[style] += sum(len(store.spans[s].raw_text.strip())
                                      for line in members for s in line.span_ids)  # fmt: skip
            if len(members) >= 3:
                frames = [frame(line) for line in members]
                size = max(frames[0].size, 1.0)
                rest = min(f.start for f in frames[1:])
                self.pending.append((style, (frames[0].start - rest) / size > INDENT))

    def freeze(self):
        self.body = self.styles.most_common(1)[0][0] if self.styles else None
        body = [indented for style, indented in self.pending if same_style(style, self.body)]
        self.paragraphs = len(body)
        self.indented = sum(body)
        return self

    @property
    def indents(self):
        return self.paragraphs > 0 and self.indented / self.paragraphs >= INDENTED_BOOK

    def record(self):
        return {"body_style": list(self.body) if self.body else None,
                "body_paragraphs": self.paragraphs, "indented_paragraphs": self.indented,
                "indents_paragraphs": self.indents}  # fmt: skip


def guarded(skipped):
    """Anything skipped between the halves (floats or set-apart text): then only the
    strongest text evidence joins (measured: a capital after a skipped box title or table
    starts new text more often than it continues)."""
    return bool(skipped)


def bottom(edges):
    """(A, skipped ids, reason): the last body unit of the page's main flow."""
    skipped = []
    for item in reversed(edges.items):
        if item.role == "heading":
            return None, skipped, "a heading ends the page"
        if item.role in {"float", "set_apart"}:
            skipped.append(item)
            continue
        return item, skipped, None
    return None, skipped, "no body text on the page"


def top(edges):
    """(B, skipped ids, reason, float-only page): the first body unit of the main flow."""
    skipped = []
    for item in edges.items:
        if item.role == "heading":
            return None, skipped, "a heading begins the page", False
        if item.role in {"float", "set_apart"}:
            skipped.append(item)
            continue
        return item, skipped, None, False
    floats = all(item.role == "float" for item in edges.items)
    return None, skipped, "no body text on the page", floats


def decide(a, b, profile, navigation, guarded=False):
    """(chain kind, confidence, reasons) for A continuing into B, or (None, 0, reasons).

    ``guarded``: something was skipped between them (floats, set-apart text); then only an
    open end before a lowercase or digit start joins."""
    ends, starts = end_kind(a.tail), start_kind(b.head)
    evidence = [f"A ends {ends}", f"B starts {starts}"]
    if a.kind in ENTRY_KINDS or b.kind in ENTRY_KINDS:
        if a.kind != b.kind:
            return None, 0.0, ["entry kinds differ", *evidence]
        if a.kind not in LINKED_ENTRIES:
            return None, 0.0, ["glossary and definition entries are not linked by rule",
                               *evidence]  # fmt: skip
        if b.open_start:
            return "entry", 0.8, ["entry continues: the next page opens with an indented "
                                  "line without an open entry"]  # fmt: skip
        if ends in {"open", "hyphen"} and starts in {"lower", "digit"}:
            return "entry", 0.75, ["entry continues: open end, lowercase start", *evidence]
        return None, 0.0, ["entry complete or a new entry opens the page", *evidence]
    if a.kind not in RUNNING or b.kind not in CONTINUING:
        return None, 0.0, [f"kinds {a.kind}->{b.kind} do not continue", *evidence]
    if b.marker:
        return None, 0.0, ["the next page opens a new list item"]
    if b.run_in:
        return None, 0.0, ["the next page opens with a run-in heading: a new paragraph"]
    if starts == "enumerator":
        return None, 0.0, ["the next page opens with an enumerator: a new item", *evidence]
    if not same_style(a.style, b.style):
        return None, 0.0, ["style changes", *evidence]
    if b.indent is not None and b.indent > INDENT:
        return None, 0.0, ["first-line indent: a new paragraph", *evidence]
    if a.lines >= 2 and b.lines >= 2 and abs(a.width - b.width) > WIDTH * max(a.width, b.width):
        return None, 0.0, ["column width differs", *evidence]
    kind = "list_item" if a.kind == "list_item" else "paragraph"
    full = a.fill is not None and a.fill <= FULL
    if kind == "list_item" and not full:
        return None, 0.0, ["a list item ends on a short or single line: complete", *evidence]
    if ends == "hyphen" and (not guarded or starts in {"lower", "digit"}):
        return kind, 0.85, ["a break hyphen ends the page: the word continues", *evidence]
    if ends in {"open", "locator"} and starts in {"lower", "digit"}:
        return kind, 0.9, ["the sentence continues on the next page", *evidence]
    if guarded:
        return None, 0.0, ["text skipped between them: only an open end before a lowercase "
                           "or digit start joins", *evidence]  # fmt: skip
    if ends in {"open", "locator"} and full:
        return kind, 0.75, ["open end on a full last line: the sentence continues", *evidence]
    if ends == "terminal" and full and profile.indents and b.indent is not None:
        return kind, 0.7, ["full last line, no first-line indent, in a book that indents its "
                           "paragraphs: the paragraph continues", *evidence]  # fmt: skip
    return None, 0.0, ["no continuation evidence", *evidence]


def unit_break(a, b, page_a, page_b, line_a, line_b, kind, confidence, reasons, skipped,
               skipped_pages, label, vocabulary, compounds, source="continuity",
               join=None, where="page"):  # fmt: skip
    """The PageBreak of A continuing into B (entries get no prose join); ``where``: page
    or column (same page, no page marker)."""
    if join is None and kind != "entry":
        join = new_join(page_a, vocabulary, compounds, line_a, _text(page_a.store, line_a),
                        line_b, _text(page_b.store, line_b), where, confidence,
                        list(reasons))  # fmt: skip
    if where == "column":
        label = (None, "none")
    return PageBreak(
        kind=where,
        from_page=page_a.geometry.page,
        from_id=a,
        from_line_id=line_a.id,
        to_page=page_b.geometry.page,
        to_id=b,
        to_line_id=line_b.id,
        page_label=label[0],
        label_source=label[1],
        skipped_pages=skipped_pages,
        skipped_ids=skipped,
        join=join,
        source=source,
        confidence=round(confidence, 4),
        reasons=list(reasons),
        review_required=confidence < REVIEW_BELOW,
    )


def refused(kind, a_page, a, b_page, b, reasons, close=False):
    """A candidate not joined; ``close``: the text says the sentence goes on (review)."""
    return Candidate(kind=kind, from_page=a_page, from_id=a, to_page=b_page, to_id=b,
                     reasons=reasons, review_required=close)  # fmt: skip
