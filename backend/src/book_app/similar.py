"""'Apply to all similar': the blocks of a book printed like a given block.

A block is similar to another when it is the same element now (type, role, heading level)
and is printed the same way: the font, size, weight and slant of its first line and the
position pattern of its box on the page (left, centred or right, and whether it is indented
from the text's left edge). The style of a line comes from the converter's own page records
(the final archive next to the publication: every span with its font, size and flags); it is
read once per converted book and kept in the job folder.

A change made to a group of units (a heading and the list after it) is repeated on each similar
block with the same number of following units of the same kinds; a block whose neighbours do
not match is listed as not applicable, with the reason.
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path

from .overlay import walk

INDEX = "style_index.json"
BOLD, ITALIC = 16, 2  # PyMuPDF span flags


def _archive(publication: Path) -> Path | None:
    manifest = publication / "manifest.json"
    if not manifest.is_file():
        return None
    final = json.loads(manifest.read_text("utf-8")).get("final_key")
    folder = publication.parent / final if final else None
    return folder if folder and folder.is_dir() else None


def style_index(publication: Path, job_dir: Path) -> dict[str, list]:
    """{line id (16 hex, as book.json names it): [font, size, bold, italic]} of the book."""
    path = job_dir / INDEX
    key = publication.name
    if path.is_file():
        saved = json.loads(path.read_text("utf-8"))
        if saved.get("publication") == key:
            return saved["lines"]
    archive = _archive(publication)
    lines: dict[str, list] = {}
    if archive is not None:
        for page in sorted(archive.glob("page_*.json.gz")):
            data = json.loads(gzip.decompress(page.read_bytes()))
            spans = data["source"]["store"]["spans"]
            for line_id, span_ids in (data.get("line_spans") or {}).items():
                found = [spans[s] for s in span_ids if s in spans and spans[s]["text"].strip()]
                if not found:
                    continue
                weight = Counter()
                for s in found:  # the style of most of the line's characters
                    style = (s["font"], round(s["size"] * 2) / 2, bool(s["flags"] & BOLD),
                             bool(s["flags"] & ITALIC))  # fmt: skip
                    weight[style] += len(s["text"])
                lines[line_id[:16]] = list(weight.most_common(1)[0][0])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"publication": key, "lines": lines}), "utf-8")
    tmp.replace(path)
    return lines


def _position(unit: dict, page: dict, left_edge: float | None) -> str:
    box = (unit.get("boxes") or [None])[0]
    if not box:
        return "none"
    width = page["width"]
    centre = (box["x0"] + box["x1"]) / 2
    if abs(centre - width / 2) <= 0.04 * width and box["x0"] > 0.15 * width:
        return "centre"
    if box["x0"] > width / 2:
        return "right"
    if left_edge is not None and box["x0"] - left_edge > 0.03 * width:
        return "indented"
    return "left"


def element(unit: dict) -> tuple:
    return (unit["type"], unit.get("role"), unit.get("level") if unit["type"] == "heading" else None,
            unit.get("list_type"))  # fmt: skip


def signature(unit: dict, lines: dict, page: dict, left_edge) -> tuple | None:
    first = next((lines.get(line) for line in (unit.get("refs") or {}).get("lines") or ()
                  if lines.get(line)), None)  # fmt: skip
    if first is None:
        return None
    return (*element(unit), *first, _position(unit, page, left_edge))


def _left_edges(book: dict) -> dict[int, float]:
    """The text's left edge per page: the most common left of the page's paragraphs."""
    edges: dict[int, Counter] = {}
    for unit, _ in walk(book["content"]):
        if unit["type"] == "paragraph" and unit.get("boxes"):
            b = unit["boxes"][0]
            edges.setdefault(b["page"], Counter())[round(b["x0"])] += 1
    return {p: c.most_common(1)[0][0] for p, c in edges.items()}


def matches(book: dict, edit: dict, lines: dict) -> dict:
    """The blocks printed like the edit's first unit (other than the edit's own units), each
    with the edit it would get: {"anchor", "style", "matches": [{unit, page, text, edit} or
    {unit, page, text, reason}]}."""
    named = list(edit.get("units") or ([edit["unit"]] if edit.get("unit") else []))
    if not named:
        return {"anchor": None, "style": None, "matches": []}
    index = {}
    for unit, siblings in walk(book["content"]):
        if unit.get("id"):
            index[unit["id"]] = (unit, siblings)
    if named[0] not in index:
        return {"anchor": None, "style": None, "matches": []}
    pages = book["pages"]
    edges = _left_edges(book)

    def sig(u):
        page_no = u["pages"][0]
        return signature(u, lines, pages[page_no - 1], edges.get(page_no))

    anchor, siblings = index[named[0]]
    want = sig(anchor)
    if want is None:
        return {"anchor": anchor["id"], "style": None, "matches": []}
    # the units the change takes after its first one, by kind (page markers aside)
    start = siblings.index(anchor)
    followers = [u for u in siblings[start + 1 :] if u["type"] != "page_marker"][: len(named) - 1]
    if [u["id"] for u in followers] != named[1:]:
        followers = None  # the units are not the ones right after the first: no repeat
    kinds = [element(u)[:2] for u in followers or ()]
    own = set(named)
    found = []
    for unit, sibs in walk(book["content"]):
        if not unit.get("id") or unit["id"] in own or element(unit) != element(anchor):
            continue
        if sig(unit) != want:
            continue
        text = " ".join(((unit.get("content") or {}).get("text") or "").split())[:100]
        row = {"unit": unit["id"], "page": unit["pages"][0], "text": text}
        if len(named) > 1:
            if followers is None:
                found.append({**row, "reason": "the change names units that do not follow each other"})
                continue
            i = sibs.index(unit)
            after = [u for u in sibs[i + 1 :] if u["type"] != "page_marker"][: len(kinds)]
            if [element(u)[:2] for u in after] != kinds or any(u["id"] in own for u in after):
                found.append({**row, "reason": "the blocks after it are not like the ones you changed"})
                continue
            ids = [unit["id"], *(u["id"] for u in after)]
        else:
            ids = [unit["id"]]
        found.append({**row, "edit": repeat(edit, ids)})
    return {"anchor": anchor["id"], "style": list(want), "matches": found}


def repeat(edit: dict, ids: list[str]) -> dict:
    """The same change on other units (same kind, same options, same scope)."""
    out = {k: v for k, v in edit.items() if k not in ("id", "at", "who", "type", "group", "before")}
    if "units" in edit:
        out["units"] = ids
    else:
        out["unit"] = ids[0]
    return out


__all__ = ["matches", "repeat", "style_index"]
