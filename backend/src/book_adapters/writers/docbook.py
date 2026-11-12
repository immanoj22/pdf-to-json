"""DocBook XML 4.2 writer. Format knowledge only: ids, labels, roles, file layout, image
names, characters and which rules apply all come from the profile."""

from __future__ import annotations

import copy
import re
import unicodedata
from collections import defaultdict

from lxml import etree

from ..engine.ledger import Ledger
from ..engine.model import (
    BibEntry,
    Bibliography,
    Division,
    Document,
    Equation,
    Figure,
    IndexDiv,
    Item,
    ListBlock,
    PageMark,
    Para,
    QandaSet,
    QuestionSet,
    ReviewEntry,
    Section,
    Sidebar,
    Table,
)
from ..engine.text import DELETE, TextRef, dropped_offsets, render
from ..rules import RULES
from .base import Delivery, ImageJob, WriteContext
from .serialize import Serializer

INLINE = frozenset(
    {
        "emphasis",
        "superscript",
        "subscript",
        "ulink",
        "anchor",
        "email",
        "phrase",
        "abbrev",
        "firstname",
        "surname",
        "othername",
        "contrib",
        "jobtitle",
        "orgname",
        "orgdiv",
        "otheraddr",
        "city",
        "state",
        "country",
    }
)
BLOCK = frozenset(
    {
        "book",
        "bookinfo",
        "authorgroup",
        "author",
        "affiliation",
        "legalnotice",
        "dedication",
        "preface",
        "part",
        "partintro",
        "chapter",
        "appendix",
        "section",
        "sidebar",
        "itemizedlist",
        "orderedlist",
        "variablelist",
        "varlistentry",
        "listitem",
        "figure",
        "informalfigure",
        "mediaobject",
        "imageobject",
        "textobject",
        "caption",
        "table",
        "informaltable",
        "tgroup",
        "thead",
        "tbody",
        "row",
        "bibliography",
        "bibliomixed",
        "index",
        "indexdiv",
        "indexentry",
        "qandaset",
        "qandadiv",
        "qandaentry",
        "question",
        "answer",
        "informalequation",
        "glossary",
    }
)
COMPACT = frozenset({"listitem", "indexentry", "bibliomixed", "question", "answer"})
HOSTS = frozenset({"para", "title", "bibliomisc", "primaryie", "secondaryie", "tertiaryie", "term"})
EMPHASIS_KINDS = ("bold", "italic", "bold_italic", "small_caps", "underline")


def fmt(pattern: str, **values) -> str:
    return pattern.format(**{k: ("" if v is None else v) for k, v in values.items()})


def last_component(num: str) -> str:
    return re.split(r"[.\-]", num)[-1]


