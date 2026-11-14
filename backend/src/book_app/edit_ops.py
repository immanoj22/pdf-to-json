"""Element changes of the Review/Browse editor, applied to the reviewer's copy of book.json.

Each change takes units of the converted book and gives them another element type, moves them
in the reading order, or takes them out of the book's content. Text is never lost: a unit's
text record moves whole into its new element (a list item, a caption, a table cell, a note of
a table, a furniture record), and a merge joins the records of several units with a line end.

Changes (``op``):
  list_set        {units, list_type, level?}  paragraphs become a bulleted or numbered list (a
                                              level above 1 nests it in the list before it); the
                                              items of one list change between bulleted/numbered
  list_level      {unit, direction}           a list item moves one level in or out
  box             {units, kind, title?}       a box (sidebar), a quote or a pull quote around
                                              units; ``title``: the first unit is the box title
  caption         {unit, figure}              the unit is a caption of that figure
  table_make      {units, columns}            units become the cells of a table, row by row
  table_text      {unit, table, role}         the unit is the title or a note of that table
  footnote        {unit}                      the unit is a footnote
  paragraph       {unit}                      a caption, footnote or credit is a body paragraph
  chapter_authors {units}                     the units are the authors line of their chapter
  question        {units}                     a multiple-choice question: the stem, the options
                                              (units printed with a letter or number mark) and
                                              the answer after them
  bibliography    {units}                     the units are bibliography entries
  index_entries   {units}                     the units are index entries
  glossary        {units}                     the units are glossary entries (term, then text)
  not_content     {units, kind}               running head, running foot, folio or printer
                                              mark: out of the book's content (kept as furniture)
  merge           {units}                     consecutive units of one kind become one unit
  move            {unit, direction}           the unit changes place with its neighbour
  unwrap          {unit}                      a table, figure or box becomes its text items (cells
                                              row by row, a figure's texts, captions and credits)
                                              as paragraphs, in reading order
  table_split     {unit, row}                 a table splits into two tables before its row ``row``
                                              (counted from 1; the title stays with the first
                                              table, the notes go with the second)
  swap_columns    {unit}                      on its page the run starting at the unit is read
                                              before the run above it (the second column first)
"""

from __future__ import annotations

import copy
import re

from .overlay import (
    EditError,
    _convert,
    _get,
    _prov,
    first_mark,
    index_units,
    new_id,
    walk,
)

TEXT_TYPES = ("paragraph", "heading", "caption", "footnote", "list_item")
FURNITURE = ("running_head", "running_foot", "folio", "production_mark")
BOX_KINDS = ("box", "quote", "pull_quote")
LETTERED = ("lower_alpha", "upper_alpha")  # the options the export writes as a question
NUMBER_MARK = re.compile(
    r"^[\s ]*(?P<open>\(?)(?P<mark>\d{1,3}|[A-Za-z]|[ivxlcdm]{1,6}|[IVXLCDM]{1,6})"
    r"(?P<punct>[.)\]:])[\s ]+"
)
ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
GLOSSARY_SEPARATORS = (":", " – ", " — ", " - ", "\t")


# ---------------------------------------------------------------------------- helpers


def _units(ix, ids) -> tuple[list, list[dict], int, int]:
    """(siblings, units in sibling order, first index, last index) of consecutive units: the
    selected units share one parent and only page markers lie between them."""
    if not ids:
        raise EditError("Select at least one item.")
    found = [_get(ix, i) for i in dict.fromkeys(ids)]
    siblings = found[0][1]
    if any(s is not siblings for _, s in found):
        raise EditError("The selected items are not in one place in the text.")
    pos = sorted(siblings.index(u) for u, _ in found)
    between = siblings[pos[0] : pos[-1] + 1]
    chosen = {id(u) for u, _ in found}
    if any(id(u) not in chosen and u["type"] != "page_marker" for u in between):
        raise EditError("Select items that follow each other.")
    return siblings, [siblings[p] for p in pos], pos[0], pos[-1]


def _markers_out(siblings, first, last) -> list[dict]:
    """The page markers between ``first`` and ``last``; they stay in the text after the new
    element (an element that cannot hold them)."""
    return [u for u in siblings[first : last + 1] if u["type"] == "page_marker"]


def _text_unit(unit: dict) -> None:
    if not unit.get("content") or unit["type"] not in TEXT_TYPES:
        raise EditError("Only text (a paragraph, heading, caption, footnote or list item) can "
                        "change into this.")  # fmt: skip


def _refs(unit: dict) -> dict:
    return copy.deepcopy(unit.get("refs") or {"lines": [], "spans": []})


