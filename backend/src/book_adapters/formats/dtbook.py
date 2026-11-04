"""DTBook 2005-3 (ANSI/NISO Z39.86-2005, the DTD NIMAS 1.1 uses) from the semantic tree.

The text hosts map one to one (para -> p, title -> h1..h6 / doctitle / hd / caption), so the
ledger stays true. Mapping choices the standard leaves open are profile settings (``dtbook``)."""

from __future__ import annotations

import re

from lxml import etree

from ..engine.model import ReviewEntry
from .convert import NUMERATION, Converter
from .markup import add_text, text_of
from .source import Source

NS = "http://www.daisy.org/z3986/2005/dtbook/"
MATHML_NS = "http://www.w3.org/1998/Math/MathML"
PUBLIC_ID = "-//NISO//DTD dtbook 2005-3//EN"
SYSTEM_ID = "http://www.daisy.org/z3986/2005/dtbook-2005-3.dtd"
MATH_SUBSET = """[
<!ENTITY % MATHML.prefixed "INCLUDE">
<!ENTITY % MATHML.prefix "m">
<!ENTITY % mathML2 PUBLIC "-//W3C//DTD MathML 2.0//EN" "http://www.w3.org/Math/DTD/mathml2/mathml2.dtd">
<!ENTITY % externalFlow "| m:math">
<!ENTITY % externalNamespaces "xmlns:m CDATA #FIXED 'http://www.w3.org/1998/Math/MathML'">
%mathML2;
]"""
BLOCK = frozenset(
    {
        "dtbook",
        "head",
        "book",
        "frontmatter",
        "bodymatter",
        "rearmatter",
        "level",
        "level1",
        "level2",
        "level3",
        "level4",
        "level5",
        "level6",
        "list",
        "dl",
        "table",
        "thead",
        "tbody",
        "tr",
        "imggroup",
        "sidebar",
        "note",
        "div",
        "prodnote",
        "blockquote",
    }  # fmt: skip
)
LEVEL_KINDS = {k: k for k in (
    "part", "chapter", "preface", "dedication", "appendix", "index", "bibliography"
)}  # fmt: skip
TEXT_HOSTS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "dt", "td", "th", "hd", "caption")


