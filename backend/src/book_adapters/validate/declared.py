"""Changes the reviewer declared on purpose, read from the book the delivery was made from.

- *removed*: a block taken out of the book text ("Remove from book"). Its text is kept in the
  book's page furniture with the flag REMOVED_FLAG, who removed it (``by:<name>``) and the
  change (``event:<id>``). The delivery does not carry it: the lossless check counts these
  tokens as an intentional removal, never as missing.
- *added*: a block the reviewer typed ("Add text here"). Its provenance carries
  ``added by <name>``. The PDF has no such text: the delivery carries it once, and the lossless
  check counts it as a declared addition, never as extra.

Both are listed in the QC report (page, text, who); the verdict is a warning, never a failure.
"""

from __future__ import annotations

import re

REMOVED_FLAG = "removed by the reviewer"
ADDED_PREFIX = "added by "
_TOKEN = re.compile(r"[\w]+", re.UNICODE)


def tokens(text: str) -> int:
    return len(_TOKEN.findall(text or ""))


def _flag(flags: list, prefix: str) -> str | None:
    return next((f[len(prefix):] for f in flags if f.startswith(prefix)), None)


def _texts(node) -> list[str]:
    """Every text of a node and the nodes below it (depth first)."""
    out: list[str] = []
    if isinstance(node, dict):
        content = node.get("content")
        if isinstance(content, dict) and "text" in content:
            out.append(content["text"])
        elif isinstance(content, list):
            for item in content:
                out += _texts(item)
        for key in ("items", "children", "captions", "credits", "text", "notes"):
            value = node.get(key)
            if isinstance(value, list):
                for child in value:
                    out += _texts(child)
        if isinstance(node.get("title"), dict):
            out += _texts({"content": node["title"].get("content")})
        for cell in node.get("cells") or ():
            out += _texts({"content": cell.get("content")})
    return out


def declared_changes(data: dict) -> dict:
    removed = []
    for item in data.get("furniture") or ():
        flags = item.get("flags") or []
        if REMOVED_FLAG not in flags:
            continue
        text = (item.get("content") or {}).get("text") or ""
        removed.append({
            "page": item["page"], "text": " ".join(text.split()), "who": _flag(flags, "by:"),
            "block": _flag(flags, "block:"), "tokens": tokens(text),
        })  # fmt: skip
    added = []

    def walk(units):
        for unit in units:
            who = next((r[len(ADDED_PREFIX):] for r in (unit.get("provenance") or {}).get("reasons") or ()
                        if r.startswith(ADDED_PREFIX)), None)
            if who is not None:
                text = " ".join(" ".join(_texts(unit)).split())
                added.append({
                    "page": (unit.get("pages") or [None])[0], "text": text, "who": who,
                    "block": unit.get("type"), "tokens": tokens(text),
                })  # fmt: skip
                continue  # the text of its children is the same text
            for key in ("items", "children"):
                if unit.get(key):
                    walk(unit[key])

    walk(data.get("content") or [])
    removed.sort(key=lambda r: (r["page"], r["text"]))
    added.sort(key=lambda r: (r["page"] or 0, r["text"]))
    return {"removed": removed, "added": added,
            "removed_tokens": sum(r["tokens"] for r in removed),
            "added_tokens": sum(r["tokens"] for r in added)}  # fmt: skip