def _base(unit: dict, type_: str, reason: str, **extra) -> dict:
    """A unit of another type with the unit's id, pages, order, boxes, refs and text."""
    out = _convert(unit, type_ if type_ in ("heading", "paragraph", "list") else "list_item")
    out["type"] = type_
    out.update(extra)
    out["provenance"] = _prov(unit, reason)
    out["review_status"] = "ok"
    return out


def _plain(unit: dict, type_: str, reason: str) -> dict:
    """A caption, footnote or paragraph from a text unit (same text record and source)."""
    keep = ("id", "pages", "order", "boxes", "refs", "content", "confidence", "continues_from",
            "continues_to", "flags", "source")  # fmt: skip
    out = {k: copy.deepcopy(unit[k]) for k in keep if k in unit}
    out["type"] = type_
    out["provenance"] = _prov(unit, reason)
    out["review_status"] = "ok"
    if type_ == "paragraph":
        out["role"] = "body"
    return out


def _roman(text: str) -> int | None:
    text = text.lower()
    if not text or any(c not in ROMAN for c in text):
        return None
    total = 0
    for a, b in zip(text, text[1:] + " ", strict=False):
        value = ROMAN[a]
        total += -value if b in ROMAN and ROMAN[b] > value else value
    return total


def number_mark(text: str) -> tuple[dict, int] | None:
    """The printed number or letter mark at the start of a text ("1.", "(a)", "iv)") as a list
    marker, and the offset where the item text starts."""
    m = NUMBER_MARK.match(text)
    if not m:
        return None
    mark = m["mark"]
    if mark.isdigit():
        kind, value = "decimal", int(mark)
    elif len(mark) > 1 or (mark in "ivxIVX" and _roman(mark) is not None and len(mark) > 1):
        roman = _roman(mark)
        if roman is None:
            return None
        kind, value = ("lower_roman" if mark.islower() else "upper_roman"), roman
    else:
        kind = "lower_alpha" if mark.islower() else "upper_alpha"
        value = ord(mark.lower()) - ord("a") + 1
    punct = {"(": "parens"}.get(m["open"], m["punct"])
    text_mark = text[m.start("open") : m.end("punct")]
    return {"text": text_mark, "type": kind, "punctuation": punct, "value": value}, m.end()


def _slice(content: dict, start: int) -> dict:
    from .overlay import slice_content

    return slice_content(content, start)


def _item(unit: dict, type_: str, marked: str, level: int, reason: str) -> tuple[dict, dict]:
    """A list item from a text unit, and the marker it was printed with (or None). ``marked``:
    bullet, number or none. The printed mark becomes the item's marker; the rest is its text."""
    text = unit["content"]["text"]
    marker, cut = None, 0
    if marked == "bullet" and (found := first_mark(text, {})):
        glyph, cut = found
        marker = {"text": glyph, "type": "bullet", "punctuation": "none", "value": None}
    elif marked == "number" and (found := number_mark(text)):
        marker, cut = found
    item = _base(unit, type_, reason, item_role="item", level=level, marker=marker,
                 children=[], locators=[], names=[], term=None)  # fmt: skip
    if cut:
        item["content"] = _slice(unit["content"], cut)
    return item, marker


def _list(first: dict, items: list[dict], list_type: str, role: str, marker_type, reason: str):
    return {
        "id": new_id(first["id"], "list", list_type, str(len(items))),
        "type": "list",
        "pages": sorted({p for u in items for p in u["pages"]}),
        "order": first.get("order", 0),
        "boxes": [b for u in items for b in (u.get("boxes") or [])],
        "confidence": 1.0,
        "continues_from": None,
        "continues_to": None,
        "flags": [],
        "items": items,
        "level": 1,
        "list_id": new_id(first["id"], "list_id", list_type),
        "list_role": role,
        "list_type": list_type,
        "marker_type": marker_type,
        "provenance": _prov(first, reason),
        "refs": {"lines": [], "spans": []},
        "review_status": "ok",
        "segment": 0,
        "source": first.get("source") or "native",
        "start": None,
    }


def _previous(siblings, index) -> dict | None:
    j = index - 1
    while j >= 0 and siblings[j]["type"] == "page_marker":
        j -= 1
    return siblings[j] if j >= 0 else None


def _replace_run(siblings, first, last, new: list[dict]) -> None:
    siblings[first : last + 1] = new


# ---------------------------------------------------------------------------- lists


