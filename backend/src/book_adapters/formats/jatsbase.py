"""Mapping shared by JATS and BITS (BITS is a JATS extension): inline, paragraphs, lists,
figures, tables, boxed text, equations, references, notes, cross-references.

JATS allows paragraph-level content in a ``sec`` only before its nested ``sec`` children, and
reference lists / footnote groups only after them. Source text keeps its order, so content
that comes after a nested section goes into a continuation ``sec`` (empty ``title``,
``specific-use="continued"``), and every one is listed for review."""

from __future__ import annotations

from lxml import etree

from .convert import NUMERATION, Converter
from .markup import text_of
from .refparse import normalize, parse_reference
from .source import Source

XLINK = "http://www.w3.org/1999/xlink"
MML = "http://www.w3.org/1998/Math/MathML"
PREFIXES = {XLINK: "xlink", MML: "mml"}
LIST_TYPES = {
    "1": "order",
    "a": "alpha-lower",
    "A": "alpha-upper",
    "i": "roman-lower",
    "I": "roman-upper",
}
REF_TYPES = {
    "figure": "fig", "informalfigure": "fig", "table": "table", "informaltable": "table",
    "bibliomixed": "bibr", "section": "sec", "chapter": "sec", "part": "sec", "appendix": "app",
    "sidebar": "boxed-text", "preface": "sec", "anchor": "other",
}  # fmt: skip
BLOCK = frozenset(
    {"article", "front", "article-meta", "journal-meta", "title-group", "contrib-group", "contrib",
     "aff", "body", "back", "sec", "list", "list-item", "def-list", "def-item", "fig", "table-wrap",
     "table", "thead", "tbody", "tr", "ref-list", "ref", "boxed-text", "caption", "graphic",
     "disp-formula", "fn-group", "fn", "app-group", "app", "alternatives", "custom-meta-group",
     "custom-meta", "book", "book-meta", "book-title-group", "front-matter", "front-matter-part",
     "book-body", "book-part", "book-part-meta", "book-back", "index", "index-entry", "index-group",
     "nav-pointer-group", "publisher", "pub-date", "journal-title-group", "def", "term-head"}
)  # fmt: skip
INLINE = frozenset(
    {"bold", "italic", "sc", "underline", "sup", "sub", "xref", "ext-link", "target",
     "named-content",
     "string-name", "given-names", "surname", "degrees", "role", "institution", "addr-line", "city",
     "state", "country", "math", "inline-formula", "alt-text", "label", "nav-pointer", "mml:math"}
)  # fmt: skip


