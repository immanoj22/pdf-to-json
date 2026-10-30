"""Outline builder: book.json -> adapter document tree (front matter, parts, chapters,
sections, blocks, back matter).

Part and chapter starts come from, in order of trust: Stage 1 headings with a part/chapter
role; printed label words in opener artwork (profile ``outline.*_label_words``); printed
table-of-contents targets (``outline.use_toc_targets``). Nothing depends on fonts or
coordinates. Every decision that is not certain becomes a review entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .load import LoadedBook
from .model import (
    BibEntry,
    Bibliography,
    BookInfo,
    Division,
    Document,
    Equation,
    Figure,
    IndexDiv,
    IndexEntry,
    Item,
    ListBlock,
    Omission,
    PageMark,
    Para,
    ReviewEntry,
    Section,
    Sidebar,
    Table,
)
from .text import TextRef, render, strip_ranges

FLOATS = frozenset({"figure", "table", "box", "equation", "caption", "footnote"})
ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def roman_value(label: str | None) -> int | None:
    if not label or not re.fullmatch(r"(?i)[ivxlcdm]+", label):
        return None
    total, prev = 0, 0
    for ch in reversed(label.lower()):
        value = ROMAN[ch]
        total = total - value if value < prev else total + value
        prev = max(prev, value)
    return total


def _alone_on_line(text: str, span: tuple[int, int]) -> bool:
    """The label word is the whole line, apart from white space and a number."""
    start = text.rfind("\n", 0, span[0]) + 1
    end = text.find("\n", span[1])
    end = len(text) if end < 0 else end
    rest = text[start : span[0]] + text[span[1] : end]
    return re.fullmatch(r"[\s\d]*|\s*[IVXLC]+\s*", rest) is not None


def find_label_word(text: str, word: str) -> tuple[int, int] | None:
    """Offsets of a printed label word, written whole ("CHAPTER") or with spaced letters
    ("C H A P T E R", "SEC TION"); case-insensitive, on word boundaries."""
    runs = [(m.start(), m.end(), m.group().upper()) for m in re.finditer(r"[^\W\d_]+", text)]
    for i in range(len(runs)):
        joined, end = "", runs[i][0]
        for j in range(i, len(runs)):
            if j > i and text[runs[j - 1][1] : runs[j][0]] not in (" ", "\t", "  "):
                break
            joined += runs[j][2]
            end = runs[j][1]
            if len(joined) >= len(word):
                break
        if joined == word.upper():
            return runs[i][0], end
    return None


@dataclass
class Start:
    index: int  # position in the body unit stream
    kind: str  # part | chapter
    evidence: str  # heading | opener | toc
    page: int
    title: list[TextRef]
    label_ref: TextRef | None = None
    number_ref: TextRef | None = None
    heading_id: str | None = None
    consumed: tuple[str, ...] = ()  # opener artwork unit ids


class OutlineBuilder:
    def __init__(self, book: LoadedBook, profile, settings, rules_on: set[str]):
        self.book = book
        self.profile = profile
        self.settings = settings
        self.rules_on = rules_on
        self.data = book.data
        self.pages = book.pages
        self.reviews: list[ReviewEntry] = []
        self.omissions: list[Omission] = []
        self.consumed: set[str] = set()
        sections = (self.data.get("navigation") or {}).get("sections") or []
        self.section_by_id = {s["id"]: s for s in sections}
        self.marks: dict[int, PageMark] = {}
        self._anchor_ids()
        self.bib_patterns = [re.compile(p) for p in profile.get("bibliography.title_patterns")]
        self.qanda_patterns = [re.compile(p) for p in profile.get("qanda.set_title_patterns")]

    # ------------------------------------------------------------------ helpers

    def ref(self, addr: str, move: str | None = None) -> TextRef:
        return TextRef(addr, self.book.records[addr], self.book.order[addr], move=move)

    def review(self, kind: str, message: str, unit: dict | None = None, rule: str | None = None):
        page = unit["pages"][0] if unit and unit.get("pages") else None
        self.reviews.append(
            ReviewEntry(kind, message, unit.get("id") if unit else None, page, rule)
        )

    def omit_unit(self, unit: dict, reason: str):
        """Every text record of a unit is listed as omitted (by profile)."""
        for addr in self._addrs(unit):
            content = self.book.records[addr]
            self.omissions.append(Omission(addr, [(0, len(content["text"]))], reason, content))

    def _addrs(self, unit: dict) -> list[str]:
        """Addresses of every text record of a unit and its descendants."""
        return list(self._unit_addrs.get(unit.get("id"), ()))

    def _build_unit_addrs(self):
        self._unit_addrs: dict[str, list[str]] = {}

        def walk(unit, owners):
            uid = unit.get("id")
            chain = owners + ([uid] if uid else [])
            for key in ("items", "children"):
                for child in unit.get(key) or ():
                    walk(child, chain)
            for cell in unit.get("cells") or ():
                for item in cell.get("content") or ():
                    if item.get("type") != "text":
                        walk(item, chain)
            own = [a for a in self._addr_by_uid.get(uid, ())]
            for owner in chain:
                self._unit_addrs.setdefault(owner, []).extend(own)

        self._addr_by_uid: dict[str, list[str]] = {}
        for addr in self.book.records:
            uid = re.split(r"[/#]", addr, maxsplit=1)[0]
            self._addr_by_uid.setdefault(uid, []).append(addr)
        for unit in self.data.get("content") or ():
            walk(unit, [])
        for addrs in self._unit_addrs.values():
            addrs.sort(key=lambda a: self.book.order[a])

    def _anchor_ids(self):
        body_pattern = self.profile.get("anchors.id")
        unlabelled = self.profile.get("anchors.unlabelled_id")
        front_pattern = self.profile.get("front_matter.page_anchor_front")
        used: set[str] = set()
        for page in self.pages:
            label, idx = page.get("label"), page["index"]
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", label) if label else None
            if page.get("zone") == "front":
                number = roman_value(label) or (int(label) if label and label.isdigit() else idx)
                anchor = front_pattern.format(number=number, page=idx, label=safe or idx)
            elif safe:
                anchor = body_pattern.format(label=safe, page=idx)
            else:
                anchor = unlabelled.format(page=idx)
            if anchor in used:
                anchor = f"{anchor}_p{idx}"
            used.add(anchor)
            self.marks[idx] = PageMark(idx, label, page.get("zone"), anchor)

    def section_kind(self, page: int) -> tuple[str, str]:
        entry = self.pages[page - 1]
        section = self.section_by_id.get(entry.get("section"))
        return (section["kind"] if section else "chapter"), (entry.get("zone") or "body")

    # ------------------------------------------------------------------ top level

    def build(self) -> Document:
        self._build_unit_addrs()
        units = self.data.get("content") or []
        groups: list[tuple[str, str, list[dict]]] = []  # (kind, zone, units)
        for unit in units:
            kind, zone = self.section_kind(unit["pages"][0])
            sid = self.pages[unit["pages"][0] - 1].get("section")
            if groups and groups[-1][3] == sid:
                groups[-1][2].append(unit)
            else:
                groups.append((kind, zone, [unit], sid))
        groups = [(k, z, us) for k, z, us, _ in groups]
        sections_cfg = self.profile.get("front_matter.sections") or {}
        self.toc_units = [u for k, z, us in groups if k == "table_of_contents" for u in us]
        bookinfo = BookInfo()
        front: list[Division] = []
        back: list[Division] = []
        body_units: list[dict] = []
        pending_marks: list[PageMark] = []
        seen_body = False
        for kind, zone, group in groups:
            cfg = sections_cfg.get(kind)
            if zone == "body" or cfg is None or cfg["element"] == "chapter":
                body_units += group
                seen_body = True
                continue
            element = cfg["element"]
            if element == "continue_previous":
                if not back:
                    body_units.extend(group)
                    continue
                element = "appendix"  # back matter came in between: it cannot continue
                cfg = {**cfg, "element": element}
                self.review(
                    "structure",
                    f"{kind} pages after other back matter written as an appendix",
                    group[0],
                )
            marks = [self.marks[u["page"]] for u in group if u["type"] == "page_marker"]
            for m in marks:
                m.keep = cfg.get("page_anchors", "keep") == "keep"
            content = [u for u in group if u["type"] != "page_marker"]
            if element == "omit" or (not content and element != "bookinfo"):
                for u in content:
                    self.omit_unit(u, f"profile omits {kind}")
                kept = [m for m in marks if m.keep]
                previous = (back or front) if seen_body else front
                if previous and not pending_marks:
                    _append_marks(previous[-1], kept)  # anchors end the previous division
                else:
                    pending_marks += kept
                continue
            if element == "bookinfo":
                bookinfo.page_marks += pending_marks + marks
                pending_marks = []
                self._bookinfo(bookinfo, content, kind)
                continue
            if element == "legalnotice":
                blocks = pending_marks + self.blocks(group, context="legal")
                pending_marks = []
                from ..rules.structure import _declare_move

                _declare_move(blocks, "copyright page placed in bookinfo (DocBook)")
                if not bookinfo.legal or all(isinstance(b, Figure) for b in bookinfo.legal):
                    bookinfo.legal.extend(blocks)
                else:
                    bookinfo.legal_after.extend(blocks)
                continue
            target = back if zone == "rear" or seen_body else front
            for division in self.front_divisions(element, group, cfg, kind):
                if pending_marks:
                    division.title_page_mark = pending_marks + division.title_page_mark
                    pending_marks = []
                target.append(division)
        body = self.body_divisions(body_units)
        if pending_marks and body:
            body[0].title_page_mark = pending_marks + body[0].title_page_mark
        for table in _tables([bookinfo.legal, bookinfo.legal_after, front, body, back]):
            self.table_cells(table)
        doc = Document(
            bookinfo,
            front,
            body,
            back,
            self.omissions,
            self.reviews,
            dict(self.book.order),
            dict(self.book.records),
            self.pages,
            set(self.book.markers),
        )
        self._first_last(doc)
        return doc

    # ------------------------------------------------------------------ front matter

    def _bookinfo(self, info: BookInfo, units: list[dict], kind: str):
        title_unit = next(
            (u for u in units if u["type"] == "heading" and u.get("role") == "book_title"), None
        )
        if not self.settings.data.get("title") and title_unit is not None:
            info.title_ref = strip_ranges(self.ref(title_unit["id"]))
        for u in units:
            if (
                u["type"] == "figure"
                and not u.get("text")
                and not u.get("captions")
                and self.profile.get("front_matter.title_page_artwork") == "legalnotice"
            ):
                fig = self.figure(u)
                if fig is not None:
                    info.legal.insert(0, fig)  # publisher logo: first in the legal notice
                continue
            self.omit_unit(u, "title page represented by book settings (bookinfo)")

    def front_divisions(
        self, element: str, group: list[dict], cfg: dict, kind: str
    ) -> list[Division]:
        """Split a front/back section into divisions at each top-level title."""
        if element == "index":
            return [self.index_division(group)]
        # Banner text is a title fallback only when Stage 1 gives this section no title
        # heading, and only for artwork that opens a page.
        has_titles = any(
            u["type"] == "heading" and u.get("level") == 1 and u.get("role") != "sidebar_title"
            for u in group
        )
        page_openers = set()
        last_marker = True
        for u in group:
            if u["type"] == "page_marker":
                last_marker = True
                continue
            if last_marker and u["type"] == "figure" and not has_titles:
                page_openers.add(u["id"])
            last_marker = False
        self._front_openers = page_openers
        chunks: list[list[dict]] = [[]]
        for unit in group:
            starts_title = (
                unit["type"] == "heading"
                and unit.get("level") == 1
                and unit.get("role") not in ("sidebar_title",)
            )
            opener = self._opener_title(unit) if unit.get("id") in page_openers else None
            has_content = any(u["type"] not in ("page_marker",) for u in chunks[-1])
            if cfg.get("split_on_titles", True) and (starts_title or opener) and has_content:
                chunks.append([])
            chunks[-1].append(unit)
        out = []
        for chunk in chunks:
            if not chunk:
                continue
            division = Division(kind=element)
            division.first_page = chunk[0]["pages"][0]
            rest = list(chunk)
            lead_marks = []
            while rest and rest[0]["type"] == "page_marker":
                lead_marks.append(self.marks[rest.pop(0)["page"]])
            title_found = False
            for i, unit in enumerate(rest):
                if unit["type"] == "page_marker":
                    continue
                if unit["type"] == "heading" and unit.get("role") != "sidebar_title":
                    division.title = [strip_ranges(self.ref(unit["id"]))]
                    rest.pop(i)
                    title_found = True
                elif unit["type"] == "figure" and unit["id"] in self._front_openers:
                    opener = self._opener_title(unit)
                    if opener:
                        division.title = opener
                        division.title_evidence = "opener"
                        self.consumed.add(unit["id"])
                        self.reviews.append(
                            ReviewEntry(
                                "adapter-inferred",
                                f"{element} title taken by the adapter from text "
                                "inside banner artwork; book.json has no heading here",
                                unit["id"],
                                unit["pages"][0],
                                "outline.opener_title",
                            )
                        )
                        rest.pop(i)
                        title_found = True
                break
            if not title_found:
                division.title_text = cfg.get("default_title")
                if division.title_text is None:
                    self.review("structure", f"{element} without a printed title", chunk[0])
            division.title_page_mark = lead_marks
            division.children = self.nodes(rest, top_level=True)
            out.append(division)
        return out

    def _opener_title(self, figure: dict) -> list[TextRef] | None:
        """Banner artwork whose only text is a title (no caption): its text is the title."""
        if not self.profile.get("outline.use_opener_text") or figure.get("captions"):
            return None
        texts = figure.get("text") or []
        if not texts or len(texts) > 3:
            return None
        refs = [strip_ranges(self.ref(f"{figure['id']}/text/{i}")) for i in range(len(texts))]
        plain = " ".join(r.plain() for r in refs).strip()
        if not plain or len(plain) > 120 or plain.endswith((".", ",", ";")):
            return None
        return [r for r in refs if not r.is_blank()]

    # ------------------------------------------------------------------ body

    def body_divisions(self, units: list[dict]) -> list[Division]:
        starts = self._starts(units)
        divisions: list[Division] = []
        current_part: Division | None = None
        bounds = [s.index for s in starts] + [len(units)]
        lead = units[: bounds[0]] if starts else units
        if any(u["type"] != "page_marker" for u in lead):
            kind = self.profile.get("outline.body_before_first_chapter")
            division = Division(kind="chapter" if kind == "chapter" else "preface")
            division.first_page = lead[0]["pages"][0]
            if division.kind == "chapter":
                division.number = 1
            division.children = self.nodes(lead, top_level=True)
            self.review("structure", "body text before the first chapter start", lead[0])
            divisions.append(division)
        elif lead:
            marks = [self.marks[u["page"]] for u in lead if u["type"] == "page_marker"]
            self._carry_marks = marks
        chapter_no = sum(1 for d in divisions if d.kind == "chapter")
        part_no = 0
        for start, end in zip(starts, bounds[1:], strict=True):
            segment = units[start.index : end]
            division = Division(
                kind=start.kind,
                title=start.title,
                label_ref=start.label_ref,
                number_ref=start.number_ref,
                first_page=start.page,
                evidence=start.evidence,
            )
            if start.evidence != "heading":
                source = {
                    "opener": "label word in opener artwork",
                    "toc": "printed table of contents target",
                }[start.evidence]
                self.reviews.append(
                    ReviewEntry(
                        "adapter-inferred",
                        f"{start.kind} start on page {start.page} inferred by "
                        f"the adapter from the {source}; book.json has no {start.kind} heading",
                        start.consumed[0] if start.consumed else None,
                        start.page,
                        f"outline.{start.evidence}",
                    )
                )
            for uid in start.consumed:
                self.consumed.add(uid)
            body = list(segment)
            marks = getattr(self, "_carry_marks", [])
            self._carry_marks = []
            while body and body[0]["type"] == "page_marker":
                marks.append(self.marks[body.pop(0)["page"]])
            if start.heading_id:
                body = [u for u in body if u.get("id") != start.heading_id]
            body = self._drop_opener_artwork(body, start)
            division.title_page_mark = marks
            if start.kind == "part":
                part_no += 1
                division.number = part_no
                division.intro = self.nodes(body, top_level=True)
                divisions.append(division)
                current_part = division
            else:
                chapter_no += 1
                division.number = chapter_no
                division.children = self.nodes(body, top_level=True)
                if not division.title:
                    self._title_from_toc(division)
                (current_part.children if current_part else divisions).append(division)
        return divisions

    def _drop_opener_artwork(self, body: list[dict], start: Start) -> list[dict]:
        if not self.profile.get("outline.drop_opener_artwork"):
            return body
        out = []
        leading = True
        for unit in body:
            if (
                leading
                and unit["type"] == "figure"
                and not unit.get("captions")
                and (not unit.get("text") or unit["id"] in start.consumed)
                and unit["pages"][0] == start.page
            ):
                self.consumed.add(unit["id"])
                for addr in self._addrs(unit):
                    content = self.book.records[addr]
                    self.omissions.append(
                        Omission(
                            addr,
                            [(0, len(content["text"]))],
                            "opener artwork (text used as title)",
                            content,
                        )
                    )
                continue
            if unit["type"] != "page_marker":
                leading = False
            out.append(unit)
        return out

    def _starts(self, units: list[dict]) -> list[Start]:
        part_roles = set(self.profile.get("outline.part_roles"))
        chapter_roles = set(self.profile.get("outline.chapter_roles"))
        page_start: dict[int, int] = {}
        for i, u in enumerate(units):
            if u["type"] == "page_marker":
                page_start.setdefault(u["page"], i)
        found: dict[tuple[int, str], Start] = {}

        def put(start: Start):
            key = (start.page, start.kind)
            if key not in found:
                found[key] = start

        for i, u in enumerate(units):
            if u["type"] == "heading" and u.get("role") in part_roles | chapter_roles:
                kind = "part" if u.get("role") in part_roles else "chapter"
                index = page_start.get(u["pages"][0], i) if self._first_on_page(units, i) else i
                title = strip_ranges(self.ref(u["id"]))
                if index != i:
                    title.move = f"{kind} title placed at the {kind} start"
                put(Start(index, kind, "heading", u["pages"][0], [title], heading_id=u["id"]))
        # Fallbacks for a kind run only when book.json has no heading of that kind: once
        # Stage 1 supplies the headings, they do nothing.
        have = {s.kind for s in found.values()}
        if self.profile.get("outline.use_opener_text"):
            for i, u in enumerate(units):
                if u["type"] != "figure" or u.get("captions") or not u.get("text"):
                    continue
                parsed = self._parse_opener(u)
                if parsed and parsed[0] not in have:
                    kind, title, label_ref, number_ref = parsed
                    page = u["pages"][0]
                    put(
                        Start(
                            page_start.get(page, i),
                            kind,
                            "opener",
                            page,
                            title,
                            label_ref,
                            number_ref,
                            consumed=(u["id"],),
                        )
                    )
        if self.profile.get("outline.use_toc_targets") and "chapter" not in have:
            toc = (self.data.get("navigation") or {}).get("toc") or []
            levels = [t["level"] for t in toc if t.get("level") is not None]
            top = min(levels) if levels else None
            for entry in toc:
                page = entry.get("target_page")
                if page is None or page not in page_start or entry.get("level") not in (top, None):
                    continue
                if any((page, k) in found for k in ("part", "chapter")):
                    continue
                if (entry.get("confidence") or 0) < 0.5:
                    continue
                put(Start(page_start[page], "chapter", "toc", page, []))
        starts = sorted(found.values(), key=lambda s: (s.index, s.kind != "part"))
        merged: list[Start] = []
        for s in starts:  # a part and a chapter on one page: the chapter starts after the part
            if (
                merged
                and merged[-1].index == s.index
                and merged[-1].kind == "part"
                and s.kind == "chapter"
            ):
                nxt = s.index + 1
                while nxt < len(units) and units[nxt]["type"] == "page_marker":
                    nxt += 1
                s.index = nxt
            merged.append(s)
        return merged

    def _first_on_page(self, units, i) -> bool:
        j = i - 1
        while j >= 0 and units[j]["type"] != "page_marker":
            if units[j]["type"] not in FLOATS:
                return False
            j -= 1
        return True

    def _parse_opener(self, figure: dict):
        """Opener artwork text with a part/chapter label word: (kind, title, label, number)."""
        words = {
            "part": [w.upper() for w in self.profile.get("outline.part_label_words")],
            "chapter": [w.upper() for w in self.profile.get("outline.chapter_label_words")],
        }
        refs = [self.ref(f"{figure['id']}/text/{i}") for i in range(len(figure["text"]))]
        if sum(len(r.plain()) for r in refs) > 200:
            return None  # opener artwork carries a label and a title, not running text
        for kind in ("part", "chapter"):
            for ref in refs:
                span = None
                for word in words[kind]:
                    span = find_label_word(ref.text, word)
                    if span and not _alone_on_line(ref.text, span):
                        span = None
                    if span:
                        break
                if not span:
                    continue
                label = ref.slice(*span)
                number = None
                title: list[TextRef] = []
                for other in refs:
                    for piece in _minus(other, label.ranges if other is ref else []):
                        plain = piece.plain()
                        if number is None and re.fullmatch(r"\s*(\d+|[IVXLC]+)\s*", plain):
                            number = strip_ranges(piece)
                            continue
                        lead = re.match(r"\s*(\d+)\s", plain)
                        if number is None and lead:
                            chars = render(piece.content, piece.ranges)
                            cut = chars[lead.end(1) - 1][1] + 1
                            number = strip_ranges(piece.slice(piece.ranges[0][0], cut))
                            piece = piece.slice(cut, piece.ranges[-1][1])
                        if not piece.is_blank():
                            title.append(strip_ranges(piece))
                if title:
                    return kind, title, label, number
        return None

    def _title_from_toc(self, division: Division):
        entries = self._toc_entries()
        match = entries.get(division.number)
        if match:
            division.title = [
                r.slice(r.ranges[0][0], r.ranges[-1][1], move="title from TOC") for r in match
            ]
            division.title_evidence = "toc"
            self.reviews.append(
                ReviewEntry(
                    "adapter-inferred",
                    f"chapter {division.number} title taken by the adapter from "
                    "the printed table of contents (no title text on the opener page)",
                    match[0].addr.split("/")[0],
                    division.first_page,
                    "outline.toc_title",
                )
            )
        else:
            self.review("structure", f"chapter {division.number} has no title (to supply)", None)

    def _toc_entries(self) -> dict[int, list[TextRef]]:
        if hasattr(self, "_toc_cache"):
            return self._toc_cache
        pattern = re.compile(self.profile.get("outline.toc_entry_number"), re.S)
        tail = re.compile(r"(?P<title>.+?)[\s.…]*(?P<page>\d+)?\s*$", re.S)
        out: dict[int, list[TextRef]] = {}
        last: int | None = None
        for unit in self.toc_units:
            for item in _walk(unit):
                if item.get("type") != "contents_entry":
                    continue
                ref = self.ref(item["id"])
                m = pattern.match(ref.text)
                if m and m.group("num"):
                    last = int(m.group("num"))
                    out[last] = [strip_ranges(ref.slice(m.start("title"), m.end("title")))]
                    continue
                words = "|".join(self.profile.get("outline.part_label_words"))
                if re.match(rf"(?i)\s*({words})\b", ref.text):
                    last = None
                    continue
                m2 = tail.match(ref.text)
                if last is not None and m2 and not out[last][-1].text.rstrip().endswith("."):
                    out[last].append(strip_ranges(ref.slice(m2.start("title"), m2.end("title"))))
        self._toc_cache = out
        return out

    # ------------------------------------------------------------------ index

    def index_division(self, group: list[dict]) -> Division:
        division = Division(kind="index", first_page=group[0]["pages"][0])
        marks = []
        rest = list(group)
        while rest and rest[0]["type"] == "page_marker":
            marks.append(self.marks[rest.pop(0)["page"]])
        division.title_page_mark = marks
        divs: list[IndexDiv] = []
        current = IndexDiv(None, None, [])
        pending_marks: list[PageMark] = []
        for unit in rest:
            t = unit["type"]
            if t == "page_marker":
                pending_marks.append(self.marks[unit["page"]])
            elif t == "heading" and not division.title and not divs and not current.entries:
                division.title = [strip_ranges(self.ref(unit["id"]))]
            elif t == "index_divider":
                if current.entries or current.title or current.lead:
                    divs.append(current)
                current = IndexDiv(strip_ranges(self.ref(unit["id"])), None, [])
                current.lead += pending_marks
                pending_marks = []
            elif t == "list" and unit.get("list_type") == "index":
                for item, level in _index_items(unit):
                    entry = self.item(item, with_children=False)
                    if pending_marks:
                        entry.parts = pending_marks + entry.parts
                        pending_marks = []
                    current.entries.append(IndexEntry(level, entry))
            else:
                blocks = self.blocks([unit])
                (current.lead if not current.entries else current.lead).extend(
                    pending_marks + blocks
                )
                pending_marks = []
                if current.entries:
                    self.review("structure", "text between index entries kept before them", unit)
        if current.entries or current.title or current.lead:
            divs.append(current)
        if pending_marks and divs and divs[-1].entries:
            divs[-1].entries[-1].item.parts += pending_marks
        elif pending_marks:
            division.title_page_mark += pending_marks
        division.index_divs = divs
        if not division.title:
            division.title_text = self.profile.get("index.default_title")
        return division

    # ------------------------------------------------------------------ blocks

    def page_mark(self, unit: dict) -> PageMark:
        return self.marks[unit["page"]]

    def nodes(self, units: list[dict], top_level: bool = False) -> list:
        """Blocks with sections opened at headings (nested by heading level)."""
        flat = self.blocks(units, allow_sections=True)
        root: list = []
        stack: list[tuple[int, Section]] = []
        for item in flat:
            if isinstance(item, _HeadingEvent):
                level = item.unit.get("level") or 1
                while stack and stack[-1][0] >= level:
                    stack.pop()
                section = Section(item.title, len(stack) + 1, heading=item.unit)
                (stack[-1][1].children if stack else root).append(section)
                stack.append((level, section))
            else:
                (stack[-1][1].children if stack else root).append(item)
        return root

    def blocks(self, units: list[dict], allow_sections: bool = False, context: str = "") -> list:
        out: list = []
        pending: dict | None = None  # {"target": id, "block": Para|ListBlock|Table|Item}
        held: list[PageMark] = []
        join = self.profile.get("paragraphs.join_continuations")
        i = 0
        units = [u for u in units if u.get("id") not in self.consumed]
        while i < len(units):
            unit = units[i]
            t = unit["type"]
            if t == "page_marker":
                (held if pending else out).append(self.page_mark(unit))
                i += 1
                continue
            if pending and unit.get("id") == pending["target"]:
                self._join(pending, unit, held)
                held = []
                pending = self._pending_for(unit, pending["block"]) if join else None
                i += 1
                continue
            if pending and t in FLOATS:
                out.append(self.block(unit, context))
                i += 1
                continue
            if pending:
                out.extend(held)
                held, pending = [], None
            if t == "heading" and allow_sections and unit.get("role") != "sidebar_title":
                bib = self._bibliography_at(units, i, unit)
                if bib:
                    block, i = bib
                    out.append(block)
                    continue
                out.append(_HeadingEvent(unit, strip_ranges(self.ref(unit["id"]))))
                i += 1
                continue
            if t == "paragraph" and unit.get("role") in ("display_title", "heading_candidate"):
                bib = self._bibliography_at(units, i, unit)
                if bib:
                    block, i = bib
                    out.append(block)
                    continue
            if t == "list" and unit.get("list_type") == "bibliography":
                block, i = self._bibliography_at(units, i, None) or (None, i)
                if block:
                    out.append(block)
                    continue
            if t == "figure" and self.profile.get("figures.attach_following_captions"):
                block = self.block(unit, context)
                j = i + 1
                if isinstance(block, Figure) and not block.captions:
                    while j < len(units) and units[j]["type"] == "caption":
                        cap = self.ref(units[j]["id"], move="caption attached to figure")
                        if not block.captions and not self._figure_label(cap):
                            break
                        block.captions.append(cap)
                        j += 1
                    if block.captions:
                        self._classify_figure(block)
                out.append(block)
                i = j
                continue
            block = self.block(unit, context)
            if block is None:
                i += 1
                continue
            out.append(block)
            if join:
                pending = self._pending_for(unit, block)
            i += 1
        out.extend(held)
        return out

    def _pending_for(self, unit: dict, block) -> dict | None:
        cont = unit.get("continues_to")
        if not cont or not cont.get("unit"):
            return None
        if isinstance(block, (Para, ListBlock, Table)):
            return {"target": cont["unit"], "block": block, "cont": cont}
        return None

    def _join(self, pending: dict, unit: dict, held: list[PageMark]):
        block = pending["block"]
        move = "continuation joined across a page or column break"
        if isinstance(block, Para) and unit.get("content"):
            block.parts += held + [self.ref(unit["id"], move=move)]
            block.unit_ids.append(unit["id"])
            hyphen = pending["cont"].get("hyphen")
            if hyphen in ("join", "soft_join"):
                prev = next(
                    (p for p in reversed(block.parts[: -1 - len(held)]) if isinstance(p, TextRef)),
                    None,
                )
                if prev is not None:
                    _drop_trailing_hyphen(prev)
            if hyphen or pending["cont"].get("word_join"):
                block.parts[-1].nospace = True
        elif isinstance(block, ListBlock) and unit["type"] == "list":
            extra = self.block(unit, "")
            from ..rules.structure import _declare_move

            _declare_move(extra, move)
            if extra.items:
                first = extra.items[0]
                prev_item = block.items[-1] if block.items else None
                item_cont = None
                if prev_item is not None:
                    src = self.book.units.get(prev_item.unit_id) or {}
                    item_cont = src.get("continues_to")
                if item_cont and item_cont.get("unit") == first.unit_id:
                    prev_item.parts += held + first.parts
                    prev_item.children += first.children
                    prev_item.merged_ids.append(first.unit_id)
                    extra.items = extra.items[1:]
                elif held:
                    first.parts = held + first.parts
                block.items += extra.items
            block.unit_ids.append(unit["id"])
        elif isinstance(block, Table) and unit["type"] == "table":
            block.parts.append(unit)
            block.trailing_marks += held
        else:
            raise AssertionError("unsupported continuation")

    def block(self, unit: dict, context: str = ""):
        t = unit["type"]
        if t == "paragraph":
            return Para([self.ref(unit["id"])], unit.get("role") or "body", [unit["id"]])
        if t == "heading":
            return Para([self.ref(unit["id"])], "display_title", [unit["id"]])
        if t in ("caption", "footnote"):
            if t == "caption":
                self.review("caption", "caption not linked to a figure or table", unit)
            return Para([self.ref(unit["id"])], t, [unit["id"]])
        if t == "index_divider":
            return Para([self.ref(unit["id"])], "label", [unit["id"]])
        if t == "list":
            return self.list_block(unit)
        if t in (
            "list_item",
            "index_entry",
            "glossary_entry",
            "definition_entry",
            "bibliography_entry",
            "contents_entry",
        ):
            return ListBlock("unmarked", None, [self.item(unit)], unit_ids=[unit["id"]])
        if t == "figure":
            return self.figure(unit)
        if t == "table":
            return self.table(unit)
        if t == "box":
            return self.sidebar(unit)
        if t == "equation":
            content = self.ref(unit["id"]) if unit["id"] in self.book.records else None
            return Equation(unit, content)
        if t == "page_marker":
            return self.page_mark(unit)
        raise ValueError(f"unknown unit type {t}")

    def item(self, unit: dict, with_children: bool = True) -> Item:
        parts = [self.ref(unit["id"])] if unit["id"] in self.book.records else []
        children = self.blocks(unit.get("children") or []) if with_children else []
        return Item(
            parts,
            children,
            unit.get("marker"),
            None,
            unit.get("item_role"),
            unit.get("level"),
            unit.get("locators") or [],
            unit["id"],
        )

    def list_block(self, unit: dict) -> ListBlock:
        items = [self.item(i) for i in unit["items"]]
        glyph = None
        for i in unit["items"]:
            marker = i.get("marker")
            if marker and marker.get("type") in ("bullet", "dash"):
                glyph = marker.get("text")
                break
        return ListBlock(
            unit.get("list_type") or "bulleted",
            unit.get("marker_type"),
            items,
            unit.get("start"),
            glyph,
            [unit["id"]],
        )

    def sidebar(self, unit: dict) -> Sidebar:
        children = list(unit.get("children") or [])
        side = Sidebar(unit)
        lead_marks = []
        while children and children[0]["type"] == "page_marker":
            lead_marks.append(self.page_mark(children.pop(0)))
        if children and children[0]["type"] == "heading":
            side.title = strip_ranges(self.ref(children[0]["id"]))
            children = children[1:]
            pattern = re.compile(self.profile.get("sidebars.title_label"))
            m = pattern.match(side.title.text[side.title.ranges[0][0] :])
            if m:
                base = side.title.ranges[0][0]
                side.label_ref = side.title.slice(base, base + m.end())
                side.num = m.group("num")
                side.title = strip_ranges(
                    side.title.slice(base + m.end(), side.title.ranges[-1][1])
                )
        side.children = lead_marks + self.blocks(children)
        return side

    def figure(self, unit: dict) -> Figure | None:
        uid = unit["id"]
        fig = Figure(unit)
        fig.captions = [
            self.ref(f"{uid}/caption/{i}") for i in range(len(unit.get("captions") or []))
        ]
        fig.texts = [self.ref(f"{uid}/text/{i}") for i in range(len(unit.get("text") or []))]
        if self.profile.get("figures.embedded_text") == "omit":
            for ref in fig.texts:  # stays in the image; book.json keeps it
                self.omissions.append(
                    Omission(
                        ref.addr,
                        [(0, len(ref.text))],
                        "text inside a figure (stays in the image)",
                        ref.content,
                    )
                )
            fig.texts = []
        fig.credits = [self.ref(f"{uid}/credit/{i}") for i in range(len(unit.get("credits") or []))]
        fig.image = unit.get("image")
        fig.page = unit["pages"][0]
        fig.page_label = self.pages[fig.page - 1].get("label")
        fig.zone = self.pages[fig.page - 1].get("zone")
        if unit.get("small") and self.profile.get("figures.small") == "omit" and not fig.texts:
            return None
        self._classify_figure(fig)
        return fig

    def _figure_label(self, ref: TextRef):
        for kind in self.profile.get("figures.kinds") or []:
            m = re.match(kind["caption_label"], ref.text[ref.ranges[0][0] :])
            if m and m.group("num"):
                return kind, m
        return None

    def _classify_figure(self, fig: Figure):
        fig.formal, fig.kind, fig.num, fig.label_ref = False, None, None, None
        if fig.captions:
            first = fig.captions[0]
            found = self._figure_label(first)
            if found:
                kind, m = found
                base = first.ranges[0][0]
                fig.kind, fig.num = kind["name"], m.group("num")
                fig.label_ref = first.slice(base, base + m.end())
                fig.captions[0] = first.slice(base + m.end(), first.ranges[-1][1])
                fig.formal = True
            elif self.profile.get("figures.titled_unnumbered") == "figure":
                fig.formal = True
            pattern = self.profile.get("figures.continued_pattern")
            if "continued_figure" in self.rules_on and re.search(pattern, first.text):
                fig.continued = True

    def table(self, unit: dict) -> Table:
        tbl = Table(unit, parts=[unit])
        if unit.get("title"):
            ref = self.ref(f"{unit['id']}/title")
            pattern = re.compile(self.profile.get("tables.title_label"))
            m = pattern.match(ref.text)
            if m:
                tbl.label_ref = ref.slice(0, m.end())
                tbl.num = m.group("num")
                ref = ref.slice(m.end(), len(ref.text))
            tbl.title = strip_ranges(ref)
        tbl.notes = [
            self.ref(f"{unit['id']}/note/{i}") for i in range(len(unit.get("notes") or []))
        ]
        return tbl

    def table_cells(self, tbl: Table):
        """Rows of the (joined) table, cell blocks; repeated header rows are omitted."""
        rows: list[list[dict]] = []
        offset = 0
        for n, part in enumerate(tbl.parts):
            skip = 0
            if n > 0 and part.get("continuation"):
                skip = part["continuation"].get("repeated_header_rows") or 0
            by_row: dict[int, list[dict]] = {}
            for cell in part["cells"]:
                by_row.setdefault(cell["row"], []).append(cell)
            for r in range(part["rows"]):
                cells = sorted(by_row.get(r, []), key=lambda c: c["column"])
                if r < skip:
                    for cell in cells:
                        for k, item in enumerate(cell.get("content") or ()):
                            addr = f"{part['id']}/cell/{cell['id']}/{k}"
                            if item.get("type") == "text":
                                self.omissions.append(
                                    Omission(
                                        addr,
                                        [(0, len(item["content"]["text"]))],
                                        "repeated table header row",
                                        item["content"],
                                    )
                                )
                            else:
                                self.omit_unit(item, "repeated table header row")
                    continue
                rows.append(cells)
            offset += part["rows"] - skip
            if n > 0 and part.get("title"):
                content = part["title"]["content"]
                self.omissions.append(
                    Omission(
                        f"{part['id']}/title",
                        [(0, len(content["text"]))],
                        "title repeated on a continued table part",
                        content,
                    )
                )
            if n > 0:
                move = "continuation joined across a page or column break"
                tbl.notes += [
                    self.ref(f"{part['id']}/note/{i}", move=move)
                    for i in range(len(part.get("notes") or []))
                ]
            if n > 0:
                for cell in part["cells"]:
                    tbl.cells_blocks[cell["id"]] = self._cell_blocks(part, cell, joined=True)
            else:
                for cell in part["cells"]:
                    tbl.cells_blocks[cell["id"]] = self._cell_blocks(part, cell)
        tbl.rows = rows
        tbl.columns = max(p["columns"] for p in tbl.parts)
        tbl.header_rows = tbl.parts[0].get("header_rows") or 0

    def _cell_blocks(self, part: dict, cell: dict, joined: bool = False) -> list:
        out: list = []
        units: list[dict] = []
        move = "continuation joined across a page or column break" if joined else None

        def flush():
            if units:
                out.extend(self.blocks(list(units)))
                units.clear()

        fragments: list[TextRef] = []
        for k, item in enumerate(cell.get("content") or ()):
            if item.get("type") == "text":
                flush()
                fragments.append(self.ref(f"{part['id']}/cell/{cell['id']}/{k}", move=move))
            else:
                if fragments:
                    out.append(Para(list(fragments), "table_text"))
                    fragments = []
                units.append(item)
        flush()
        if fragments:
            out.append(Para(list(fragments), "table_text"))
        if move:
            for block in out:
                for part_ref in getattr(block, "parts", []):
                    if isinstance(part_ref, TextRef):
                        part_ref.move = move
        return out

    # ------------------------------------------------------------------ bibliography

    def _bib_title(self, ref: TextRef) -> bool:
        plain = ref.plain()
        return any(p.match(plain) for p in self.bib_patterns)

    def _bibliography_at(self, units: list[dict], i: int, title_unit: dict | None):
        """A references title followed by reference lists/paragraphs (to the next heading)."""
        title = None
        j = i
        if title_unit is not None:
            ref = strip_ranges(self.ref(title_unit["id"]))
            if not self._bib_title(ref):
                return None
            title = ref
            j = i + 1
        entries: list[BibEntry] = []
        marks: list[PageMark] = []
        while j < len(units):
            u = units[j]
            t = u["type"]
            if t == "page_marker":
                marks.append(self.page_mark(u))
            elif t == "list" and (
                u.get("list_type") in ("bibliography", "numbered", "unmarked")
                or entries == []
                and title is not None
            ):
                for item in u["items"]:
                    ref = self.ref(item["id"])
                    if title is None and not entries and self._bib_title(strip_ranges(ref)):
                        title = strip_ranges(ref)
                        continue
                    entries.append(self._bib_entry(item, marks))
                    marks = []
            elif t == "paragraph" and u.get("role") == "body" and title is not None:
                entries.append(self._bib_entry(u, marks))
                marks = []
            else:
                break
            j += 1
        if not entries:
            return None
        if marks:
            entries[-1].parts += marks
        return Bibliography(title, entries), j

    def _bib_entry(self, unit: dict, marks: list[PageMark]) -> BibEntry:
        ref = self.ref(unit["id"])
        entry = BibEntry(list(marks), unit_id=unit["id"])
        marker = unit.get("marker")
        if marker and marker.get("text"):
            entry.marker_ref = self.ref(f"{unit['id']}#marker")
            entry.marker_text = marker["text"]
        else:
            m = re.match(self.profile.get("bibliography.marker_from_text"), ref.text)
            if m and self.profile.get("bibliography.marker_element"):
                entry.marker_ref = strip_ranges(ref.slice(m.start("marker"), m.end("marker")))
                entry.marker_text = m.group("marker")
                ref = ref.slice(m.end(), len(ref.text))
        entry.parts.append(strip_ranges(ref))
        for child in unit.get("children") or ():
            for block in self.blocks([child]):
                if isinstance(block, PageMark):
                    entry.parts.append(block)
                else:
                    for item in getattr(block, "items", []):
                        if f"{item.unit_id}#marker" in self.book.records:
                            entry.parts.append(self.ref(f"{item.unit_id}#marker"))
                        entry.parts += item.parts
                    entry.parts += [p for p in getattr(block, "parts", [])]
        return entry

    # ------------------------------------------------------------------ first/last roles

    def _first_last(self, doc: Document):
        if not self.profile.get("anchors.first_last_roles"):
            return

        def marks_of(node, acc):
            if isinstance(node, PageMark):
                acc.append(node)
            elif isinstance(node, (TextRef, str, type(None))):
                return
            elif isinstance(node, list):
                for n in node:
                    marks_of(n, acc)
            elif hasattr(node, "__dataclass_fields__"):
                for name in node.__dataclass_fields__:
                    if name in ("unit", "parts_units", "image", "marker", "locators", "heading"):
                        continue
                    value = getattr(node, name)
                    if isinstance(value, (list, PageMark)) or hasattr(
                        value, "__dataclass_fields__"
                    ):
                        marks_of(value, acc)
            return acc

        def visit(div: Division):
            if div.kind in ("part", "chapter"):
                if div.kind == "part":
                    acc = marks_of(div.title_page_mark, []) + marks_of(div.intro, [])
                else:
                    acc = marks_of(div.title_page_mark, []) + marks_of(div.children, [])
                acc = [m for m in acc if m.keep]
                if acc:
                    acc[0].role = "first"
                    if len(acc) > 1:
                        acc[-1].role = "last"
                    div.first_page = acc[0].page
                    div.last_page = acc[-1].page
            for child in div.children:
                if isinstance(child, Division):
                    visit(child)

        for div in doc.body:
            visit(div)


def _append_marks(division: Division, marks: list[PageMark]):
    if division.kind == "index" and division.index_divs and division.index_divs[-1].entries:
        division.index_divs[-1].entries[-1].item.parts.extend(marks)
    else:
        division.children.extend(marks)


@dataclass
class _HeadingEvent:
    unit: dict
    title: TextRef


def _tables(node):
    """Every Table in a document subtree (cells are walked after their table)."""
    if isinstance(node, Table):
        yield node
        return
    if isinstance(node, list):
        for n in node:
            yield from _tables(n)
    elif hasattr(node, "__dataclass_fields__") and not isinstance(node, (TextRef, PageMark)):
        for name in node.__dataclass_fields__:
            value = getattr(node, name)
            if isinstance(value, list) or (
                hasattr(value, "__dataclass_fields__")
                and not isinstance(value, (TextRef, PageMark))
            ):
                yield from _tables(value)


def _minus(ref: TextRef, cut: list[tuple[int, int]]) -> list[TextRef]:
    """Pieces of ref outside the cut ranges."""
    pieces = []
    for s, e in ref.ranges:
        pos = s
        for cs, ce in sorted(cut):
            if ce <= pos or cs >= e:
                continue
            if cs > pos:
                pieces.append(ref.slice(pos, cs))
            pos = max(pos, ce)
        if pos < e:
            pieces.append(ref.slice(pos, e))
    return pieces


def _drop_trailing_hyphen(ref: TextRef):
    chars = render(ref.content, ref.ranges)
    while chars and chars[-1][0] == " ":
        chars.pop()
    if chars and chars[-1][0] in "-­‐":
        cut = chars[-1][1]
        ref.ranges = [(s, min(e, cut)) for s, e in ref.ranges if s < cut] or [(cut, cut)]


def _walk(unit):
    yield unit
    for key in ("items", "children"):
        for child in unit.get(key) or ():
            yield from _walk(child)


def _index_items(unit: dict):
    for item in unit["items"]:
        yield item, item.get("level") or 1
        for child in item.get("children") or ():
            if child.get("type") == "list":
                for sub, level in _index_items(child):
                    yield sub, level if sub.get("level") else (item.get("level") or 1) + 1
            else:
                yield child, (item.get("level") or 1) + 1


def build_document(book: LoadedBook, profile, settings, rules_on: set[str]) -> Document:
    return OutlineBuilder(book, profile, settings, rules_on).build()
