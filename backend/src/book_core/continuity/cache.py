"""Book-level continuity stage after tables: chains of units and tables across page breaks.

Pass 1 reads every page once for the book profile (body style, paragraph indents) and the
book's compound lexicon (hyphen decisions use the unchanged Step 9 rule). Pass 2 walks the
pages in order: it keeps the earlier links (Step 9 page joins the lists stage kept, lists
entry links and continued items), decides the remaining page breaks
(``continuity.decide``), and chains the tables the tables stage marked as continued
(``continuity.tables``). Only the book record is cached; no earlier stage reads it. The
final archive publishes it and applies its links to the units.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from book_core.cache_store import read_model, write_model
from book_core.caching import assert_producer_unchanged, code_digest
from book_core.continuity import decide, tables
from book_core.continuity.edges import ENTRY_KINDS, column_change, page_edges
from book_core.continuity.models import Chain, PageBreak
from book_core.extraction.fingerprints import stable_id
from book_core.model.common import Provenance
from book_core.paragraphs.geometry import frame
from book_core.paragraphs.lexicon import Profile

VERSION = "continuity-1"
CONFIG = {"decide": decide.CONFIG, "tables": {"mark_words": tables.MARK_WORDS}}
LOADED_DIGEST = code_digest("continuity")


@dataclass
class PageInput:
    """What the stage reads of one page."""

    page: object  # ExtractedPage (span store, geometry)
    layout: object  # PageLayout
    units: list  # final unit view (lists-stage units with table lines taken out)
    order: object  # lists-stage PageReadingOrder
    tables: list  # text-owning TableRecords
    claimed: frozenset  # unit ids a final figure links (caption, credit, internal text)
    navigation: str | None
    label: tuple  # (printed label, label source)


def continuity_fingerprint(keys):
    return stable_id(json.dumps(keys, sort_keys=True), code_digest("continuity"), VERSION,
                     json.dumps(CONFIG, sort_keys=True))  # fmt: skip


def _earlier(lists, paragraphs):
    """({from page: [(from unit, to unit, kind, to page)]} of the links the lists stage
    kept, {(from page, previous line, next line): Step 9 LineJoin})."""
    joins = {(j.from_page, j.join.previous_line_id, j.join.next_line_id): j.join
             for j in paragraphs.book.page_joins}  # fmt: skip
    by_from = {}
    for link in lists.page_links:
        by_from.setdefault(link["from_page"], []).append(
            (link["from_unit_id"], link["to_unit_id"], link.get("kind", "paragraph"),
             link["to_page"]))  # fmt: skip
    return by_from, joins


class _Side:
    """One page's data kept while its successor is examined."""

    def __init__(self, item, edges):
        self.item, self.edges = item, edges
        self.lines = {line.id: line for line in item.layout.lines}
        self.units = {u.id: u for u in item.units}


def link_book(inputs, headings, lists, paragraphs, vocabulary, total, digest):
    """BookContinuity fields (chains, candidates, dropped links, profile, counts).

    ``inputs()``: a fresh iterator of PageInput in page order; ``headings``: unit ids the
    structure stage made headings; ``lists``: the lists-stage book result (page links);
    ``paragraphs``: the Step 9 book result (page joins with their line joins)."""
    profile, lexicon = decide.BookProfile(), Profile()
    for item in inputs():
        profile.add_page(item.page.store, item.layout, item.units, item.order)
        lexicon.add_page(item.page, item.layout, SimpleNamespace(edges=[]))
    profile.freeze()
    compounds = lexicon.freeze()["compounds"]
    by_from, joins = _earlier(lists, paragraphs)
    breaks, kinds, candidates, dropped = [], {}, [], []
    previous, prior, waiting = None, None, []
    for item in inputs():
        number = item.page.geometry.page
        edges = page_edges(number, item.page.store, item.layout, item.units, item.order,
                           item.tables, item.claimed, headings, profile.body, item.navigation,
                           *item.label)  # fmt: skip
        current = _Side(item, edges)
        _columns(current, profile, vocabulary, compounds, breaks, kinds, candidates)
        if prior is not None:
            _tables(prior, current, breaks, kinds, candidates)
        prior = current
        if previous is None:
            previous = current
            continue
        b, skipped_b, why_b, float_only = decide.top(edges)
        kept = _kept(previous, current, by_from, joins, vocabulary, compounds, breaks, kinds,
                     dropped)  # fmt: skip
        if (not kept and b is None and float_only and len(waiting) < decide.MAX_SKIPPED
                and number < total):  # fmt: skip
            waiting.append(number)  # a float-only page: the text may go on after it
            continue
        if not kept:
            _new(previous, current, b, skipped_b, why_b, profile, vocabulary, compounds,
                 breaks, kinds, candidates, waiting)  # fmt: skip
        previous, waiting = current, []
    chains = _chains(breaks, kinds, digest)
    counts = {}
    for chain in chains:
        counts[f"chains_{chain.kind}"] = counts.get(f"chains_{chain.kind}", 0) + 1
        for brk in chain.breaks:
            key = f"breaks_{chain.kind}_{brk.source}"
            counts[key] = counts.get(key, 0) + 1
    counts["candidates"] = len(candidates)
    counts["candidates_review"] = sum(c.review_required for c in candidates)
    counts["dropped_links"] = len(dropped)
    return {"chains": chains, "candidates": candidates, "dropped_links": dropped,
            "profile": profile.record(), "counts": counts}  # fmt: skip