class DocBookWriter:
    name = "docbook"

    def write(self, doc: Document, ctx: WriteContext) -> Delivery:
        self.doc, self.ctx, self.p = doc, ctx, ctx.profile
        self.settings = ctx.settings
        self.rules_on = ctx.rules_on
        self.ledger = Ledger()
        self.reviews: list[ReviewEntry] = []
        self.pending: list[PageMark] = []
        self.last_host = None
        self.host_owner = None  # division element of last_host
        self.division_el = None
        self.chapter_ctx: dict = {}
        self.preface_paras: int | None = None
        self.char_rules = sorted(
            n
            for n in self.rules_on
            if RULES[n].phase == "characters" and n != "index_range_en_dash"
        )
        self.link_rules = sorted(n for n in self.rules_on if RULES[n].phase == "links")
        isbn = self.settings.data.get("isbn")
        self.isbn = isbn or self.p.get("delivery.missing_isbn_folder")
        if not isbn:
            self.reviews.append(
                ReviewEntry(
                    "settings", f"ISBN not supplied: delivery uses {self.isbn!r} as its name"
                )
            )
        self.images: list[ImageJob] = []
        self.alt_placeholders: list[str] = []
        self.anchor_of_page = {m.page: m.anchor_id for m in self._all_marks()}
        self._prepare()
        book = etree.Element("book")
        self.book_el = book
        self.front_els = self._write_bookinfo(book)
        for division in doc.front:
            self.front_els.append(self._write_division(book, division))
        self.chapter_els: list[tuple[Division, etree._Element, Division | None]] = []
        for division in doc.body:
            self._write_division(book, division)
        self.index_el = None
        for division in doc.back:
            el = self._write_division(book, division)
            if division.kind == "index":
                self.index_el = el
        for division in doc.after:
            self._write_division(book, division)
        return self._package(book)

    # ------------------------------------------------------------------ preparation

    def _all_marks(self):
        seen = set()
        for mark in _walk_marks(self.doc):
            if id(mark) not in seen:
                seen.add(id(mark))
                yield mark

    def _prepare(self):
        ids = self.p.get("ids")
        outside = ids["outside_chapter"]
        self.fig_kinds = {k["name"]: k for k in self.p.get("figures.kinds") or []}
        self._seen_ids: set[str] = set()
        part_no = 0
        self._counters: dict = {}  # per {chapter} value: ids stay unique across divisions
        self._unlabelled: set[int] = set()  # divisions written as chapters without a label
        if self.p.get("back_matter.as_chapter"):
            self._back_matter_as_chapters()
        for division in self.doc.body + self.doc.after:
            if division.kind == "part":
                part_no = division.chosen_number or part_no + 1
                division.number = part_no
        for division in _divisions(self.doc):
            if division.kind not in ("part", "index"):
                _hoist_bibliographies(division)
            chapter = division.number if division.kind == "chapter" else outside
            if division.kind == "part":
                division.id = fmt(
                    ids["part"], part=division.number, chapter=outside, n=division.number
                )
                label = self.p.get("labels.part")
                division.label = fmt(label, n=division.number) if label else None
                self._number_nodes(division.intro, outside, {})
            elif division.kind == "chapter":
                division.id = fmt(ids["chapter"], chapter=division.number, n=division.number)
                label = self.p.get("labels.chapter")
                division.label = (
                    fmt(label, n=division.number)
                    if label and id(division) not in self._unlabelled
                    else None
                )
                maps = {"bib_ids": {}, "object_ids": {}}
                self._number_nodes(division.children, chapter, maps)
                division.link_maps = maps  # type: ignore[attr-defined]
            elif division.kind == "index":
                division.id = ids["index"]
            else:
                self._number_nodes(division.children, outside, {})
        self._name_images()

    def _back_matter_as_chapters(self):
        """Guideline item 40/41: appendices and glossaries are chapters, numbered on from
        the last chapter of the book, so their ids follow the chapter scheme."""
        last = max(
            (
                d.number or 0
                for d in _divisions(self.doc)
                if d.kind == "chapter"
            ),
            default=0,
        )
        for division in self.doc.back:
            if division.kind in ("appendix", "glossary"):
                last += 1
                division.kind = "chapter"
                division.number = last
                self._unlabelled.add(id(division))

    def _number_nodes(self, nodes, chapter, maps):
        ids = self.p.get("ids")
        # Counters run on through every division numbered with the same {chapter} value
        # (front matter, parts and appendices share the outside-chapter value).
        counters, sections, bib_count = self._counters.setdefault(
            str(chapter), (defaultdict(int), defaultdict(int), [0])
        )

        def visit(node_list, depth=0):
            for node in node_list:
                if isinstance(node, Section):
                    if ids["section_numbering"] == "per_parent":
                        sections[node.depth] += 0
                    sections[node.depth] += 1
                    n = sections[node.depth]
                    node.id = fmt(ids["section"], chapter=chapter, level=node.depth, n=n)
                    role = ids.get("section_title_role")
                    node.title_role = (
                        fmt(role, chapter=chapter, level=node.depth, n=n) if role else None
                    )
                    visit(node.children, node.depth)
                elif isinstance(node, Figure):
                    self._number_figure(node, chapter, counters, maps)
                elif isinstance(node, Table):
                    if node.title is not None or node.label_ref is not None:
                        counters["table"] += 1
                        n = last_component(node.num) if node.num else f"u{counters['table']}"
                        node.id = fmt(ids["table"], chapter=chapter, n=n, num=node.num)
                        role = ids.get("table_title_role")
                        node.title_role = (
                            fmt(role, chapter=chapter, n=n, num=node.num) if role else None
                        )
                        label = self.p.get("labels.table")
                        node.label = fmt(label, num=node.num) if label and node.num else None
                        if node.num:
                            maps.setdefault("object_ids", {})[("table", node.num)] = node.id
                    for blocks in node.cells_blocks.values():
                        visit(blocks, depth)
                elif isinstance(node, Sidebar):
                    if node.num:
                        n = last_component(node.num)
                        node.id = fmt(ids["sidebar"], chapter=chapter, n=n, num=node.num)
                        role = ids.get("sidebar_title_role")
                        node.title_role = (
                            fmt(role, chapter=chapter, n=n, num=node.num) if role else None
                        )
                        label = self.p.get("labels.sidebar")
                        node.label = fmt(label, num=node.num) if label else None
                        maps.setdefault("object_ids", {})[("sidebar", node.num)] = node.id
                    visit(node.children, depth)
                elif isinstance(node, Bibliography):
                    bib_count[0] += 1
                    base = fmt(ids["bibliography"], chapter=chapter)
                    node.id = base if bib_count[0] == 1 else f"{base}{bib_count[0]}"
                    for k, entry in enumerate(node.entries, 1):
                        number = _int(entry.marker_text) or k
                        entry.id = fmt(ids["bibliography_entry"], chapter=chapter, n=number)
                        if bib_count[0] > 1:
                            entry.id = f"{entry.id}_{bib_count[0]}"
                        maps.setdefault("bib_ids", {}).setdefault(number, entry.id)
                    visit(node.lead, depth)
                elif isinstance(node, ListBlock):
                    for item in node.items:
                        visit(item.children, depth)
                elif isinstance(node, QandaSet):
                    for item in node.items:
                        visit(item.children, depth)
                elif isinstance(node, QuestionSet):
                    visit(node.blocks(), depth)

        visit(nodes)
        seen = self._seen_ids
        for node in _iter_nodes(nodes):  # ids are unique in the book
            node_id = getattr(node, "id", None)
            if node_id:
                k = 2
                while node.id in seen:
                    node.id = f"{node_id}_{k}"
                    k += 1
                seen.add(node.id)

    def _number_figure(self, fig: Figure, chapter, counters, maps):
        ids = self.p.get("ids")
        if not fig.formal:
            return
        kind = self.fig_kinds.get(fig.kind) if fig.kind else None
        if kind is None:
            kind = next(iter(self.fig_kinds.values()), None)
            if kind is None:
                fig.formal = False
                return
        counters[kind["name"]] += 1
        if fig.continued:
            counters[(kind["name"], "cont", fig.num)] += 1
            n = last_component(fig.num) if fig.num else f"u{counters[kind['name']]}"
            fig.id = fmt(
                ids["continued_figure"],
                chapter=chapter,
                n=n,
                num=fig.num,
                k=counters[(kind["name"], "cont", fig.num)],
            )
            fig.label = self.p.get("labels.continued_figure")
            fig.title_role = fmt(kind["title_role"], chapter=chapter, n=n, num=fig.num)
            return
        n = last_component(fig.num) if fig.num else f"u{counters[kind['name']]}"
        fig.id = fmt(kind["id"], chapter=chapter, n=n, num=fig.num)
        fig.title_role = fmt(kind["title_role"], chapter=chapter, n=n, num=fig.num)
        if fig.num:
            word = fig.label_ref.plain().strip() if fig.label_ref else ""
            fig.label = fmt(kind["label"], num=fig.num, word=word)
            if fig.verbatim_label and word:  # book text is never changed: the printed label
                fig.label = " ".join(word.split()).rstrip(".:")
            maps.setdefault("object_ids", {})[(kind["name"], fig.num)] = fig.id

    def _image_format(self) -> str:
        return self.p.get("images.format")

    def _name_images(self):
        pattern = self.p.get("images.name")
        front = self.p.get("images.front_name")
        ext = self._image_format()
        per_page: dict[int, int] = defaultdict(int)
        front_n = 0
        big_mode = self.p.get("images.big_include")
        self.image_of: dict[int, str] = {}
        for node in _iter_doc_blocks(self.doc):
            image, page, unit = None, None, None
            if isinstance(node, Figure) and node.image:
                image, page, unit = node.image, node.page, node.unit
            elif (
                isinstance(node, Equation)
                and node.unit.get("image")
                and self.p.get("images.equation_images")
            ):
                image, page, unit = node.unit["image"], node.unit["pages"][0], node.unit
            if image is None:
                continue
            entry = self.ctx.book.pages[page - 1]
            if entry.get("zone") == "front":
                front_n += 1
                stem = fmt(front, n=front_n, page=page, page_label=entry.get("label"))
            else:
                per_page[page] += 1
                label = entry.get("label") or f"p{page}"
                label = re.sub(r"[^A-Za-z0-9_.-]", "_", label)
                stem = fmt(pattern, page_label=label, page=page, n=per_page[page])
            name = f"{stem}.{ext}"
            big = (
                isinstance(node, Figure)
                and node.formal
                and (big_mode == "all_figures" or (node.num is not None and not node.continued))
            )  # a continued figure has a blank label: no big image (item 17 follows labels)
            if big_mode == "all_figures" and isinstance(node, Figure):
                big = True
            self.images.append(ImageJob(image["file"], name, big, page, unit["id"]))
            self.image_of[id(node)] = name

    # ------------------------------------------------------------------ inline text

    def _subst(self, ref: TextRef, extra: dict | None = None) -> str:
        """The record's text after the profile's character rules; every character a rule
        changed inside the written ranges is recorded in the ledger."""
        text = ref.text
        for name in self.char_rules:
            ctx = {"apostrophe": self.p.get("characters.apostrophe")}
            new, reviews = RULES[name].func(text, ctx)
            for message in reviews:
                self.reviews.append(
                    ReviewEntry("character", message, ref.addr.split("/")[0], None, name)
                )
            text = self._record_changes(ref, text, new, name)
        if extra and "index_range_en_dash" in self.rules_on:
            new, _ = RULES["index_range_en_dash"].func(text, extra)
            text = self._record_changes(ref, text, new, "index_range_en_dash")
        return text

    def _record_changes(self, ref: TextRef, old: str, new: str, rule: str) -> str:
        if new == old:
            return new
        assert len(new) == len(old), f"rule {rule} changed the text length"
        for s, e in ref.ranges:
            for i in range(s, e):
                if new[i] != old[i]:
                    self.ledger.change(
                        ref.addr, i, ref.text[i], "" if new[i] == DELETE else new[i], rule
                    )
        return new

    def _style_spans(self, ref: TextRef, allowed: tuple, extra_links=(), title_depth=None):
        """Per-span (start, end, key part) for allowed span kinds of this record."""
        spans = []
        inline = self.p.get("inline.map") or {}
        for span in ref.content.get("spans") or ():
            kind = span["kind"]
            if kind not in allowed:
                continue
            if (
                title_depth is not None
                and "no_italic_heading_level3" in self.rules_on
                and RULES["no_italic_heading_level3"].func(
                    {"container": "section_title", "depth": title_depth, "span": kind}
                )
            ):
                continue
            if kind == "small_caps" and self.p.get("inline.small_caps") == "never":
                continue
            if kind == "link":
                href = span.get("href")
                if not href and span.get("target"):
                    anchor = self.anchor_of_page.get(span["target"]["page"])
                    href = f"#{anchor}" if anchor else None
                if href:
                    spans.append((span["start"], span["end"], ("link", href)))
                continue
            mapping = inline.get(kind)
            if not mapping or not mapping.get("element"):
                continue
            spans.append(
                (span["start"], span["end"], (kind, mapping["element"], mapping.get("role")))
            )
        for start, end, href in extra_links:
            spans.append((start, end, ("link", href)))
        return spans

    def _key(self, raw: int, spans) -> tuple:
        """The element chain (outermost first) for one source character. Emphasis, then
        super/subscript, then the link, except that an element whose span lies inside a
        link's span goes inside the link ("<ulink>73<emphasis>f</emphasis></ulink>")."""
        kinds = set()
        href = None
        script = None
        link_range = None
        inner: set[str] = set()  # elements (by tag/role) whose span lies inside the link
        covering = [(s, e, part) for s, e, part in spans if s <= raw < e]
        for start, end, part in covering:
            if part[0] == "link" and href is None:
                href, link_range = part[1], (start, end)
        for start, end, part in covering:
            if part[0] == "link":
                continue
            if (
                link_range
                and link_range[0] <= start
                and end <= link_range[1]
                and ((start, end) != link_range)
            ):
                inner.add(part[1] if part[1] in ("superscript", "subscript") else part[0])
            if part[1] in ("superscript", "subscript"):
                script = part[1]
            else:
                kinds.add(part)
        names = {k[0] for k in kinds}
        roles = []
        nested = self.p.get("inline.bold_italic") == "nested"
        if "bold_italic" in inner:
            inner |= {"bold", "italic"}
        if nested and "bold_italic" in names:
            kinds = {k for k in kinds if k[0] != "bold_italic"}
            inline = self.p.get("inline.map") or {}
            for name in ("bold", "italic"):
                m = inline.get(name)
                if m and m.get("element"):
                    kinds.add((name, m["element"], m.get("role")))
            names = {k[0] for k in kinds}
        if (
            not nested
            and {"bold", "italic"} <= names
            and (self.p.get("inline.map") or {}).get("bold_italic")
        ):
            bi = self.p.get("inline.map")["bold_italic"]
            roles.append((bi["element"], bi.get("role"), "bold_italic"))
            if inner & {"bold", "italic"}:
                inner.add("bold_italic")
            kinds = {k for k in kinds if k[0] not in ("bold", "italic")}
        roles += [(k[1], k[2], k[0]) for k in kinds]
        order = {"bold": 0, "bolditalic": 1, "italic": 2}
        outer, inside = [], []
        for el, role, name in sorted(set(roles), key=lambda r: (order.get(r[1], 3), str(r))):
            spec = (el, (("role", role),) if role else ())
            (inside if name in inner else outer).append(spec)
        if script:
            (inside if script in inner else outer).append((script, ()))
        if href and href.startswith("mailto:") and self.p.get("links.email") == "email":
            link = [("email", ())]
        elif href:
            link = [("ulink", (("url", href),))]
        else:
            link = []
        return tuple(outer + link + inside)

    def render(
        self,
        el,
        parts: list,
        allowed: tuple,
        links: bool = False,
        host: bool = True,
        title_depth=None,
        extra: dict | None = None,
    ):
        """Write inline parts (text refs and page marks) into el, with spans, anchors and
        ledger entries."""
        if host and self.pending:
            for mark in self.pending:
                self._anchor(el, mark)
            self.pending = []
        segments = []
        for part in parts:
            if isinstance(part, PageMark):
                segments.append(part)
                continue
            text = self._subst(part, extra.get(part.addr) if extra else None)
            link_spans = self._links(part, text, links) if links else []
            drops = [d for link in link_spans for d in (link[3] if len(link) > 3 else ())]
            if drops:  # line ends inside a web address are not spaces
                chars = list(text)
                for d in drops:
                    chars[d] = DELETE
                text = self._record_changes(part, text, "".join(chars), "link_urls_emails")
            chars = render(part.content, part.ranges, text=text)
            spans = self._style_spans(part, allowed, [link[:3] for link in link_spans], title_depth)
            segments.append((part, chars, spans))
        # spacing between pieces, trimming at both ends
        text_segments = [s for s in segments if not isinstance(s, PageMark)]
        if text_segments:
            first, last = text_segments[0], text_segments[-1]
            while first[1] and first[1][0][0] == " ":
                first[1].pop(0)
            while last[1] and last[1][-1][0] == " ":
                last[1].pop()
        prev_chars = None
        for seg in segments:
            if isinstance(seg, PageMark):
                self._close_to(el)
                self._anchor(self._base, seg)
                continue
            ref, chars, spans = seg
            if prev_chars is not None and chars and not ref.nospace:
                if prev_chars[-1][0] != " " and chars[0][0] != " ":
                    chars.insert(0, (" ", -1))
            elif prev_chars is not None and ref.nospace:
                while chars and chars[0][0] == " ":
                    chars.pop(0)
            rendered = []
            self._open_base(el)
            for ch, raw in chars:
                key = self._key(raw, spans) if raw >= 0 else self._current_key()
                self._ensure_chain(key)
                self._append(ch)
                rendered.append(ch)
            self.ledger.text(
                ref, "".join(rendered), el, kind="marker" if ref.kind == "marker" else "text"
            )
            if chars:
                prev_chars = chars
        self._close_to(el)
        if host and el.tag in HOSTS:
            self.last_host = el
            self.host_owner = self.division_el

    # --- chain management over one host element
    def _open_base(self, el):
        if getattr(self, "_base", None) is not el:
            self._base = el
            self._chain: list[tuple[tuple, etree._Element]] = []

    def _current_key(self):
        return tuple(k for k, _ in getattr(self, "_chain", []))

    def _ensure_chain(self, key: tuple):
        chain = self._chain
        common = 0
        while common < len(chain) and common < len(key) and chain[common][0] == key[common]:
            common += 1
        del chain[common:]
        parent = chain[-1][1] if chain else self._base
        for spec in key[common:]:
            tag, attrs = spec
            child = etree.SubElement(parent, tag)
            for k, v in attrs:
                child.set(k, v)
            chain.append((spec, child))
            parent = child

    def _append(self, s: str):
        target = self._chain[-1][1] if self._chain else self._base
        if len(target):
            target[-1].tail = (target[-1].tail or "") + s
        else:
            target.text = (target.text or "") + s

    def _close_to(self, el):
        self._open_base(el)
        self._chain = []

    def _anchor(self, el, mark: PageMark):
        if not mark.keep or not self.p.get("anchors.enabled"):
            return
        a = etree.SubElement(el, "anchor")
        a.set("id", mark.anchor_id)
        if mark.role:
            a.set("role", mark.role)

    def _links(self, ref: TextRef, text: str, which=True):
        """Links the profile's link rules add to this text: (start, end, href[, drops]).
        ``which``: True for every link rule, or "web" for web/e-mail addresses only
        (bibliography entries: their numbers and titles are not cross-references)."""
        out = []
        spans = ref.content.get("spans") or []
        existing = [(s["start"], s["end"]) for s in spans if s["kind"] == "link"]
        ctx = dict(self.chapter_ctx or {})
        ctx["mention_words"] = self._mention_words()
        ctx["dropped"] = dropped_offsets(ref.content)
        ctx["www_scheme"] = self.p.get("links.www_scheme")
        for name in self.link_rules:
            if which == "web" and name != "link_urls_emails":
                continue
            for link in RULES[name].func(text, spans, ctx):
                start, end = link[0], link[1]
                if any(s < end and start < e for s, e in existing):
                    continue
                if not any(s <= start and end <= e for s, e in ref.ranges):
                    continue
                out.append(link)
                existing.append((start, end))
        return out

    def _mention_words(self) -> dict:
        words = {}
        for name in self.fig_kinds:
            words[name] = name
            words[name + "s"] = name
            if name == "figure":
                words.update({"fig": "figure", "figs": "figure"})
        words.update({"table": "table", "tables": "table", "box": "sidebar"})
        return words

    # ------------------------------------------------------------------ bookinfo

    def _write_bookinfo(self, book) -> list:
        info = etree.SubElement(book, "bookinfo")
        self.division_el = info
        title = etree.SubElement(info, "title")
        if "bookinfo" in self.p.get("anchors.titles"):
            for mark in self.doc.bookinfo.page_marks:
                self._anchor(title, mark)
        else:
            self.pending += self.doc.bookinfo.page_marks
        if self.settings.data.get("title"):
            self._settings_text(title, self.settings.data["title"], "title")
        elif self.doc.bookinfo.title_ref is not None:
            self.render(
                title, [self.doc.bookinfo.title_ref], ("superscript", "subscript"), host=False
            )
        else:
            self.reviews.append(ReviewEntry("settings", "book title to supply"))
        if not self.settings.data.get("authorgroups"):
            self._write_title_page_authors(info)
        for group in self.settings.data.get("authorgroups") or []:
            ag = etree.SubElement(info, "authorgroup")
            for person in group:
                author = etree.SubElement(ag, "author")
                if person.get("contrib"):
                    self._settings_text(
                        etree.SubElement(author, "contrib"), person["contrib"], "contrib"
                    )
                    author[-1].tail = " "
                for tag, key in (
                    ("firstname", "firstname"),
                    ("surname", "surname"),
                    ("othername", "degrees"),
                ):
                    if person.get(key):
                        child = etree.SubElement(author, tag)
                        if tag == "othername":
                            child.set("role", "degrees")
                        self._settings_text(child, person[key], key)
                        child.tail = " "
                aff = person.get("affiliation")
                if aff:
                    if len(author):
                        author[-1].tail = None
                    a = etree.SubElement(author, "affiliation")
                    for tag in ("jobtitle", "orgname"):
                        if aff.get(tag):
                            self._settings_text(etree.SubElement(a, tag), aff[tag], tag)
                    if any(aff.get(k) for k in ("city", "state", "country")):
                        addr = etree.SubElement(a, "address")
                        for tag in ("city", "state", "country"):
                            if aff.get(tag):
                                if len(addr):
                                    addr[-1].tail = ", "
                                self._settings_text(etree.SubElement(addr, tag), aff[tag], tag)
                if len(author) and author[-1].tail == " ":
                    author[-1].tail = None
        if self.doc.bookinfo.legal:
            legal = etree.SubElement(info, "legalnotice")
            self._write_nodes(legal, self.doc.bookinfo.legal, container="legalnotice")
            self._flush_into(legal)
        isbn = self.settings.data.get("isbn")
        if isbn:
            self._settings_text(etree.SubElement(info, "isbn"), isbn, "isbn")
        if self.doc.bookinfo.legal_after:
            legal = etree.SubElement(info, "legalnotice")
            self._write_nodes(legal, self.doc.bookinfo.legal_after, container="legalnotice")
            self._flush_into(legal)
        return []

    def _write_title_page_authors(self, info):
        """Author groups read from the title page: every part is a slice of the printed text
        (source styles kept in contrib only, as delivered). DocBook fixes the order inside
        an affiliation (jobtitle, orgname, orgdiv, address); a part written before a part
        printed ahead of it is a declared move."""
        for group in self.doc.bookinfo.authors:
            ag = etree.SubElement(info, "authorgroup")
            for person in group:
                author = etree.SubElement(ag, "author")
                written: list[tuple] = []

                def put(parent, tag, refs, allowed=(), attrs=(), tail=None, written=written):
                    refs = [r for r in refs if r is not None]
                    if not refs:
                        return None
                    el = etree.SubElement(parent, tag, dict(attrs))
                    for ref in refs:
                        key = (ref.order, ref.ranges[0][0])
                        if written and key < max(written):
                            ref.move = ref.move or "affiliation part placed in DocBook order"
                        written.append(key)
                    self.render(el, refs, allowed, host=False)
                    el.tail = tail
                    return el

                put(author, "contrib", [person.contrib], _all_kinds()[:-1], tail=" ")
                put(author, "firstname", [person.firstname], tail=" ")
                put(author, "surname", [person.surname], tail=" ")
                put(author, "othername", person.degrees, attrs=[("role", "degrees")], tail=" ")
                parts = [person.jobtitle, person.orgname, person.orgdiv, person.otheraddr]
                if any(parts) or person.city or person.country:
                    if len(author):
                        author[-1].tail = None
                    aff = etree.SubElement(author, "affiliation")
                    put(aff, "jobtitle", person.jobtitle)
                    put(aff, "orgname", person.orgname)
                    for div in person.orgdiv:
                        put(aff, "orgdiv", [div])
                    place = [person.city, person.state, person.country]
                    if person.otheraddr or any(place):
                        address = etree.SubElement(aff, "address")
                        for ref in person.otheraddr:
                            put(address, "otheraddr", [ref], tail=", ")
                        for tag, ref in zip(("city", "state", "country"), place, strict=True):
                            put(address, tag, [ref], tail=", ")
                        if len(address):
                            address[-1].tail = None
                if len(author) and author[-1].tail == " ":
                    author[-1].tail = None

    def _settings_text(self, el, value: str, note: str):
        el.text = (el.text or "") + value
        self.ledger.other("settings", value, el, note)

    # ------------------------------------------------------------------ divisions

    def _write_division(self, parent, division: Division):
        kind = division.kind
        tag = {
            "preface": "preface",
            "dedication": "dedication",
            "appendix": "appendix",
            "glossary": "appendix",
            "index": "index",
            "bibliography": "bibliography",
            "chapter": "chapter",
            "part": "part",
        }.get(kind, "appendix")
        if kind == "bibliography":
            content = [
                c for c in _flatten_sections(division.children) if not isinstance(c, PageMark)
            ]
            if not content or not all(isinstance(c, Bibliography) for c in content):
                # DTD: a book-level bibliography holds entries only; with other text it is
                # an appendix (its reference lists become bibliographies at its end)
                tag = "appendix"
        if kind == "part" and not any(isinstance(c, Division) for c in division.children):
            tag = "chapter"  # a part needs chapters (DTD); written as a chapter for review
            self.reviews.append(
                ReviewEntry(
                    "structure",
                    "part without chapters written as a chapter",
                    None,
                    division.first_page,
                )
            )
        el = etree.SubElement(parent, tag)
        prev_division = self.division_el
        self.division_el = el
        if division.id and tag in ("part", "chapter", "index"):
            el.set("id", division.id)
        if division.label and tag in ("part", "chapter"):
            el.set("label", division.label)
        for ref, note in ((division.label_ref, "label word"), (division.number_ref, "number")):
            if ref is not None:
                self.ledger.attr(ref, division.label or "", f"{kind} {note} in label")
        title = etree.SubElement(el, "title")
        allow = kind in self.p.get("anchors.titles") or tag in self.p.get("anchors.titles")
        if allow:
            for mark in division.title_page_mark:
                self._anchor(title, mark)
        else:
            self.pending += division.title_page_mark
        if division.title:
            self.render(title, division.title, tuple(self.p.get("inline.in_titles")), host=False)
        elif division.title_text:
            title.text = (title.text or "") + division.title_text
            self.ledger.other("generated", division.title_text, title, f"{kind} title")
        if kind == "chapter":
            self.chapter_ctx = getattr(division, "link_maps", {})
        else:
            self.chapter_ctx = {}
        self.preface_paras = 0 if kind in ("preface", "dedication") else None
        if kind == "index":
            self._write_index(el, division)
        elif kind == "part" and tag == "part":
            if division.intro:
                intro = etree.SubElement(el, "partintro")
                target = intro
                if self.p.get("outline.part_intro_wrapper") == "sidebar":
                    target = etree.SubElement(intro, "sidebar")
                nodes = division.intro
                if target is not intro:  # one wrapper sidebar: boxes inside it are unwrapped
                    nodes = _unwrap_sidebars(nodes)
                self._write_nodes(
                    target, nodes, container="sidebar" if target is not intro else "partintro"
                )
                self._flush_into(intro)
                if not len(target):
                    etree.SubElement(target, "para")
            else:
                self._flush_into(el)
            for child in division.children:
                child_el = self._write_division(el, child)
                self.chapter_els.append((child, child_el, division))
        elif tag == "bibliography":  # entries straight in the book-level bibliography
            for node in _flatten_sections(division.children):
                if isinstance(node, Bibliography):
                    self._write_nodes(el, node.lead, container="bibliography")
                    self._write_bib_entries(el, node)
                else:
                    self._write_nodes(el, [node], container="bibliography")
            self._flush_into(el)
        else:
            nodes = division.intro + division.children if kind == "part" else division.children
            if kind == "dedication":
                nodes = _flatten_sections(nodes)
            self._write_nodes(el, nodes, container=tag)
            self._flush_into(el)
            if len(el) == 1:
                etree.SubElement(el, "para")
                self.reviews.append(
                    ReviewEntry("structure", f"{kind} has no content", None, division.first_page)
                )
            if kind == "chapter" and parent is self.book_el:
                self.chapter_els.append((division, el, None))
        self.preface_paras = None
        self.division_el = prev_division
        return el

    def _flush_into(self, el):
        """Pending page anchors at the end of a division: end of the last para written in it
        (item 32), or a new para at the deepest open position."""
        if not self.pending:
            return
        host = self.last_host if self.host_owner is el or _is_ancestor(el, self.last_host) else None
        if host is not None and self.p.get("anchors.standalone") == "previous_para":
            for mark in self.pending:
                self._anchor(host, mark)
            self.pending = []
            return
        target = el
        while len(target) and target[-1].tag in ("section", "partintro", "sidebar"):
            target = target[-1]
        if len(target) and target[-1].tag in ("bibliography", "index") and host is not None:
            for mark in self.pending:
                self._anchor(host, mark)
            self.pending = []
            return
        para = etree.SubElement(target, "para")
        for mark in self.pending:
            self._anchor(para, mark)
        self.pending = []
        self.last_host, self.host_owner = para, self.division_el

    # ------------------------------------------------------------------ nodes

    def _write_nodes(self, parent, nodes, container: str):
        for node in nodes:
            if isinstance(node, PageMark):
                if node.keep:
                    self.pending.append(node)
                continue
            if isinstance(node, Section):
                self._write_section(parent, node)
                continue
            self._write_block(parent, node, container)

    def _wrap(self, parent, container: str, block: str, default_wrap: bool = False):
        """The element a block goes into: parent, or a new para when a rule asks for it."""
        wrap = default_wrap
        for name in ("sidebar_children_in_para", "nested_list_in_para", "list_in_entry_in_para"):
            if name in self.rules_on and RULES[name].func({"container": container, "block": block}):
                wrap = True
        if wrap:
            para = etree.SubElement(parent, "para")
            if self.pending:
                for mark in self.pending:
                    self._anchor(para, mark)
                self.pending = []
            return para
        return parent

    def _write_section(self, parent, section: Section):
        el = etree.SubElement(parent, "section")
        if section.id:
            el.set("id", section.id)
        title = etree.SubElement(el, "title")
        if section.title_role:
            title.set("role", section.title_role)
        if section.title is not None:
            self.render(
                title,
                [section.title],
                tuple(self.p.get("inline.in_titles")),
                host=False,
                title_depth=section.depth,
            )
        self._write_nodes(el, section.children, container="section")
        content = [c for c in el if c.tag != "title"]
        if not content:
            para = etree.SubElement(el, "para")
            if self.pending:
                for mark in self.pending:
                    self._anchor(para, mark)
                self.pending = []
            else:
                self.reviews.append(
                    ReviewEntry(
                        "structure",
                        "section without content (a para is required by the DTD)",
                        None,
                        None,
                    )
                )
            self.last_host, self.host_owner = para, self.division_el

    def _para_role(self, para: Para, parent) -> str | None:
        if para.role_override:
            return para.role_override
        roles = self.p.get("paragraphs.roles") or {}
        role = roles.get(para.kind, roles.get("body"))
        running = parent.tag in ("section", "chapter", "preface", "appendix", "partintro")
        if running and para.kind in (self.p.get("paragraphs.running_text_kinds") or ()):
            after_title = len(parent) and parent[-1].tag == "title"
            key = (
                "paragraphs.first_after_title_role" if after_title else "paragraphs.following_role"
            )
            role = self.p.get(key) or role
        return role

    def _write_block(self, parent, block, container: str):
        if isinstance(block, Para):
            if all(isinstance(p, PageMark) or p.is_blank() for p in block.parts):
                self.pending += [p for p in block.parts if isinstance(p, PageMark) and p.keep]
                return
            role = self._para_role(block, parent)
            el = etree.SubElement(parent, "para")
            if role:
                el.set("role", role)
            body = block.kind in (
                "body",
                "display_title",
                "label",
                "heading_candidate",
                "list_item_candidate",
                "table_text",
                "figure_text",
            )
            self.render(el, block.parts, _all_kinds(), links=body)
        elif isinstance(block, ListBlock):
            self._write_list(self._wrap(parent, container, "list"), block)
        elif isinstance(block, Figure):
            wrap = self.p.get("figures.formal_wrap" if block.formal else "figures.informal_wrap")
            target = self._wrap(
                parent,
                container,
                "figure",
                default_wrap=wrap == "para" or container in ("listitem", "entry"),
            )
            self._write_figure(target, block)
        elif isinstance(block, Table):
            target = self._wrap(parent, container, "table", default_wrap=container in ("listitem",))
            self._write_table(target, block)
        elif isinstance(block, Sidebar):
            self._write_sidebar(parent, block)
        elif isinstance(block, Equation):
            self._write_equation(
                self._wrap(parent, container, "equation", default_wrap=container == "entry"),
                block,
            )
        elif isinstance(block, Bibliography):
            self._write_bibliography(parent, block)
        elif isinstance(block, QuestionSet):
            if parent.tag in ("section", "chapter", "appendix", "preface", "partintro"):
                self._write_question_set(parent, block)
            else:  # qandaset is not allowed here (DTD): the units follow in reading order
                self._write_nodes(parent, block.blocks(), container=container)
        elif isinstance(block, QandaSet):
            if parent.tag in ("section", "chapter", "appendix", "preface", "partintro"):
                self._write_qanda(parent, block)
            else:  # qandaset is not allowed here (DTD): an ordered list keeps the questions
                if block.title is not None:
                    self._write_block(parent, Para([block.title], "display_title"), container)
                self._write_list(
                    self._wrap(parent, container, "list"),
                    ListBlock("numbered", "decimal", block.items),
                )
        else:
            raise TypeError(type(block))

    # ------------------------------------------------------------------ lists

    def _write_list(self, parent, block: ListBlock):
        numbered = block.list_type in ("numbered", "lettered") or (
            block.marker_type in (self.p.get("lists.numeration") or {})
        )
        definition = block.list_type in ("definition", "glossary") and all(
            self.ctx.book.units.get(i.unit_id, {}).get("term") for i in block.items
        )
        if definition:
            el = etree.SubElement(parent, "variablelist")
            for item in block.items:
                self._marker_structure(item)
                entry = etree.SubElement(el, "varlistentry")
                term_range = self.ctx.book.units[item.unit_id]["term"]
                lead_marks = [m for m in item.parts if isinstance(m, PageMark)]
                ref = next(p for p in item.parts if isinstance(p, TextRef))
                self.pending += [
                    m for m in lead_marks if m.keep and item.parts.index(m) < item.parts.index(ref)
                ]
                term = etree.SubElement(entry, "term")
                self.render(term, [ref.slice(*term_range)], _all_kinds(), host=False)
                li = etree.SubElement(entry, "listitem")
                rest = ref.slice(term_range[1], ref.ranges[-1][1])
                para = etree.SubElement(li, "para")
                after = item.parts[item.parts.index(ref) + 1 :]
                self.render(para, [rest] + after, _all_kinds(), links=True)
                self._write_nodes(li, item.children, container="listitem")
            return
        if numbered:
            el = etree.SubElement(parent, "orderedlist")
            numeration = (self.p.get("lists.numeration") or {}).get(block.marker_type or "decimal")
            el.set("numeration", numeration or "arabic")
            if block.continues:
                el.set("continuation", "continues")
            elif block.start and block.start > 1:
                el.set("continuation", "restarts")
                el.set("role", str(block.start))
        else:
            el = etree.SubElement(parent, "itemizedlist")
            mark = self._mark(block)
            if mark:
                el.set("mark", mark)
        for item in block.items:
            self._marker_structure(item)
            li = etree.SubElement(el, "listitem")
            text_parts = [p for p in item.parts]
            if text_parts or not item.children:
                para = etree.SubElement(li, "para")
                self.render(para, text_parts, _all_kinds(), links=True)
            self._write_nodes(li, item.children, container="listitem")

    def _marker_structure(self, item: Item):
        if item.marker_ref is not None:
            return
        for uid in [item.unit_id] + item.merged_ids:
            addr = f"{uid}#marker"
            if addr in self.doc.records:
                self.ledger.structure(
                    addr,
                    self.doc.order[addr],
                    len(self.doc.records[addr]["text"]),
                    "list marker shown by list numbering/mark",
                )

    def _mark(self, block: ListBlock) -> str | None:
        if block.list_type == "unmarked" or not block.glyph:
            if block.glyph is None and block.list_type != "unmarked":
                return self.p.get("lists.default_mark")
            return self.p.get("lists.unmarked_mark")
        marks = self.p.get("lists.marks") or {}
        glyph = block.glyph.strip()
        if glyph in marks:
            return marks[glyph]
        # a letter, digit, fraction or control character is a symbol font's glyph decoded
        # as text: its shape is unknown, so the mark is a guess a person must check
        broken = not glyph or any(unicodedata.category(c)[0] in "LNC" for c in glyph)
        self.reviews.append(
            ReviewEntry(
                "list",
                f"{'broken bullet glyph' if broken else 'unknown bullet'} {glyph!r}: "
                f"mark {self.p.get('lists.default_mark')!r} (add it to lists.marks)",
                block.unit_ids[0],
                severity="must_check" if broken else None,
            )
        )
        return self.p.get("lists.default_mark")

    # ------------------------------------------------------------------ figures

    def _imagedata(self, parent, name: str, align: bool = True):
        io = etree.SubElement(parent, "imageobject")
        data = etree.SubElement(io, "imagedata")
        if align and self.p.get("figures.imagedata_align"):
            data.set("align", self.p.get("figures.imagedata_align"))
        data.set("fileref", fmt(self.p.get("delivery.fileref"), isbn=self.isbn, image=name))
        data.set("format", self.p.get("images.format_attribute"))

    def _alt(self, media, alt: dict | None, unit: dict, page: int | None):
        text = (alt or {}).get("text") or ""
        to = etree.SubElement(media, "textobject")
        phrase = etree.SubElement(to, "phrase")
        if text:
            phrase.text = text
        else:
            phrase.text = self.p.get("figures.alt_text_placeholder") or None
            self.alt_placeholders.append(unit.get("id"))
            self.reviews.append(
                ReviewEntry(
                    "alt_text", "alt text to supply (placeholder written)", unit.get("id"), page
                )
            )

    def _write_figure(self, parent, fig: Figure):
        name = self.image_of.get(id(fig))
        formal = fig.formal and fig.id
        el = etree.SubElement(parent, "figure" if formal else "informalfigure")
        if formal:
            el.set("id", fig.id)
            if fig.label:
                el.set("label", fig.label)
            title = etree.SubElement(el, "title")
            if fig.title_role:
                title.set("role", fig.title_role)
            if fig.label_ref is not None:
                self.ledger.attr(fig.label_ref, fig.label or "", "figure label")
            if not fig.continued:
                self.render(
                    title, fig.captions, tuple(self.p.get("inline.in_object_titles")), host=False
                )
            elif fig.captions:
                for ref in fig.captions:
                    self.ledger.attr(ref, "", "continued figure caption (item 13)")
        elif fig.captions:
            self.reviews.append(
                ReviewEntry(
                    "figure",
                    "caption on an informal figure kept as a para",
                    fig.unit["id"],
                    fig.page,
                )
            )
        media = etree.SubElement(el, "mediaobject")
        if name:
            self._imagedata(media, name)
        else:
            self.reviews.append(
                ReviewEntry("figure", "figure without an image file", fig.unit["id"], fig.page)
            )
        self._alt(media, fig.unit.get("alt_text"), fig.unit, fig.page)
        if fig.texts and self.p.get("figures.embedded_text") == "textobject":
            to = etree.SubElement(media, "textobject")
            to.set("role", "figuretext")
            for ref in fig.texts:
                if ref.is_blank():
                    continue
                para = etree.SubElement(to, "para")
                self.render(para, [ref], _all_kinds(), host=False)
        credits = list(fig.credits)
        if fig.texts and self.p.get("figures.embedded_text") == "caption":
            credits = fig.texts + credits
        if not formal and fig.captions:
            credits = fig.captions + credits
        if credits and self.p.get("figures.credits") == "caption":
            cap = etree.SubElement(media, "caption")
            for ref in credits:
                para = etree.SubElement(cap, "para")
                self.render(para, [ref], _all_kinds(), host=False)
        elif credits:
            for ref in credits:
                para = etree.SubElement(
                    parent if parent.tag != "para" else parent.getparent(), "para"
                )
                role = (self.p.get("paragraphs.roles") or {}).get("credit")
                if role:
                    para.set("role", role)
                self.render(para, [ref], _all_kinds())

    def _write_equation(self, parent, eq: Equation):
        if eq.content is not None and eq.unit.get("output") == "text":
            para = etree.SubElement(parent, "para")
            self.render(para, [eq.content], _all_kinds())
            return
        el = etree.SubElement(parent, "informalequation")
        media = etree.SubElement(el, "mediaobject")
        name = self.image_of.get(id(eq))
        if name:
            self._imagedata(media, name, align=False)
        alt = eq.unit.get("alt_text") or {}
        text = alt.get("text") or (
            eq.unit.get("latex") if self.p.get("equations.alt_from") == "alt_text_or_latex" else ""
        )
        to = etree.SubElement(media, "textobject")
        phrase = etree.SubElement(to, "phrase")
        phrase.text = text or self.p.get("figures.alt_text_placeholder") or None
        if not text:
            self.alt_placeholders.append(eq.unit["id"])
            self.reviews.append(
                ReviewEntry(
                    "alt_text",
                    "equation alt text to supply (placeholder written)",
                    eq.unit["id"],
                    eq.unit["pages"][0],
                )
            )
        if eq.unit.get("output") in ("mathml", "mathml_parts"):
            self.reviews.append(
                ReviewEntry(
                    "equation",
                    "MathML cannot be written in DocBook 4.2; image/LaTeX fallback used",
                    eq.unit["id"],
                    eq.unit["pages"][0],
                )
            )
        if eq.content is not None:
            cap = etree.SubElement(media, "caption")
            para = etree.SubElement(cap, "para")
            self.render(para, [eq.content], _all_kinds(), host=False)

    # ------------------------------------------------------------------ tables

    def _write_table(self, parent, tbl: Table):
        formal = tbl.id is not None
        el = etree.SubElement(parent, "table" if formal else "informaltable")
        if formal:
            el.set("id", tbl.id)
            if tbl.label:
                el.set("label", tbl.label)
        el.set("frame", self.p.get("tables.frame"))
        if formal:
            title = etree.SubElement(el, "title")
            if tbl.title_role:
                title.set("role", tbl.title_role)
            if tbl.label_ref is not None:
                self.ledger.attr(tbl.label_ref, tbl.label or "", "table label")
            if tbl.title is not None:
                self.render(
                    title, [tbl.title], tuple(self.p.get("inline.in_object_titles")), host=False
                )
        cols = max(tbl.columns, 1)
        tgroup = etree.SubElement(el, "tgroup")
        tgroup.set("cols", str(cols))
        for c in range(1, cols + 1):
            spec = etree.SubElement(tgroup, "colspec")
            spec.set("colnum", str(c))
            spec.set("colname", str(c))
        rows = tbl.rows
        header = min(tbl.header_rows, len(rows))
        if header == len(rows) and rows:
            header -= 1
        notes_rows = self.p.get("tables.notes") == "spanning_row" and tbl.notes
        if header:
            thead = etree.SubElement(tgroup, "thead")
            for row in rows[:header]:
                self._write_row(thead, row, cols, header=True)
        tbody = etree.SubElement(tgroup, "tbody")
        for row in rows[header:]:
            self._write_row(tbody, row, cols, header=False)
        if notes_rows:
            for ref in tbl.notes:
                row = etree.SubElement(tbody, "row")
                entry = etree.SubElement(row, "entry")
                if self.p.get("tables.align"):
                    entry.set("align", self.p.get("tables.align"))
                if self.p.get("tables.body_valign"):
                    entry.set("valign", self.p.get("tables.body_valign"))
                entry.set("namest", "1")
                entry.set("nameend", str(cols))
                para = etree.SubElement(entry, "para")
                if self.p.get("tables.note_role"):
                    para.set("role", self.p.get("tables.note_role"))
                self.render(para, [ref], _all_kinds(), links=True)
        if not len(tbody):
            row = etree.SubElement(tbody, "row")
            etree.SubElement(row, "entry")
        if tbl.notes and not notes_rows:
            for ref in tbl.notes:
                container = parent.getparent() if parent.tag == "para" else parent
                para = etree.SubElement(container, "para")
                if self.p.get("tables.note_role"):
                    para.set("role", self.p.get("tables.note_role"))
                self.render(para, [ref], _all_kinds(), links=True)
        self.pending += [m for m in tbl.trailing_marks if m.keep]

    def _write_row(self, parent, cells: list[dict], cols: int, header: bool):
        row = etree.SubElement(parent, "row")
        for cell in cells:
            entry = etree.SubElement(row, "entry")
            start = cell["column"] + 1
            span = cell.get("column_span", 1)
            if span > 1:
                entry.set("namest", str(start))
                entry.set("nameend", str(min(start + span - 1, cols)))
            else:
                entry.set("colname", str(start))
            if cell.get("row_span", 1) > 1:
                entry.set("morerows", str(cell["row_span"] - 1))
            if self.p.get("tables.align"):
                entry.set("align", self.p.get("tables.align"))
            valign = self.p.get("tables.header_valign" if header else "tables.body_valign")
            if valign:
                entry.set("valign", valign)
            blocks = self._cell_blocks(cell)
            self._write_nodes(entry, blocks, container="entry")
            if self.pending and len(entry):
                pass
        if not len(row):
            etree.SubElement(row, "entry")
            self.reviews.append(ReviewEntry("table", "row without cells (covered by spans)"))

    def _cell_blocks(self, cell: dict) -> list:
        return self._table_cells_lookup().get(cell["id"], [])

    def _table_cells_lookup(self) -> dict:
        if not hasattr(self, "_cells"):
            self._cells = {}
            for node in _iter_doc_blocks(self.doc):
                if isinstance(node, Table):
                    self._cells.update(node.cells_blocks)
        return self._cells

    # ------------------------------------------------------------------ sidebars, bibliography

    def _write_sidebar(self, parent, side: Sidebar):
        el = etree.SubElement(parent, "sidebar")
        if side.id:
            el.set("id", side.id)
            if side.label:
                el.set("label", side.label)
        if side.title is not None:
            title = etree.SubElement(el, "title")
            if side.title_role:
                title.set("role", side.title_role)
            if side.label_ref is not None:
                self.ledger.attr(side.label_ref, side.label or "", "box label")
            self.render(
                title, [side.title], tuple(self.p.get("inline.in_object_titles")), host=False
            )
        self._write_nodes(el, _flatten_sections(side.children), container="sidebar")
        if not [c for c in el if c.tag != "title"]:
            para = etree.SubElement(el, "para")
            if self.pending:
                for mark in self.pending:
                    self._anchor(para, mark)
                self.pending = []

    def _write_bibliography(self, parent, bib: Bibliography):
        el = etree.SubElement(parent, "bibliography")
        if getattr(bib, "id", None):
            el.set("id", bib.id)
        if bib.title is not None:
            title = etree.SubElement(el, "title")
            self.render(title, [bib.title], tuple(self.p.get("inline.in_titles")), host=False)
        self._write_nodes(el, bib.lead, container="bibliography")
        self._write_bib_entries(el, bib)

    def _write_bib_entries(self, el, bib: Bibliography):
        marker_el = self.p.get("bibliography.marker_element")
        for entry in bib.entries:
            mixed = etree.SubElement(el, self.p.get("bibliography.entry_element"))
            if entry.id:
                mixed.set("id", entry.id)
            if entry.marker_ref is not None and marker_el:
                abbrev = etree.SubElement(mixed, marker_el)
                self.render(abbrev, [entry.marker_ref], (), host=False)
                abbrev.tail = " "
            elif entry.marker_ref is not None:
                entry.parts.insert(0, entry.marker_ref)
            misc = etree.SubElement(mixed, self.p.get("bibliography.entry_text_element"))
            self.render(misc, entry.parts, _all_kinds(), links="web")

    def _write_question_set(self, parent, qs: QuestionSet):
        """Item 22: qandaset / qandadiv / qandaentry / question (the stem as a para, then the
        options as an orderedlist numeration="loweralpha") / answer (the key line and the
        explanation). The printed question number is the entry's role."""
        el = etree.SubElement(parent, "qandaset")
        div = etree.SubElement(el, "qandadiv")
        for entry in qs.entries:
            node = etree.SubElement(div, "qandaentry")
            if entry.number is not None:
                node.set("role", str(entry.number))
            question = etree.SubElement(node, "question")
            blocks = list(entry.question)
            first = blocks[0] if blocks else None
            if isinstance(first, ListBlock) and len(first.items) == 1:
                item = first.items[0]
                self._marker_structure(item)
                para = etree.SubElement(question, "para")
                self.render(para, item.parts, _all_kinds(), links=True)
                self._write_nodes(question, item.children, container="question")
                blocks = blocks[1:]
            self._write_nodes(question, blocks, container="question")
            if entry.answer:
                answer = etree.SubElement(node, "answer")
                self._write_nodes(answer, entry.answer, container="answer")

    def _write_qanda(self, parent, qs: QandaSet):
        el = etree.SubElement(parent, "qandaset")
        div = etree.SubElement(el, "qandadiv")
        if qs.title is not None:
            title = etree.SubElement(div, "title")
            self.render(title, [qs.title], tuple(self.p.get("inline.in_titles")), host=False)
        for item in qs.items:
            self._marker_structure(item)
            entry = etree.SubElement(div, "qandaentry")
            question = etree.SubElement(entry, "question")
            para = etree.SubElement(question, "para")
            self.render(para, item.parts, _all_kinds(), links=True)
            self._write_nodes(question, item.children, container="listitem")

    # ------------------------------------------------------------------ index

    def _write_index(self, el, division: Division):
        link = self.p.get("index.link")
        suffix = re.compile(self.p.get("index.suffix_in_link"))
        divs = division.index_divs
        mode = self.p.get("index.divs")
        if mode != "none" and not any(d.title for d in divs):
            divs = _divs_by_letter(divs) if mode in ("by_first_letter", "from_dividers") else divs
        elif mode != "none":  # entries before the first printed divider get a letter div
            fixed = []
            for div in divs:
                if div.title is None and div.entries:
                    fixed += [d for d in _divs_by_letter([div]) if d.entries or d.lead]
                else:
                    fixed.append(div)
            divs = fixed
        divs = _carry_empty_divs(divs)
        lead_written = False
        for div in divs:
            if div.lead and not div.entries and div.title is None and div.title_text is None:
                self._write_nodes(el, _unwrap_sidebars(div.lead), container="index")
                lead_written = True
                continue
            target = el
            if mode != "none" and (div.title is not None or div.title_text):
                target = etree.SubElement(el, "indexdiv")
                title = etree.SubElement(target, "title")
                if div.title is not None:
                    self.render(title, [div.title], (), host=False)
                else:
                    title.text = div.title_text
                    self.ledger.other("generated", div.title_text, title, "index letter")
            if div.lead:
                self._write_nodes(target, _unwrap_sidebars(div.lead), container="index")
            current = None
            for entry in div.entries:
                level = entry.level or 1
                if level <= 1 or current is None:
                    if level > 1:
                        self.reviews.append(
                            ReviewEntry(
                                "index",
                                "sub-entry without a main entry written as a main entry",
                                entry.item.unit_id,
                            )
                        )
                    current = etree.SubElement(target, "indexentry")
                    tag = "primaryie"
                else:
                    tag = "secondaryie" if level == 2 else "tertiaryie"
                    if tag == "tertiaryie" and current.find("secondaryie") is None:
                        tag = "secondaryie"  # DTD: a tertiary entry follows a secondary one
                        self.reviews.append(
                            ReviewEntry(
                                "index",
                                "level-3 entry without a level-2 entry written as level 2",
                                entry.item.unit_id,
                            )
                        )
                ie = etree.SubElement(current, tag)
                self._render_index_item(ie, entry.item, link, suffix)
        _ = lead_written
        if not [c for c in el if c.tag not in ("title",)]:
            etree.SubElement(el, "para")

    def _render_index_item(self, el, item: Item, link: str, suffix):
        links = []
        extra = {}
        for part in item.parts:
            if not isinstance(part, TextRef):
                continue
            ranges = []
            for loc in item.locators:
                if loc["kind"] == "cross_reference":
                    continue
                start, end = loc["start"], loc["end"]
                ranges.append((start, end))
                m = suffix.match(part.text[end:])
                if m:
                    end += m.end()
                page = loc.get("target_page")
                anchor = self.anchor_of_page.get(page) if page else None
                end_anchor = self.anchor_of_page.get(loc.get("end_target_page") or -1)
                dash = re.search(r"\s*[-–‐]\s*", part.text[start:end])
                if (
                    anchor
                    and end_anchor
                    and dash
                    and loc["kind"] == "range"
                    and self.p.get("index.range_links") == "both_ends"
                ):  # "43–46": each page number links to its own page, the dash between
                    links.append((start, start + dash.start(), fmt(link, anchor=anchor)))
                    links.append((start + dash.end(), end, fmt(link, anchor=end_anchor)))
                elif anchor:
                    links.append((start, end, fmt(link, anchor=anchor)))
                else:
                    self.reviews.append(
                        ReviewEntry(
                            "index",
                            f"locator {part.text[loc['start'] : loc['end']]!r}"
                            " has no resolved page",
                            item.unit_id,
                        )
                    )
            extra[part.addr] = {"index_entry": True, "locator_ranges": ranges}
        if self.pending:
            for mark in self.pending:
                self._anchor(el, mark)
            self.pending = []
        self._index_links = links
        parts = item.parts
        self._render_with_links(el, parts, links, extra)

    def _render_with_links(self, el, parts, links, extra):
        saved = self._links
        self._links = lambda ref, text, which=True: list(links)  # type: ignore[assignment]
        try:
            self.render(el, parts, _all_kinds(), links=True, extra=extra)
        finally:
            self._links = saved  # type: ignore[assignment]

    # ------------------------------------------------------------------ packaging

    def _first_last_roles(self):
        """role first/last on the first and last page anchors written in each part (title and
        intro) and chapter, in document order; division page ranges follow them."""
        page_of = {v: k for k, v in self.anchor_of_page.items()}
        for division, el, _part in self.chapter_els:
            self._roles_in(el, [a for a in el.iter("anchor")], division, page_of)
        for el in self.book_el.iter("part"):
            own = [
                a
                for a in el.iter("anchor")
                if not any(x.tag == "chapter" for x in a.iterancestors())
            ]
            self._roles_in(el, own, None, page_of)

    def _roles_in(self, el, anchors, division, page_of):
        if not self.p.get("anchors.first_last_roles") or not anchors:
            return
        for a in anchors:
            if "role" in a.attrib:
                del a.attrib["role"]
        anchors[0].set("role", "first")
        if len(anchors) > 1:
            anchors[-1].set("role", "last")
        if division is not None:
            division.first_page = page_of.get(anchors[0].get("id"))
            division.last_page = page_of.get(anchors[-1].get("id"))

    def _package(self, book) -> Delivery:
        p = self.p
        self._first_last_roles()
        root = fmt(p.get("delivery.root_folder"), isbn=self.isbn)
        delivery = Delivery(root=root, ledger=self.ledger, reviews=self.reviews)
        ser = self._serializer()
        main = fmt(p.get("delivery.main_file"), isbn=self.isbn)
        delivery.files[main] = self._document(
            ser, book, p.get("delivery.main_declaration"), p.get("delivery.main_doctype"), "book"
        )
        delivery.main_file = main
        folder = p.get("delivery.chapters_folder")
        chapters = []
        for division, el, part in self.chapter_els:
            if division.kind != "chapter":
                continue
            chapters.append((division, el, part))
        if p.get("delivery.split_files"):
            decl = p.get("delivery.split_declaration")
            doctype = p.get("delivery.split_doctype")
            front = p.get("delivery.front_file")
            if front:
                fb = etree.Element("book")
                for child in book:
                    if child.tag in ("bookinfo", "preface", "dedication") or (
                        child.tag == "appendix" and child in self._front_division_els()
                    ):
                        fb.append(copy.deepcopy(child))
                path = f"{folder}/{front}"
                delivery.files[path] = self._document(ser, fb, decl, doctype, "book")
                delivery.split_files[path] = "front"
            first_in_part: set[int] = set()
            seen_parts: set[int] = set()
            for division, _el, part in chapters:
                if part is not None and id(part) not in seen_parts:
                    seen_parts.add(id(part))
                    first_in_part.add(id(division))
            for division, el, _part in chapters:
                name = fmt(p.get("delivery.chapter_file"), chapter_id=division.id)
                path = f"{folder}/{name}"
                if p.get("delivery.part_files") and id(division) in first_in_part:
                    part_el = el.getparent()
                    wrapper = etree.Element("part", dict(part_el.attrib))
                    for child in part_el:
                        if child.tag in ("title", "partintro"):
                            wrapper.append(copy.deepcopy(child))
                    wrapper.append(copy.deepcopy(el))
                    delivery.files[path] = self._document(ser, wrapper, decl, doctype, "part")
                else:
                    delivery.files[path] = self._document(
                        ser, copy.deepcopy(el), decl, doctype, "chapter"
                    )
                delivery.split_files[path] = division.id
            index_file = p.get("delivery.index_file")
            if index_file and self.index_el is not None:
                path = f"{folder}/{index_file}"
                delivery.files[path] = self._document(
                    ser, copy.deepcopy(self.index_el), decl, doctype, "index"
                )
                delivery.split_files[path] = "index"
        info = p.get("delivery.page_info.file")
        rows = []
        for division, _el, _part in chapters:
            first = (
                self.ctx.book.pages[division.first_page - 1]["label"] if division.first_page else ""
            )
            last = (
                self.ctx.book.pages[division.last_page - 1]["label"] if division.last_page else ""
            )
            rows.append(
                {
                    "id": division.id,
                    "first": first,
                    "last": last,
                    "first_page": division.first_page,
                    "last_page": division.last_page,
                }
            )
        delivery.divisions = rows
        if info:
            lines = ["<page-info>"]
            for row in rows:
                lines += [
                    "<ch>",
                    f"\t<chnumber>{row['id']}</chnumber>",
                    f"\t<firstpage>{row['first'] or ''}</firstpage>",
                    f"\t<lastpage>{row['last'] or ''}</lastpage>",
                    "</ch>",
                ]
            lines.append("</page-info>")
            delivery.files[info] = ("\n".join(lines) + "\n").encode("utf-8")
        delivery.images = self.images
        delivery.anchors = self.anchor_of_page
        delivery.alt_placeholders = self.alt_placeholders
        return delivery

    def _front_division_els(self):
        return []

    def _serializer(self) -> Serializer:
        chars = self.p.get("characters")
        return Serializer(
            chars["escape"], chars["attribute_escape"], chars["non_ascii"], BLOCK, COMPACT
        )

    def _document(self, ser: Serializer, el, declaration: bool, doctype: str, root: str) -> bytes:
        out = []
        if declaration:
            out.append('<?xml version="1.0" encoding="UTF-8"?>\n')
        dtd = self.p.get("dtd")
        line = f'<!DOCTYPE {root} PUBLIC "{dtd["public_id"]}" "{dtd["system_id"]}">'
        if doctype == "active":
            out.append(line + "\n")
        elif doctype == "commented":
            out.append(f"<!--{line}-->\n")
        out.append(ser.element(el))
        out.append("\n")
        return "".join(out).encode("utf-8")


