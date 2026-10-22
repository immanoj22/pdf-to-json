"""One page's lists and entries over the Step 9 units (Step 11).

Each list-capable stream (main flow, sidebars, callouts, notes, cards, credits; not figure or
table text, which later steps decide) is read in its order. Consecutive Step 9 units that may
hold list text (paragraphs, list candidates, heading candidates that Step 10 did not make
headings) form blocks; a block is segmented by the page's printed-navigation kind (Step 10):

- **Index**: per lane, a line at the base indent starts an entry. An indented line continues
  it unless the previous line completed an entry (it ends with a locator, or ends early
  although the next word would have fitted) and the line does not start with a locator: then
  it is a sub-entry, its level from the indent rank. One- or two-letter lines are dividers.
  Locators link to physical pages through the Step 8 labels.
- **Glossary**: entries in entry order (``lists.glossary``); a new cell or a leading term
  starts an entry; a page-reference line attaches to the entry before it. A glossary page
  whose entries the layout set in a table region is read the same way: its table streams
  and table-text units are entry text there (the tables stage keeps such a page's table a
  possible table, so the lines stay in these entries).
- **Bibliography**: in a reference-like hanging-indent block (most entries carry a year),
  a base-indent line starts an entry.
- **Contents and other lists**: every Step 9 unit (one per printed entry) is an entry; its
  level is the indent rank of its first line.
- **Elsewhere**: marked lists (bullets, dashes, numbers, letters and Roman numerals with
  sequence evidence), nested by marker indent and type, with hanging continuation lines;
  definition runs (two or more lines opening with a heavier term ended by a wide separator);
  unmarked lists (three or more one-line units of one style, start and pitch, none ending a
  sentence).

Lines outside list segments keep their Step 9 units. An item is split from or merged over
Step 9 units only at line boundaries and in stream order; a Step 10 heading unit is never
split or merged. No figure, table or math is decided here.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median

import regex

from book_core.extraction.fingerprints import stable_id
from book_core.lists.glossary import entry_order, reorder_stream
from book_core.lists.joins import new_join
from book_core.lists.lines import line_evidence, refs_for, sequence_markers
from book_core.lists.models import (
    REVIEW_BELOW,
    ItemUnit,
    Locator,
    Marker,
    PageLists,
    StructuredList,
)
from book_core.lists.roles import list_role
from book_core.model.common import Provenance
from book_core.paragraphs.inline import style_runs
from book_core.paragraphs.models import Boundary
from book_core.paragraphs.segment import LANE_CHANGES

LISTS_VERSION = "lists-1"
DEFAULT_CONFIG = {
    "indent": 0.8,  # font sizes: a deeper marker or a hanging continuation
    "continuation_gap": 1.9,  # font sizes of baseline advance a continuation may span
    "max_definition_lines": 6,
    "row_sync": 0.6,
    "unmarked_min_items": 3,
    "reference_year_share": 0.5,
    "question_share": 0.6,
}
LIST_STREAMS = frozenset({"main", "sidebar", "callout", "card", "note", "credit"})
ELIGIBLE = frozenset({"paragraph", "list_item_candidate", "heading_candidate"})
# On a glossary page, a table region holds glossary entries: its stream and units are read.
GLOSSARY_STREAMS = LIST_STREAMS | {"table"}
GLOSSARY_ELIGIBLE = ELIGIBLE | {"table_text"}
COLUMN_GAP = 4.0  # font sizes between line starts of two columns
CLASSIC_BULLETS = frozenset("•‣⁃∙⋅∘◦▪▫●○■□◆◇►▶➢➤✓✔※·")
_YEAR = regex.compile(r"(?<!\p{N})(1[5-9]\p{N}{2}|20\p{N}{2})(?!\p{N})")
_STARTS_LOCATOR = regex.compile(r"^\s*\p{L}{0,3}\p{N}")
_WORD = regex.compile(r"\S+")
_TERMINAL = regex.compile(r"[.!?。！？؟]\s*[\"'”’»)]*\s*$")
NAV_MODES = {"index": "index", "glossary": "glossary", "bibliography": "bibliography",
             "table_of_contents": "contents", "other_list": "contents"}  # fmt: skip


@dataclass
class PageContext:
    """What Step 11 knows about a page beyond its Step 9 units (Steps 8 and 10)."""

    navigation: str | None = None
    heading_units: frozenset = frozenset()  # Step 10 headings: never split or merged
    run_in_units: frozenset = frozenset()  # units opening with a Step 10 run-in heading
    label_pages: dict = field(default_factory=dict)  # printed label -> [physical pages]
    vocabulary: dict = field(default_factory=dict)
    compounds: dict = field(default_factory=dict)
    config: dict = field(default_factory=lambda: dict(DEFAULT_CONFIG))


@dataclass
class Segment:
    lines: list
    kind: str
    reasons: list
    confidence: float = 0.8
    marker: object = None
    level: int = 1
    list_key: tuple | None = None
    item_role: str | None = None
    term: tuple | None = None  # (line id, raw end offset)
    joins: dict = field(default_factory=dict)  # (a, b) -> (kind, confidence, reasons)


@dataclass
class ListDraft:
    key: tuple
    kind: str
    marker_type: str | None
    start: int | None
    level: int
    parent: object = None  # Segment of the parent item
    items: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    signature: tuple = ()
    last_value: int | None = None
    marker_start: float = 0.0
    confidence: float = 0.8


def _median(values, default=0.0):
    values = list(values)
    return median(values) if values else default


def lane_runs(block, edge_kind):
    runs = [[block[0]]]
    for a, b in zip(block, block[1:], strict=False):
        if edge_kind.get((a.id, b.id)) in LANE_CHANGES:
            runs.append([b])
        else:
            runs[-1].append(b)
    return runs


def indent_ranks(run):
    """{line id: indent rank} for one lane run (0 = base), and the lane's line end edge."""
    text = [line for line in run if not line.blank]
    if not text:
        return {}, 0.0
    size = _median(line.size for line in text)
    starts = sorted(line.start for line in text)
    # The base indent is the leftmost start that at least two lines share (a lone stray line
    # does not set it). A quantile would fail in a column of long wrapped entries, where
    # nearly every line is an indented continuation.
    base = next((a for a, b in zip(starts, starts[1:], strict=False) if b - a <= 0.4 * size),
                starts[int(0.1 * (len(starts) - 1))])  # fmt: skip
    centres = []
    for start in starts:
        if start < base - 0.4 * size:
            continue
        if centres and start - centres[-1][-1] <= 0.4 * size:
            centres[-1].append(start)
        else:
            centres.append([start])
    centres = [_median(c) for c in centres]
    ranks = {}
    for line in text:
        if line.start < base + 0.4 * size:
            ranks[line.id] = 0
        else:
            ranks[line.id] = min(range(len(centres)), key=lambda i: abs(centres[i] - line.start))
    ends = sorted(line.end for line in text)
    return ranks, ends[int(0.9 * (len(ends) - 1))]