def list_set(data, ix, edit):
    list_type = edit.get("list_type")
    if list_type not in ("bulleted", "numbered"):
        raise EditError("A list is bulleted or numbered.")
    level = int(edit.get("level") or 1)
    if not 1 <= level <= 6:
        raise EditError("A list level is from 1 to 6.")
    siblings, units, first, last = _units(ix, edit.get("units") or [])
    content = [u for u in units if u["type"] != "page_marker"]
    if all(u["type"] == "list_item" for u in content):
        # Items of one list: the list changes between bulleted and numbered.
        owner = next((u for u, _ in walk(data["content"]) if u.get("items") is siblings), None)
        if owner is None or len(content) != len(owner["items"]):
            raise EditError("Select every item of the list to change its kind.")
        owner["list_type"] = list_type
        if list_type == "numbered" and owner.get("marker_type") in (None, "bullet", "dash"):
            owner["marker_type"] = "decimal"
        if list_type == "bulleted":
            owner["marker_type"] = "bullet"
        owner["provenance"] = _prov(owner, f"made a {list_type} list by the reviewer")
        return
    for u in content:
        if u["type"] not in ("paragraph", "heading"):
            raise EditError("Only paragraphs (or a whole list) can be made into a list.")
    marked = "bullet" if list_type == "bulleted" else "number"
    items, markers = [], []
    for u in content:
        item, marker = _item(u, "list_item", marked, level, f"made a list item by the reviewer")
        items.append(item)
        markers.append(marker)
    kinds = {m["type"] for m in markers if m}
    marker_type = (kinds.pop() if len(kinds) == 1 else None) if kinds else (
        "bullet" if list_type == "bulleted" else "decimal")  # fmt: skip
    new = _list(content[0], items, list_type, "general", marker_type, "list made by the reviewer")
    marks = _markers_out(siblings, first, last)
    if level == 1:
        _replace_run(siblings, first, last, [new, *marks])
        return
    # A nested list belongs to the last item of the list just before it.
    host = _previous(siblings, first)
    if host is None or host["type"] != "list" or not host.get("items"):
        raise EditError("A nested list needs a list just before it.")
    parent = host["items"][-1]
    depth, probe = 1, parent
    while depth + 1 < level:
        inner = next((c for c in reversed(probe.get("children") or []) if c["type"] == "list"),
                     None)  # fmt: skip
        if inner is None or not inner.get("items"):
            break
        probe, depth = inner["items"][-1], depth + 1
    new["level"] = depth + 1
    for item in new["items"]:
        item["level"] = depth + 1
    probe.setdefault("children", []).append(new)
    probe["pages"] = sorted({*probe["pages"], *new["pages"]})
    _replace_run(siblings, first, last, marks)


def list_level(data, ix, edit):
    unit, items = _get(ix, edit["unit"])
    if unit["type"] != "list_item":
        raise EditError("Only a list item has a level.")
    owner = next((u for u, _ in walk(data["content"]) if u.get("items") is items), None)
    direction = edit.get("direction")
    i = items.index(unit)
    if direction == "in":
        if i == 0:
            raise EditError("The first item of a list cannot move in: there is no item above it.")
        above = items[i - 1]
        nested = next((c for c in reversed(above.get("children") or []) if c["type"] == "list"),
                      None)  # fmt: skip
        if nested is None:
            nested = _list(unit, [], owner["list_type"], owner.get("list_role") or "general",
                           owner.get("marker_type"), "nested list made by the reviewer")  # fmt: skip
            nested["level"] = (owner.get("level") or 1) + 1
            above.setdefault("children", []).append(nested)
        items.pop(i)
        unit["level"] = (owner.get("level") or 1) + 1
        nested["items"].append(unit)
        nested["pages"] = sorted({*nested["pages"], *unit["pages"]})
        above["pages"] = sorted({*above["pages"], *unit["pages"]})
        if not items:
            raise EditError("A list keeps at least one item.")
        return
    if direction != "out":
        raise EditError("A list item moves in or out.")
    # Out: the item follows the item that holds its list, one level up.
    holder = next(
        (
            (u, sib)
            for u, sib in walk(data["content"])
            if u["type"] == "list_item" and owner in (u.get("children") or [])
        ),
        None,
    )
    if holder is None:
        raise EditError("This item is already at the top level of its list.")
    parent_item, outer_items = holder
    tail = items[i + 1 :]
    del items[i:]
    unit["level"] = parent_item.get("level") or 1
    if tail:  # the items after it stay under it, one level down as before
        rest = copy.deepcopy(owner)
        rest["id"] = new_id(owner["id"], "rest", unit["id"])
        rest["list_id"] = owner["list_id"]
        rest["items"] = tail
        rest["pages"] = sorted({p for t in tail for p in t["pages"]})
        unit.setdefault("children", []).append(rest)
    if not items:
        parent_item["children"] = [c for c in parent_item["children"] if c is not owner]
    outer_items.insert(outer_items.index(parent_item) + 1, unit)


# ---------------------------------------------------------------------------- boxes


