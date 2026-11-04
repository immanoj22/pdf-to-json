"""Tree rules: rearrange the adapter document tree. Moves are declared on the moved text
refs; removals are listed as omissions; anything uncertain is a review entry."""

from __future__ import annotations

import re

from ..engine.model import (
    Bibliography,
    Division,
    Figure,
    Item,
    ListBlock,
    Omission,
    PageMark,
    Para,
    QandaSet,
    ReviewEntry,
    Section,
    Sidebar,
    Table,
)
from ..engine.text import TextRef


def node_lists(node):
    """Every mutable list of block nodes in a subtree (depth first, parents first)."""
    if isinstance(node, list):
        yield node
        for child in list(node):
            yield from node_lists(child)
        return
    if isinstance(node, Division):
        yield from node_lists(node.intro)
        yield from node_lists(node.children)
        for div in node.index_divs:
            yield from node_lists(div.lead)
    elif isinstance(node, Section):
        yield from node_lists(node.children)
    elif isinstance(node, Sidebar):
        yield from node_lists(node.children)
    elif isinstance(node, ListBlock):
        for item in node.items:
            yield from node_lists(item.children)
    elif isinstance(node, Table):
        for blocks in node.cells_blocks.values():
            yield from node_lists(blocks)
    elif isinstance(node, Bibliography):
        yield from node_lists(node.lead)
    elif isinstance(node, QandaSet):
        for item in node.items:
            yield from node_lists(item.children)


def all_lists(doc):
    yield from node_lists(doc.bookinfo.legal)
    yield from node_lists(doc.bookinfo.legal_after)
    for division in doc.front + doc.body + doc.back + doc.after:
        yield from node_lists(division)


def refs_in(node):
    """Every TextRef in a subtree."""
    if isinstance(node, TextRef):
        yield node
    elif isinstance(node, list):
        for n in node:
            yield from refs_in(n)
    elif isinstance(node, dict) or node is None or isinstance(node, (str, int, PageMark)):
        return
    elif hasattr(node, "__dataclass_fields__"):
        for name in node.__dataclass_fields__:
            if name in ("unit", "image", "marker", "locators", "heading", "parts_units"):
                continue
            value = getattr(node, name)
            if name == "cells_blocks":
                for blocks in value.values():
                    yield from refs_in(blocks)
            else:
                yield from refs_in(value)


def _declare_move(node, reason: str):
    for ref in refs_in(node):
        ref.move = ref.move or reason


# --------------------------------------------------------------------------- item 26


def sidebar_not_in_list(doc, ctx) -> None:
    """Item 26: close the list before a sidebar found inside an item; continue the list
    after the sidebar (an ordered list continues its numbering)."""
    for blocks in list(all_lists(doc)):
        i = 0
        while i < len(blocks):
            block = blocks[i]
            if not isinstance(block, ListBlock):
                i += 1
                continue
            split = _first_item_with_sidebar(block)
            if split is None:
                i += 1
                continue
            k, item = split
            sidebars = [c for c in item.children if isinstance(c, Sidebar)]
            item.children = [c for c in item.children if not isinstance(c, Sidebar)]
            for side in sidebars:
                _declare_move(side, "sidebar moved out of a list (item 26)")
            head = ListBlock(
                block.list_type,
                block.marker_type,
                block.items[: k + 1],
                block.start,
                block.glyph,
                block.unit_ids,
            )
            tail_items = block.items[k + 1 :]
            new = [head] + sidebars
            if tail_items:
                new.append(
                    ListBlock(
                        block.list_type,
                        block.marker_type,
                        tail_items,
                        None,
                        block.glyph,
                        block.unit_ids,
                        continues=True,
                    )
                )
            blocks[i : i + 1] = new
            i += len(new) - (1 if tail_items else 0)


def _first_item_with_sidebar(block: ListBlock):
    for k, item in enumerate(block.items):
        if any(isinstance(c, Sidebar) for c in item.children):
            return k, item
    return None


# --------------------------------------------------------------------------- item 25


_SET_NUM = re.compile(r"[A-Za-z]\s*(?:,|and|&|to|–|-)\s*[A-Za-z]\b")


def set_figures_separate(doc, ctx) -> None:
    """Item 25: every figure holds one image (book.json figures are single images). A
    caption whose number names several parts ("Figs 5.5A and B") is reviewed: the parts
    are separate images that need their own figure numbers."""
    for blocks in all_lists(doc):
        for block in blocks:
            if isinstance(block, Figure) and block.formal and block.label_ref is not None:
                label = block.label_ref.plain()
                caption = " ".join(r.plain() for r in block.captions)
                if (
                    _SET_NUM.search(label)
                    or re.match(r"(?i)\s*figs\b", label)
                    or re.match(r"\s*\(?[A-H]\)?\s", caption)
                ):
                    doc.reviews.append(
                        ReviewEntry(
                            "figure",
                            f"set figure {label.strip()!r}: check that each image is its "
                            "own figure with its own number",
                            block.unit.get("id"),
                            block.page,
                            "set_figures_separate",
                        )
                    )


# --------------------------------------------------------------------------- item 39


def numbered_figure_alone_in_table(doc, ctx) -> None:
    """Item 39: an untitled table whose cells hold only numbered figures is not coded as a
    table; the figures are written in its place."""
    for blocks in list(all_lists(doc)):
        for block in list(blocks):
            if not isinstance(block, Table) or block.title is not None or block.label_ref:
                continue
            contents = [
                b for bs in block.cells_blocks.values() for b in bs if not isinstance(b, PageMark)
            ]
            if (
                contents
                and all(isinstance(b, Figure) and b.formal for b in contents)
                and not block.notes
            ):
                marks = [
                    b for bs in block.cells_blocks.values() for b in bs if isinstance(b, PageMark)
                ]
                index = blocks.index(block)
                blocks[index : index + 1] = contents + marks + block.trailing_marks