def _kept(previous, current, by_from, joins, vocabulary, compounds, breaks, kinds, dropped):
    """Earlier links from ``previous`` to ``current`` (consecutive pages only)."""
    a_page = previous.item.page.geometry.page
    b_page = current.item.page.geometry.page
    found = False
    for a, b, kind, to_page in by_from.get(a_page, []):
        if to_page != b_page:
            continue
        ua, ub = previous.units.get(a), current.units.get(b)
        if ua is None or ub is None:
            dropped.append({"from_page": a_page, "from_unit_id": a, "to_page": b_page,
                            "to_unit_id": b, "reason": "a linked unit is no longer in the "
                            "final view (its lines are in a table)"})  # fmt: skip
            continue
        line_a, line_b = previous.lines[ua.line_ids[-1]], current.lines[ub.line_ids[0]]
        entry = kind == "entry"
        join = None if entry else joins.get((a_page, line_a.id, line_b.id))
        chain_kind = "entry" if entry else (
            "list_item" if ua.kind == "list_item" else "paragraph")  # fmt: skip
        source = "lists" if entry or join is None else "paragraphs"
        reasons = ["kept: " + ("entry link of the lists stage" if entry else
                               "Step 9 page join kept by the lists stage")]  # fmt: skip
        brk = decide.unit_break(a, b, previous.item.page, current.item.page, line_a, line_b,
                                chain_kind, 0.8 if join is None else join.confidence, reasons,
                                [], [], current.item.label, vocabulary, compounds,
                                source=source, join=join)  # fmt: skip
        breaks.append(brk)
        kinds[(a, b)] = chain_kind
        found = True
    return found


def _new(previous, current, b, skipped_b, why_b, profile, vocabulary, compounds, breaks,
         kinds, candidates, waiting):  # fmt: skip
    a, skipped_a, why_a = decide.bottom(previous.edges)
    a_page = previous.item.page.geometry.page
    b_page = current.item.page.geometry.page
    if a is None or b is None:
        candidates.append(decide.refused("paragraph", a_page, a.id if a else None, b_page,
                                         b.id if b else None, [why_a or why_b]))  # fmt: skip
        return
    if any(brk.from_id == a.id for brk in breaks) or any(brk.to_id == b.id for brk in breaks):
        return
    guard = decide.guarded([*skipped_a, *skipped_b])
    kind, confidence, reasons = decide.decide(a, b, profile, previous.edges.navigation, guard)
    if kind is None:
        close = any(r in reasons for r in ("A ends open", "A ends hyphen")) and any(
            r in reasons for r in ("B starts lower", "B starts digit"))  # fmt: skip
        candidates.append(decide.refused("paragraph", a_page, a.id, b_page, b.id, reasons,
                                         close))  # fmt: skip
        return
    line_a = previous.lines[a.last_line]
    line_b = current.lines[b.first_line]
    reasons = list(reasons)
    if waiting:
        reasons.append(f"{len(waiting)} page(s) holding only floats between the halves")
    brk = decide.unit_break(a.id, b.id, previous.item.page, current.item.page, line_a, line_b,
                            kind, confidence, reasons, [x.id for x in [*skipped_a, *skipped_b]],
                            list(waiting),
                            current.item.label, vocabulary, compounds)  # fmt: skip
    breaks.append(brk)
    kinds[(a.id, b.id)] = kind


def column_end(line, frames, side):
    """No text line of the main flow lies below (``side`` "below") or above this line in
    its column (overlapping its inline extent by half of the shorter)."""
    for f in frames:
        overlap = min(f.end, line.end) - max(f.start, line.start)
        if overlap < 0.5 * min(f.end - f.start, line.end - line.start):
            continue
        if side == "below" and f.block > line.block + 0.5 * line.size:
            return False
        if side == "above" and f.block < line.block - 0.5 * line.size:
            return False
    return True