def box(data, ix, edit):
    kind = edit.get("kind") or "box"
    if kind not in BOX_KINDS:
        raise EditError("Choose a box, a quote or a pull quote.")
    siblings, units, first, last = _units(ix, edit.get("units") or [])
    content = [u for u in units if u["type"] != "page_marker"]
    if not content:
        raise EditError("Select the text that goes into the box.")
    children = copy.deepcopy(siblings[first : last + 1])
    if edit.get("title"):
        if kind != "box":
            raise EditError("A quote has no title.")
        head = next(i for i, c in enumerate(children) if c["type"] != "page_marker")
        title = children[head]
        if title["type"] not in ("paragraph", "heading"):
            raise EditError("The box title must be a line of text.")
        children[head] = _base(title, "heading", "box title set by the reviewer",
                               level=title.get("level") or 3, role="sidebar_title",
                               level_method="reviewer")  # fmt: skip
        for key in ("item_role", "marker", "children", "locators", "names", "term"):
            children[head].pop(key, None)
        if head:  # the title comes first; the page markers before it follow it
            children.insert(0, children.pop(head))
    flags = [] if kind == "box" else [kind]
    new = {
        "id": new_id(content[0]["id"], "box", kind),
        "type": "box",
        "box_kind": "sidebar" if kind == "box" else "callout",
        "pages": sorted({p for u in content for p in u["pages"]}),
        "order": content[0].get("order", 0),
        "boxes": [b for u in content for b in (u.get("boxes") or [])],
        "confidence": 1.0,
        "continues_from": None,
        "continues_to": None,
        "flags": flags,
        "children": children,
        "provenance": _prov(content[0], f"{kind.replace('_', ' ')} made by the reviewer"),
        "refs": {"lines": [], "spans": []},
        "review_status": "ok",
        "source": content[0].get("source") or "native",
    }
    _replace_run(siblings, first, last, [new])


# ---------------------------------------------------------------------------- figures and tables


def _text_record(unit: dict, prefix: str) -> dict:
    return {"id": unit["id"], "content": copy.deepcopy(unit["content"]), "refs": _refs(unit),
            "review_status": "ok"}  # fmt: skip


def caption(data, ix, edit):
    unit, siblings = _get(ix, edit["unit"])
    _text_unit(unit)
    figure, _ = _get(ix, edit.get("figure") or "")
    if figure["type"] != "figure":
        raise EditError("Choose the figure the caption belongs to.")
    if unit is figure:
        raise EditError("A figure is not its own caption.")
    figure.setdefault("captions", []).append(_text_record(unit, "caption"))
    figure["provenance"] = _prov(figure, "caption linked by the reviewer")
    siblings.remove(unit)


def table_text(data, ix, edit):
    unit, siblings = _get(ix, edit["unit"])
    _text_unit(unit)
    table, _ = _get(ix, edit.get("table") or "")
    if table["type"] != "table":
        raise EditError("Choose the table.")
    role = edit.get("role")
    record = {"id": unit["id"], "role": role, "refs": _refs(unit),
              "content": copy.deepcopy(unit["content"]), "number": None, "numbered": False}  # fmt: skip
    if role == "title":
        if table.get("title"):
            raise EditError("This table has a title already.")
        table["title"] = record
    elif role == "note":
        table.setdefault("notes", []).append(record)
    else:
        raise EditError("A table text is its title or a note.")
    table["provenance"] = _prov(table, f"table {role} set by the reviewer")
    siblings.remove(unit)


def table_make(data, ix, edit):
    columns = int(edit.get("columns") or 1)
    if not 1 <= columns <= 20:
        raise EditError("A table has 1 to 20 columns.")
    siblings, units, first, last = _units(ix, edit.get("units") or [])
    content = [u for u in units if u["type"] != "page_marker"]
    for u in content:
        _text_unit(u)
    if len(content) < columns:
        raise EditError("Select at least one item for each column.")
    cells = []
    for n, u in enumerate(content):
        row, col = divmod(n, columns)
        box_ = (u.get("boxes") or [None])[0] or {"page": u["pages"][0], "x0": 0, "y0": 0,
                                                    "x1": 0, "y1": 0}  # fmt: skip
        cells.append({
            "id": u["id"], "row": row, "column": col, "box": box_, "column_span": 1,
            "row_span": 1, "role": "data", "headers": [],
            "content": [{"type": "text", "content": copy.deepcopy(u["content"]),
                         "refs": _refs(u)}],
        })  # fmt: skip
    rows = (len(content) + columns - 1) // columns
    head = content[0]
    new = {
        "id": new_id(head["id"], "table", str(columns)),
        "type": "table",
        "pages": sorted({p for u in content for p in u["pages"]}),
        "order": head.get("order", 0),
        "boxes": [b for u in content for b in (u.get("boxes") or [])],
        "cells": cells,
        "columns": columns,
        "rows": rows,
        "header_rows": 0,
        "notes": [],
        "title": None,
        "flags": [],
        "provenance": _prov(head, "table made by the reviewer"),
        "refs": {"lines": [], "spans": []},
        "review_status": "ok",
        "source": head.get("source") or "native",
    }
    _replace_run(siblings, first, last, [new, *_markers_out(siblings, first, last)])


