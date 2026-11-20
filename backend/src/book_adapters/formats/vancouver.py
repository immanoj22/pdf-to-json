"""Numbered Vancouver-style references: ``[n]`` + ``Surname AB, Surname C, et al. Title. Journal
2012; 75(3): 311-35. [http://dx.doi.org/...] [PMID: 123]``.

The parts come only from the printed text (no lookup, no guess, no list of journals or
names). A reference that does not fit the journal pattern is still returned, with a ``flags``
entry saying what a person must look at; the writer turns each flag into a review item.

The rules (taken from the client's rule-based converter and its sample output):

* authors ``Surname AB`` become initials ``A.B.``; ``et al`` is a mark, not a name;
* the title ends at the FIRST full stop (or ``?``/``!``); the rest of that sentence is the source;
* the last page is completed (``311-35`` is 311 to 335);
* an article number (``E239-53``) is an item id (``e239-e253``), other letter pages stay pages;
* the DOI/URL in ``[ ]`` and the PMID are kept as written;
* a line ending in a hyphen keeps the hyphen (no space is added).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

UPPER = "A-ZÀ-ÖØ-Þ"
YEAR = r"(?:19|20)\d\d"
MARKER = re.compile(r"(?m)^[ \t]*\[(\d+)\][ \t]*(?:\n|[ \t]+)")  # "[12]"
DOTTED = re.compile(r"(?m)^[ \t]*(\d{1,4})[.)](?:[ \t]+(?=\S)|[ \t]*$)")  # "12. Author", "12.<tab>Author", "12." alone


@dataclass
class Reference:
    number: int
    full: str  # the printed reference, lines joined
    authors: list[tuple[str | None, str]] = field(default_factory=list)  # (initials, surname)
    et_al: bool = False
    title: str | None = None
    source: str | None = None
    year: str | None = None
    volume: str | None = None
    issue: str | None = None
    issue_last: str | None = None
    first_page: str | None = None
    last_page: str | None = None
    article_number: str | None = None
    url: str | None = None
    pmid: str | None = None
    text: str | None = None  # what is left of a non-journal reference
    publisher: str | None = None
    place: str | None = None
    edition: str | None = None
    kind: str | None = None  # the parser's type (article-journal, book, chapter ...)
    engine: str = "rules"  # which reader made it (rules | anystyle)
    flags: list[str] = field(default_factory=list)  # what a person must look at

    @property
    def uncertain(self) -> bool:
        return bool(self.flags)


# ------------------------------------------------------------------ text -> numbered blocks


def _header_key(line: str) -> str:
    return " ".join(re.sub(r"\d+", "", line).split())


def detect_headers(text: str) -> set[str]:
    """Running page headers/footers: a line (its digits removed) that repeats on many pages.
    Nothing is named: a line is a header because the document repeats it."""
    counts: Counter[str] = Counter()
    for line in text.splitlines():
        key = _header_key(line)
        if sum(c.isalpha() for c in key) >= 6:  # words, not the digits-removed tail of a citation
            counts[key] += 1
    return {k for k, n in counts.items() if n >= 3 and not k.startswith("[")}


@dataclass(frozen=True)
class Block:
    """One numbered reference in the text: its number, the marker's offsets and the offsets of
    the reference text that follows it."""

    number: int
    marker: tuple[int, int]
    body: tuple[int, int]


def numbered_blocks(text: str) -> list[Block]:
    """The numbered list found in ``text``: ``[n]`` markers (the list starts at the last ``[1]``
    that begins a line: a body sentence that happens to start with ``[1]`` earlier in the text is
    not the list), else ``n.`` markers, taken only as a run 1, 2, 3 ... (a line that happens to
    start with a year or a figure is not a marker)."""
    markers = list(MARKER.finditer(text))
    if markers:
        firsts = [i for i, m in enumerate(markers) if m.group(1) == "1"]
        if firsts:
            markers = markers[firsts[-1] :]
    else:
        markers = _run(list(DOTTED.finditer(text)))
    out = []
    for i, m in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        out.append(Block(int(m.group(1)), (m.start(), m.end()), (m.end(), end)))
    return out


def _run(found: list[re.Match]) -> list[re.Match]:
    """The longest run of markers numbered 1, 2, 3 ... in order (later wins a tie)."""
    best: list[re.Match] = []
    for start, first in enumerate(found):
        if first.group(1) != "1":
            continue
        chain, want = [first], 2
        for m in found[start + 1 :]:
            if int(m.group(1)) == want:
                chain.append(m)
                want += 1
        if len(chain) >= len(best):
            best = chain
    return best


def split_numbered(text: str) -> list[tuple[int, str]]:
    """``[(number, block text)]`` of the numbered list."""
    return [(b.number, text[b.body[0] : b.body[1]]) for b in numbered_blocks(text)]


def line_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Offsets of each line of ``text[start:end]``."""
    spans, pos = [], start
    for raw in text[start:end].split("\n"):
        spans.append((pos, pos + len(raw)))
        pos += len(raw) + 1
    return spans