def column_ranks(block):
    """({line id: indent rank}, {line id: column}, {column: (start, line end edge)}).

    Columns are clusters of line starts separated by more than COLUMN_GAP font sizes (indent
    steps are smaller), so a column whose lane run holds only continuation lines still
    measures indents from its column's base, and narrow gutters do not merge columns.
    """
    text = [line for line in block if not line.blank]
    if not text:
        return {}, {}, {}
    size = _median(line.size for line in text)
    columns = []
    for line in sorted(text, key=lambda x: x.start):
        if columns and line.start - columns[-1][-1].start <= COLUMN_GAP * size:
            columns[-1].append(line)
        else:
            columns.append([line])
    ranks, column_of, edges = {}, {}, {}
    for index, lines in enumerate(columns):
        column_ranks_, edge = indent_ranks(lines)
        ranks.update(column_ranks_)
        edges[index] = (min(line.start for line in lines), edge)
        for line in lines:
            column_of[line.id] = index
    return ranks, column_of, edges


def hanging_votes(run, ranks, edge):
    """(hanging votes, prose votes): a full base line running into an indented line is an
    entry wrapping; a short base line before an indented line ends a prose paragraph."""
    text = [line for line in run if not line.blank]
    hanging = prose = 0
    for a, b in zip(text, text[1:], strict=False):
        full = (edge - a.end) / a.size < 2.5
        if ranks.get(a.id) == 0 and ranks.get(b.id, 0) > 0:
            hanging += full
            prose += not full
        elif ranks.get(a.id, 0) > 0 and ranks.get(b.id) == 0:
            hanging += not full
            prose += full
    return hanging, prose