class DtbookConverter(Converter):
    def __init__(self, src: Source, cfg: dict):
        super().__init__(src, cfg)
        self.math_used = False
        self.notes = 0
        self.pages = {p.id: p for p in src.pages()}
        self.max_level = cfg["headings"]["max_level"]
        self.deep_headings = 0

    # ------------------------------------------------------------------ inline

    def inline_chain(self, ch):
        tag = ch.tag
        if tag == "emphasis":
            role = ch.get("role")
            if role == "bold":
                return [("strong", {})]
            if role == "bolditalic":
                return [("strong", {}), ("em", {})]
            if role in ("smallcaps", "underline"):
                return [("span", {"class": role})]
            return [("em", {})]
        if tag in ("superscript", "subscript"):
            return [("sup" if tag == "superscript" else "sub", {})]
        return [("span", {"class": tag})]

    def inline_special(self, ch, dst) -> bool:
        if ch.tag == "anchor":
            page = self.pages.get(ch.get("id"))
            if page is None:
                return True
            node = etree.SubElement(dst, "pagenum", {"id": page.id, "page": page.kind})
            node.text = page.label
            return True
        if ch.tag == "ulink":
            url = ch.get("url") or ""
            if url.startswith("#") and url[1:] not in self.src.ids:
                self.broken_links += 1
                self.broken_examples.append(url[1:])
                self.inline_into(ch, dst)
                return True
            a = etree.SubElement(dst, "a", {"href": url})
            if not url.startswith("#"):
                a.set("external", "true")
            self.inline_into(ch, a)
            return True
        return False

    def label(self, parent, label: str | None):
        if label and label.strip():
            span = etree.SubElement(parent, "span", {"class": "label"})
            span.text = label
            span.tail = " "

    def text_node(self, tag: str, src, parent, attrs=None, label=None):
        node = etree.SubElement(parent, tag, attrs or {})
        self.label(node, label)
        self.inline_into(src, node)
        return node

    # ------------------------------------------------------------------ document

    def build(self):
        s = self.src
        root = etree.Element("dtbook")
        head = etree.SubElement(root, "head")
        for name, content in self.metadata():
            etree.SubElement(head, "meta", {"name": name, "content": content})
        book = etree.SubElement(root, "book")
        front = etree.SubElement(book, "frontmatter")
        self.front_matter(front)
        body = etree.Element("bodymatter")
        rear = etree.Element("rearmatter")
        divisions = s.divisions()
        if not any(d.get("x-zone") == "body" for d in divisions):
            self.review("structure", "no body division: every division is written in bodymatter")
            zones = {id(d): "body" for d in divisions}
        else:
            zones = {id(d): d.get("x-zone") for d in divisions}
        for d in divisions:
            zone = zones[id(d)]
            target = front if zone == "front" else rear if zone == "back" else body
            self.division(d, target, 1)
        if not len(body):
            self.review("structure", "bodymatter is empty: an empty level1 was written")
            lv = etree.SubElement(body, "level1")
            etree.SubElement(lv, "p")
        book.append(body)
        if len(rear):
            book.append(rear)
        if self.broken_links:
            self.review(
                "link",
                f"{self.broken_links} internal link(s) pointed at anchors that are not in the book "
                f"(for example #{self.broken_examples[0]}); the links were removed",
            )
        return root

    def metadata(self) -> list[tuple[str, str]]:
        s, cfg = self.src, self.cfg
        meta = [("dc:Title", s.title_text() or "TITLE_TO_SUPPLY")]
        for p in s.people():
            if p.name:
                meta.append(("dc:Creator", p.name))
        meta.append(("dc:Language", s.language(cfg["metadata"]["language"])))
        isbn = s.isbn()
        if isbn:
            meta.append(("dc:Identifier", isbn))
        meta.append(("dtb:uid", self.uid()))
        return meta

    def uid(self) -> str:
        isbn = self.src.isbn()
        if isbn:
            return isbn
        sha = (self.src.book.data["metadata"].get("content_sha256") or "")[:16]
        return f"urn:content-sha256:{sha}"

    def front_matter(self, front):
        s = self.src
        info = s.bookinfo
        title = s.title_el()
        dt = etree.SubElement(front, "doctitle")
        if title is not None:
            self.inline_into(title, dt)
        if not (dt.text or len(dt)):
            dt.text = None
        for author in info.iter("author"):
            self.docauthor(author, front)
        legal = [c for c in info if c.tag in ("legalnotice", "isbn")]
        if legal:
            lv = etree.SubElement(front, "level1", {"class": "copyright"})
            for c in legal:
                if c.tag == "legalnotice":
                    self.blocks(c, lv)
                else:
                    p = etree.SubElement(lv, "p", {"class": "isbn"})
                    self.inline_into(c, p)
            if not len(lv):
                etree.SubElement(lv, "p")

    def docauthor(self, author, front):
        da = etree.SubElement(front, "docauthor")
        for child in author:
            if child.tag == "affiliation":
                for sub in child.iter():
                    if sub is child or sub.tag == "address":
                        continue
                    span = etree.SubElement(da, "span", {"class": sub.tag})
                    self.inline_into(sub, span)
                    span.tail = " "
                continue
            span = etree.SubElement(da, "span", {"class": child.tag})
            self.inline_into(child, span)
            span.tail = " "
        if len(da):
            da[-1].tail = None

    # ------------------------------------------------------------------ divisions and sections

    def level(self, parent, n: int, attrs: dict):
        if n > 6:
            return None
        return etree.SubElement(parent, f"level{n}", attrs)

    def division(self, el, parent, n: int):
        kind = self.src.kind(el)
        attrs = {"class": LEVEL_KINDS.get(kind, kind)}
        if el.get("id"):
            attrs["id"] = el.get("id")
        lv = self.level(parent, n, attrs)
        title = el.find("title")
        if title is not None and (title.text or len(title) or el.get("label")):
            h = etree.SubElement(lv, f"h{n}")
            self.label(h, el.get("label"))
            self.inline_into(title, h)
        if el.tag == "part":
            nested = self.cfg["parts"] == "nested"
            for ch in el:
                if ch.tag == "title":
                    continue
                if ch.tag == "chapter":
                    self.division(ch, lv if nested else parent, n + 1 if nested else n)
                else:
                    self.block(ch, lv)
        elif el.tag == "index":
            self.index_body(el, lv, n)
        elif el.tag == "bibliography":
            self.bib_entries(el, lv)
            self.blocks(el, lv, skip=("title", "bibliomixed"))
        else:
            self.blocks(el, lv)
        self.ensure_content(lv, kind)

    def ensure_content(self, lv, what):
        if not [c for c in lv if not c.tag.startswith("h") or c.tag == "hd"]:
            etree.SubElement(lv, "p")
            self.review("structure", f"{what} has no content (an empty p was written)")

    def b_section(self, el, parent):
        n = int(parent.tag[5]) + 1 if parent.tag.startswith("level") else 6
        title = el.find("title")
        if n > self.max_level:
            self.deep_headings += 1
            if title is not None:
                self.text_node(
                    "bridgehead", title, parent, {"id": el.get("id")} if el.get("id") else None
                )
            self.review(
                "structure",
                f"section nested deeper than level {self.max_level}: heading written as bridgehead",
            )
            self.blocks(el, parent)
            return
        attrs = {"id": el.get("id")} if el.get("id") else {}
        lv = etree.SubElement(parent, f"level{n}", attrs)
        if title is not None and (title.text or len(title)):
            h = etree.SubElement(lv, f"h{n}")
            self.inline_into(title, h)
        self.blocks(el, lv)
        self.ensure_content(lv, "section")

    # ------------------------------------------------------------------ blocks

    def b_para(self, el, parent):
        kind = el.get("x-kind")
        for run in self.segments(el):
            if run[0] == "block":
                self.block(run[1], parent)
                continue
            if not self.has_text(run[1]) and len(run[1]) == 0:
                continue
            if kind == "footnote":
                self.notes += 1
                note = etree.SubElement(
                    parent, "note", {"id": f"note{self.notes}", "class": "footnote"}
                )
                p = etree.SubElement(note, "p")
                self.inline_run_into(run[1], p)
                continue
            attrs = {}
            cls = {"caption": "caption", "credit": "credit"}.get(kind) or el.get("role")
            if cls:
                attrs["class"] = cls
            p = etree.SubElement(parent, "p", attrs)
            self.inline_run_into(run[1], p)

    def b_itemizedlist(self, el, parent):
        lst = etree.SubElement(parent, "list", {"type": "ul"})
        self.items(el, lst)

    def b_orderedlist(self, el, parent):
        attrs = {"type": "ol", "enum": NUMERATION.get(el.get("numeration") or "arabic", "1")}
        if el.get("continuation") == "restarts" and (el.get("role") or "").isdigit():
            attrs["start"] = el.get("role")
        lst = etree.SubElement(parent, "list", attrs)
        self.items(el, lst)

    def items(self, el, lst):
        for li_src in el.findall("listitem"):
            li = etree.SubElement(lst, "li")
            self.cell_content(li_src, li)
            if not (li.text or len(li)):
                li.text = None

    def cell_content(self, src, dst):
        """Content of a list item or table cell: a single plain para is written as inline
        text, anything else as blocks."""
        kids = list(src)
        if (
            len(kids) == 1
            and kids[0].tag == "para"
            and not kids[0].get("role")
            and not any(c.tag in ("anchor", *self.block_tags()) for c in kids[0])
        ):
            self.inline_into(kids[0], dst)
        else:
            self.blocks(src, dst, skip=())

    @staticmethod
    def block_tags():
        from .convert import BLOCK_CHILDREN

        return BLOCK_CHILDREN

    def b_variablelist(self, el, parent):
        dl = etree.SubElement(parent, "dl")
        for entry in el.findall("varlistentry"):
            term = entry.find("term")
            dt = etree.SubElement(dl, "dt")
            if term is not None:
                self.inline_into(term, dt)
            dd = etree.SubElement(dl, "dd")
            li = entry.find("listitem")
            if li is not None:
                self.blocks(li, dd, skip=())

    def b_sidebar(self, el, parent):
        attrs = {"id": el.get("id")} if el.get("id") else {}
        attrs["render"] = self.cfg["sidebar_render"]
        sb = etree.SubElement(parent, "sidebar", attrs)
        title = el.find("title")
        if title is not None:
            self.text_node("hd", title, sb, label=el.get("label"))
        self.blocks(el, sb)
        if not len(sb):
            etree.SubElement(sb, "p")

    # --- figures

    def b_figure(self, el, parent):
        media = el.find("mediaobject")
        info = self.src.media(media) if media is not None else None
        attrs = {"id": el.get("id")} if el.get("id") else {}
        grp = etree.SubElement(parent, "imggroup", attrs)
        if info is not None and info.image:
            etree.SubElement(
                grp, "img", {"src": f"{self.cfg['images_folder']}/{info.image}", "alt": info.alt}
            )
        else:
            self.review("figure", "figure without an image file", None)
        title = el.find("title")
        if title is not None and (title.text or len(title) or el.get("label")):
            cap = etree.SubElement(grp, "caption")
            self.label(cap, el.get("label"))
            self.inline_into(title, cap)
        if info is not None and info.figure_text:
            pn = etree.SubElement(
                grp, "prodnote", {"class": "figure-text", "render": self.cfg["sidebar_render"]}
            )
            for para in info.figure_text:
                p = etree.SubElement(pn, "p")
                self.inline_into(para, p)
        if info is not None and info.caption:
            cap = etree.SubElement(grp, "caption")
            for para in info.caption:
                p = etree.SubElement(cap, "p", {"class": "credit"})
                self.inline_into(para, p)
        if not len(grp):
            parent.remove(grp)

    b_informalfigure = b_figure

    def b_mediaobject(self, el, parent):
        self.b_figure(etree.fromstring("<informalfigure/>") if False else _wrap_media(el), parent)

    def b_informalequation(self, el, parent):
        math = self.src.mathml(el)
        if math is not None and self.cfg["math"]["mathml"]:
            self.math_used = True
            p = etree.SubElement(parent, "p", {"class": "equation"})
            node = _to_namespaced(math, MATHML_NS)
            latex = self.src.latex(el)
            if latex:
                node.set("alttext", latex)
            p.append(node)
            return
        media = el.find("mediaobject")
        info = self.src.media(media) if media is not None else None
        grp = etree.SubElement(parent, "imggroup", {"class": "equation"})
        if info is not None and info.image:
            etree.SubElement(
                grp, "img", {"src": f"{self.cfg['images_folder']}/{info.image}", "alt": info.alt}
            )
        if info is not None and info.caption:
            cap = etree.SubElement(grp, "caption")
            for para in info.caption:
                p = etree.SubElement(cap, "p")
                self.inline_into(para, p)
        if not len(grp):
            parent.remove(grp)

    # --- tables

    def b_table(self, el, parent):
        attrs = {"id": el.get("id")} if el.get("id") else {}
        table = etree.SubElement(parent, "table", attrs)
        title = el.find("title")
        if title is not None and (title.text or len(title) or el.get("label")):
            cap = etree.SubElement(table, "caption")
            self.label(cap, el.get("label"))
            self.inline_into(title, cap)
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
        tag = "th" if header else "td"
        attrs = {}
        if header:
            attrs["scope"] = "col"
        start, end = entry.get("namest"), entry.get("nameend")
        if start and end and start.isdigit() and end.isdigit() and int(end) > int(start):
            attrs["colspan"] = str(int(end) - int(start) + 1)
            if header:
                attrs["scope"] = "colgroup"
        if entry.get("morerows"):
            attrs["rowspan"] = str(int(entry.get("morerows")) + 1)
        cell = etree.SubElement(tr, tag, attrs)
        if any(c.tag == "anchor" for c in entry.iter()):
            self.blocks(entry, cell, skip=())  # pagenum is not allowed directly in a cell
        else:
            self.cell_content(entry, cell)

    # --- bibliography, index, q and a

    def b_bibliography(self, el, parent):
        title = el.find("title")
        n = int(parent.tag[5]) + 1 if parent.tag.startswith("level") else 6
        holder = parent
        if title is not None and (title.text or len(title)) and n <= self.max_level:
            attrs = {"class": "bibliography"}
            if el.get("id"):
                attrs["id"] = el.get("id")
            holder = etree.SubElement(parent, f"level{n}", attrs)
            h = etree.SubElement(holder, f"h{n}")
            self.inline_into(title, h)
        elif title is not None:
            self.text_node("bridgehead", title, parent)
        self.blocks(el, holder, skip=("title", "bibliomixed"))
        self.bib_entries(el, holder)
        if holder is not parent:
            self.ensure_content(holder, "bibliography")

    def bib_entries(self, el, parent):
        entries = el.findall("bibliomixed")
        if not entries:
            return
        lst = etree.SubElement(parent, "list", {"type": "pl", "class": "bibliography"})
        for e in entries:
            attrs = {"id": e.get("id")} if e.get("id") else {}
            li = etree.SubElement(lst, "li", attrs)
            for ch in e:
                span = etree.SubElement(
                    li, "span", {"class": "abbrev" if ch.tag == "abbrev" else "bibliomisc"}
                )
                self.inline_into(ch, span)
                span.tail = " " if ch.tag == "abbrev" else None

    def index_body(self, el, lv, n):
        for ch in el:
            if ch.tag == "title":
                continue
            if ch.tag == "indexdiv":
                holder = lv
                t = ch.find("title")
                if t is not None and (t.text or len(t)) and n + 1 <= self.max_level:
                    holder = etree.SubElement(lv, f"level{n + 1}", {"class": "indexdiv"})
                    h = etree.SubElement(holder, f"h{n + 1}")
                    self.inline_into(t, h)
                self.index_entries(ch, holder)
                if holder is not lv:
                    self.ensure_content(holder, "index division")
            elif ch.tag == "indexentry":
                self.index_entries(el, lv)
                break
            else:
                self.block(ch, lv)

    def index_entries(self, src, parent):
        """Entries and the blocks between them, in order: a run of entries is one list."""
        run: list = []
        for c in src:
            if c.tag == "indexentry":
                run.append(c)
                continue
            if run:
                self.entry_list(run, parent)
                run = []
            if c.tag != "title":
                self.block(c, parent)
        if run:
            self.entry_list(run, parent)

    def entry_list(self, entries, parent):
        lst = etree.SubElement(parent, "list", {"type": "pl", "class": "index"})
        for ie in entries:
            li = sub_list = tert_list = sec = None
            for part in ie:
                if part.tag == "primaryie":
                    li = etree.SubElement(lst, "li", {"class": "ie1"})
                    self.inline_into(part, li)
                    sub_list = tert_list = None
                elif part.tag == "secondaryie":
                    if sub_list is None:
                        sub_list = etree.SubElement(li, "list", {"type": "pl"})
                    sec = etree.SubElement(sub_list, "li", {"class": "ie2"})
                    self.inline_into(part, sec)
                    tert_list = None
                elif part.tag == "tertiaryie":
                    if tert_list is None:
                        tert_list = etree.SubElement(sec, "list", {"type": "pl"})
                    tl = etree.SubElement(tert_list, "li", {"class": "ie3"})
                    self.inline_into(part, tl)
                else:
                    self.block(part, parent)

    def b_qandaset(self, el, parent):
        lst = etree.SubElement(parent, "list", {"type": "ol", "class": "qanda"})
        for div in el.findall("qandadiv"):
            t = div.find("title")
            if t is not None and (t.text or len(t)):
                self.text_node("hd", t, lst)
            for entry in div.findall("qandaentry"):
                li = etree.SubElement(lst, "li")
                for q in entry.findall("question"):
                    self.cell_content(q, li)
        if not len(lst):
            parent.remove(lst)

    def b_anchor(self, el, parent):
        p = etree.SubElement(parent, "p")
        self.inline_special(el, p)

    def b_partintro(self, el, parent):
        self.blocks(el, parent)


def _wrap_media(media):
    wrapper = etree.Element("informalfigure")
    wrapper.append(media)
    return wrapper


def _to_namespaced(node, ns):
    """MathML element tree with every element in the MathML namespace (attributes kept)."""
    out = etree.Element(f"{{{ns}}}{etree.QName(node).localname}")
    for k, v in node.attrib.items():
        if not k.startswith("{"):
            out.set(k, v)
    out.text = node.text
    for child in node:
        if isinstance(child.tag, str):
            c = _to_namespaced(child, ns)
            c.tail = child.tail
            out.append(c)
    return out


_ = (re, add_text, text_of, ReviewEntry)