def line_kind(line: str, headers: set[str] | frozenset[str]) -> str | None:
    """Why a line is not reference text (``blank``, ``page number``, ``running header``), or
    None when it is."""
    s = line.strip()
    if not s:
        return "blank"
    if re.fullmatch(r"\d{1,4}", s):
        return "page number"
    if re.fullmatch(r"(?:\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}:\d{2}(?::\d{2})?|\s)+", s):
        return "print stamp"  # "10-11-2025 15:29:28" printed on a page
    if _header_key(s) in headers:
        return "running header"
    return None


def join_lines(lines: list[str]) -> str:
    """Lines as one text: a hyphen at a line end keeps the hyphen and adds no space."""
    t = ""
    for s in lines:
        if not t:
            t = s
        elif t.endswith("-") and s[:1].isalnum():
            t += s
        else:
            t += " " + s
    return t


def tidy(t: str) -> str:
    """Printing artifacts around brackets and full stops removed."""
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"\s+\)", ")", t)
    t = re.sub(r"\s+([.,;])(?=\s|$)", r"\1", t)
    return re.sub(r"(?<!\.)\.\.(?!\.)", ".", t)


def clean_block(block: str, headers: set[str] | frozenset[str] = frozenset()) -> str:
    """One reference as a single line: page headers and lone page numbers dropped, the lines
    joined (:func:`join_lines`), printing artifacts removed (:func:`tidy`)."""
    kept = [raw.strip() for raw in block.splitlines() if line_kind(raw, headers) is None]
    return tidy(join_lines(kept))


# ------------------------------------------------------------------ parsing


def complete_last_page(first: str, last: str | None) -> str | None:
    """``311`` + ``35`` is 335: a last page shorter than the first gives its leading digits."""
    if not last:
        return None
    if len(last) < len(first) and first[: len(first) - len(last)].isdigit():
        return first[: len(first) - len(last)] + last
    return last


def parse_authors(text: str) -> tuple[list[tuple[str | None, str]], bool]:
    et = False
    out: list[tuple[str | None, str]] = []
    for item in (x.strip() for x in text.strip().rstrip(".").split(",")):
        if not item:
            continue
        if re.fullmatch(r"et al\.?", item, re.I):
            et = True
            continue
        if re.fullmatch(r"(Eds?|ed\.?|eds\.?)", item):
            continue
        item = re.sub(r"\s+(?:Jr|Sr|II|III|IV)\.?$", "", item)  # a name suffix is not part of the initials
        m = re.match(rf"^(.*?)\s+([{UPPER}]{{1,6}}(?:-[A-Z]{{1,3}})?)$", item)
        if m:
            out.append((".".join(m.group(2).replace("-", "")) + ".", m.group(1)))
        else:
            out.append((None, item))
    return out, et


def parse(number: int, text: str) -> Reference:
    ref = Reference(number=number, full=text)
    urls = re.findall(r"\[(https?://[^\]\s]+)\]", text)
    pm = re.search(r"\[PMID:\s*(\d+)\]", text)
    ref.url = urls[0] if urls else None
    ref.pmid = pm.group(1) if pm else None
    core = re.sub(r"\s*\[(?:https?://[^\]]+|PMID:[^\]]+)\]", "", text).strip()
    core = re.sub(r"(?<=\d)- (?=\d)", "-", core)  # "833- 9" -> "833-9" (parsing only)
    if not ref.url:  # a bare address inside the text
        bare = re.search(r"(https?://[^\s)(]+)", core)
        if bare:
            ref.url = bare.group(1)
            core = re.sub(r":?\s*" + re.escape(bare.group(1)), " ", core).strip()

    authors_text, rest = "", core
    m = re.match(r"^(.*?(?:,\s*et al)?)\.\s+(.*)$", core)
    if (
        m
        and re.search(rf"(?:^|,\s*)[^,]+\s[{UPPER}]{{1,6}}(?:-[A-Z]{{1,3}})?(?:,|$)", m.group(1) + ",")
        and not re.search(r"(?<![-\w])[a-z]{4,}\b", re.sub(r"et al", "", m.group(1)))
    ):
        authors_text, rest = m.group(1), m.group(2)
    if authors_text:
        ref.authors, ref.et_al = parse_authors(authors_text)
    else:
        ref.flags.append("no authors detected")

    journal = re.search(
        rf"^(?P<head>.*?)(?:\s+|(?<=\.))(?P<year>{YEAR})\s*;\s*(?P<vol>[^():;]+?)\s*"
        r"(?:\((?P<iss>[^)]+)\))?\s*(?::\s*(?P<pages>[A-Za-z]?\d[\w\-]*))?\.?\s*$",
        rest,
    )
    if journal and not re.match(r"^(pp?\.)", journal.group("vol").strip()):
        return _journal(ref, journal)
    return _other(ref, rest)