class PageLister:
    def __init__(self, page, layout, paragraphs, context):
        self.page, self.layout, self.paragraphs, self.context = page, layout, paragraphs, context
        self.config = context.config
        self.lines = {line.id: line for line in layout.lines}
        self.unit_of = {lid: u for u in paragraphs.units for lid in u.line_ids}
        self.order = paragraphs.order
        self.evidence = {}
        for stream in self.order.streams:
            for lid in stream.line_ids:
                self.evidence[lid] = line_evidence(
                    page.store, self.lines[lid], stream, self.unit_of[lid]
                )
        self.step9_joins = {(j.previous_line_id, j.next_line_id): j
                            for u in paragraphs.units for j in u.joins}  # fmt: skip
        self.order_changes = []
        self.cells = {}
        self.drafts = []
        glossary = NAV_MODES.get(context.navigation) == "glossary"
        self.list_streams = GLOSSARY_STREAMS if glossary else LIST_STREAMS
        self.eligible = GLOSSARY_ELIGIBLE if glossary else ELIGIBLE

    # ------------------------------------------------------------------ blocks
    def blocks(self, stream):
        blocks, current = [], []
        for lid in stream.line_ids:
            line = self.evidence[lid]
            eligible = (
                line.unit_kind in self.eligible and line.unit_id not in self.context.heading_units
            )
            if eligible:
                current.append(line)
            elif current:
                blocks.append(current)
                current = []
        if current:
            blocks.append(current)
        return blocks

    def edge_kind(self):
        return {(e.source, e.target): e.kind for e in self.order.edges}

    # ------------------------------------------------------------------ glossary order
    def glossary_order(self):
        ids = [s.id for s in self.order.streams if s.kind in self.list_streams]
        for stream_id in ids:
            stream = next(s for s in self.order.streams if s.id == stream_id)
            for block in self.blocks(stream):
                new, cells, evidence = entry_order(block, self.config)
                if new is None or [line.id for line in new] == [line.id for line in block]:
                    continue
                self.order, decision = reorder_stream(
                    self.order, stream_id, [line.id for line in block],
                    [line.id for line in new], evidence,
                    ["glossary entry order: term then definition, entry by entry, first column "
                     "first; a page reference attaches to its entry (reference convention)"],
                )  # fmt: skip
                self.order_changes.append(decision)
                self.cells.update(cells)

    # ------------------------------------------------------------------ segmenters
    def segment_block(self, block, edge_kind):
        mode = NAV_MODES.get(self.context.navigation)
        if mode == "index":
            return self.index_entries(block, edge_kind)
        if mode == "glossary":
            return self.glossary_entries(block, edge_kind)
        if mode == "contents":
            return self.contents_entries(block, edge_kind)
        if mode == "bibliography":
            segments = self.reference_entries(block, edge_kind)
            if segments is not None:
                return segments
        return self.general(block, edge_kind)

    def _divider(self, line):
        letters = sum(c.isalpha() for c in line.text)
        return letters <= 2 and not any(c.isdigit() for c in line.text)

    def index_entries(self, block, edge_kind):
        segments, current = [], None
        key = ("index", block[0].id)
        ranks, column_of, edges = column_ranks(block)
        for line in block:
            if line.blank:
                if current is not None:
                    current.lines.append(line)
                continue
            if self._divider(line):
                segments.append(Segment([line], "", ["one- or two-letter divider line"]))
                current = None
                continue
            rank = ranks.get(line.id, 0)
            if current is None or rank == 0:
                current = Segment([line], "index_entry", ["base indent: a new index entry"],
                                  0.85, level=1, list_key=key, item_role="entry")  # fmt: skip
                if rank > 0:
                    current.reasons = ["indented line without an open entry"]
                    current.confidence = 0.6
                segments.append(current)
                continue
            previous = current.lines[-1]
            same_column = column_of.get(previous.id) == column_of.get(line.id)
            start, edge = edges.get(column_of.get(line.id), (line.start, line.end))
            words = _WORD.findall(line.raw)
            room = edge - previous.end
            fits = (
                same_column
                and bool(words)
                and room > max((len(words[0]) + 1) * 0.6 * line.size, 0.35 * (edge - start))
            )  # a clearly short line: the entry heading ended there
            complete = previous.tail_locator and not previous.open_end
            locator_start = bool(_STARTS_LOCATOR.match(line.raw))
            if not locator_start and not previous.open_end and (complete or fits):
                why = ("previous line completes its entry with a locator" if complete else
                       "previous line ends early although the next word fits")  # fmt: skip
                current = Segment([line], "index_entry", [f"indented: a sub-entry ({why})"],
                                  0.75, level=min(rank + 1, 3), list_key=key,
                                  item_role="sub_entry")  # fmt: skip
                segments.append(current)
            else:
                kind = "line" if same_column else "column"
                current.lines.append(line)
                current.joins[(previous.id, line.id)] = (
                    kind, 0.8, ["index entry continues: indented line after an open line"],
                )  # fmt: skip
        return segments

    def glossary_entries(self, block, edge_kind):
        segments, current = [], None
        key = ("glossary", block[0].id)
        for line in block:
            cell = self.cells.get(line.id)
            if line.blank:
                if current is not None:
                    current.lines.append(line)
                continue
            if line.page_ref and current is not None:
                current.lines.append(line)
                current.joins[(current.lines[-2].id, line.id)] = (
                    "column", 0.8, ["page reference attached to its entry"],
                )  # fmt: skip
                continue
            new_cell = current is None or (cell is not None and cell != self.cells.get(
                current.lines[0].id))  # fmt: skip
            if new_cell or line.term_end is not None:
                reasons = ["a leading term starts a glossary entry"] if line.term_end is not None \
                    else ["a new glossary cell (row and column)"]  # fmt: skip
                current = Segment(
                    [line],
                    "definition_entry",
                    reasons,
                    0.85,
                    list_key=key,
                    item_role="entry",
                    term=(line.id, line.term_end) if line.term_end else None,
                )
                segments.append(current)
            else:
                previous = current.lines[-1]
                current.lines.append(line)
                current.joins[(previous.id, line.id)] = (
                    "line", 0.8, ["glossary entry continues in its cell"],
                )  # fmt: skip
        return segments

    def contents_entries(self, block, edge_kind):
        segments, key = [], ("contents", block[0].id)
        ranks = column_ranks(block)[0]
        current_unit = None
        for line in block:
            if line.unit_id != current_unit:
                current_unit = line.unit_id
                segments.append(Segment([line], "contents_entry",
                                        ["printed navigation entry (one Step 9 unit)"], 0.8,
                                        level=ranks.get(line.id, 0) + 1, list_key=key,
                                        item_role="entry"))  # fmt: skip
            else:
                segments[-1].lines.append(line)
        return segments

    def reference_entries(self, block, edge_kind):
        """Hanging-indent reference entries, or None when the block is not reference-like."""
        segments, key = [], ("bibliography", block[0].id)
        ranks, column_of, edges = column_ranks(block)
        hanging_total = prose_total = 0
        for column, (_, edge) in edges.items():
            lines = [line for line in block if column_of.get(line.id) == column]
            votes = hanging_votes(lines, ranks, edge)
            hanging_total += votes[0]
            prose_total += votes[1]
        current = None
        for line in block:
            if line.blank:
                if current is not None:
                    current.lines.append(line)
                continue
            if current is None or ranks.get(line.id, 0) == 0:
                current = Segment([line], "bibliography_entry",
                                  ["base indent: a new reference entry"], 0.8,
                                  list_key=key, item_role="entry")  # fmt: skip
                if ranks.get(line.id, 0) > 0:
                    current.reasons = ["indented line without an open entry"]
                    current.confidence = 0.6
                segments.append(current)
            else:
                previous = current.lines[-1]
                same = column_of.get(previous.id) == column_of.get(line.id)
                current.lines.append(line)
                current.joins[(previous.id, line.id)] = (
                    "line" if same else "column", 0.8,
                    ["reference entry continues: hanging indent"],
                )  # fmt: skip
        dated = sum(any(_YEAR.search(line.text) for line in s.lines) for s in segments)
        if (hanging_total <= prose_total or len(segments) < 2
                or dated / len(segments) < self.config["reference_year_share"]):  # fmt: skip
            return None
        return segments

    # ------------------------------------------------------------------ general lists
    def general(self, block, edge_kind):
        kept = sequence_markers(block)
        for line in block:
            m = line.marker
            if m is None:
                continue
            if m.type in {"bullet", "dash"}:
                glyph = m.signature[1]
                same = [x for x in block if x.marker is not None
                        and x.marker.signature == m.signature
                        and abs(x.start - line.start) <= 0.5 * line.size]  # fmt: skip
                if (m.type == "dash" or glyph not in CLASSIC_BULLETS) and len(same) < 2:
                    line.marker = None  # a lone dash or symbol: dialogue, a sign, not a list
        segments = self.marked(block, edge_kind, kept)
        segments = self.definitions(segments, edge_kind)
        return self.unmarked(segments)

    def marked(self, block, edge_kind, kept):
        """Segments: list items for marked lines and their continuations, plain otherwise."""
        segments, stack, current = [], [], None
        for index, line in enumerate(block):
            previous = block[index - 1] if index else None
            m = line.marker
            if m is not None:
                text_start = line.text_start
                following = block[index + 1] if index + 1 < len(block) else None
                if line.own_marker_line and following is not None:
                    text_start = following.start  # the item text is the next line (same row)
                marker_start = line.start
                # A new column: a lane transition, or geometry (the marker sits above the
                # previous line, or starts beyond its end), so indents are not comparable.
                lane_change = previous is not None and (
                    edge_kind.get((previous.id, line.id)) in LANE_CHANGES
                    or line.block < previous.block - 0.35 * line.size
                    or line.start > previous.end
                )
                draft = self._place(stack, m, marker_start, line, lane_change)
                reason = kept.get(line.id) or (
                    "marker line: a marker alone on its line opens the item" if line.own_marker_line
                    else f"{m.type.replace('_', ' ')} marker starts a list item"
                )  # fmt: skip
                current = Segment([line], "list_item", [reason], 0.9 if m.type != "dash" else 0.75,
                                  marker=m, level=draft.level, list_key=draft.key,
                                  item_role="item")  # fmt: skip
                current.text_start = text_start if text_start is not None else line.start
                current.marker_start = marker_start
                draft.items.append(current)
                segments.append(current)
                continue
            if current is not None and previous is not None:
                why = self._continues(current, previous, line, edge_kind)
                if why:
                    kind = (
                        "column"
                        if edge_kind.get((previous.id, line.id)) in LANE_CHANGES
                        else (
                            "row" if abs(line.block - previous.block) < 0.35 * line.size else "line"
                        )
                    )
                    if kind == "column" or line.block < previous.block - 0.35 * line.size:
                        # The item goes on in another column: open lists move with it.
                        shift = line.start - previous.start
                        for open_list in stack:
                            open_list.marker_start += shift
                        current.marker_start += shift
                        current.text_start += shift
                    current.lines.append(line)
                    current.joins[(previous.id, line.id)] = (kind, 0.8, [why])
                    continue
            current = None
            stack.clear()
            segments.append(Segment([line], "", ["not a list line"]))
        return segments

    def _continues(self, item, previous, line, edge_kind):
        """Why ``line`` continues the open item, or None."""
        if line.blank:
            return None
        joined = (previous.id, line.id) in self.step9_joins
        if joined and line.unit_id not in self.context.heading_units:
            return "Step 9 joined the line: the item continues"
        if edge_kind.get((previous.id, line.id)) in LANE_CHANGES:
            return None
        if abs(line.size - previous.size) > 0.25 * previous.size:
            return None
        gap = (line.block - previous.block) / max(previous.size, 0.1)
        if not 0 < gap <= self.config["continuation_gap"]:
            return None
        indent = self.config["indent"]
        hanging = line.start >= item.text_start - 0.5 * line.size and (
            line.start > item.marker_start + indent * 0.5 * line.size
        )  # fmt: skip
        if hanging and line.marker is None:
            return "hanging continuation aligned with the item text"
        return None

    def _place(self, stack, m, start, line, lane_change=False):
        """The list draft an item with marker ``m`` at inline ``start`` joins (nesting).

        After a column or band change, indents of the previous column mean nothing: a marker
        that continues an open list's sequence re-anchors that list at its new position;
        otherwise the stack is closed and a new list starts.
        """
        size, indent = line.size, self.config["indent"]
        if lane_change and stack:
            match = next(
                (d for d in reversed(stack)
                 if d.marker_type == m.type and d.signature == m.signature
                 and (m.value is None or d.last_value is None or m.value == d.last_value + 1)),
                None,
            )  # fmt: skip
            if match is not None:
                while stack[-1] is not match:
                    stack.pop()
                match.marker_start, match.last_value = start, m.value
                match.reasons.append("the list continues in the next column")
                return match
            stack.clear()
        while stack and start < stack[-1].marker_start - 0.5 * size:
            stack.pop()
        parent = None
        if stack:
            top = stack[-1]
            same = top.marker_type == m.type and top.signature == m.signature
            if start > top.marker_start + indent * size and top.items:
                parent = top.items[-1]
            elif same:
                if m.value is not None and top.last_value is not None and m.value <= top.last_value:
                    stack.pop()  # restart: a new list at the same level
                    return self._open(stack, m, start, line, top.level, top.parent,
                                      "numbering restarts")  # fmt: skip
                if (
                    m.value is not None
                    and top.last_value is not None
                    and m.value > top.last_value + 1
                ):
                    top.reasons.append("numbering skips a value")
                top.last_value = m.value
                return top
            else:
                ancestor = next(
                    (d for d in reversed(stack[:-1]) if d.marker_type == m.type
                     and d.signature == m.signature), None,
                )  # fmt: skip
                if ancestor is not None:
                    while stack[-1] is not ancestor:
                        stack.pop()
                    ancestor.last_value = m.value
                    return ancestor
                finer = {"decimal": 0, "upper_alpha": 1, "upper_roman": 1, "lower_alpha": 2,
                         "lower_roman": 2, "bullet": 3, "dash": 3}  # fmt: skip
                if finer[m.type] > finer[top.marker_type] and top.items:
                    parent = top.items[-1]
                else:
                    stack.pop()
                    return self._open(stack, m, start, line, top.level, top.parent,
                                      "marker type changes: a new list")  # fmt: skip
        level = stack[-1].level + 1 if parent is not None else 1
        why = "deeper marker: a nested list" if parent is not None else "first marker of a list"
        return self._open(stack, m, start, line, level, parent, why)

    def _open(self, stack, m, start, line, level, parent, why):
        kind = {"bullet": "bulleted", "dash": "bulleted", "decimal": "numbered",
                "lower_alpha": "lettered", "upper_alpha": "lettered",
                "lower_roman": "numbered", "upper_roman": "numbered"}[m.type]  # fmt: skip
        draft = ListDraft(
            key=("marked", line.id), kind=kind, marker_type=m.type, start=m.value, level=level,
            parent=parent, reasons=[why], signature=m.signature, last_value=m.value,
            marker_start=start,
        )  # fmt: skip
        stack.append(draft)
        self.drafts.append(draft)
        return draft

    def definitions(self, segments, edge_kind):
        """Definition runs among plain lines: two or more term lines at one start."""
        out, run = [], []

        def flush():
            out.extend(self._definition_run(run, edge_kind))
            run.clear()

        for segment in segments:
            if segment.kind:
                flush()
                out.append(segment)
            else:
                run.append(segment.lines[0])
        flush()
        return out

    def _definition_run(self, lines, edge_kind):
        plain = [Segment([line], "", ["not a list line"]) for line in lines]
        terms = [line for line in lines if line.term_end is not None and line.marker is None
                 and line.unit_id not in self.context.run_in_units
                 and self._wide_separator(line)]  # fmt: skip
        if len(terms) < 2:
            return plain
        segments, current, key = [], None, ("definition", terms[0].id)
        term_ids = {line.id for line in terms}
        for index, line in enumerate(lines):
            previous = lines[index - 1] if index else None
            if line.id in term_ids:
                current = Segment(
                    [line],
                    "definition_entry",
                    ["a heavier leading term ended by a wide separator"],
                    0.8,
                    list_key=key,
                    item_role="entry",
                    term=(line.id, line.term_end),
                )
                segments.append(current)
                continue
            joined = previous is not None and (previous.id, line.id) in self.step9_joins
            short = (
                current is not None and len(current.lines) < self.config["max_definition_lines"]
            )  # the limit binds only continuations Step 9 did not join
            if (current is not None and previous is not None and not line.blank
                    and (joined or (short and self._definition_continues(
                        current, previous, line, edge_kind)))):  # fmt: skip
                current.joins[(previous.id, line.id)] = ("line", 0.75, ["definition continues"])
                current.lines.append(line)
                continue
            current = None
            segments.append(Segment([line], "", ["not a list line"]))
        return segments

    def _wide_separator(self, line):
        joint = line.raw[max(0, line.term_end - 2) : line.term_end + 3]
        return bool(regex.search(r"[\t  ]|\s{2,}", joint))

    def _definition_continues(self, entry, previous, line, edge_kind):
        if (previous.id, line.id) in self.step9_joins:
            return True
        if edge_kind.get((previous.id, line.id)) in LANE_CHANGES:
            return False
        gap = (line.block - previous.block) / max(previous.size, 0.1)
        start = entry.lines[0].start
        return 0 < gap <= self.config["continuation_gap"] and line.start >= start - 0.5 * line.size

    def unmarked(self, segments):
        """Runs of one-line plain units of one style, start and pitch, none ending a sentence."""
        out, run = [], []
        minimum = self.config["unmarked_min_items"]

        def flush():
            if len(run) >= minimum and self._uniform(run):
                key = ("unmarked", run[0].lines[0].id)
                for segment in run:
                    out.append(Segment(segment.lines, "list_item",
                                       ["unmarked list: one-line units of one style, start and "
                                        "pitch, none ending a sentence"], 0.65,
                                       list_key=key, item_role="item"))  # fmt: skip
            else:
                out.extend(run)
            run.clear()

        for segment in segments:
            line = segment.lines[0]
            whole = not segment.kind and self._whole_unit(line)
            if whole and not _TERMINAL.search(line.text) and not line.blank:
                run.append(segment)
            else:
                flush()
                out.append(segment)
        flush()
        return out

    def _whole_unit(self, line):
        unit = self.unit_of[line.id]
        return len(unit.line_ids) == 1 and unit.kind in {"paragraph", "list_item_candidate"}

    def _uniform(self, run):
        lines = [s.lines[0] for s in run]
        size = lines[0].size
        if any(abs(x.size - size) > 0.25 for x in lines):
            return False
        if any(abs(x.start - lines[0].start) > 0.5 * size for x in lines):
            return False
        if len({round(x.bold_share) for x in lines}) > 1:
            return False
        advances = [b.block - a.block for a, b in zip(lines, lines[1:], strict=False)]
        if any(a <= 0 for a in advances):
            return False
        typical = _median(advances)
        return typical <= 2.2 * size and all(abs(a - typical) <= 0.25 * typical for a in advances)

    # ------------------------------------------------------------------ assembly
    def build(self, resolved_device="cpu"):
        if NAV_MODES.get(self.context.navigation) == "glossary":
            self.glossary_order()
        edge_kind = self.edge_kind()
        segment_of = {}
        for stream in self.order.streams:
            if stream.kind not in self.list_streams:
                continue
            for block in self.blocks(stream):
                for segment in self.segment_block(block, edge_kind):
                    if segment.kind:
                        for line in segment.lines:
                            segment_of[line.id] = segment
        units, lists = self._units(segment_of, edge_kind)
        return PageLists(
            source_sha256=self.layout.source_sha256,
            page=self.layout.page,
            lists_version=LISTS_VERSION,
            units=units,
            order=self.order,
            order_changes=self.order_changes,
            provenance=Provenance(
                source_sha256=self.layout.source_sha256,
                engine="book_core.lists",
                engine_version=LISTS_VERSION,
                method="derived",
                resolved_device=resolved_device,
            ),
        ), lists

    def _sid(self, *parts):
        return stable_id(self.layout.source_sha256, self.layout.page, *parts)

    def _units(self, segment_of, edge_kind):
        units, item_of_segment = [], {}
        for stream in self.order.streams:
            groups = []
            for lid in stream.line_ids:
                segment = segment_of.get(lid)
                key = ("segment", id(segment)) if segment is not None else (
                    "unit", self.unit_of[lid].id)  # fmt: skip
                if groups and groups[-1][0] == key:
                    groups[-1][1].append(lid)
                else:
                    groups.append((key, [lid]))
            for (kind, _), line_ids in groups:
                if kind == "unit":
                    units.append(self._plain(stream, line_ids, edge_kind))
                else:
                    segment = segment_of[line_ids[0]]
                    unit = self._item(stream, segment, line_ids, edge_kind)
                    item_of_segment[id(segment)] = unit
                    units.append(unit)
        lists = self._lists(units, item_of_segment, segment_of)
        list_of = {item_id: lst.id for lst in lists for item_id in lst.item_ids}
        units = [u.model_copy(update={"list_id": list_of[u.id]}) if u.id in list_of else u
                 for u in units]  # fmt: skip
        position = {u.id: i for i, u in enumerate(units)}
        by_id = {u.id: u for u in units}
        roled = []
        for lst in lists:
            items = [by_id[i] for i in lst.item_ids]
            role, why = list_role(lst, items, units, position, self.context, self.evidence,
                                  self.config)  # fmt: skip
            roled.append(lst.model_copy(update={"role": role, "reasons": [*lst.reasons, why]}))
        return units, roled

    def _plain(self, stream, line_ids, edge_kind):
        unit = self.unit_of[line_ids[0]]
        if line_ids == unit.line_ids:
            return ItemUnit(**{k: v for k, v in unit.model_dump().items()
                               if k not in {"continues_from", "continues_to"}},
                            source_unit_ids=[unit.id])  # fmt: skip
        position = unit.line_ids.index(line_ids[0])
        boundary = unit.boundary if position == 0 else Boundary(
            confidence=0.8, reasons=["the rest of a Step 9 unit after a list item"],
        )  # fmt: skip
        return self._make(stream, line_ids, unit.kind, [unit.id], boundary, {}, edge_kind,
                          namespace="part")  # fmt: skip

    def _item(self, stream, segment, line_ids, edge_kind):
        sources = list(dict.fromkeys(self.unit_of[lid].id for lid in line_ids))
        confidence = round(segment.confidence, 4)
        boundary = Boundary(confidence=confidence, reasons=segment.reasons,
                            review_required=confidence < REVIEW_BELOW)  # fmt: skip
        unit = self._make(stream, line_ids, segment.kind, sources, boundary, segment.joins,
                          edge_kind, namespace="item")  # fmt: skip
        update = {"item_role": segment.item_role, "level": segment.level}
        first = self.evidence[line_ids[0]]
        if segment.marker is not None:
            m = segment.marker
            update["marker"] = Marker(
                refs=refs_for(first.spans, m.start, m.end), type=m.type, value=m.value,
                punctuation=m.punctuation, padded=m.padded, own_line=first.own_marker_line,
            )  # fmt: skip
        if segment.term is not None:
            line = self.evidence[segment.term[0]]
            after = segment.marker.end if segment.marker is not None and line is first else 0
            after += len(line.raw[after:]) - len(line.raw[after:].lstrip())
            refs = refs_for(line.spans, after, segment.term[1])
            if refs:
                update["term"] = refs
        if segment.kind == "index_entry":
            update["locators"] = self._locators(line_ids)
            refs = self._index_term(line_ids)
            if refs:
                update["term"] = refs
        if segment.kind == "list_item" and self.evidence[line_ids[-1]].question:
            update["item_role"] = "question"
        return unit.model_copy(update=update)

    def _index_term(self, line_ids):
        """The entry heading: the first line's text before its first locator."""
        first = self.evidence[line_ids[0]]
        cut = first.locators[0][0] if first.locators else len(first.raw.rstrip())
        cut = len(first.raw[:cut].rstrip().rstrip(",;:").rstrip())
        start = len(first.raw) - len(first.raw.lstrip())
        return refs_for(first.spans, start, cut) if cut > start else []

    def _locators(self, line_ids):
        result = []
        for lid in line_ids:
            line = self.evidence[lid]
            for start, end, kind in line.locators:
                text = line.raw[start:end]
                refs = refs_for(line.spans, start, end)
                if not refs:
                    continue
                if kind == "cross_reference":
                    result.append(
                        Locator(
                            refs=refs,
                            kind=kind,
                            confidence=0.6,
                            reasons=["cross-reference word (lexicon)"],
                        )
                    )
                    continue
                parts = regex.split(r"\s*[–—-]\s*", text.strip())
                label, end_label = parts[0], parts[1] if len(parts) > 1 else None
                target, qualifier, why = self._resolve(label)
                end_target = None
                if end_label is not None:
                    if len(end_label) < len(label) and label[-len(end_label) :].isdigit():
                        end_label = label[: len(label) - len(end_label)] + end_label
                    end_target = self._resolve(end_label)[0]
                result.append(Locator(
                    refs=refs, kind=kind, label=label, end_label=end_label, qualifier=qualifier,
                    target_page=target, end_target_page=end_target,
                    confidence=0.85 if target is not None else 0.5, reasons=[why],
                ))  # fmt: skip
        return result

    def _resolve(self, label):
        """(physical page, qualifier, why) of a printed label through the Step 8 labels."""
        pages = self.context.label_pages
        if label in pages and len(pages[label]) == 1:
            return pages[label][0], None, "printed label found in the Step 8 page labels"
        match = regex.match(r"^(\p{Ll}{1,3})(\p{N}+)$", label)
        if match and match.group(2) in pages and len(pages[match.group(2)]) == 1:
            return (
                pages[match.group(2)][0],
                match.group(1),
                "page number after a lowercase qualifier found in the Step 8 page labels",
            )
        if label in pages:
            return None, None, "printed label names several pages"
        return None, None, "printed label not found in the Step 8 page labels"

    def _make(self, stream, line_ids, kind, sources, boundary, segment_joins, edge_kind,
              namespace):  # fmt: skip
        joins = []
        for a, b in zip(line_ids, line_ids[1:], strict=False):
            old = self.step9_joins.get((a, b))
            if old is not None:
                joins.append(old)
                continue
            join_kind, confidence, reasons = segment_joins.get((a, b), (
                "column" if edge_kind.get((a, b)) in LANE_CHANGES else "line", 0.7,
                ["lines of one item"],
            ))  # fmt: skip
            ea, eb = self.evidence[a], self.evidence[b]
            joins.append(new_join(self.page, self.context.vocabulary, self.context.compounds,
                                  self.lines[a], ea.text, self.lines[b], eb.text, join_kind,
                                  confidence, reasons))  # fmt: skip
        members = [self.lines[lid] for lid in line_ids]
        source_units = [u for u in self.paragraphs.units if u.id in set(sources)]
        main = max(source_units, key=lambda u: len(u.line_ids))
        spans = {sid for lid in line_ids for sid in self.lines[lid].span_ids}
        runs = [r for u in source_units for r in u.language_runs
                if all(ref.span_id in spans for ref in r.refs)]  # fmt: skip
        review = boundary.review_required or any(j.review_required for j in joins)
        return ItemUnit(
            id=self._sid(namespace, line_ids[0]),
            page=self.layout.page,
            stream_id=stream.id,
            stream_kind=stream.kind,
            kind=kind,
            line_ids=line_ids,
            source_unit_ids=sources,
            boundary=boundary,
            joins=joins,
            style_runs=style_runs(self.page.store, members),
            language=main.language,
            language_confidence=main.language_confidence,
            language_runs=runs,
            list_id="pending" if kind in {"list_item", "definition_entry", "index_entry",
                                          "bibliography_entry", "contents_entry"} else None,
            review_required=review,
        )  # fmt: skip

    # ------------------------------------------------------------------ lists
    def _lists(self, units, item_of_segment, segment_of):
        drafts = {d.key: d for d in self.drafts}
        members = defaultdict(list)
        seen = set()
        for segment in segment_of.values():
            if id(segment) in seen:
                continue
            seen.add(id(segment))
            members[segment.list_key].append(segment)
        order = {u.id: i for i, u in enumerate(units)}
        lists = []
        for key, segments in members.items():
            items = sorted((item_of_segment[id(s)] for s in segments), key=lambda u: order[u.id])
            draft = drafts.get(key)
            first = segments[0]
            kind = draft.kind if draft else {
                "index": "index", "glossary": "glossary", "contents": "contents",
                "bibliography": "bibliography", "definition": "definition",
                "unmarked": "unmarked"}[key[0]]  # fmt: skip
            parent = item_of_segment.get(id(draft.parent)) if draft and draft.parent else None
            levels = Counter(u.level for u in items)
            confidence = round(_median(u.boundary.confidence for u in items), 4)
            lists.append(StructuredList(
                id=self._sid("list", items[0].line_ids[0]),
                kind=kind,
                marker_type=draft.marker_type if draft else None,
                start=draft.start if draft else None,
                item_ids=[u.id for u in items],
                parent_item_id=parent.id if parent else None,
                level=draft.level if draft else min(levels),
                first_page=self.layout.page,
                last_page=self.layout.page,
                confidence=confidence,
                reasons=(draft.reasons if draft else first.reasons[:1]) or ["list"],
                evidence={"items": len(items)},
                review_required=confidence < REVIEW_BELOW,
            ))  # fmt: skip
        return lists


def build_page_lists(page, layout, paragraphs, context, resolved_device="cpu"):
    """(PageLists, [StructuredList]) for one page (lists are page-local here; the book stage
    joins lists and entries that continue on the next page)."""
    return PageLister(page, layout, paragraphs, context).build(resolved_device)
