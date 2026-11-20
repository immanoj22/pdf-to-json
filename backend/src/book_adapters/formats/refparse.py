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
    """The Authors. Title. (Year) pattern, else the AOSIS pattern (:func:`parse_aosis`)."""
    return _parse_journal_pattern(text) or parse_aosis(text)


def _parse_journal_pattern(text: str) -> dict | None:
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


# ------------------------------------------------------------------ "Surname, I.I. & Surname, I.I., 2025, ‘Title’, Source 16(6), 977–1110. URL"

YEAR_AT = regex.compile(r",\s*(?P<year>\d{4}[a-z]?)(?P<sep>[.,])\s+(?=\S)")
QUOTED = regex.compile(r"^[‘'](?P<title>.+?)[’'][,.]\s+(?P<rest>.+)$", regex.S)
GIVEN_FIRST = regex.compile(r"^(?P<given>(?:\p{Lu}[\p{L}]?\.[\s \-]?)+)\s*(?P<sur>\p{L}[^,&]*?)$")
EDITORS = regex.compile(r"^(?P<eds>.+?)\s*\((?:eds?|ed)\.?\),\s+(?P<rest>.+)$", regex.S)
PAGES = regex.compile(r",?\s*pp?\.\s*(?P<first>[\p{L}\d.]+)(?:\s*[‐-―\-]\s*(?P<last>[\p{L}\d.]+))?")
VOLUME = regex.compile(
    r"^(?P<source>.+?)\s+(?P<vol>\d+)(?:\((?P<issue>[^)]+)\))?,\s+"
    r"(?P<first>[\p{L}\d.]+)(?:\s*[‐-―\-]\s*(?P<last>[\p{L}\d.]+))?(?P<after>.*)$", regex.S
)
VIEWED = regex.compile(r",?\s*viewed\s+\d.*$", regex.S)
LINK = regex.compile(r"(?:^|[\s,.])(?:from\s+)?(?P<url>https?://\s*\S.*?)\.?$", regex.S)
DOI = regex.compile(r"^https?://(?:dx\.)?doi\.org/(?P<doi>10\.\S+)$")


def _sub(match, name, base):
    start, end = match.span(name)
    return (base + start, base + end)


def _strip(text, span, chars=" .,"):
    start, end = span
    while start < end and text[start] in chars:
        start += 1
    while end > start and text[end - 1] in chars:
        end -= 1
    return (start, end)


def _persons(text: str, start: int, end: int):
    """(persons, etal, collab) of the author text[start:end] in "Surname, I.I. & Surname, I.I."
    form; an organisation (no initials anywhere) is a collab; anything else is None."""
    chunk = text[start:end]
    et_al = False
    m = regex.search(r",?\s+et al\.?$", chunk)
    if m:
        et_al, end = True, start + m.start()
        chunk = text[start:end]
    persons, pos = [], start
    while pos < end:
        m = PERSON.match(text, pos, endpos=end)
        if not m:
            persons = None
            break
        sur, given = m.span("sur"), m.span("given")
        given = (given[0], given[0] + len(m.group("given").rstrip()))
        persons.append(((sur[0], sur[0] + len(m.group("sur").rstrip())), given))
        pos = given[1]
        if pos >= end:
            break
        s = SEP.match(text, pos, endpos=end)
        if not s:
            persons = None
            break
        pos = s.end()
    if persons and pos >= end - 0:
        return persons, et_al, None
    if not regex.search(r"\b\p{Lu}\.", chunk) and chunk.strip():
        return None, False, _strip(text, (start, end), " ,")
    return None


def _editors(text: str, start: int, end: int):
    """Names written "R.K. Kushwaha, P.K. Yadav & A. Devi": [(surname span, given span)], or None."""
    out = []
    pos = start
    for piece in regex.finditer(r"[^,&]+|(?:\s+and\s+)", text[start:end]):
        raw = piece.group()
        if not raw.strip() or raw.strip() == "and":
            continue
        a = start + piece.start()
        m = GIVEN_FIRST.match(text[a : start + piece.end()].strip())
        if not m:
            return None
        lead = len(text[a : start + piece.end()]) - len(text[a : start + piece.end()].lstrip())
        base = a + lead
        out.append(((base + m.start("sur"), base + m.end("sur")), (base + m.start("given"), base + m.start("given") + len(m.group("given").rstrip()))))
    return out or None


def _end_link(text, start, end):
    """(content end, doi span or None, uri span or None) of a tail that may end in a link."""
    m = LINK.search(text, start, end)
    if not m:
        return end, None, None
    u = m.span("url")
    url = text[u[0] : u[1]].replace(" ", "").rstrip(".")
    d = DOI.match(url)
    uri = (u[0], u[1])
    doi = None
    if d:
        doi, uri = (u[0], u[1]), None
    return m.start("url") if text[m.start("url") - 1 : m.start("url")] != "" else m.start("url"), doi, uri


