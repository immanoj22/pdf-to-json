"""Link rules: internal links added while text is written. They never change text; they
return (start, end, href) over source offsets of the record."""

from __future__ import annotations

import re

_CITE = re.compile(r"\d+")
_CITE_ONLY = re.compile(r"^[\s\d,;–—\-]+$")


def link_citations(text: str, spans: list[dict], ctx: dict) -> list[tuple[int, int, str]]:
    """Superscript reference numbers ("4", "1–8", "2,5") link to bibliography entries of
    the same chapter (``ctx['bib_ids']``: number -> id). Numbers without an entry stay
    plain."""
    bib = ctx.get("bib_ids") or {}
    if not bib:
        return []
    out = []
    for span in spans:
        if span["kind"] != "superscript":
            continue
        piece = text[span["start"] : span["end"]]
        if not _CITE_ONLY.match(piece):
            continue
        for m in _CITE.finditer(piece):
            target = bib.get(int(m.group()))
            if target:
                out.append((span["start"] + m.start(), span["start"] + m.end(), f"#{target}"))
    return out


def link_object_mentions(text: str, spans: list[dict], ctx: dict) -> list[tuple[int, int, str]]:
    """ "Fig. 1", "Figure 2.3", "Table 4", "Flowchart 1", "Box 2" in running text link to the
    object with that printed number in the same chapter (``ctx['object_ids']``:
    (kind, number) -> id; ``ctx['mention_words']``: printed word -> kind)."""
    ids = ctx.get("object_ids") or {}
    words = ctx.get("mention_words") or {}
    if not ids or not words:
        return []
    alternation = "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True))
    pattern = re.compile(rf"\b({alternation})\.?\s*(\d+(?:\.\d+)*[A-Z]?)\b", re.I)
    supers = sorted(s["start"] for s in spans if s["kind"] == "superscript")
    out = []
    for m in pattern.finditer(text):
        kind = words.get(m.group(1).lower())
        number, end = m.group(2), m.end()
        cut = next((s for s in supers if m.start(2) < s < m.end(2)), None)
        if cut is not None:  # a citation number set in superscript is not part of it
            number = text[m.start(2) : cut].rstrip(".")
            end = m.start(2) + len(number)
        target = ids.get((kind, number))
        if target:
            out.append((m.start(), end, f"#{target}"))
    return out