# ---------------------------------------------------------------------------- text roles


def footnote(data, ix, edit):
    unit, siblings = _get(ix, edit["unit"])
    _text_unit(unit)
    if unit["type"] == "list_item":
        raise EditError("A list item cannot be a footnote; take it out of the list first.")
    siblings[siblings.index(unit)] = _plain(unit, "footnote", "made a footnote by the reviewer")


def paragraph(data, ix, edit):
    unit, siblings = _get(ix, edit["unit"])
    if unit["type"] not in ("caption", "footnote", "paragraph"):
        raise EditError("Only a caption, a footnote or a paragraph of another kind can be made a "
                        "body paragraph here.")  # fmt: skip
    new = _plain(unit, "paragraph", "made a body paragraph by the reviewer")
    new["flags"] = [f for f in new.get("flags") or [] if f != "chapter_authors"]
    siblings[siblings.index(unit)] = new


def chapter_authors(data, ix, edit):
    siblings, units, first, last = _units(ix, edit.get("units") or [])
    for u in units:
        if u["type"] == "page_marker":
            continue
        if u["type"] != "paragraph":
            raise EditError("Only paragraphs can be the authors line.")
        u["role"] = "credit"
        u["flags"] = [*(f for f in u.get("flags") or [] if f != "chapter_authors"),
                      "chapter_authors"]  # fmt: skip
        u["provenance"] = _prov(u, "chapter authors set by the reviewer")
        u["review_status"] = "ok"


def _entries(data, ix, edit, item_type, list_type, role, reason, term=False):
    siblings, units, first, last = _units(ix, edit.get("units") or [])
    content = [u for u in units if u["type"] != "page_marker"]
    items = []
    for u in content:
        _text_unit(u)
        if u["type"] == "list_item":
            raise EditError("Select paragraphs (a list item is already an entry of a list).")
        item = _base(u, item_type, reason, item_role=None, level=1, marker=None, children=[],
                     locators=[], names=[], term=None)  # fmt: skip
        if term:
            text = u["content"]["text"]
            cut = min((text.find(s) for s in GLOSSARY_SEPARATORS if text.find(s) > 0),
                      default=-1)  # fmt: skip
            if cut < 0:
                cut = text.find("\n")
            if cut <= 0:
                raise EditError("Each glossary entry needs its term first, then ':' or a dash "
                                "or a new line, then the text: " + repr(text[:40]))  # fmt: skip
            item["term"] = [0, cut]
        items.append(item)
    marks = _markers_out(siblings, first, last)
    before = _previous(siblings, first)
    if before is not None and before["type"] == "list" and before.get("list_type") == list_type:
        before["items"] += items  # the entries continue the list just before them
        before["pages"] = sorted({*before["pages"], *(p for i in items for p in i["pages"])})
        _replace_run(siblings, first, last, marks)
        return
    new = _list(content[0], items, list_type, role, None, reason)
    _replace_run(siblings, first, last, [new, *marks])


def bibliography(data, ix, edit):
    _entries(data, ix, edit, "bibliography_entry", "bibliography", "bibliography",
             "bibliography entry set by the reviewer")  # fmt: skip


def index_entries(data, ix, edit):
    _entries(data, ix, edit, "index_entry", "index", "index", "index entry set by the reviewer")


def glossary(data, ix, edit):
    _entries(data, ix, edit, "glossary_entry", "glossary", "glossary",
             "glossary entry set by the reviewer", term=True)  # fmt: skip


