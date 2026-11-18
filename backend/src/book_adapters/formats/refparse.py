"""Structured parts of one reference printed as ``Authors. Title. (Year) Source Vol, pp. a–b.``

The parts come only from the printed text (no lookup, no guess) and are returned as positions in
it, so the writer can wrap each part in an element and keep every other character of the
reference exactly where it was printed. A reference that does not fit the pattern is returned as
``None`` and stays a plain mixed-citation. The pattern is the one the bibliography is printed in
(surname, initials; the title; the year in brackets; the source, volume and pages), never a list
of names or journals."""

from __future__ import annotations

import regex

INITIALS = r"(?:\p{Lu}[\p{L}]?\.[\s \-]?)+"
PERSON = regex.compile(rf"(?P<sur>[^,.()]+?),\s+(?P<given>{INITIALS})")
SEP = regex.compile(r"\s*(?:,\s*(?:and\s+|&\s+)?|\s+and\s+|\s*&\s+)")
TAIL = regex.compile(
    r"^(?P<title>.+?)[.?!]?\s*\((?P<year>\d{4}[a-z]?)\)\s*(?P<source>.+?)"
    r"(?:\s+(?P<vol>[\p{L}\d][\p{L}\d\-./]*))?"
    r"(?:,?\s+pp?\.\s*(?P<first>[\p{L}\d.]+)(?:\s*[‐-―\-]\s*(?P<last>[\p{L}\d.]+))?)?\.?\s*$"
)


def normalize(text: str) -> str:
    return " ".join(text.split())


def _span(match, name, base, strip=" .,"):
    start, end = match.span(name)
    while start < end and match.string[start] in strip:
        start += 1
    while end > start and match.string[end - 1] in strip:
        end -= 1
    return (base + start, base + end)


def parse_reference(text: str) -> dict | None:
    """``text`` is the normalized reference (:func:`normalize`). Returns
    {"authors": [(surname span, given-names span)], "title", "year", "source", "volume",
    "fpage", "lpage"} with (start, end) spans into ``text`` (volume, fpage, lpage may be
    None), or None."""
    authors, pos = [], 0
    while True:
        m = PERSON.match(text, pos)
        if not m:
            break
        sur, given = m.span("sur"), m.span("given")
        given = (given[0], given[0] + len(m.group("given").rstrip()))
        authors.append(((sur[0], sur[0] + len(m.group("sur").rstrip())), given))
        pos = given[1]
        s = SEP.match(text, pos)
        if not s or not PERSON.match(text, s.end()):
            break
        pos = s.end()
    if not authors:
        return None
    base = pos
    while base < len(text) and text[base] in " .,":
        base += 1
    t = TAIL.match(text[base:])
    if not t:
        return None
    rest = text[base:]
    source = _span(t, "source", base, " ,")
    vol = _span(t, "vol", base, ".,") if t.group("vol") else None
    if vol and rest[vol[0] - base : vol[1] - base].isalpha():  # a word, not a volume
        source, vol = (source[0], vol[1]), None
    if source[0] >= source[1] or not (vol or t.group("first")):  # a book has a publisher only
        return None
    return {
        "authors": authors,
        "title": _span(t, "title", base, " .?!"),
        "year": _span(t, "year", base),
        "source": source,
        "volume": vol,
        "fpage": _span(t, "first", base, ".") if t.group("first") else None,
        "lpage": _span(t, "last", base, ".") if t.group("last") else None,
    }
