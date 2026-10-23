"""One page's evidence at its edges: the main flow's items and the features of its units.

The main flow is the page's main stream in reading order over the final unit view: each
item is a text-owning table or a final unit (furniture kinds are left out). An item is

- a **float** when it is a table, a table's linked title or note, a caption or figure-text
  unit, a unit a figure links (caption, credit, text inside its region), or a display
  equation unit read at its anchor between two units (owner decision, Step 17): floats
  never break a continuation and are skipped at the page edges;
- a **heading** when the structure stage made it a heading (a real heading or section
  start): a continuation never crosses it;
- **set apart** when its style differs from the book's body style (index and bibliography
  entries on their own pages excepted: they are set in their own style), or it is a heading
  candidate the structure stage did not make a heading (box titles, labels): skipped at the
  edges, like floats, but a page of set-apart text is not a float page;
- **body** text otherwise.

Each unit's features are measured in its lines' reading frame (right-to-left and vertical
aware): its dominant style, the start and end of its first and last lines, its column
extent, the first line's indent and the last line's fill in font sizes, and the text cues
at its ends (the NFKC tail and head; evidence only, never stored).
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from statistics import median

import regex

from book_core.paragraphs.geometry import frame
from book_core.paragraphs.segment import _style

FURNITURE = frozenset({"running_head", "running_foot", "folio", "production_mark", "artifact",
                       "invisible"})  # fmt: skip
FLOAT_KINDS = frozenset({"caption", "figure_text", "table_text"})
ENTRY_KINDS = frozenset({"index_entry", "definition_entry", "bibliography_entry"})
LINKED_ENTRIES = frozenset({"index_entry", "bibliography_entry"})  # linked across pages
ENTRY_PAGES = frozenset({"index", "bibliography"})
SENTENCE_END = regex.compile(r"[.!?…:;。！？؟]\s*[\"'”’»)\]]*\s*$")
HYPHEN_END = regex.compile(r"\p{L}[-­‐‑]\s*$")
LOCATOR_END = regex.compile(r"\p{N}\s*$")
# An enumerator opening a line: a number of at most three digits or one letter, then "." or
# ")" and a space ("13 . Let", "a. Find", "4) The"): a new item, never a continuation.
ENUMERATOR = regex.compile(r"^\s*[(\[]?(?:\p{N}{1,3}|\p{L})\s*[.)\]]\s")


@dataclass
class UnitEdge:
    """Features of one final unit (or table) at a page edge."""

    id: str
    kind: str
    stream_kind: str
    role: str  # float, heading, set_apart, body
    first_line: str = ""
    last_line: str = ""
    lines: int = 0
    style: tuple = ()
    size: float = 0.0
    width: float = 0.0
    indent: float | None = None  # first line, font sizes past the other lines' start
    fill: float | None = None  # last line, font sizes short of the unit's end
    tail: str = ""  # NFKC end of the last line (evidence only)
    head: str = ""  # NFKC start of the first line (evidence only)
    marker: bool = False
    list_id: str | None = None
    open_start: bool = False  # lists stage: an indented line without an open entry
    run_in: bool = False  # opens with a run-in heading (structure stage)
    linked: bool = False  # a float linked to a table or figure (title, note, caption, credit)
    first_frame: object = None  # Frame of the first line (start, end, block, size)
    last_frame: object = None
    boundary: tuple = ()


@dataclass
class PageEdges:
    page: int
    navigation: str | None
    label: str | None
    label_source: str
    items: list = field(default_factory=list)  # [UnitEdge] in main-flow order


def _text(store, line):
    raw = "".join(store.spans[s].raw_text for s in line.span_ids)
    return unicodedata.normalize("NFKC", raw)


def unit_style(store, lines):
    """The dominant style of a unit's lines (by characters)."""
    votes = Counter()
    for line in lines:
        votes[_style(store, line)] += max(1, len(_text(store, line).strip()))
    return votes.most_common(1)[0][0] if votes else ("", 0.0, False, False)


def same_style(a, b):
    return bool(a) and bool(b) and a[0] == b[0] and abs(a[1] - b[1]) <= 0.5 and a[2:] == b[2:]


def unit_edge(unit, store, lines, role):
    members = [lines[lid] for lid in unit.line_ids if lid in lines]
    frames = [frame(line) for line in members]
    size = median(f.size for f in frames) if frames else 1.0
    start = min(f.start for f in (frames[1:] or frames)) if frames else 0.0
    end = max(f.end for f in frames) if frames else 0.0
    many = len(frames) >= 2
    return UnitEdge(
        id=unit.id,
        kind=unit.kind,
        stream_kind=unit.stream_kind,
        role=role,
        first_line=unit.line_ids[0],
        last_line=unit.line_ids[-1],
        lines=len(unit.line_ids),
        style=unit_style(store, members),
        size=size,
        width=(end - min(f.start for f in frames)) if frames else 0.0,
        indent=((frames[0].start - start) / size) if many else None,
        fill=((end - frames[-1].end) / size) if many else None,
        tail=_text(store, members[-1]).rstrip()[-24:] if members else "",
        head=_text(store, members[0]).lstrip()[:24] if members else "",
        marker=getattr(unit, "marker", None) is not None,
        list_id=getattr(unit, "list_id", None),
        open_start="indented line without an open entry" in unit.boundary.reasons,
        boundary=tuple(unit.boundary.reasons),
        first_frame=frames[0] if frames else None,
        last_frame=frames[-1] if frames else None,
    )