def question(data, ix, edit):
    """Stem units until the first unit printed with a letter or number mark, the marked units
    as the options (a lettered list), the units after the options as the answer."""
    siblings, units, first, last = _units(ix, edit.get("units") or [])
    content = [u for u in units if u["type"] != "page_marker"]
    lists = [k for k, u in enumerate(content) if u["type"] == "list"]
    for k, u in enumerate(content):
        if k not in lists:
            _text_unit(u)
        if u["type"] == "list_item":
            raise EditError("Select paragraphs and lists; a single list item is not a question.")
    if lists:
        # The options were read as a list already: the stem before it, the answer after it.
        stem_end = lists[0]
        if len(lists) > 1 or stem_end == 0:
            raise EditError("Select the question's text, then its one list of options.")
        options_list = copy.deepcopy(content[stem_end])
        if len(options_list["items"]) < 2:
            raise EditError("A multiple-choice question has at least two options.")
        stem, answer = content[:stem_end], content[stem_end + 1 :]
        opts = options_list
        if opts.get("marker_type") not in LETTERED:
            raise EditError("The options must be lettered, like (a) or B.")
        opts["list_type"], opts["list_role"] = "numbered", "options"
        opts["provenance"] = _prov(opts, "options set by the reviewer")
    else:
        stem_end = next((i for i, u in enumerate(content)
                         if i and number_mark(u["content"]["text"])), None)  # fmt: skip
        if stem_end is None:
            raise EditError("The options must start with a letter or a number, like (a) or B.")
        end = stem_end
        while end < len(content) and number_mark(content[end]["content"]["text"]):
            end += 1
        stem, options, answer = content[:stem_end], content[stem_end:end], content[end:]
        if len(options) < 2:
            raise EditError("A multiple-choice question has at least two options.")
        items = []
        for u in options:
            item, _ = _item(u, "list_item", "number", 1, "option set by the reviewer")
            items.append(item)
        kinds = {i["marker"]["type"] if i.get("marker") else None for i in items}
        if len(kinds) != 1 or not kinds <= set(LETTERED):
            raise EditError("The options must be lettered, like (a) or B.")
        marker_type = kinds.pop()
        opts = _list(options[0], items, "numbered", "options", marker_type,
                     "options set by the reviewer")  # fmt: skip
    head = stem[0]
    number = number_mark(head["content"]["text"])
    pages = sorted({p for u in content for p in u["pages"]})

    def part(kind, children, key=None):
        return {
            "id": new_id(head["id"], "question", kind),
            "type": kind, "pages": sorted({p for c in children for p in c["pages"]}) or pages,
            "order": (children[0] if children else head).get("order", 0), "boxes": [],
            "confidence": 1.0, "continues_from": None, "continues_to": None, "flags": [],
            "children": children, "key": key, "provenance": _prov(head, f"question {kind} set by the reviewer"),
            "refs": {"lines": [], "spans": []}, "review_status": "ok", "source": head.get("source") or "native",
        }  # fmt: skip

    parts = [part("question", [*copy.deepcopy(stem), opts])]
    if answer:
        key = None
        found = re.search(r"\(([A-Za-z])\)|\b([A-Za-z])\b\s*$", answer[0]["content"]["text"][:60])
        if found:
            key = (found[1] or found[2]).lower()
        parts.append(part("answer", copy.deepcopy(answer), key))
    entry = {
        "id": new_id(head["id"], "question_entry"), "type": "question_entry", "pages": pages,
        "order": head.get("order", 0), "boxes": [], "confidence": 1.0, "continues_from": None,
        "continues_to": None, "flags": [], "children": parts,
        "number": number[0]["value"] if number and number[0]["type"] == "decimal" else None,
        "provenance": _prov(head, "question set by the reviewer"), "refs": {"lines": [], "spans": []},
        "review_status": "ok", "source": head.get("source") or "native",
    }  # fmt: skip
    marks = _markers_out(siblings, first, last)
    before = _previous(siblings, first)
    if before is not None and before["type"] == "question_set":
        before["children"].append(entry)
        before["pages"] = sorted({*before["pages"], *pages})
        _replace_run(siblings, first, last, marks)
        return
    qset = {**{k: v for k, v in entry.items() if k not in ("number",)},
            "id": new_id(head["id"], "question_set"), "type": "question_set",
            "children": [entry]}  # fmt: skip
    _replace_run(siblings, first, last, [qset, *marks])


# ---------------------------------------------------------------------------- out of the book


def not_content(data, ix, edit):
    kind = edit.get("kind")
    if kind not in FURNITURE:
        raise EditError("Say what it is: running head, running foot, page number or printer mark.")
    siblings, units, first, last = _units(ix, edit.get("units") or [])
    content = [u for u in units if u["type"] != "page_marker"]
    for u in content:
        if not u.get("content"):
            raise EditError("Only text can be taken out of the book here.")
    furniture = data.get("furniture")
    if furniture is None:
        furniture = data["furniture"] = []
    for u in content:
        furniture.append({
            "id": u["id"], "kind": kind, "page": u["pages"][0], "refs": _refs(u),
            "content": copy.deepcopy(u["content"]), "boxes": copy.deepcopy(u.get("boxes") or []),
            "confidence": 1.0, "flags": ["set by the reviewer"], "review_status": "ok",
        })  # fmt: skip
        siblings.remove(u)


# ---------------------------------------------------------------------------- merge and order