class JatsBase(Converter):
    markers_between_refs = False  # BITS lets a paragraph (the page marker) stand between references

    def __init__(self, src: Source, cfg: dict):
        super().__init__(src, cfg)
        self.pages = {p.id: p for p in src.pages()}
        self.page_list: list = []
        self.kinds = {
            e.get("id"): REF_TYPES.get(e.tag, "other") for e in src.tree.iter() if e.get("id")
        }
        self.notes = 0
        self.refs_total = 0
        self.refs_structured = 0
        self.continued = 0
        self.math_used = False
        self.xlink = False

    # ------------------------------------------------------------------ inline

    def inline_chain(self, ch):
        tag = ch.tag
        if tag == "emphasis":
            role = ch.get("role")
            if role == "bold":
                return [("bold", {})]
            if role == "bolditalic":
                return [("bold", {}), ("italic", {})]
            if role == "smallcaps":
                return [("sc", {})]
            if role == "underline":
                return [("underline", {})]
            return [("italic", {})]
        if tag in ("superscript", "subscript"):
            return [("sup" if tag == "superscript" else "sub", {})]
        return [("named-content", {"content-type": tag})]

    def inline_special(self, ch, dst) -> bool:
        if ch.tag == "anchor":
            page = self.pages.get(ch.get("id"))
            if page is not None:
                etree.SubElement(dst, "target", {"id": page.id, "target-type": "page-break"})
                self.page_list.append(page)
            return True
        if ch.tag == "ulink":
            url = ch.get("url") or ""
            if url.startswith("#"):
                if url[1:] not in self.src.ids:
                    self.broken_links += 1
                    self.broken_examples.append(url[1:])
                    self.inline_into(ch, dst)
                    return True
                home = getattr(self, "article_ids", {}).get(url[1:])
                if home is not None and home != getattr(self, "current_key", home):
                    self.xlink = True  # the target is in another article: a link to its file
                    name = self.cfg["files"]["per_article"].format(
                        isbn=self.src.isbn() or "ISBN_TO_SUPPLY", key=home
                    )
                    a = etree.SubElement(
                        dst,
                        "ext-link",
                        {"ext-link-type": "uri", f"{{{XLINK}}}href": f"{name}{url}"},
                    )
                    self.inline_into(ch, a)
                    return True
                x = etree.SubElement(
                    dst, "xref", {"rid": url[1:], "ref-type": self.kinds.get(url[1:], "other")}
                )
                self.inline_into(ch, x)
                return True
            self.xlink = True
            kind = "email" if url.startswith("mailto:") else "uri"
            a = etree.SubElement(dst, "ext-link", {"ext-link-type": kind, f"{{{XLINK}}}href": url})
            self.inline_into(ch, a)
            return True
        return False

    def label(self, parent, label):
        if label and label.strip():
            node = etree.SubElement(parent, "label")
            node.text = label
            return node
        return None

    def title(self, parent, src, tag="title"):
        node = etree.SubElement(parent, tag)
        self.inline_into(src, node)
        return node

    # ------------------------------------------------------------------ slots in a sec

    def slot(self, parent, kind: str):
        """The element a paragraph-level (``para``), section (``sec``) or back-matter
        (``back``) child goes into, keeping JATS's order: para-level, sec, back."""
        if parent.tag not in ("sec", "body", "app", "ack"):
            return parent
        tags = [c.tag for c in parent]
        has_sec = "sec" in tags
        has_back = any(t in ("ref-list", "fn-group", "glossary", "notes") for t in tags)
        if kind == "para" and (has_sec or has_back):
            last = parent[-1]
            if last.tag == "sec" and last.get("specific-use") == "continued" and not has_back:
                return last
            if has_back and last.tag == "sec" and last.get("specific-use") == "continued":
                return last
            self.continued += 1
            sec = etree.SubElement(parent, "sec", {"specific-use": "continued"})
            etree.SubElement(sec, "title")
            return sec
        if kind == "sec" and has_back:
            self.continued += 1
            sec = etree.SubElement(parent, "sec", {"specific-use": "continued"})
            etree.SubElement(sec, "title")
            return sec
        return parent

    # ------------------------------------------------------------------ blocks

    def b_para(self, el, parent):
        kind = el.get("x-kind")
        for run in self.segments(el):
            if run[0] == "block":
                self.block(run[1], parent)
                continue
            if not self.has_text(run[1]) and len(run[1]) == 0:
                continue
            target = self.slot(parent, "para")
            if kind == "footnote":
                self.notes += 1
                box = etree.SubElement(target, "boxed-text", {"content-type": "footnote"})
                p = etree.SubElement(box, "p")
                self.inline_run_into(run[1], p)
                continue
            attrs = {}
            cls = {"caption": "caption", "credit": "credit"}.get(kind) or el.get("role")
            if cls:
                attrs["content-type"] = cls
            p = etree.SubElement(target, "p", attrs)
            self.inline_run_into(run[1], p)

    def b_itemizedlist(self, el, parent):
        lst = etree.SubElement(self.slot(parent, "para"), "list", {"list-type": "bullet"})
        self.items(el, lst)

    def b_orderedlist(self, el, parent):
        num = NUMERATION.get(el.get("numeration") or "arabic", "1")
        lst = etree.SubElement(self.slot(parent, "para"), "list", {"list-type": LIST_TYPES[num]})
        self.items(el, lst)

    def items(self, el, lst):
        for li_src in el.findall("listitem"):
            li = etree.SubElement(lst, "list-item")
            self.item_content(li_src, li)
            if not len(li):
                etree.SubElement(li, "p")

    def item_content(self, src, li):
        """list-item content is paragraph-level: text goes in a p, lists beside it."""
        kids = list(src)
        if (
            len(kids) == 1
            and kids[0].tag == "para"
            and not any(c.tag in self.block_tags() for c in kids[0])
        ):
            p = etree.SubElement(li, "p")
            self.inline_into(kids[0], p)
            return
        for ch in kids:
            self.block(ch, li)
        self.wrap_blocks(li)

    @staticmethod
    def wrap_blocks(li):
        """A list item holds p, list and def-list only: other blocks (figure, table, box,
        formula) go inside a p, which accepts them."""
        for child in list(li):
            if child.tag not in ("p", "list", "def-list", "label", "title"):
                p = etree.Element("p")
                child.addprevious(p)
                p.append(child)
                p.tail = child.tail
                child.tail = None

    @staticmethod
    def block_tags():
        from .convert import BLOCK_CHILDREN

        return BLOCK_CHILDREN

    def b_variablelist(self, el, parent):
        dl = etree.SubElement(self.slot(parent, "para"), "def-list")
        for entry in el.findall("varlistentry"):
            item = etree.SubElement(dl, "def-item")
            term = etree.SubElement(item, "term")
            t = entry.find("term")
            if t is not None:
                self.inline_into(t, term)
            d = etree.SubElement(item, "def")
            li = entry.find("listitem")
            if li is not None:
                self.item_content(li, d)
            if not len(d):
                etree.SubElement(d, "p")

    def b_sidebar(self, el, parent):
        attrs = {"id": el.get("id")} if el.get("id") else {}
        box = etree.SubElement(self.slot(parent, "para"), "boxed-text", attrs)
        self.label(box, el.get("label"))
        title = el.find("title")
        if title is not None and (title.text or len(title)):
            cap = etree.SubElement(box, "caption")
            self.title(cap, title)
        self.blocks(el, box)
        if not [c for c in box if c.tag in ("p", "list", "table-wrap", "fig", "boxed-text")]:
            etree.SubElement(box, "p")

    def block(self, el, parent) -> None:
        """An element with no mapping never loses its text: it is kept in a paragraph and the
        element goes on the review list."""
        if getattr(self, f"b_{el.tag}", None) is None:
            text = " ".join("".join(el.itertext()).split())
            if text:
                self.review("structure", f"element <{el.tag}> has no mapping: its text is kept "
                                         "in a paragraph")  # fmt: skip
                etree.SubElement(self.slot(parent, "para"), "p").text = text
                return
        super().block(el, parent)

    def b_blockquote(self, el, parent):
        """DocBook writes three things as a blockquote: a quotation (role quote), a pull quote
        (role pullquote), a box inside a question, an answer or a legal notice (role box) and a
        table inside a legal notice (role table). None is dropped: a quotation is a
        ``disp-quote`` (a pull quote says so in ``specific-use="pull"``; an attribution becomes
        ``attrib``), a box is ``boxed-text`` and a table stands where its blockquote stood."""
        role = el.get("role")
        if role == "table":
            self.blocks(el, parent)
            return
        if role == "box":
            self.b_sidebar(el, parent)
            return
        attrs = {"id": el.get("id")} if el.get("id") else {}
        if role == "pullquote":
            attrs["specific-use"] = "pull"
        quote = etree.SubElement(self.slot(parent, "para"), "disp-quote", attrs)
        label = el.get("xreflabel") or el.get("label")
        if label:
            self.label(quote, label)
        title = el.find("title")
        if title is not None and (title.text or len(title)):
            self.title(quote, title)
        self.blocks(el, quote, skip=("title", "attribution"))
        if not [c for c in quote if c.tag not in ("label", "title")]:
            etree.SubElement(quote, "p")
        for attribution in el.findall("attribution"):
            self.inline_into(attribution, etree.SubElement(quote, "attrib"))

    def b_figure(self, el, parent):
        media = el.find("mediaobject")
        info = self.src.media(media) if media is not None else None
        attrs = {"id": el.get("id")} if el.get("id") else {}
        fig = etree.SubElement(self.slot(parent, "para"), "fig", attrs)
        self.label(fig, el.get("label"))
        title = el.find("title")
        if title is not None and (title.text or len(title)):
            cap = etree.SubElement(fig, "caption")
            self.title(cap, title)
        if info is not None and info.image:
            self.xlink = True
            g = etree.SubElement(
                fig, "graphic", {f"{{{XLINK}}}href": f"{self.cfg['images_folder']}/{info.image}"}
            )
            alt = etree.SubElement(g, "alt-text")
            alt.text = info.alt
        else:
            self.review("figure", "figure without an image file")
        if info is not None:
            for para in info.figure_text:
                p = etree.SubElement(fig, "p", {"content-type": "figure-text"})
                self.inline_into(para, p)
            for para in info.caption:
                a = etree.SubElement(fig, "attrib")
                self.inline_into(para, a)

    b_informalfigure = b_figure

    def b_mediaobject(self, el, parent):
        wrapper = etree.Element("informalfigure")
        wrapper.append(el)
        self.b_figure(wrapper, parent)

    def b_informalequation(self, el, parent):
        from .dtbook import _to_namespaced

        target = self.slot(parent, "para")
        math = self.src.mathml(el)
        if math is not None and self.cfg["math"]["mathml"]:
            self.math_used = True
            f = etree.SubElement(target, "disp-formula")
            node = _to_namespaced(math, MML)
            latex = self.src.latex(el)
            if latex:
                node.set("alttext", latex)
            label = self.src.unit(el.get("x-unit")).get("label")
            media = el.find("mediaobject")
            info = self.src.media(media) if media is not None else None
            if label:
                self.label(f, label)
            if info is not None and info.caption:
                # the equation's own printed characters (text-set math): kept as its source
                # text (number included, so the order of the words is the source order), beside the MathML
                text = " ".join(" ".join("".join(p.itertext()).split()) for p in info.caption)
                if text:
                    alt = etree.SubElement(f, "alt-text", {"content-type": "source-text"})
                    alt.text = text
            f.append(node)
            return
        media = el.find("mediaobject")
        info = self.src.media(media) if media is not None else None
        f = etree.SubElement(target, "disp-formula")
        if info is not None and info.image:
            self.xlink = True
            g = etree.SubElement(
                f, "graphic", {f"{{{XLINK}}}href": f"{self.cfg['images_folder']}/{info.image}"}
            )
            etree.SubElement(g, "alt-text").text = info.alt
        if info is not None:
            for para in info.caption:
                p = etree.SubElement(f, "p")
                self.inline_into(para, p)
        if not len(f):
            target.remove(f)

    def b_table(self, el, parent):
        attrs = {"id": el.get("id")} if el.get("id") else {}
        wrap = etree.SubElement(self.slot(parent, "para"), "table-wrap", attrs)
        self.label(wrap, el.get("label"))
        title = el.find("title")
        if title is not None and (title.text or len(title)):
            cap = etree.SubElement(wrap, "caption")
            self.title(cap, title)
        table = etree.SubElement(wrap, "table")
        tgroup = el.find("tgroup")
        for section in tgroup:
            if section.tag not in ("thead", "tbody"):
                continue
            part = etree.SubElement(table, section.tag)
            for row in section.findall("row"):
                tr = etree.SubElement(part, "tr")
                for entry in row.findall("entry"):
                    self.cell(entry, tr, section.tag == "thead")
            if not len(part):
                table.remove(part)
        if table.find("tbody") is None:
            tb = etree.SubElement(table, "tbody")
            etree.SubElement(etree.SubElement(tb, "tr"), "td")

    b_informaltable = b_table

    def cell(self, entry, tr, header: bool):
        attrs = {"scope": "col"} if header else {}
        start, end = entry.get("namest"), entry.get("nameend")
        if start and end and start.isdigit() and end.isdigit() and int(end) > int(start):
            attrs["colspan"] = str(int(end) - int(start) + 1)
            if header:
                attrs["scope"] = "colgroup"
        if entry.get("morerows"):
            attrs["rowspan"] = str(int(entry.get("morerows")) + 1)
        cell = etree.SubElement(tr, "th" if header else "td", attrs)
        kids = list(entry)
        if all(c.tag == "para" and not any(g.tag in self.block_tags() for g in c) for c in kids):
            for i, c in enumerate(kids):
                if i:
                    etree.SubElement(cell, "break").tail = " "
                self.inline_into(c, cell)
        else:
            for c in kids:
                self.block(c, cell)
            self.flatten_cell(cell)

    def flatten_cell(self, cell):
        """A table cell holds p, list, graphic and formulas, not fig, boxed-text or a nested
        table: their text stays, in order, as paragraphs (the graphic is kept)."""
        for child in list(cell):
            if child.tag not in ("fig", "boxed-text", "table-wrap"):
                continue
            new: list = []
            if child.tag == "fig":
                for part in child:
                    if part.tag == "caption":
                        new += [self.as_p(t) for t in part]
                    elif part.tag == "graphic":
                        new.append(part)
                    elif part.tag in ("p", "attrib"):
                        new.append(self.as_p(part))
            elif child.tag == "boxed-text":
                for part in child:
                    new += [self.as_p(t) for t in part] if part.tag == "caption" else [part]
            else:
                self.review("table", "a table inside a table cell was flattened to paragraphs")
                for part in child.iter("title", "td", "th"):
                    new.append(self.as_p(part))
            tail = child.tail
            for item in new:
                child.addprevious(item)
            if new:
                new[-1].tail = tail
            cell.remove(child)

    @staticmethod
    def as_p(src):
        p = etree.Element("p")
        p.text = src.text
        for c in src:
            p.append(c)
        return p

    def b_bibliography(self, el, parent):
        attrs = {"id": el.get("id")} if el.get("id") else {}
        target = self.slot(parent, "back")
        rl = etree.SubElement(target, "ref-list", attrs)
        t = el.find("title")
        if t is not None and (t.text or len(t)):
            self.title(rl, t)
        self.blocks(el, rl, skip=("title", "bibliomixed"))
        self.refs(el, rl)

    def refs(self, el, rl):

        for e in el.findall("bibliomixed"):
            attrs = {"id": e.get("id")} if e.get("id") else {}
            ref = etree.SubElement(rl, "ref", attrs)
            cit = None
            for ch in e:
                if ch.tag == "abbrev":
                    lab = etree.SubElement(ref, "label")
                    self.inline_into(ch, lab)
                else:
                    cit = etree.SubElement(ref, "mixed-citation")
                    self.inline_into(ch, cit)
                    for t in cit.iter("target"):  # not allowed in a citation
                        t.tag = "named-content"
                        t.set("content-type", "page-break")
                        del t.attrib["target-type"]
                    # a page break that opens the entry stands between the entries, where the
                    # page turns (a paragraph holding the marker); one inside the text stays
                    lead = []
                    while self.markers_between_refs and len(cit) and not (cit.text or "").strip() \
                            and cit[0].tag == "named-content" \
                            and cit[0].get("content-type") == "page-break":  # fmt: skip
                        marker = cit[0]
                        tail = marker.tail
                        cit.remove(marker)
                        cit.text = (cit.text or "") + (tail or "")
                        lead.append(marker)
                    if lead:
                        holder = etree.Element("p")
                        for marker in lead:
                            etree.SubElement(holder, "target",
                                             {"id": marker.get("id"), "target-type": "page-break"})
                        ref.addprevious(holder)
            if cit is None:
                etree.SubElement(ref, "mixed-citation")
            elif self.cfg.get("references", {}).get("style") == "structured":
                self.structure_reference(ref, cit)
        if self.cfg.get("references", {}).get("style") == "structured" and self.refs_total:
            self.review(
                "reference",
                f"structured references: {self.refs_structured} of {self.refs_total} references "
                f"parsed into element-citation; the others stay mixed-citation",
            )

    def structure_reference(self, ref, cit):
        """Add the structured form of a reference next to its printed text, when the text fits
        the ``Authors. Title. (Year) Source Volume, pp. a-b.`` pattern: a citation-alternatives
        holding the mixed-citation (every printed character, unchanged) and an element-citation
        (the DTD allows no text in it: only the parts). A reference that does not fit stays a
        mixed-citation alone."""
        self.refs_total += 1
        text = normalize("".join(cit.itertext()))  # the italic source and bold volume carry no more than their words
        parts = parse_reference(text)
        if parts is None:  # not the printed pattern: the two readers (trained parser + rules) decide
            return self.structure_read(ref, cit, text)
        if "sequence" in parts:
            return self.structure_aosis(ref, cit, text, parts)
        ec = etree.Element("element-citation", {"publication-type": "journal"})
        group = etree.SubElement(ec, "person-group", {"person-group-type": "author"})
        for sur, given in parts["authors"]:
            name = etree.SubElement(group, "name")
            etree.SubElement(name, "surname").text = text[sur[0] : sur[1]]
            etree.SubElement(name, "given-names").text = text[given[0] : given[1]]
        rest = [(parts[k], tag) for k, tag in (("title", "article-title"), ("source", "source"),
                ("year", "year"), ("volume", "volume"), ("fpage", "fpage"), ("lpage", "lpage"))
                if parts[k]]  # fmt: skip
        for (start, end), tag in sorted(rest):
            etree.SubElement(ec, tag).text = text[start:end]
        self.refs_structured += 1
        alt = etree.Element("citation-alternatives")
        ref.replace(cit, alt)
        alt.append(cit)
        alt.append(ec)

    def structure_read(self, ref, cit, text):
        """Any other style (Vancouver, IEEE, APA, Harvard ...): the reading of
        :mod:`book_adapters.formats.hybrid`. Written only when both readers agree or one passes
        the validators; otherwise the reference stays as printed and is a review item."""
        from . import hybrid

        reading = hybrid.resolve_all([(0, text)])[0]
        if reading.flags or not reading.authors:
            why = "; ".join(reading.flags) or "no authors"
            self.review("reference", f"reference not structured (kept as printed; {why}): {text[:110]}")
            return
        ec = etree.Element("element-citation", {"publication-type": "journal" if reading.source and reading.volume else "book"})
        group = etree.SubElement(ec, "person-group", {"person-group-type": "author"})
        for initials, surname in reading.authors:
            name = etree.SubElement(group, "name")
            etree.SubElement(name, "surname").text = surname
            if initials:
                etree.SubElement(name, "given-names").text = initials
        if reading.et_al:
            etree.SubElement(group, "etal")
        for tag, value in (("article-title" if reading.source else "source", reading.title), ("source", reading.source),
                           ("year", reading.year), ("volume", reading.volume), ("issue", reading.issue),
                           ("fpage", reading.first_page or reading.article_number), ("lpage", reading.last_page),
                           ("edition", reading.edition), ("publisher-name", reading.publisher), ("publisher-loc", reading.place)):
            if value:
                etree.SubElement(ec, tag).text = value
        if reading.url and "doi.org/" in reading.url:
            etree.SubElement(ec, "pub-id", {"pub-id-type": "doi"}).text = reading.url.split("doi.org/", 1)[1]
        if reading.pmid:
            etree.SubElement(ec, "pub-id", {"pub-id-type": "pmid"}).text = reading.pmid
        self.refs_structured += 1
        alt = etree.Element("citation-alternatives")
        ref.replace(cit, alt)
        alt.append(cit)
        alt.append(ec)

    def structure_aosis(self, ref, cit, text, parts):
        """The AOSIS pattern (``Authors, year, ‘Title’, Source vol(issue), pages. link``): the
        same citation-alternatives, the parts in printed order; an address or DOI loses the
        spaces a line end left in it (the printed text beside it is unchanged)."""
        ec = etree.Element("element-citation", {"publication-type": parts["pub_type"]})

        def group(kind, people):
            g = etree.SubElement(ec, "person-group", {"person-group-type": kind})
            for sur, given in people:
                name = etree.SubElement(g, "name")
                etree.SubElement(name, "surname").text = text[sur[0] : sur[1]]
                etree.SubElement(name, "given-names").text = text[given[0] : given[1]]
            return g

        if parts["collab"]:
            g = etree.SubElement(ec, "person-group", {"person-group-type": "author"})
            etree.SubElement(g, "collab").text = text[parts["collab"][0] : parts["collab"][1]]
        else:
            g = group("author", parts["authors"])
            if parts["etal"]:
                etree.SubElement(g, "etal")
        if parts.get("editors"):
            group("editor", parts["editors"])
        for tag, (start, end) in parts["sequence"]:
            value = text[start:end]
            if tag in ("doi", "uri"):
                value = "".join(value.split())
                if tag == "doi":
                    value = value.split("doi.org/", 1)[-1]
                    el = etree.SubElement(ec, "pub-id", {"pub-id-type": "doi"})
                else:
                    el = etree.SubElement(ec, "uri")
                el.text = value
            else:
                etree.SubElement(ec, tag).text = value
        self.refs_structured += 1
        alt = etree.Element("citation-alternatives")
        ref.replace(cit, alt)
        alt.append(cit)
        alt.append(ec)

    def b_qandaset(self, el, parent):
        lst = etree.SubElement(
            self.slot(parent, "para"), "list", {"list-type": "order", "specific-use": "qanda"}
        )
        for div in el.findall("qandadiv"):
            for entry in div.findall("qandaentry"):
                li = etree.SubElement(lst, "list-item")
                for q in entry.findall("question"):
                    self.item_content(q, li)
                if not len(li):
                    etree.SubElement(li, "p")

    def b_anchor(self, el, parent):
        p = etree.SubElement(self.slot(parent, "para"), "p")
        self.inline_special(el, p)

    def b_partintro(self, el, parent):
        self.blocks(el, parent)

    def b_section(self, el, parent):
        attrs = {"id": el.get("id")} if el.get("id") else {}
        sec = etree.SubElement(self.slot(parent, "sec"), "sec", attrs)
        title = el.find("title")
        t = etree.SubElement(sec, "title")
        if title is not None:
            self.inline_into(title, t)
        self.blocks(el, sec)

    # --- index (list form; BITS overrides with index-entry)

    def b_index_div(self, el, parent):
        raise NotImplementedError


_ = text_of