# --------------------------------------------------------------------------- item 37


def suggested_reading_as_chapter(doc, ctx) -> None:
    """Item 37 (book option): a Suggested Reading bibliography at the end of a chapter
    becomes its own chapter (as in the TOC), coded as a bullet list."""
    patterns = [
        re.compile(p) for p in ctx["profile"].get("bibliography.suggested_reading_patterns")
    ]

    def visit(container: list, owner_list: list, owner_index: int):
        for node in list(container):
            if isinstance(node, Section):
                visit(node.children, owner_list, owner_index)
            if (
                isinstance(node, Bibliography)
                and node.title is not None
                and any(p.match(node.title.plain()) for p in patterns)
                and container[-1] is node
            ):
                container.remove(node)
                items = [
                    Item(([e.marker_ref] if e.marker_ref else []) + e.parts, unit_id=e.unit_id)
                    for e in node.entries
                ]
                chapter = Division(kind="chapter", title=[node.title])
                chapter.children = list(node.lead) + [ListBlock("bulleted", None, items, glyph="•")]
                owner_list.insert(owner_index + 1, chapter)
                doc.reviews.append(
                    ReviewEntry(
                        "structure",
                        "Suggested Reading coded as its own chapter (item 37)",
                        None,
                        None,
                        "suggested_reading_as_chapter",
                    )
                )

    def chapters(lst):
        i = 0
        while i < len(lst):
            div = lst[i]
            if isinstance(div, Division) and div.kind == "part":
                chapters(div.children)
            elif isinstance(div, Division) and div.kind == "chapter":
                visit(div.children, lst, i)
            i += 1

    chapters(doc.body)
    chapters(doc.after)
    _renumber(doc.body + doc.after)


def _renumber(body: list):
    n = 0

    def walk(lst):
        nonlocal n
        for div in lst:
            if isinstance(div, Division) and div.kind == "part":
                walk(div.children)
            elif isinstance(div, Division) and div.kind == "chapter":
                n += 1
                div.number = n

    walk(body)


# --------------------------------------------------------------------------- item 13


def continued_figure(doc, ctx) -> None:
    """Item 13: the outline marks continued figures (caption matches
    ``figures.continued_pattern``); they stay formal figures. Nothing else to rearrange;
    the writer gives them the continued id, a blank label and an empty title."""
    for blocks in all_lists(doc):
        for block in blocks:
            if isinstance(block, Figure) and block.continued:
                block.formal = True


# --------------------------------------------------------------------------- item 31


def epigraph_as_paras(doc, ctx) -> None:
    """Item 31: no epigraph wrapper: the quotation is a noindent para and its source line an
    alignright para. Applies to paragraphs Stage 1 marks as epigraph/attribution (no
    Stage 1 role exists yet: see docs/adapter_requests.md)."""
    for blocks in all_lists(doc):
        for block in blocks:
            if isinstance(block, Para) and block.kind == "epigraph":
                block.role_override = "noindent"
            elif isinstance(block, Para) and block.kind == "attribution":
                block.role_override = "alignright"


# --------------------------------------------------------------------------- item 22


def qanda_sets(doc, ctx) -> None:
    """Item 22: a question-set title (``qanda.set_title_patterns``) followed by numbered
    lists becomes one qandaset/qandadiv; lists of question items (item_role question)
    become a qandadiv of their own."""
    patterns = [re.compile(p) for p in ctx["profile"].get("qanda.set_title_patterns")]
    for blocks in list(all_lists(doc)):
        i = 0
        while i < len(blocks):
            block = blocks[i]
            title = None
            if (
                isinstance(block, Para)
                and block.kind in ("display_title", "heading_candidate")
                and len(block.parts) == 1
                and isinstance(block.parts[0], TextRef)
                and any(p.match(block.parts[0].plain()) for p in patterns)
            ):
                title = block.parts[0]
                j = i + 1
            elif (
                isinstance(block, ListBlock)
                and block.items
                and all(it.item_role == "question" for it in block.items)
            ):
                j = i
            else:
                i += 1
                continue
            items: list[Item] = []
            k = j
            while k < len(blocks) and isinstance(blocks[k], (ListBlock, PageMark)):
                if isinstance(blocks[k], ListBlock):
                    if blocks[k].list_type not in ("numbered", "lettered", "unmarked") and not all(
                        it.item_role == "question" for it in blocks[k].items
                    ):
                        break
                    items += blocks[k].items
                else:
                    if items:
                        items[-1].parts.append(blocks[k])
                    else:
                        break
                k += 1
            if not items:
                i += 1
                continue
            blocks[i:k] = [QandaSet(title, items)]
            i += 1


def color_plate_note_removal(doc, ctx) -> None:
    """Item 23 (book option): remove "(For color version, see Color Plate N)" from the
    text; each removal is listed as omitted with this reason."""
    pattern = re.compile(ctx["profile"].get("color_plates.note_pattern"))
    seen = set()
    for blocks in list(all_lists(doc)):
        for ref in refs_in(blocks):
            if id(ref) in seen:
                continue
            seen.add(id(ref))
            new_ranges = []
            for s, e in ref.ranges:
                pos = s
                for m in pattern.finditer(ref.text, s, e):
                    if m.start() > pos:
                        new_ranges.append((pos, m.start()))
                    doc.omissions.append(
                        Omission(
                            ref.addr,
                            [(m.start(), m.end())],
                            "colour plate note removed (item 23)",
                            ref.content,
                        )
                    )
                    pos = m.end()
                if pos < e:
                    new_ranges.append((pos, e))
            if new_ranges != ref.ranges:
                ref.ranges = new_ranges or [(s, s)]