def _join_content(contents: list[dict]) -> dict:
    """One text record from several, joined by a line end: spans shifted, joins kept."""
    out = copy.deepcopy(contents[0])
    text, spans, joins = out["text"], list(out.get("spans") or []), list(out.get("joins") or [])
    for c in contents[1:]:
        shift = len(text) + 1
        text = text + "\n" + c["text"]
        spans += [{**s, "start": s["start"] + shift, "end": s["end"] + shift}
                  for s in c.get("spans") or ()]  # fmt: skip
        joins += [{**j, "at": j["at"] + shift,
                   "hyphen_at": j["hyphen_at"] + shift if j.get("hyphen_at") is not None else None}
                  for j in c.get("joins") or ()]  # fmt: skip
    out.update(text=text, spans=spans, joins=joins, raw=None, source_runs=[])
    return out


def merge(data, ix, edit):
    siblings, units, first, last = _units(ix, edit.get("units") or [])
    content = [u for u in units if u["type"] != "page_marker"]
    if len(content) < 2:
        raise EditError("Select at least two items to merge.")
    kinds = {u["type"] for u in content}
    if len(kinds) != 1 or kinds.pop() not in TEXT_TYPES:
        raise EditError("Only items of one kind (paragraphs, headings, captions, footnotes or "
                        "list items) can be merged.")  # fmt: skip
    head = content[0]
    if any(u.get("children") for u in content[1:]):
        raise EditError("A list item with a list inside it cannot be merged into another item.")
    head["content"] = _join_content([u["content"] for u in content])
    refs = _refs(head)
    for u in content[1:]:
        r = u.get("refs") or {}
        refs["lines"] += [x for x in r.get("lines") or [] if x not in refs["lines"]]
        refs["spans"] += r.get("spans") or []
    head["refs"] = refs
    head["boxes"] = [b for u in content for b in (u.get("boxes") or [])]
    head["pages"] = sorted({p for u in content for p in u["pages"]})
    head["continues_to"] = content[-1].get("continues_to")
    if head["continues_to"]:
        target = ix.get(head["continues_to"]["unit"])
        if target and target[0].get("continues_from"):
            target[0]["continues_from"] = {**target[0]["continues_from"], "unit": head["id"]}
    if head["type"] == "paragraph":
        head["line_breaks"] = None
    head["provenance"] = _prov(head, f"{len(content)} items merged by the reviewer")
    gone = {id(u) for u in content[1:]}
    marks = _markers_out(siblings, first, last)
    kept = [u for u in siblings[first : last + 1] if id(u) not in gone and u["type"] != "page_marker"]
    _replace_run(siblings, first, last, [*kept, *marks])


def move(data, ix, edit):
    unit, siblings = _get(ix, edit["unit"])
    direction = edit.get("direction")
    if direction not in ("up", "down"):
        raise EditError("A block moves up or down.")
    i = siblings.index(unit)
    step = -1 if direction == "up" else 1
    j = i + step
    while 0 <= j < len(siblings) and siblings[j]["type"] == "page_marker":
        j += step
    if not 0 <= j < len(siblings):
        raise EditError(f"This is already the {'first' if step < 0 else 'last'} item here.")
    siblings[i], siblings[j] = siblings[j], siblings[i]


def swap_columns(data, ix, edit):
    """The run of units on the unit's page, starting at the unit, is read before the units of
    that page above it in the reading order (the person points at the first block of the
    column that comes first)."""
    unit, siblings = _get(ix, edit["unit"])
    page = unit["pages"][0]
    i = siblings.index(unit)
    on_page = [k for k, u in enumerate(siblings)
               if u["type"] != "page_marker" and u["pages"][0] == page]  # fmt: skip
    start = on_page[0]
    if i == start:
        raise EditError("Choose the first block of the column that should be read first; this "
                        "block already starts the page.")  # fmt: skip
    end = on_page[-1]
    if any(siblings[k]["type"] != "page_marker" and siblings[k]["pages"][0] != page
           for k in range(start, end + 1)):  # fmt: skip
        raise EditError("Other pages' text lies between the blocks of this page.")
    run = siblings[start : end + 1]
    pos = run.index(unit)
    siblings[start : end + 1] = run[pos:] + run[:pos]


def _texts_of(node):
    """(content, refs, id hint) of every text record of a table cell item, depth first."""
    if isinstance(node, dict):
        marker = node.get("marker")
        if isinstance(marker, dict) and marker.get("text"):
            yield marker, {"lines": [], "spans": []}
        content = node.get("content")
        if isinstance(content, dict) and "text" in content:
            yield content, node.get("refs") or {"lines": [], "spans": []}
        elif isinstance(content, list):
            for item in content:
                yield from _texts_of(item)
        for key in ("items", "children"):
            for child in node.get(key) or ():
                yield from _texts_of(child)