def _equation_items(equations, stream_id):
    """{after line id (None: stream start): [UnitEdge]} of the display equation units
    anchored in the main stream, in their anchor order (floats: they never break a
    continuation and are skipped at the page edges)."""
    found = {}
    for unit in sorted(equations, key=lambda u: (u.anchor.position, u.anchor.order)):
        if unit.anchor.stream_id != stream_id:
            continue
        found.setdefault(unit.anchor.after_line_id, []).append(
            UnitEdge(id=unit.id, kind="equation", stream_kind="main", role="float")
        )
    return found


def page_edges(number, store, layout, units, order, tables, claimed, headings, body,
               navigation=None, label=None, label_source="none", equations=()):  # fmt: skip
    """PageEdges of one page.

    ``units``: the final unit view; ``tables``: text-owning table records; ``claimed``: unit
    ids a figure links (caption, credit, internal text); ``headings``: (heading unit ids,
    ids of units opening with a run-in heading) of the structure stage; ``body``: the book's
    body style (``None`` before it is known); ``equations``: the page's display equation
    units (read at their anchors as floats)."""
    headings, run_in = headings
    lines = {line.id: line for line in layout.lines}
    table_of = {lid: t for t in tables for lid in t.line_ids}
    table_texts = {t.unit_id for table in tables for t in [table.title, *table.notes]
                   if t is not None and t.unit_id is not None}  # fmt: skip
    unit_of = {lid: u for u in units for lid in u.line_ids}
    items, seen = [], set()
    for stream in order.streams:
        if stream.kind != "main":
            continue
        anchored = _equation_items(equations, stream.id)
        items.extend(anchored.pop(None, []))
        for lid in stream.line_ids:
            _main_item(lid, table_of, unit_of, seen, items, claimed, table_texts, headings,
                       run_in, store, lines, body, navigation)  # fmt: skip
            pending = anchored.pop(lid, [])
            unit = unit_of.get(lid)
            if pending and (unit is None or unit.line_ids[-1] == lid or lid in table_of):
                items.extend(pending)  # between two items: a float at this place
            # An equation anchored inside a unit (its text goes on after it) is not an edge.
    return PageEdges(page=number, navigation=navigation, label=label, label_source=label_source,
                     items=items)  # fmt: skip


def _main_item(lid, table_of, unit_of, seen, items, claimed, table_texts, headings, run_in,
               store, lines, body, navigation):  # fmt: skip
    """Append the item of main-stream line ``lid`` the first time its unit or table is met."""
    table = table_of.get(lid)
    if table is not None:
        if table.id not in seen:
            seen.add(table.id)
            items.append(UnitEdge(id=table.id, kind="table", stream_kind="main", role="float",
                                  linked=True))  # fmt: skip
        return
    unit = unit_of.get(lid)
    if unit is None or unit.id in seen or unit.kind in FURNITURE:
        return
    seen.add(unit.id)
    if unit.kind in FLOAT_KINDS or unit.id in claimed or unit.id in table_texts:
        role = "float"
    elif unit.id in headings:
        role = "heading"
    elif unit.kind == "heading_candidate":
        role = "set_apart"
    else:
        role = "body"
    edge = unit_edge(unit, store, lines, role)
    edge.run_in = unit.id in run_in
    edge.linked = unit.id in claimed or unit.id in table_texts
    entries = unit.kind in LINKED_ENTRIES and navigation in ENTRY_PAGES
    if role == "body" and body is not None and not entries and not same_style(edge.style, body):
        edge.role = "set_apart"
    items.append(edge)


def end_kind(tail):
    """How a unit's last line ends: hyphen, terminal (sentence end), locator, open."""
    if HYPHEN_END.search(tail):
        return "hyphen"
    if SENTENCE_END.search(tail):
        return "terminal"
    if LOCATOR_END.search(tail):
        return "locator"
    return "open"


def start_kind(head):
    """How a unit's first line starts: enumerator, lower, upper, digit, other (first letter
    or digit)."""
    if ENUMERATOR.match(head):
        return "enumerator"
    for ch in head:
        if ch.isalpha():
            return "lower" if ch.islower() else ("upper" if ch.isupper() else "other")
        if ch.isdigit():
            return "digit"
    return "other"


def column_change(a, b):
    """B's first line begins a new column after A's last line: it starts past A's last line
    end and above it, in the lines' reading frame."""
    fa, fb = a.last_frame, b.first_frame
    if fa is None or fb is None:
        return False
    return fb.start >= fa.end - 0.5 * fa.size and fb.block < fa.block - 0.5 * fa.size
