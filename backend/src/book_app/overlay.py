"""Review edits applied to a *copy* of the converter's book.json.

The converter's output is never edited. An export (and the browse view) builds an overlay
publication from the converter's folder plus the reviewer's edits, in the order they were
made, and the adapter reads that overlay as it would any publication. Every edit is
re-checked against the book schema, and a text edit never loses text: a split moves
characters between two units, a list drops only the printed bullet mark.

Edits (``op``):
  heading_set     {unit, level, role?}   level of a heading, or make a paragraph a heading
  heading_remove  {unit}                 a heading becomes a body paragraph
  new_chapter     {unit}                 the heading (or paragraph) starts a new chapter
  join_next       {unit}                 the paragraph continues in the next paragraph
  unjoin          {unit}                 remove that continuation
  split           {unit, line}           the paragraph starts a new paragraph at line `line`
  make_list       {units: [...]}         consecutive bullet paragraphs become one list
  heading_kind    {unit, kind}           part, chapter, section, front_matter or back_matter
  heading_number  {unit, number}         the number of a chapter or part (printed or chosen)
  heading_text    {unit, text}           the title loses a stray number at its start or end
  heading_attach  {unit}                 the heading belongs to the chapter before it
  alt_text        {unit, text}           description of a figure or an equation
  decorative      {unit, value}          a figure is decoration (profile decides to omit it)
  char            {unit, offset, char}   replace one character (minus sign / en dash)
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

from book_adapters.engine.load import book_schema

BULLET_CHARS = set("•●■◼◻▪▫□❖♦♢◆◇◊➔➜➢➤→–—·○◦▸►‣⁃∙")
SECTION_ROLES = {1: "section"}


class EditError(ValueError):
    pass


def new_id(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]


_DEFS = {
    "heading": "Heading",
    "paragraph": "Paragraph",
    "list_item": "ListItem",
    "list": "ListNode",
}


def _allowed(type_name: str) -> set[str]:
    return set(book_schema()["$defs"][_DEFS[type_name]]["properties"])


def walk(units, parent=None):
    """(unit, siblings list) for every unit of the content tree."""
    for unit in units:
        yield unit, units
        for key in ("items", "children"):
            if unit.get(key):
                yield from walk(unit[key], unit)


def index_units(data: dict) -> dict[str, tuple[dict, list]]:
    return {u["id"]: (u, siblings) for u, siblings in walk(data["content"]) if u.get("id")}


# ---------------------------------------------------------------------------- text slicing


def slice_content(content: dict, start: int, end: int | None = None) -> dict:
    """The part of a text record between two offsets: spans clipped and shifted, line-end
    joins kept with their offsets shifted. Equal to the source text over that range."""
    text = content["text"]
    end = len(text) if end is None else end
    out = copy.deepcopy(content)
    out["text"] = text[start:end]
    spans = []
    for s in content.get("spans") or ():
        a, b = max(s["start"], start), min(s["end"], end)
        if a < b:
            spans.append({**s, "start": a - start, "end": b - start})
    out["spans"] = spans
    joins = []
    for j in content.get("joins") or ():
        if start <= j["at"] < end:
            hyphen = j.get("hyphen_at")
            joins.append(
                {
                    **j,
                    "at": j["at"] - start,
                    "hyphen_at": hyphen - start if hyphen is not None and hyphen >= start else None,
                }
            )
    out["joins"] = joins
    out["raw"] = None
    out["source_runs"] = []
    return out


def line_starts(text: str) -> list[int]:
    starts, pos = [0], 0
    for line in text.split("\n")[:-1]:
        pos += len(line) + 1
        starts.append(pos)
    return starts


# ---------------------------------------------------------------------------- operations


def _convert(unit: dict, to_type: str, **extra) -> dict:
    keep = _allowed(to_type)
    out = {k: v for k, v in unit.items() if k in keep}
    out.update(type=to_type, **extra)
    return out


def _replace(siblings: list, unit: dict, new: dict) -> None:
    siblings[siblings.index(unit)] = new


def _chapter_level(data: dict) -> int:
    levels = [
        u.get("level")
        for u, _ in walk(data["content"])
        if u["type"] == "heading" and u.get("role") == "chapter" and u.get("level")
    ]
    return min(levels) if levels else 1


def _heading(data, ix, edit, chapter=False):
    unit, siblings = _get(ix, edit["unit"])
    if unit["type"] not in ("heading", "paragraph"):
        raise EditError("Only a heading or a paragraph can be a heading.")
    if chapter:
        level, role = _chapter_level(data), "chapter"
    else:
        level = int(edit["level"])
        if level < 1 or level > 9:
            raise EditError("A heading level is from 1 to 9.")
        role = edit.get("role") or (
            unit.get("role")
            if unit["type"] == "heading" and unit.get("role") != "chapter"
            else SECTION_ROLES.get(level, "subsection")
        )
    if unit["type"] == "heading":
        unit["level"], unit["role"], unit["level_method"] = level, role, "reviewer"
        unit["review_status"] = "ok"
    else:
        new = _convert(
            unit, "heading", level=level, role=role, level_method="reviewer", review_status="ok"
        )
        new["provenance"] = _prov(unit, "made a heading by the reviewer")
        _replace(siblings, unit, new)


def _heading_remove(data, ix, edit):
    unit, siblings = _get(ix, edit["unit"])
    if unit["type"] != "heading":
        raise EditError("This is not a heading.")
    new = _convert(unit, "paragraph", role="body", review_status="ok")
    new["provenance"] = _prov(unit, "heading removed by the reviewer")
    _replace(siblings, unit, new)
    outline = (data.get("navigation") or {}).get("outline")
    if outline:
        data["navigation"]["outline"] = [e for e in outline if e.get("heading") != unit["id"]]


def _prov(unit: dict, reason: str) -> dict:
    p = copy.deepcopy(unit.get("provenance") or {"stages": []})
    p.setdefault("stages", [])
    if "review" not in p["stages"]:
        p["stages"].append("review")
    p["reasons"] = [*p.get("reasons", []), reason]
    return p


def _get(ix, unit_id):
    if unit_id not in ix:
        raise EditError(
            f"The text {unit_id} is no longer in the book (an earlier edit changed it)."
        )
    return ix[unit_id]


def _continuation(target: str, kind: str = "column", hyphen: str | None = None) -> dict:
    return {
        "unit": target,
        "kind": kind,
        "confidence": 1.0,
        "hyphen": hyphen,
        "word_join": False,
        "page_marker": None,
        "skipped": [],
        "review_status": "ok",
    }


def _join_next(data, ix, edit):
    unit, siblings = _get(ix, edit["unit"])
    if unit["type"] != "paragraph":
        raise EditError("Only a paragraph can be joined with the next paragraph.")
    i = siblings.index(unit)
    nxt = next((u for u in siblings[i + 1 :] if u["type"] not in ("page_marker",)), None)
    if nxt is None or nxt["type"] != "paragraph":
        raise EditError("The next item is not a paragraph, so there is nothing to join with.")
    kind = "column" if unit["pages"][-1] == nxt["pages"][0] else "page"
    hyphen = "soft_join" if unit["content"]["text"].rstrip().endswith("\xad") else None
    unit["continues_to"] = _continuation(nxt["id"], kind, hyphen)
    nxt["continues_from"] = _continuation(unit["id"], kind, hyphen)


def _unjoin(data, ix, edit):
    unit, _ = _get(ix, edit["unit"])
    cont = unit.get("continues_to")
    if not cont:
        raise EditError("This paragraph is not joined with the next one.")
    target = ix.get(cont["unit"])
    if target:
        target[0]["continues_from"] = None
    unit["continues_to"] = None


def _split(data, ix, edit):
    unit, siblings = _get(ix, edit["unit"])
    if unit["type"] != "paragraph":
        raise EditError("Only a paragraph can be split.")
    text = unit["content"]["text"]
    starts = line_starts(text)
    line = int(edit["line"])
    if not 1 <= line < len(starts):
        raise EditError("Choose a line inside the paragraph to start the new paragraph.")
    k = starts[line]
    first = slice_content(unit["content"], 0, k - 1)  # the line end itself is not text
    second = slice_content(unit["content"], k)
    if not first["text"].strip() or not second["text"].strip():
        raise EditError("Both parts of a split need text.")
    new = copy.deepcopy(unit)
    new["id"] = new_id(unit["id"], "split", str(line))
    if new["id"] in ix:
        raise EditError("This paragraph is already split there.")
    refs = unit.get("refs") or {"lines": [], "spans": []}
    n_lines = len(starts)
    if len(refs.get("lines") or ()) == n_lines:
        unit["refs"] = {**refs, "lines": refs["lines"][:line]}
        new["refs"] = {**refs, "lines": refs["lines"][line:]}
    box = unit.get("boxes") or []
    if len(box) == 1:
        b = box[0]
        cut = b["y0"] + (b["y1"] - b["y0"]) * line / n_lines
        unit["boxes"] = [{**b, "y1": round(cut, 2)}]
        new["boxes"] = [{**b, "y0": round(cut, 2)}]
    unit["content"], new["content"] = first, second
    new["continues_from"] = None
    new["continues_to"] = unit.get("continues_to")
    unit["continues_to"] = None
    if new["continues_to"]:
        target = ix.get(new["continues_to"]["unit"])
        if target and target[0].get("continues_from"):
            target[0]["continues_from"] = {**target[0]["continues_from"], "unit": new["id"]}
    new["provenance"] = _prov(unit, f"split at line {line + 1} by the reviewer")
    siblings.insert(siblings.index(unit) + 1, new)


def first_mark(text: str, marks: dict) -> tuple[str, int] | None:
    """The printed bullet mark at the start of a text and the offset where the text starts."""
    m = re.match(r"^[\s ]*(\S+)", text)
    if not m:
        return None
    token = m.group(1)
    glyph = token if token in marks else (token[0] if token[0] in BULLET_CHARS else None)
    if glyph is None:
        return None
    end = m.start(1) + len(glyph)
    while end < len(text) and text[end] in " \t    ":
        end += 1
    return glyph, end


def _make_list(data, ix, edit, marks):
    ids = edit["units"]
    if len(ids) < 1:
        raise EditError("Select at least one paragraph.")
    units = [_get(ix, i)[0] for i in ids]
    siblings = ix[ids[0]][1]
    if any(ix[i][1] is not siblings for i in ids):
        raise EditError("The selected paragraphs are not in one place in the text.")
    pos = [siblings.index(u) for u in units]
    if pos != sorted(pos) or any(b - a != 1 for a, b in zip(pos, pos[1:], strict=False)):
        raise EditError("Select paragraphs that follow each other.")
    if any(u["type"] != "paragraph" for u in units):
        raise EditError("Only paragraphs can be made into a list.")
    items = []
    for u in units:
        found = first_mark(u["content"]["text"], marks)
        if not found:
            raise EditError("No bullet mark at the start of: " + repr(u["content"]["text"][:30]))
        glyph, cut = found
        item = _convert(
            u,
            "list_item",
            item_role="item",
            level=1,
            marker={"text": glyph, "type": "bullet", "punctuation": "none", "value": None},
            children=[],
            locators=[],
            names=[],
            term=None,
        )
        item["content"] = slice_content(u["content"], cut)
        item["provenance"] = _prov(u, "bullet paragraph made a list item by the reviewer")
        items.append(item)
    first = units[0]
    lst = {
        "id": new_id(first["id"], "list", str(len(ids))),
        "type": "list",
        "pages": sorted({p for u in units for p in u["pages"]}),
        "order": first.get("order", 0),
        "boxes": [],
        "confidence": 1.0,
        "continues_from": None,
        "continues_to": None,
        "flags": [],
        "items": items,
        "level": 1,
        "list_id": new_id(first["id"], "list_id"),
        "list_role": "general",
        "list_type": "bulleted",
        "marker_type": "bullet",
        "provenance": _prov(first, "list made by the reviewer"),
        "refs": {"lines": [], "spans": []},
        "review_status": "ok",
        "segment": 0,
        "source": "native",
        "start": None,
    }
    siblings[pos[0] : pos[-1] + 1] = [lst]


def _alt_text(data, ix, edit):
    unit, _ = _get(ix, edit["unit"])
    if unit["type"] not in ("figure", "equation"):
        raise EditError("Only a figure or an equation has alt text.")
    text = (edit.get("text") or "").strip()
    if not text:
        raise EditError("Write the description.")
    unit["alt_text"] = {
        "text": text,
        "source": "human",
        "status": "verified",
        "language": None,
        "model": None,
    }


def _decorative(data, ix, edit):
    unit, _ = _get(ix, edit["unit"])
    if unit["type"] != "figure":
        raise EditError("Only a figure can be decorative.")
    value = bool(edit.get("value", True))
    unit["decorative"] = value
    unit["decorative_reason"] = "marked by the reviewer" if value else None


def _char(data, ix, edit):
    unit, _ = _get(ix, edit["unit"])
    content = unit.get("content")
    if not content:
        raise EditError("This item has no text.")
    offset, ch = int(edit["offset"]), edit["char"]
    text = content["text"]
    if len(ch) != 1 or not 0 <= offset < len(text):
        raise EditError("That character is no longer there.")
    content["text"] = text[:offset] + ch + text[offset + 1 :]


KINDS = ("part", "chapter", "section", "front_matter", "back_matter")
NUMBER_RE = re.compile(r"[0-9]{1,4}|[IVXLCDMivxlcdm]{1,8}|[A-Za-z]")


def _number(value) -> str:
    text = str(value or "").strip()
    if not NUMBER_RE.fullmatch(text):
        raise EditError("A number is digits, a Roman numeral or one letter.")
    return text


def _heading_kind(data, ix, edit):
    kind = edit.get("kind")
    if kind not in KINDS:
        raise EditError("A heading is a part, a chapter, a section, front matter or back matter.")
    unit, _ = _get(ix, edit["unit"])
    chapter = _chapter_level(data)
    role, level = {
        "chapter": ("chapter", chapter),
        "part": ("part", max(1, chapter - 1)),
        "section": ("section", chapter + 1),
        "front_matter": ("front_section_title", 1),
        "back_matter": ("rear_section_title", 1),
    }[kind]
    if kind in ("front_matter", "back_matter"):
        _move_page_zone(data, unit, "front" if kind == "front_matter" else "rear")
    _heading(data, ix, {"unit": edit["unit"], "level": min(level, 9), "role": role})


def _move_page_zone(data, unit, zone):
    """The heading's page joins the front or the rear matter when it touches it; a page in the
    middle of the book cannot (the book parts decide the zones)."""
    pages = data.get("pages") or []
    page = unit["pages"][0]
    if not 1 <= page <= len(pages) or pages[page - 1].get("zone") == zone:
        return
    others = pages[: page - 1] if zone == "front" else pages[page:]
    if any(p.get("zone") != zone for p in others):
        where = "first" if zone == "front" else "last"
        raise EditError(f"This page is not among the {where} pages. Change the book parts.")
    pages[page - 1]["zone"] = zone


def _heading_number(data, ix, edit):
    unit, _ = _get(ix, edit["unit"])
    if unit["type"] != "heading":
        raise EditError("Only a heading has a number.")
    unit["number"] = _number(edit.get("number"))


def _heading_text(data, ix, edit):
    """The title keeps its words: only a number (with its spaces and punctuation) at the start
    or the end may go. The converter's text is never edited; this is the reviewer's copy."""
    unit, _ = _get(ix, edit["unit"])
    if unit["type"] != "heading":
        raise EditError("Only the text of a heading can be edited.")
    old, new = unit["content"]["text"], edit.get("text")
    if not isinstance(new, str) or not new.strip():
        raise EditError("The title cannot be empty.")
    start = old.find(new)
    if start < 0:
        raise EditError("A title can only lose a number at its start or its end.")
    gone = old[:start] + old[start + len(new) :]
    if not gone or any(unicodedata.category(c)[0] not in "NZPSC" for c in gone):
        raise EditError("A title can only lose a number at its start or its end.")
    unit["content"] = slice_content(unit["content"], start, start + len(new))
    unit["provenance"] = _prov(unit, "number removed from the title by the reviewer")
    removed = gone.strip(" .:-)(\t\n")
    if NUMBER_RE.fullmatch(removed) and not unit.get("number"):
        unit["number"] = removed  # the number the title lost is the number of the chapter


def _heading_attach(data, ix, edit):
    unit, _ = _get(ix, edit["unit"])
    if unit["type"] != "heading":
        raise EditError("Only a heading can belong to the chapter before.")
    unit["level"], unit["level_method"] = _chapter_level(data) + 1, "reviewer"
    unit["role"] = "feature_title"


def chapter_rows(data: dict) -> list[dict]:
    """Every part and chapter of the book as it will be exported: number, title, page."""
    rows = []
    for unit, _ in walk(data["content"]):
        if unit["type"] != "heading" or unit.get("role") not in ("part", "chapter"):
            continue
        text = " ".join((unit["content"]["text"] or "").split())
        number, title = unit.get("number"), text
        match = re.match(r"^(\d+|[IVXLCDMivxlcdm]+)[.:)\-\u2013\u2014\s]+(\S.*)$", text) or None
        tail = re.match(r"^(\S.*?)\s+(\d+)$", text)
        if match and not number:
            number, title = match[1], match[2]
        elif tail and not number:
            title, number = tail[1], tail[2]
        rows.append({
            "unit": unit["id"], "role": unit["role"], "level": unit.get("level"),
            "number": number, "title": title, "text": text, "page": unit["pages"][0],
            "set_by_reviewer": bool(unit.get("number")),
        })  # fmt: skip
    return rows


STRUCTURAL = {"book_title", "part", "unit", "chapter", "front_section_title", "rear_section_title"}
ATTACHED = {"feature_title", "sidebar_title"}


def _keep_inside(data: dict) -> None:
    """The headings printed after a chapter or part the person set, up to the next start, belong
    to it: one set at the start's level or above (the converter read the chapter one level
    lower than the person did) goes one level below the start, so the export does not read it
    as a start of its own. Starts the converter made are left as they are."""
    level = None
    for unit, _ in walk(data["content"]):
        if unit["type"] != "heading":
            continue
        role = unit.get("role")
        if role in STRUCTURAL:
            mine = role in ("part", "chapter") and unit.get("level_method") == "reviewer"
            level = unit.get("level") if mine else None
        elif level is not None and role not in ATTACHED and unit.get("level", 9) <= level:
            unit["level"], unit["level_method"] = min(level + 1, 9), "reviewer"


def apply_edits(
    data: dict, edits: list[dict], marks: dict | None = None
) -> tuple[dict, list[dict], list[dict]]:
    """A new book dict with the edits applied, the edits that were applied and the ones that
    could not be (each with a plain reason)."""
    data = copy.deepcopy(data)
    applied, failed = [], []
    for edit in edits:
        ix = index_units(data)
        snapshot = copy.deepcopy(data["content"])
        try:
            op = edit["op"]
            if op == "heading_set":
                _heading(data, ix, edit)
            elif op == "new_chapter":
                _heading(data, ix, edit, chapter=True)
                if edit.get("number") not in (None, ""):
                    _heading_number(data, index_units(data), edit)
            elif op == "heading_kind":
                _heading_kind(data, ix, edit)
            elif op == "heading_number":
                _heading_number(data, ix, edit)
            elif op == "heading_text":
                _heading_text(data, ix, edit)
            elif op == "heading_attach":
                _heading_attach(data, ix, edit)
            elif op == "heading_remove":
                _heading_remove(data, ix, edit)
            elif op == "join_next":
                _join_next(data, ix, edit)
            elif op == "unjoin":
                _unjoin(data, ix, edit)
            elif op == "split":
                _split(data, ix, edit)
            elif op == "make_list":
                _make_list(data, ix, edit, marks or {})
            elif op == "alt_text":
                _alt_text(data, ix, edit)
            elif op == "decorative":
                _decorative(data, ix, edit)
            elif op == "char":
                _char(data, ix, edit)
            else:
                raise EditError(f"Unknown edit {op!r}.")
            applied.append(edit)
        except (EditError, KeyError, ValueError) as exc:
            data["content"] = snapshot
            failed.append({"edit": edit.get("id"), "op": edit.get("op"), "reason": str(exc)})
    if any(e["op"] == "new_chapter" or (e["op"] == "heading_kind"
           and e.get("kind") in ("chapter", "part")) for e in applied):  # fmt: skip
        _keep_inside(data)
    return data, applied, failed


def apply_checked(data: dict, edits: list[dict], marks: dict | None = None):
    """``apply_edits``, then a schema check; if the result is not a valid book, the edits are
    applied one by one and the ones that break the book are refused with a plain reason."""
    result, applied, failed = apply_edits(data, edits, marks)
    if not schema_errors(result):
        return result, applied, failed
    current, applied, failed = data, [], []
    for edit in edits:
        nxt, ok, bad = apply_edits(current, [edit], marks)
        if bad:
            failed += bad
        elif schema_errors(nxt):
            failed.append(
                {
                    "edit": edit.get("id"),
                    "op": edit.get("op"),
                    "reason": "This change would make the book invalid, so it was not applied.",
                }
            )
        else:
            current, applied = nxt, applied + ok
    return current, applied, failed


# ---------------------------------------------------------------------------- overlay folder


def schema_errors(data: dict) -> list[str]:
    import jsonschema

    validator = jsonschema.Draft202012Validator(book_schema())
    return [
        f"{'/'.join(map(str, e.path))}: {e.message[:160]}"
        for e in sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.path)))[:5]
    ]


def write_overlay(publication: Path, data: dict, target: Path, check: bool = True) -> Path:
    """An overlay publication folder: the modified book.json, a matching manifest, and the
    converter's images and review crops linked (not copied)."""
    errors = schema_errors(data) if check else []
    if errors:
        raise EditError("The edited book does not match the book schema: " + "; ".join(errors))
    if target.exists():
        for child in target.iterdir():
            if child.is_symlink() or child.is_file():
                child.unlink()
            else:
                import shutil

                shutil.rmtree(child)
    target.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    (target / "book.json").write_bytes(raw)
    if (publication / "manifest.json").is_file():
        manifest = json.loads((publication / "manifest.json").read_text("utf-8"))
        files = manifest.get("files", {})
        digest = hashlib.sha256(raw).hexdigest()
        if isinstance(files, dict):
            files["book.json"] = digest
        else:
            for entry in files:
                if entry.get("path") == "book.json":
                    entry["sha256"] = digest
        manifest["overlay"] = True
        (target / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), "utf-8")
    for name in ("images", "review"):
        if (publication / name).exists():
            os.symlink((publication / name).resolve(), target / name)
    return target


def edits_key(edits: list[dict]) -> str:
    return hashlib.sha256(json.dumps(edits, sort_keys=True).encode()).hexdigest()[:16]