def parse_aosis(text: str) -> dict | None:
    """The AOSIS pattern, in the same position form as :func:`parse_reference`, plus
    ``pub_type``, ``sequence`` (tag, span) in printed order, ``editors``, ``etal``, ``collab``.
    Anything that does not fit returns None (the reference stays a mixed-citation)."""
    ym = YEAR_AT.search(text)
    if not ym:
        return None
    found = _persons(text, 0, ym.start())
    if not found:
        return None
    persons, etal, collab = found
    year = _sub(ym, "year", 0)
    pos = ym.end()
    q = QUOTED.match(text[pos:])
    sequence = [("year", year)]
    editors = None
    if q:
        title = _sub(q, "title", pos)
        rest0 = pos + q.start("rest")
        rest = text[rest0:]
        chap = regex.match(r"in\s+(?P<body>.+)$", rest, regex.S)
        if chap:
            pub_type = "book"
            body0 = rest0 + chap.start("body")
            body = text[body0:]
            em = EDITORS.match(body)
            if em:
                editors = _editors(text, body0, body0 + em.end("eds"))
                body0 += em.start("rest")
                body = text[body0:]
            # the source runs to the volume or pages, else to the viewed date or the link
            stop = len(body)
            for pat in (regex.compile(r",\s*vol\.\s*\d+"), PAGES, VIEWED, regex.compile(r"[.,]?\s*https?://")):
                m = pat.search(body)
                if m and m.start() < stop:
                    stop = m.start()
            source = _strip(text, (body0, body0 + stop))
            if source[0] >= source[1]:
                return None
            pg = PAGES.search(body)
            publisher = city = None
            fpage = lpage = None
            if pg:
                fpage, lpage = _sub(pg, "first", body0), (_sub(pg, "last", body0) if pg.group("last") else None)
                tail_start = body0 + pg.end()
                tail = text[tail_start:]
                tail = VIEWED.sub("", tail)
                tail = regex.sub(r"[.,]?\s*(?:from\s+)?https?://.*$", "", tail, flags=regex.S)
                parts = [(m.start(), m.end()) for m in regex.finditer(r"[^,]+", tail) if m.group().strip(" .")]
                if len(parts) == 2:
                    publisher = _strip(text, (tail_start + parts[0][0], tail_start + parts[0][1]))
                    city = _strip(text, (tail_start + parts[1][0], tail_start + parts[1][1]))
                elif len(parts) == 1:
                    publisher = _strip(text, (tail_start + parts[0][0], tail_start + parts[0][1]))
                    city = None
            conf = regex.search(r"conference|symposium|proceedings|congress|workshop", text[source[0] : source[1]], regex.I)
            if conf:
                pub_type = "confproc"
            sequence += [("chapter-title" if not conf else "article-title", title),
                         ("conf-name" if conf else "source", source)]
            for tag, span in (("fpage", fpage), ("lpage", lpage), ("publisher-name", publisher), ("publisher-loc", city)):
                if span:
                    sequence.append((tag, span))
            vol = regex.search(r",\s*vol\.\s*(?P<v>\d+)", body[: stop + 12])
            if vol:
                sequence.append(("volume", _sub(vol, "v", body0)))
        else:
            pub_type = "journal"
            m = VOLUME.match(rest)
            if not m:
                return None
            source = _sub(m, "source", rest0)
            sequence += [("article-title", title), ("source", source), ("volume", _sub(m, "vol", rest0))]
            if m.group("issue"):
                sequence.append(("issue", _sub(m, "issue", rest0)))
            sequence.append(("fpage", _sub(m, "first", rest0)))
            if m.group("last"):
                sequence.append(("lpage", _sub(m, "last", rest0)))
            after = rest0 + m.start("after")
            tail = text[after:]
            tail = VIEWED.sub("", tail)
            lm = regex.search(r"(?:from\s+)?(?P<url>https?://\s*\S.*?)\.?$", tail, regex.S)
            if lm is None and tail.strip(" .,"):
                return None  # something follows the pages that is not a viewed date or a link
    else:
        # an untitled-in-quotes source: report, policy or web page: "Title, Publisher, City, viewed ..."
        pub_type = "report"
        body0, body = pos, text[pos:]
        stop = len(body)
        for pat in (VIEWED, regex.compile(r"[.,]?\s*(?:from\s+)?https?://")):
            m = pat.search(body)
            if m and m.start() < stop:
                stop = m.start()
        segs = [(m.start(), m.end()) for m in regex.finditer(r"[^,]+(?:,(?=\S)[^,]+)*", body[:stop])]
        pieces = [(m.start(), m.end()) for m in regex.finditer(r"[^,]+", body[:stop]) if m.group().strip(" .")]
        if not pieces:
            return None
        if len(pieces) >= 3:
            publisher = pieces[-2]
            city = pieces[-1]
            title_end = publisher[0] - 1
            title = _strip(text, (body0, body0 + title_end))
            sequence += [("source", title), ("publisher-name", _strip(text, (body0 + publisher[0], body0 + publisher[1]))),
                         ("publisher-loc", _strip(text, (body0 + city[0], body0 + city[1])))]
        else:
            sequence += [("source", _strip(text, (body0, body0 + stop)))]
        if sequence[-1][1][0] >= sequence[-1][1][1]:
            return None
    link = regex.search(r"(?:^|[\s,.])(?:from\s+)?(?P<url>https?://\s*\S.*?)\.?$", text, regex.S)
    if link:
        u = link.span("url")
        url = "".join(text[u[0] : u[1]].split()).rstrip(".")
        d = DOI.match(url)
        sequence.append(("doi" if d else "uri", u))
    sequence = [(tag, _strip(text, span, " .,;")) for tag, span in sequence]
    sequence = [(tag, span) for tag, span in sequence if span[0] < span[1]]
    return {
        "authors": persons or [], "collab": collab, "etal": etal, "editors": editors,
        "pub_type": pub_type, "sequence": sequence, "year": year,
        "title": None, "source": None, "volume": None, "fpage": None, "lpage": None,
    }