def _paragraph_of(owner: dict, key: str, n: int, content: dict, refs: dict, box_, reason: str):
    return {
        "id": new_id(owner["id"], "unwrap", key, str(n)),
        "type": "paragraph",
        "pages": list(owner.get("pages") or [(box_ or {}).get("page", 1)]),
        "order": owner.get("order", 0),
        "boxes": [copy.deepcopy(box_)] if box_ else [],
        "confidence": 1.0,
        "continues_from": None,
        "continues_to": None,
        "flags": [],
        "role": "body",
        "line_breaks": None,
        "content": copy.deepcopy(content),
        "refs": copy.deepcopy(refs),
        "provenance": _prov(owner, reason),
        "review_status": "ok",
        "source": owner.get("source") or "native",
    }


def unwrap(data, ix, edit):
    unit, siblings = _get(ix, edit["unit"])
    reason = f"{unit['type']} unwrapped by the reviewer"
    out: list[dict] = []
    if unit["type"] == "box":
        out = list(unit.get("children") or [])
    elif unit["type"] == "table":
        records = []
        if unit.get("title"):
            records.append((unit["title"]["content"], unit["title"].get("refs"), None))
        for cell in sorted(unit.get("cells") or [], key=lambda c: (c["row"], c["column"])):
            for item in cell.get("content") or []:
                records += [(c, r, cell.get("box")) for c, r in _texts_of(item)]
        for note in unit.get("notes") or []:
            records.append((note["content"], note.get("refs"), None))
        out = [_paragraph_of(unit, "t", n, c, r or {"lines": [], "spans": []}, b, reason)
               for n, (c, r, b) in enumerate(records)]  # fmt: skip
    elif unit["type"] == "figure":
        records = []
        for key in ("text", "captions", "credits"):
            for rec in unit.get(key) or []:
                if isinstance(rec.get("content"), dict):
                    records.append((rec["content"], rec.get("refs")))
        box_ = (unit.get("boxes") or [None])[0]
        out = [_paragraph_of(unit, "f", n, c, r or {"lines": [], "spans": []}, box_, reason)
               for n, (c, r) in enumerate(records)]  # fmt: skip
    else:
        raise EditError("Only a table, a figure or a box can be unwrapped.")
    if not out:
        raise EditError("There is no text in it to take out.")
    siblings[siblings.index(unit) : siblings.index(unit) + 1] = out


def table_split(data, ix, edit):
    table, siblings = _get(ix, edit["unit"])
    if table["type"] != "table":
        raise EditError("Choose a table to split.")
    rows = sorted({c["row"] for c in table.get("cells") or []})
    at = int(edit.get("row") or 0)
    if not 2 <= at <= len(rows):
        raise EditError(f"Split before a row from 2 to {len(rows)}.")
    cut = rows[at - 1]
    if any(c["row"] < cut < c["row"] + c.get("row_span", 1) for c in table["cells"]):
        raise EditError("A cell reaches across that row, so the table cannot split there.")
    second = copy.deepcopy(table)
    top = [c for c in table["cells"] if c["row"] < cut]
    low = [c for c in second["cells"] if c["row"] >= cut]
    for c in low:
        c["row"] -= cut
    table["cells"], second["cells"] = top, low
    table["rows"], second["rows"] = at - 1, len(rows) - at + 1
    second["header_rows"] = 0
    table["header_rows"] = min(table.get("header_rows") or 0, table["rows"])
    table["notes"], second["title"] = [], None
    table["continues_to"], second["continues_from"] = None, None
    for part, cells in ((table, top), (second, low)):
        pages = sorted({c["box"]["page"] for c in cells if c.get("box")}) or part["pages"]
        part["pages"] = pages
        part["boxes"] = [b for b in part.get("boxes") or [] if b.get("page") in pages] or part.get("boxes") or []
        part["refs"] = {"lines": [], "spans": []}
        part["provenance"] = _prov(table, f"table split before row {at} by the reviewer")
        part["review_status"] = "ok"
    second["id"] = new_id(table["id"], "split", str(at))
    siblings.insert(siblings.index(table) + 1, second)


OPS = {
    "list_set": list_set, "list_level": list_level, "box": box, "caption": caption,
    "table_make": table_make, "table_text": table_text, "footnote": footnote,
    "paragraph": paragraph, "chapter_authors": chapter_authors, "question": question,
    "bibliography": bibliography, "index_entries": index_entries, "glossary": glossary,
    "not_content": not_content, "merge": merge, "move": move, "swap_columns": swap_columns,
    "unwrap": unwrap, "table_split": table_split,
}  # fmt: skip


def touched(edit: dict) -> list[str]:
    """The unit ids an edit names (to update only those rows in the browser)."""
    ids = list(edit.get("units") or [])
    for key in ("unit", "figure", "table"):
        if edit.get(key):
            ids.append(edit[key])
    return ids


__all__ = ["OPS", "index_units", "number_mark", "touched"]