def _columns(side, profile, vocabulary, compounds, breaks, kinds, candidates):
    """Units continued into the next column of the same page: consecutive body units of
    the main flow (floats between them skipped) where the first ends its column (no text
    line of the main flow below it there) and the second begins the next (none above)."""
    items = side.edges.items
    number = side.item.page.geometry.page
    text_frames = [
        frame(side.lines[lid])
        for item in items if item.role != "float" and item.kind != "table"
        for lid in side.units[item.id].line_ids if lid in side.lines
    ]  # fmt: skip
    for k, a in enumerate(items):
        if a.role != "body" or a.kind in ENTRY_KINDS:
            continue
        skipped, b = [], None
        for item in items[k + 1 :]:
            if item.role == "float":
                skipped.append(item)
                continue
            b = item
            break
        if b is None or b.role != "body" or b.kind in ENTRY_KINDS or not column_change(a, b):
            continue
        if not (column_end(a.last_frame, text_frames, "below")
                and column_end(b.first_frame, text_frames, "above")):  # fmt: skip
            candidates.append(decide.refused("paragraph", number, a.id, number, b.id, [
                "column: the units do not end and begin their columns"]))  # fmt: skip
            continue
        if side.units[a.id].continues_to or side.units[b.id].continues_from:
            continue  # linked already (a Step 9 column join keeps one unit)
        kind, confidence, reasons = decide.decide(a, b, profile, side.edges.navigation,
                                                  decide.guarded(skipped))  # fmt: skip
        if kind is None:
            candidates.append(decide.refused("paragraph", number, a.id, number, b.id,
                                             ["column: " + r for r in reasons]))  # fmt: skip
            continue
        brk = decide.unit_break(a.id, b.id, side.item.page, side.item.page,
                                side.lines[a.last_line], side.lines[b.first_line], kind,
                                confidence, ["the unit continues in the next column", *reasons],
                                [x.id for x in skipped], [], (None, "none"), vocabulary,
                                compounds, where="column")  # fmt: skip
        breaks.append(brk)
        kinds[(a.id, b.id)] = kind


def _tables(previous, current, breaks, kinds, candidates):
    """Table chains between two consecutive pages, and column mismatches (review)."""
    a_page = previous.item.page.geometry.page
    b_page = current.item.page.geometry.page
    first_tables, next_tables = previous.item.tables, current.item.tables
    a = (a_page, previous.item.page.store, previous.lines, previous.item.units,
         previous.item.order)  # fmt: skip
    b = (b_page, current.item.page.store, current.lines, current.item.units, current.item.order)
    by_id = {t.id: t for t in next_tables}
    for table in first_tables:
        to = table.continues_to
        if to is None or to.page != b_page or to.table_id not in by_id:
            continue
        brk = tables.table_break(table, by_id[to.table_id], a, b, current.item.label)
        breaks.append(brk)
        kinds[(table.id, to.table_id)] = "table"
    if first_tables and next_tables:
        last = max(first_tables, key=lambda t: t.bbox.y1 if not t.rotation else t.bbox.x1)
        first = min(next_tables, key=lambda t: t.bbox.y0 if not t.rotation else t.bbox.x0)
        found = tables.mismatch(last, first, previous.item.layout.content_bbox,
                                current.item.layout.content_bbox, a_page)  # fmt: skip
        if found is not None:
            candidates.append(found)


def _chains(breaks, kinds, digest):
    following = {brk.from_id: brk for brk in breaks}
    targets = {brk.to_id for brk in breaks}
    chains = []
    for brk in breaks:
        if brk.from_id in targets:
            continue
        members, pages, chain_breaks = [brk.from_id], [brk.from_page], []
        step = brk
        while step is not None:
            chain_breaks.append(step)
            members.append(step.to_id)
            pages.append(step.to_page)
            step = following.get(step.to_id)
        found = {kinds[(x.from_id, x.to_id)] for x in chain_breaks}
        kind = ("table" if "table" in found else "entry" if "entry" in found else
                "list_item" if "list_item" in found else "paragraph")  # fmt: skip
        chains.append(Chain(
            id=stable_id(digest, "chain", members[0]), kind=kind, members=members,
            pages=pages, breaks=chain_breaks,
            review_required=any(x.review_required for x in chain_breaks),
        ))  # fmt: skip
    return sorted(chains, key=lambda c: (c.pages[0], c.members[0]))


def analyze_book_continuity(inputs, headings, lists, paragraphs, vocabulary, keys, cache_dir,
                            total, digest):  # fmt: skip
    """(key, BookContinuity) for the book; ``keys``: the cache keys of its inputs."""
    from book_core.continuity.models import BookContinuity

    assert_producer_unchanged("continuity", LOADED_DIGEST)
    key = continuity_fingerprint(keys)
    path = Path(cache_dir) / "continuity" / f"{key}.json"
    if path.exists():
        return key, read_model(path, BookContinuity, key)
    found = link_book(inputs, headings, lists, paragraphs, vocabulary, total, digest)
    book = BookContinuity(
        source_sha256=digest, pages=total, version=VERSION, config=CONFIG,
        cache_key_inputs={"continuity_key": key, **{k: str(v) for k, v in keys.items()}},
        provenance=Provenance(source_sha256=digest, engine="book_core.continuity",
                              engine_version=VERSION, method="derived"),
        **found,
    )  # fmt: skip
    assert_producer_unchanged("continuity", LOADED_DIGEST)
    write_model(path, book, key)
    return key, book


def load_book(cache_dir, key):
    from book_core.continuity.models import BookContinuity

    return read_model(Path(cache_dir) / "continuity" / f"{key}.json", BookContinuity, key)


__all__ = ["PageBreak", "PageInput", "analyze_book_continuity", "link_book", "load_book"]