# ---------------------------------------------------------------------- helpers


def _all_kinds() -> tuple:
    return (
        "bold",
        "italic",
        "bold_italic",
        "superscript",
        "subscript",
        "small_caps",
        "underline",
        "link",
    )


def _int(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def _is_ancestor(el, node) -> bool:
    while node is not None:
        if node is el:
            return True
        node = node.getparent()
    return False


def _unwrap_sidebars(nodes: list) -> list:
    out = []
    for node in nodes:
        if isinstance(node, Sidebar):
            if node.title is not None:
                out.append(Para([node.title], "display_title"))
            out += _unwrap_sidebars(_flatten_sections(node.children))
        elif isinstance(node, Section):
            out += _unwrap_sidebars(_flatten_sections([node]))
        else:
            out.append(node)
    return out


def _flatten_sections(nodes: list) -> list:
    out = []
    for node in nodes:
        if isinstance(node, Section):
            if node.title is not None:
                out.append(Para([node.title], "display_title"))
            out += _flatten_sections(node.children)
        else:
            out.append(node)
    return out


def _hoist_bibliographies(division: Division):
    """DocBook puts a bibliography after all sections of a chapter: move every chapter
    bibliography found inside sections to the chapter end (a declared move when anything
    followed it)."""
    found: list[Bibliography] = []

    def strip(nodes: list) -> list:
        out = []
        for node in nodes:
            if isinstance(node, Bibliography):
                found.append(node)
                continue
            if isinstance(node, Section):
                node.children = strip(node.children)
            out.append(node)
        return out

    flat = list(_iter_nodes(division.children))
    last_content = [n for n in flat if not isinstance(n, PageMark)]
    division.children = strip(division.children)
    if not found:
        return
    tail = last_content[-1] if last_content else None
    for bib in found:
        if bib is not tail and not _is_last_with_entries(bib, tail):
            from ..rules.structure import _declare_move

            _declare_move(bib, "bibliography placed at the chapter end (DocBook)")
    division.children += found


def _is_last_with_entries(bib, tail) -> bool:
    return tail is not None and any(tail is e for e in bib.entries)


def _carry_empty_divs(divs: list[IndexDiv]) -> list[IndexDiv]:
    """An index div without entries (DTD: indexdiv needs entries) passes its title and text
    to the next div's lead; at the end they go before the first div (a declared move)."""
    out: list[IndexDiv] = []
    carry: list = []
    for div in divs:
        if not out and not carry and not div.entries and div.title is None and div.lead:
            out.append(div)  # text before the first letter (the index note) stays there
            continue
        if not div.entries:
            if div.title is not None:
                carry.append(Para([div.title], "label"))
            carry += div.lead
            continue
        if carry:
            from ..rules.structure import _declare_move

            _declare_move(carry, "index text without entries placed before the next letter")
        div.lead = carry + div.lead
        carry = []
        out.append(div)
    if carry:
        from ..rules.structure import _declare_move

        _declare_move(carry, "index text without entries placed at the index start")
        out.insert(0, IndexDiv(None, None, [], carry))
    return out


def _divs_by_letter(divs: list[IndexDiv]) -> list[IndexDiv]:
    """Group index entries by the first letter of main entries (generated letter titles).
    A group's own text (a second index's title) stays before its entries."""
    out: list[IndexDiv] = []
    for div in divs:
        if div.lead:
            out.append(IndexDiv(None, None, [], list(div.lead)))
        last = None
        for entry in div.entries:
            letter = None
            if (entry.level or 1) <= 1:
                text = "".join(p.plain() for p in entry.item.parts if isinstance(p, TextRef))
                first = next((c for c in text if c.isalnum()), "#")
                letter = first.upper() if first.isalpha() else "#"
            if letter and (last is None or last.title_text != letter):
                last = IndexDiv(None, letter, [])
                out.append(last)
            if last is None:
                last = IndexDiv(None, "#", [])
                out.append(last)
            last.entries.append(entry)
    return out


def _iter_nodes(nodes):
    for node in nodes:
        yield node
        if isinstance(node, Section):
            yield from _iter_nodes(node.children)
        elif isinstance(node, Sidebar):
            yield from _iter_nodes(node.children)
        elif isinstance(node, Bibliography):
            yield from _iter_nodes(node.lead)
            yield from node.entries
        elif isinstance(node, (ListBlock, QandaSet)):
            for item in node.items:
                yield from _iter_nodes(item.children)
        elif isinstance(node, QuestionSet):
            yield from _iter_nodes(node.blocks())
        elif isinstance(node, Table):
            for blocks in node.cells_blocks.values():
                yield from _iter_nodes(blocks)


def _divisions(doc: Document):
    for division in doc.front:
        yield division
    for division in doc.body:
        yield division
        for child in division.children:
            if isinstance(child, Division):
                yield child
    for division in doc.back:
        yield division
    for division in doc.after:
        yield division
        for child in division.children:
            if isinstance(child, Division):
                yield child


def _iter_doc_blocks(doc: Document):
    """Blocks in writing order (for image naming): bookinfo, front, body, back."""
    yield from _iter_nodes(doc.bookinfo.legal)
    yield from _iter_nodes(doc.bookinfo.legal_after)
    for division in doc.front:
        yield from _iter_nodes(division.intro + division.children)
    for divisions in (doc.body, doc.back, doc.after):
        for division in divisions:
            yield from _iter_nodes(division.intro)
            for child in division.children:
                if isinstance(child, Division):
                    yield from _iter_nodes(child.intro + child.children)
                else:
                    yield from _iter_nodes([child])
            for div in division.index_divs:
                yield from _iter_nodes(div.lead)


def _walk_marks(doc: Document):
    def walk(node):
        if isinstance(node, PageMark):
            yield node
        elif isinstance(node, list):
            for n in node:
                yield from walk(n)
        elif isinstance(node, (TextRef, str, int, dict)) or node is None:
            return
        elif hasattr(node, "__dataclass_fields__"):
            for name in node.__dataclass_fields__:
                value = getattr(node, name)
                if name == "cells_blocks":
                    for blocks in value.values():
                        yield from walk(blocks)
                elif isinstance(value, (list, PageMark)) or hasattr(value, "__dataclass_fields__"):
                    yield from walk(value)

    yield from walk(doc.bookinfo)
    for division in doc.front + doc.body + doc.back + doc.after:
        yield from walk(division)


_ = (BibEntry, Item)