def _journal(ref: Reference, m: re.Match) -> Reference:
    head = m.group("head")
    ref.year = m.group("year")
    ref.volume = m.group("vol").strip()
    if re.fullmatch(r"\d+\s*-\s*\d+", ref.volume) and not m.group("iss") and not m.group("pages"):
        first, last = re.split(r"\s*-\s*", ref.volume)
        ref.volume = None
        ref.first_page, ref.last_page = first, complete_last_page(first, last)
        ref.title = head
        ref.flags.append("no journal/volume given (book chapter?) - please check")
        return ref
    issue = m.group("iss")
    if issue and "-" in issue:
        ref.issue, ref.issue_last = issue.split("-", 1)
    else:
        ref.issue = issue
    pages = m.group("pages")
    if pages:
        pm = re.match(r"^([A-Za-z])(\d+)(?:-(\d+))?$", pages)
        if pm and pm.group(1) in "Ee":  # an article number such as E239-53
            first = pm.group(1).lower() + pm.group(2)
            last = pm.group(3)
            ref.article_number = first + (
                "-" + pm.group(1).lower() + complete_last_page(pm.group(2), last) if last else ""
            )
        elif pm:  # C185-92 -> C185 / C192
            ref.first_page = pm.group(1) + pm.group(2)
            if pm.group(3):
                ref.last_page = pm.group(1) + complete_last_page(pm.group(2), pm.group(3))
        else:
            pp = pages.split("-")
            ref.first_page = pp[0]
            if len(pp) > 1 and pp[1]:
                ref.last_page = complete_last_page(pp[0], pp[1])
    else:
        ref.flags.append("no page numbers found")
    question = re.match(r"^(.*?[?!])\s+(.*)$", head)
    stop = re.match(r"^(.*?)\.\s+(.*)$", head)
    if question and (not stop or len(question.group(1)) < len(stop.group(1))):
        ref.title, ref.source = question.group(1), question.group(2)
    elif stop:
        ref.title, ref.source = stop.group(1), stop.group(2)
    else:
        ref.source = head
        ref.flags.append("title/journal could not be separated (missing full stop in the PDF?)")
    if ref.source:
        ref.source = ref.source.rstrip(".")  # "Lancet. 1999;353": the full stop only separates
    if ref.source and len(ref.source) > 90 and ref.title:
        ref.flags.append("title was cut at an inner full stop - check title / sourcetitle")
    return ref


def _other(ref: Reference, rest: str) -> Reference:
    """A book, web page, magazine or anything not in the journal pattern: best effort."""
    ref.flags.append("non-journal reference (book/web/other) - please check")
    year = re.search(rf"\b({YEAR})\b", rest)
    ref.year = year.group(1) if year else None
    pages = re.search(r"\bpp?\.\s*(\d+)(?:\s*-\s*(\d+))?", rest)
    if pages:
        ref.first_page = pages.group(1)
        if pages.group(2):
            ref.last_page = complete_last_page(pages.group(1), pages.group(2))
    work = re.sub(r"[;,]?\s*\bpp?\.\s*\d+(?:\s*-\s*\d+)?", "", rest)
    sm = re.match(r"^(.*?)\.\s+(.*)$", work)
    if sm:
        source, tail = sm.group(1), sm.group(2)
        tail = re.sub(rf"[;,]?\s*\b{YEAR}\b\s*;?\s*", " ", tail, count=1).strip(" ;,")
        tail = re.sub(r"\.\s+\.$", ".", tail)
        tail = re.sub(r"\s+\.$", "", tail)
        tail = re.sub(r"\s+\)", ")", tail)
        if pages:
            tail = tail.rstrip(" .")
        ref.source = source
        ref.text = re.sub(r"\s+", " ", tail) or None
    else:
        ref.source = re.sub(rf"\s*\b{YEAR}\b\s*\.?\s*$", "", work).strip().rstrip(".")
    return ref


def parse_list(text: str) -> list[Reference]:
    """Every reference of the numbered list found in ``text`` (running headers removed)."""
    headers = detect_headers(text)
    return [parse(n, clean_block(block, headers)) for n, block in split_numbered(text)]
