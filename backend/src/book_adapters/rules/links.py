"""Link rules: links added while text is written. They return (start, end, href) over
source offsets of the record, or (start, end, href, drops) where drops are offsets of line
ends inside the linked text that are not spaces (the writer records each in the ledger)."""

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


_URL_START = re.compile(r"(?i)\b(?:https?://|www\.)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_CHARS = re.compile(r"[^\s<>\"“”‘’]+")
_URL_TRAIL = ".,;:!?)]}'\""


def _continues(before: str, run: str) -> bool:
    """A line end inside a web address: the address broke after a slash, or the next
    line's run is a path ("eu/Guidelines", "ba911…/1697…/ART.pdf"), not a word."""
    if before == "/":
        return True
    lower = run[0].isdigit() or run[0].islower()
    if before in "-_=&?" and lower and not any(c.isupper() for c in run):
        return "." in run or "/" in run  # "code-of-practice-annexes-" / "october-2021.pdf"
    return "/" in run and lower


def _url_end(text: str, start: int, dropped: set[int]) -> tuple[int, list[int]]:
    """End of a web address starting at ``start`` and the line ends inside it (those a join
    decision already removes are not listed). Trailing punctuation is not part of it."""
    end = _URL_CHARS.match(text, start).end()
    breaks: list[int] = []
    while end < len(text) and text[end] == "\n":
        nxt = end
        while nxt < len(text) and text[nxt] == "\n":
            nxt += 1
        m = _URL_CHARS.match(text, nxt)
        if not m or not _continues(text[end - 1], m.group()):
            break
        breaks += [i for i in range(end, nxt) if i not in dropped]
        end = m.end()
    while end > start and text[end - 1] in _URL_TRAIL:
        end -= 1
    return end, [b for b in breaks if b < end]


_HOST = re.compile(r"[\w-]+(?:\.[\w-]+)*\.?")


def _linkable(href: str) -> bool:
    """A printed address links only if its host is a real host name. A typo in the source
    (``…gwu.edu.Kalamazoo%20Essential….pdf``: no slash after the host) stays plain text,
    since readers' software rejects such a link (EPUBCheck RSC-020)."""
    rest = re.sub(r"(?i)^https?://", "", href)
    host = re.split(r"[/?#]", rest, maxsplit=1)[0].rpartition("@")[2]
    host = re.sub(r":\d*$", "", host)
    return bool(_HOST.fullmatch(host))


def link_urls_emails(text: str, spans: list[dict], ctx: dict) -> list[tuple]:
    """Web and e-mail addresses printed in the text (no PDF link annotation) link to
    themselves: ``www.`` gets the profile's scheme (``ctx['www_scheme']``), an e-mail gets
    ``mailto:``. Line ends inside a web address are returned as drops."""
    dropped = ctx.get("dropped") or set()
    out: list[tuple] = []
    taken: list[tuple[int, int]] = []
    for m in _URL_START.finditer(text):
        if any(s <= m.start() < e for s, e in taken):
            continue
        end, breaks = _url_end(text, m.start(), dropped)
        if end - m.start() <= len(m.group()):
            continue
        skip = set(breaks) | dropped
        href = "".join(
            ch for i, ch in enumerate(text[m.start() : end], m.start())
            if i not in skip and ch != "\xad"
        )  # fmt: skip
        if href.lower().startswith("www."):
            href = (ctx.get("www_scheme") or "http://") + href
        if not _linkable(href):
            continue
        out.append((m.start(), end, href, breaks))
        taken.append((m.start(), end))
    for m in _EMAIL.finditer(text):
        start, end = m.start(), m.end()
        while end > start and text[end - 1] in _URL_TRAIL:
            end -= 1
        if any(s < end and start < e for s, e in taken):
            continue
        out.append((start, end, "mailto:" + text[start:end], []))
        taken.append((start, end))
    return sorted(out)


def link_object_mentions(text: str, spans: list[dict], ctx: dict) -> list[tuple[int, int, str]]:
    """ "Fig. 1", "Figure 2.3", "Table 4", "Flowchart 1", "Box 2" in running text link to the
    object with that printed number in the same chapter (``ctx['object_ids']``:
    (kind, number) -> id; ``ctx['mention_words']``: printed word -> kind). In "Tables 1 and
    2" or "Figs. 3, 4" each further number links on its own (as delivered)."""
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
        if cut is not None:
            continue
        pos = end
        while more := _MORE_NUMBERS.match(text, pos):
            target = ids.get((kind, more.group(1)))
            if target:
                out.append((more.start(1), more.end(1), f"#{target}"))
            pos = more.end()
    return out


_MORE_NUMBERS = re.compile(r"(?:\s*,\s*|\s+(?:and|&)\s+)(\d+(?:\.\d+)*[A-Z]?)\b")
