"""ePub 3 writer: the same engine as the DocBook writer, a different output.

The DocBook writer's passes run unchanged: the outline, ids and numbering, the characters
pass, links, the review-decisions overlay (applied to book.json before the adapter), the
emission ledger. They build one tree of DocBook-named elements whose hosts (para, title, entry,
...) hold all the text. This writer turns that tree into XHTML pages with a 1:1 mapping of the
text hosts, so the ledger's token blocks stay valid for the lossless check, and packages the
pages with images, style sheets, the navigation document and the package document.

Everything client-specific comes from the profile's ``epub`` section."""

from __future__ import annotations

import posixpath
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from lxml import etree

from ..engine.model import Division, ReviewEntry
from ..engine.packager import encode_image
from ..engine.profile import epub_section
from ..engine.text import TextRef
from .base import Delivery, WriteContext
from .docbook import DocBookWriter, fmt
from .xhtml import document, new_html

MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".css": "text/css",
    ".xhtml": "application/xhtml+xml",
}
# Elements that start a block inside a para (the para is split around them).
BLOCK_TAGS = frozenset(
    {
        "figure",
        "informalfigure",
        "table",
        "informaltable",
        "itemizedlist",
        "orderedlist",
        "variablelist",
        "sidebar",
        "informalequation",
        "qandaset",
        "bibliography",
        "mediaobject",
    }
)
EPUB_TYPES = {
    "part": ("part", "doc-part"),
    "chapter": ("chapter", "doc-chapter"),
    "preface": ("preface", "doc-preface"),
    "dedication": ("dedication", "doc-dedication"),
    "appendix": ("appendix", "doc-appendix"),
    "glossary": ("glossary", "doc-glossary"),
    "index": ("index", "doc-index"),
    "bibliography": ("bibliography", "doc-bibliography"),
}
NUMERATION = {
    "arabic": "1",
    "loweralpha": "a",
    "upperalpha": "A",
    "lowerroman": "i",
    "upperroman": "I",
}
GUIDE_TYPES = {
    "cover": "cover",
    "halftitlepage": "other.halftitle",
    "titlepage": "title-page",
    "copyright-page": "copyright-page",
    "toc": "toc",
    "bodymatter": "text",
    "index": "index",
    "glossary": "glossary",
    "bibliography": "bibliography",
    "preface": "preface",
    "foreword": "foreword",
    "dedication": "dedication",
}
ROLE_CLASSES = ("noindent", "indent", "small", "aligncenter", "subchapter")
KIND_CLASSES = ("caption", "credit", "display_title", "label")


@dataclass
class Head:
    """A heading listed in the contents."""

    level: int  # 1 = division title, 2 = section of depth 1 ...
    nest: int  # level in the contents tree (chapters of a part sit under the part)
    id: str
    text: str
    page: str  # file name of its page


@dataclass
class Page:
    name: str
    role: str  # cover | halftitle | titlepage | copyright | toc | division
    kind: str
    title: str
    html: etree._Element
    body: etree._Element
    zone: str = "front"  # front | body | back
    heads: list[Head] = field(default_factory=list)
    generated: bool = False  # built from settings/profile, not from book text
    math: bool = False
    division_id: str | None = None
    first: bool = False


def _rel(from_dir: str, to_path: str) -> str:
    return posixpath.relpath(to_path, from_dir or ".")


class Epub3Writer(DocBookWriter):
    name = "epub3"

    # ------------------------------------------------------------------ hooks into the tree

    def write(self, doc, ctx: WriteContext) -> Delivery:
        self.cfg = epub_section(ctx.profile)
        self.has_epub_section = bool(ctx.profile.get("epub"))
        self._div_by_el: dict = {}
        self._depth = 0
        self._heads: list[Head] = []
        self._footnotes = 0
        self._ol_end = 0
        self._math_seen = False
        self.lang = self._language(ctx)
        return super().write(doc, ctx)

    def _language(self, ctx: WriteContext) -> str:
        chosen = ctx.settings.data.get("language")
        if chosen:
            return chosen
        languages = (ctx.book.data.get("metadata") or {}).get("languages") or []
        if languages:
            return max(languages, key=lambda x: x.get("share", 0))["code"]
        return self.cfg["metadata"]["language"]

    def _image_format(self) -> str:
        return self.cfg["images"]["format"]

    def _write_division(self, parent, division: Division):
        el = super()._write_division(parent, division)
        self._div_by_el[el] = division
        return el

    def _anchor(self, el, mark):
        if not mark.keep or not self.p.get("anchors.enabled"):
            return
        a = etree.SubElement(el, "anchor")
        a.set("id", mark.anchor_id)
        a.set("label", mark.label or str(mark.page))
        if mark.role:
            a.set("role", mark.role)

    def _write_block(self, parent, block, container: str):
        from ..engine.model import Para

        n = len(parent)
        super()._write_block(parent, block, container)
        if isinstance(block, Para) and len(parent) > n:
            el = parent[n]
            el.set("pkind", block.kind)
            ref = next((p for p in block.parts if isinstance(p, TextRef)), None)
            if ref is not None:
                language = ref.content.get("language")
                if language and language.split("-")[0] != self.lang.split("-")[0]:
                    el.set("lang", language)
                if ref.content.get("direction") == "rtl":
                    el.set("dir", "rtl")

    def _write_equation(self, parent, eq):
        unit = eq.unit
        output = unit.get("output")
        if eq.content is not None and output == "text":
            return super()._write_equation(parent, eq)
        root = self._math_root(unit) if self.cfg["math"]["mathml"] else None
        el = etree.SubElement(parent, "informalequation")
        mode = unit.get("presentation")
        el.set("mode", mode if mode in ("inline", "display") else "display")
        alt = (unit.get("alt_text") or {}).get("text") or (
            unit.get("latex") if self.p.get("equations.alt_from") == "alt_text_or_latex" else ""
        )
        if not alt:
            self.alt_placeholders.append(unit["id"])
            self.reviews.append(
                ReviewEntry(
                    "alt_text",
                    "equation alt text to supply (placeholder written)",
                    unit["id"],
                    unit["pages"][0],
                )
            )
        el.set("alt", alt or self.p.get("figures.alt_text_placeholder") or "")
        if root is not None:
            el.set("kind", "mathml")
            holder = etree.SubElement(el, "mathml")
            holder.append(root)
        else:
            el.set("kind", "image")
            name = self.image_of.get(id(eq))
            if name:
                etree.SubElement(el, "imagedata").set("fileref", name)
            if output in ("mathml", "mathml_parts"):
                self.reviews.append(
                    ReviewEntry(
                        "equation",
                        "MathML not available for this equation: image fallback used",
                        unit["id"],
                        unit["pages"][0],
                    )
                )
        if eq.content is not None:
            cap = etree.SubElement(el, "caption")
            para = etree.SubElement(cap, "para")
            self.render(para, [eq.content], ("superscript", "subscript"), host=False)

    def _math_root(self, unit):
        """The equation's MathML as plain elements, or None when there is none or it is not
        well-formed MathML."""
        if unit.get("output") not in ("mathml", "mathml_parts") or not unit.get("mathml"):
            return None
        try:
            src = etree.fromstring(unit["mathml"].encode("utf-8"))
        except etree.XMLSyntaxError:
            return None
        if etree.QName(src).localname != "math":
            wrapper = etree.Element("{http://www.w3.org/1998/Math/MathML}math")
            wrapper.append(src)
            src = wrapper

        def plain(node):
            if not isinstance(node.tag, str):
                return None
            out = etree.Element(etree.QName(node).localname)
            for k, v in node.attrib.items():
                if not k.startswith("{"):
                    out.set(k, v)
            out.text = node.text
            for child in node:
                new = plain(child)
                if new is not None:
                    out.append(new)
                    new.tail = child.tail
            return out

        return plain(src)

    # ------------------------------------------------------------------ inline conversion

    @staticmethod
    def _add_text(dst, text):
        if not text:
            return
        if len(dst):
            dst[-1].tail = (dst[-1].tail or "") + text
        else:
            dst.text = (dst.text or "") + text

    def _inline_node(self, ch):
        """(outer, inner) XHTML elements for one DocBook inline element."""
        tag = ch.tag
        if tag == "emphasis":
            role = ch.get("role")
            if role == "bold":
                el = etree.Element("b")
                return el, el
            if role == "bolditalic":
                outer = etree.Element("b")
                return outer, etree.SubElement(outer, "i")
            if role in ("smallcaps", "underline"):
                el = etree.Element("span")
                el.set("class", "f-smallcaps" if role == "smallcaps" else "f-underline")
                return el, el
            el = etree.Element("i")
            return el, el
        if tag in ("superscript", "subscript"):
            el = etree.Element("sup" if tag == "superscript" else "sub")
            return el, el
        if tag == "ulink":
            el = etree.Element("a")
            el.set("href", ch.get("url") or "#")
            return el, el
        if tag == "email":
            el = etree.Element("a")
            el.set("href", "mailto:" + "".join(ch.itertext()).strip())
            return el, el
        if tag == "anchor":
            el = etree.Element("span")
            label = ch.get("label") or ""
            el.set("epub_type", "pagebreak")
            el.set("role", "doc-pagebreak")
            el.set("id", ch.get("id"))
            el.set("title", label)
            el.set("aria_label", label)
            return el, el
        el = etree.Element("span")
        el.set("class", tag)
        return el, el

    def _copy_inline(self, dst, src):
        """src's text and inline children, as XHTML inline content of dst."""
        self._add_text(dst, src.text)
        for ch in src:
            if ch.tag in BLOCK_TAGS or ch.tag == "para":
                continue
            outer, inner = self._inline_node(ch)
            if ch.tag != "anchor":
                self._copy_inline(inner, ch)
            dst.append(outer)
            outer.tail = ch.tail

    def _inline_el(self, tag: str, src, **attrs):
        el = etree.Element(tag)
        for k, v in attrs.items():
            el.set(k.rstrip("_"), v)
        self._copy_inline(el, src)
        return el

    @staticmethod
    def _has_content(el) -> bool:
        return bool((el.text or "").strip()) or len(el) > 0

    # ------------------------------------------------------------------ block conversion

    def _x_blocks(self, parent_out, src, skip=("title",)):
        for ch in src:
            if ch.tag in skip:
                continue
            parent_out.extend(self._x_block(ch))

    def _x_block(self, el) -> list:
        tag = el.tag
        fn = getattr(self, f"_x_{tag}", None)
        if fn is None:
            if tag == "title":
                return []
            span = etree.Element("p")
            self._copy_inline(span, el)
            return [span] if self._has_content(span) else []
        return fn(el)

    def _x_anchor(self, el):
        outer, _ = self._inline_node(el)
        return [outer]

    def _x_para(self, el) -> list:
        out: list = []
        cur = None
        classes = [el.get("role")] if el.get("role") in ROLE_CLASSES else []
        kind = el.get("pkind")
        if kind in KIND_CLASSES:
            classes.append(kind.replace("_", "-"))

        def start():
            nonlocal cur
            if cur is None:
                cur = etree.Element("p")
                if classes:
                    cur.set("class", " ".join(classes))
                if el.get("lang"):
                    cur.set("lang", el.get("lang"))
                    cur.set("xml_lang", el.get("lang"))
                if el.get("dir"):
                    cur.set("dir", el.get("dir"))
            return cur

        def flush():
            nonlocal cur
            if cur is not None and (self._has_content(cur)):
                out.append(cur)
            cur = None

        if (el.text or "").strip():
            self._add_text(start(), el.text)
        for ch in el:
            if ch.tag in BLOCK_TAGS:
                flush()
                out.extend(self._x_block(ch))
                if (ch.tail or "").strip():
                    self._add_text(start(), ch.tail)
                continue
            p = start()
            outer, inner = self._inline_node(ch)
            if ch.tag != "anchor":
                self._copy_inline(inner, ch)
            p.append(outer)
            outer.tail = ch.tail
        flush()
        if kind == "footnote" and out:
            self._footnotes += 1
            aside = etree.Element("aside")
            aside.set("epub_type", "footnote")
            aside.set("role", "doc-footnote")
            aside.set("id", f"fn{self._footnotes}")
            aside.extend(out)
            return [aside]
        return out

    def _x_section(self, el) -> list:
        self._depth += 1
        try:
            sec = etree.Element("section")
            title = el.find("title")
            if title is not None and self._has_content(title):
                level = min(1 + self._depth, 6)
                hid = el.get("id") or f"sec{len(self._heads)}"
                sec.append(self._heading(level, title, hid, level))
            self._x_blocks(sec, el)
            return [sec]
        finally:
            self._depth -= 1

    def _heading(
        self, level: int, title, hid: str, listed_level: int | None, label=None, fallback=None
    ):
        """A heading element; a heading that is listed in the contents gets its return link
        (guideline EPUB item 5) and a Head record."""
        h = etree.Element(f"h{min(level, 6)}")
        h.set("id", hid)
        if label:
            span = etree.SubElement(h, "span")
            span.set("class", "label")
            span.text = label
            span.tail = " "
        self._copy_inline(h, title)
        if listed_level is not None and listed_level <= self.cfg["nav"]["toc_depth"]:
            text = " ".join("".join(h.itertext()).split())
            if not text:  # a heading with only a page break: the contents need some text
                text = fallback or "Untitled"
            self._heads.append(Head(listed_level, listed_level, hid, text, ""))
            return_mode = self.cfg["nav"]["toc_return"]
            if return_mode != "none":
                a = etree.Element("a")
                a.set("class", "toc-return")
                a.set("href", self._return_href(hid, return_mode))
                a.text, h.text = h.text, None
                for child in list(h):
                    a.append(child)
                h.append(a)
        return h

    def _return_href(self, hid: str, mode: str) -> str:
        pk = self.cfg["package"]
        toc = pk["toc_file"]
        if toc:
            target = posixpath.join(pk["text_folder"], toc)
        else:
            target = pk["nav_file"]
        href = _rel(pk["text_folder"], target)
        frag = self.cfg["nav"]["toc_container_id"] if mode == "container" else f"toc-{hid}"
        return f"{href}#{frag}"

    def _plain_heading(self, level: int, title, cls: str | None = None):
        if title is None or not self._has_content(title):
            return None
        h = self._inline_el(f"h{min(level, 6)}", title)
        if cls:
            h.set("class", cls)
        return h

    def _x_sidebar(self, el) -> list:
        aside = etree.Element("aside")
        aside.set("class", "box")
        if el.get("id"):
            aside.set("id", el.get("id"))
        title = el.find("title")
        if title is not None and self._has_content(title):
            p = etree.SubElement(aside, "p")
            p.set("class", "box-title")
            self._label(p, el.get("label"))
            self._copy_inline(p, title)
        self._x_blocks(aside, el)
        return [aside]

    @staticmethod
    def _label(parent, label):
        if label and label.strip():
            span = etree.SubElement(parent, "span")
            span.set("class", "label")
            span.text = label
            span.tail = " "

    def _li_content(self, li, src):
        """Content of a list item or table cell: a single plain para is unwrapped to inline
        text."""
        holder = etree.Element("x")
        self._x_blocks(holder, src, skip=("title", "term"))
        blocks = list(holder)
        if len(blocks) == 1 and blocks[0].tag == "p" and not blocks[0].get("class"):
            p = blocks[0]
            li.text = p.text
            for child in list(p):
                li.append(child)
        else:
            li.extend(blocks)

    def _x_itemizedlist(self, el) -> list:
        ul = etree.Element("ul")
        ul.set("class", f"mk-{el.get('mark') or 'bullet'}")
        for item in el.findall("listitem"):
            self._li_content(etree.SubElement(ul, "li"), item)
        return [ul]

    def _x_orderedlist(self, el) -> list:
        ol = etree.Element("ol")
        numeration = el.get("numeration") or "arabic"
        ol.set("type", NUMERATION.get(numeration, "1"))
        items = el.findall("listitem")
        start = None
        if el.get("continuation") == "continues" and self._ol_end:
            start = self._ol_end + 1
        elif el.get("continuation") == "restarts" and (el.get("role") or "").isdigit():
            start = int(el.get("role"))
        if start and start > 1:
            ol.set("start", str(start))
        self._ol_end = (start or 1) - 1 + len(items)
        for item in items:
            self._li_content(etree.SubElement(ol, "li"), item)
        return [ol]

    def _x_variablelist(self, el) -> list:
        dl = etree.Element("dl")
        for entry in el.findall("varlistentry"):
            term = entry.find("term")
            if term is not None:
                dl.append(self._inline_el("dt", term))
            listitem = entry.find("listitem")
            if listitem is not None:
                self._li_content(etree.SubElement(dl, "dd"), listitem)
        return [dl]

    def _x_figure(self, el) -> list:
        fig = etree.Element("figure")
        if el.get("id"):
            fig.set("id", el.get("id"))
        media = el.find("mediaobject")
        alt, texts = "", []
        if media is not None:
            data = media.find("imageobject/imagedata")
            for to in media.findall("textobject"):
                if to.get("role") == "figuretext":
                    texts += to.findall("para")
                else:
                    alt = "".join(to.itertext())
            if data is not None:
                img = etree.SubElement(fig, "img")
                img.set("src", self._image_href(posixpath.basename(data.get("fileref"))))
                img.set("alt", alt)
        cap = etree.Element("figcaption")
        title = el.find("title")
        if title is not None and self._has_content(title):
            p = etree.SubElement(cap, "p")
            p.set("class", "figtitle")
            self._label(p, el.get("label"))
            self._copy_inline(p, title)
        if media is not None:
            for credit in media.findall("caption/para"):
                p = self._inline_el("p", credit)
                p.set("class", "credit")
                if self._has_content(p):
                    cap.append(p)
        for para in texts:
            p = self._inline_el("p", para)
            p.set("class", "figtext")
            if self._has_content(p):
                cap.append(p)
        if len(cap):
            fig.append(cap)
        return [fig]

    _x_informalfigure = _x_figure

    def _image_href(self, name: str) -> str:
        pk = self.cfg["package"]
        return _rel(pk["text_folder"], posixpath.join(pk["image_folder"], name))

    def _x_informalequation(self, el) -> list:
        div = etree.Element("div")
        div.set("class", "equation")
        alt = el.get("alt") or ""
        caption = el.find("caption/para")
        if el.get("kind") == "mathml":
            self._math_seen = True
            math = el.find("mathml")[0]
            math.set("alttext", alt)
            math.set("display", "block" if el.get("mode") == "display" else "inline")
            semantics = etree.Element("semantics")
            mrow = etree.SubElement(semantics, "mrow")
            mrow.text = math.text
            math.text = None
            for child in list(math):
                mrow.append(child)
            math.append(semantics)
            if caption is not None and self._has_content(caption):
                ann = etree.SubElement(semantics, "annotation")
                ann.set("encoding", "text/plain")
                self._copy_inline(ann, caption)
            div.append(math)
        else:
            data = el.find("imagedata")
            if data is not None:
                img = etree.SubElement(div, "img")
                img.set("src", self._image_href(data.get("fileref")))
                img.set("alt", alt)
            if caption is not None and self._has_content(caption):
                p = self._inline_el("p", caption)
                p.set("class", "eq-text hidden-heading")
                p.set("aria_hidden", "true")
                div.append(p)
        return [div]

    def _x_table(self, el) -> list:
        table = etree.Element("table")
        if el.get("id"):
            table.set("id", el.get("id"))
        title = el.find("title")
        if title is not None and self._has_content(title):
            cap = etree.SubElement(table, "caption")
            self._label(cap, el.get("label"))
            self._copy_inline(cap, title)
        tgroup = el.find("tgroup")
        if tgroup is None:
            return [table]
        for section, tag in (("thead", "th"), ("tbody", "td")):
            src = tgroup.find(section)
            if src is None:
                continue
            out = etree.SubElement(table, section)
            for row in src.findall("row"):
                tr = etree.SubElement(out, "tr")
                for entry in row.findall("entry"):
                    cell = etree.SubElement(tr, tag)
                    if tag == "th":
                        cell.set("scope", "col")
                    if entry.get("namest") and entry.get("nameend"):
                        span = int(entry.get("nameend")) - int(entry.get("namest")) + 1
                        if span > 1:
                            cell.set("colspan", str(span))
                    if entry.get("morerows"):
                        cell.set("rowspan", str(int(entry.get("morerows")) + 1))
                    self._li_content(cell, entry)
        return [table]

    _x_informaltable = _x_table

    def _x_bibliography(self, el) -> list:
        sec = etree.Element("section")
        sec.set("class", "bibliography")
        sec.set("epub_type", "bibliography")
        sec.set("role", "doc-bibliography")
        if el.get("id"):
            sec.set("id", el.get("id"))
        h = self._plain_heading(min(self._depth + 2, 6), el.find("title"))
        if h is not None:
            sec.append(h)
        self._x_blocks(sec, el)
        return [sec]

    def _x_bibliomixed(self, el) -> list:
        p = etree.Element("p")
        p.set("class", "bib")
        if el.get("id"):
            p.set("id", el.get("id"))
        for ch in el:
            span = self._inline_el("span", ch)
            span.set("class", "abbrev" if ch.tag == "abbrev" else "bibliomisc")
            span.tail = " " if ch.tag == "abbrev" else None
            p.append(span)
        return [p]

    def _x_qandaset(self, el) -> list:
        sec = etree.Element("section")
        sec.set("class", "qanda")
        for div in el.findall("qandadiv"):
            h = self._plain_heading(min(self._depth + 2, 6), div.find("title"))
            if h is not None:
                sec.append(h)
            for entry in div.findall("qandaentry"):
                answer = entry.find("answer")
                if answer is None:
                    holder = etree.SubElement(sec, "div")
                    holder.set("class", "question")
                    question = entry.find("question")
                    if question is not None:
                        self._x_blocks(holder, question)
                    continue
                item = etree.SubElement(sec, "section")  # a question with its printed answer
                item.set("class", "qandaentry")
                if entry.get("role"):
                    item.set("data-number", entry.get("role"))
                holder = etree.SubElement(item, "div")
                holder.set("class", "question")
                question = entry.find("question")
                if question is not None:
                    self._x_blocks(holder, question)
                reply = etree.SubElement(item, "aside")
                reply.set("class", "answer")
                self._x_blocks(reply, answer)
        return [sec]

    def _x_legalnotice(self, el) -> list:
        holder = etree.Element("x")
        self._x_blocks(holder, el)
        return list(holder)

    def _x_partintro(self, el) -> list:
        holder = etree.Element("x")
        children = [c for c in el if c.tag != "title"]
        if len(children) == 1 and children[0].tag == "sidebar" and not children[0].get("id"):
            side = children[0]
            if side.find("title") is None:
                self._x_blocks(holder, side)
                return list(holder)
        self._x_blocks(holder, el)
        return list(holder)

    def _x_index_body(self, sec, el):
        for ch in el:
            if ch.tag == "title":
                continue
            if ch.tag == "indexdiv":
                h = self._plain_heading(2, ch.find("title"), "index-letter")
                if h is not None:
                    sec.append(h)
                self._x_index_body(sec, ch)
            elif ch.tag == "indexentry":
                for ie in ch:
                    level = {"primaryie": 1, "secondaryie": 2, "tertiaryie": 3}.get(ie.tag, 1)
                    sec.append(self._inline_el("p", ie, class_=f"index-entry index-l{level}"))
            else:
                sec.extend(self._x_block(ch))

    # ------------------------------------------------------------------ authors

    def _x_authorgroup(self, el) -> list:
        div = etree.Element("div")
        div.set("class", "authorgroup")
        for author in el.findall("author"):
            p = etree.SubElement(div, "p")
            p.set("class", "author")
            for ch in author:
                if ch.tag == "affiliation":
                    for part in ch:
                        if part.tag == "address":
                            for sub in part:
                                self._line(p, sub)
                        else:
                            self._line(p, part)
                else:
                    span = self._inline_el("span", ch, class_=ch.tag)
                    span.tail = " "
                    p.append(span)
            if len(p) and p[-1].tag == "span" and p[-1].tail == " ":
                p[-1].tail = None
        return [div]

    def _line(self, p, part):
        if len(p) and p[-1].tag != "br":
            etree.SubElement(p, "br")
        p.append(self._inline_el("span", part, class_=part.tag))

    # ------------------------------------------------------------------ pages

    def _css_hrefs(self) -> list[str]:
        pk = self.cfg["package"]
        return [
            _rel(pk["text_folder"], posixpath.join(pk["style_folder"], c["name"]))
            for c in self.cfg["css"]
        ]

    def _page(self, name: str, role: str, kind: str, title: str, zone: str, **body_attrs) -> Page:
        html, body = new_html(self.lang, title or kind, self._css_hrefs())
        for k, v in body_attrs.items():
            body.set(k.rstrip("_"), v)
        return Page(name, role, kind, title or kind, html, body, zone)

    def _book_title(self, info) -> str:
        if self.settings.data.get("title"):
            return self.settings.data["title"]
        title = info.find("title") if info is not None else None
        text = " ".join("".join(title.itertext()).split()) if title is not None else ""
        return text or (self.ctx.book.data.get("metadata") or {}).get("title") or "Untitled"

    def _build_front_pages(self, book_el) -> list[Page]:
        info = book_el.find("bookinfo")
        pk, cfg = self.cfg["package"], self.cfg
        pages: list[Page] = []
        title = self._book_title(info)
        if cfg["half_title"]["enabled"]:
            page = self._page(
                pk["half_title_file"],
                "halftitle",
                "halftitlepage",
                cfg["half_title"]["heading"],
                "front",
                epub_type="frontmatter halftitlepage",
            )
            page.generated = True
            sec = etree.SubElement(page.body, "section")
            sec.set("epub_type", "halftitlepage")
            sec.set("role", "region")
            sec.set("aria_label", cfg["half_title"]["heading"])
            h = etree.SubElement(sec, "h1")
            h.text = cfg["half_title"]["heading"]
            if not cfg["half_title"]["heading_visible"]:
                h.set("class", "hidden-heading")
            etree.SubElement(sec, "p", {"class": "halftitle"}).text = title
            pages.append(page)
        page = self._page(pk["title_page_file"], "titlepage", "titlepage", title, "front")
        page.body.set("epub_type", "frontmatter")
        sec = etree.SubElement(page.body, "section")
        sec.set("epub_type", "titlepage")
        sec.set("class", "title-page")
        sec.set("aria_label", cfg["title_page"]["label"])
        sec.set("role", "region")
        if info is not None:
            t = info.find("title")
            if t is not None and self._has_content(t):
                h = self._inline_el("h1", t, class_="booktitle", id="titlepage-title")
                sec.append(h)
            for group in info.findall("authorgroup"):
                sec.extend(self._x_authorgroup(group))
        pages.append(page)
        legal = info.findall("legalnotice") if info is not None else []
        isbn = info.find("isbn") if info is not None else None
        if legal or isbn is not None:
            page = self._page(pk["copyright_file"], "copyright", "copyright-page", "", "front")
            page.title = cfg["copyright"]["label"]
            page.body.set("epub_type", "frontmatter")
            sec = etree.SubElement(page.body, "section")
            sec.set("epub_type", "copyright-page")
            sec.set("aria_label", cfg["copyright"]["label"])
            sec.set("role", "region")
            for child in info:  # bookinfo order: legal notice, ISBN, legal notice
                if child.tag == "legalnotice":
                    self._x_blocks(sec, child)
                elif child.tag == "isbn":
                    p = etree.SubElement(sec, "p", {"class": "isbn"})
                    self._label(p, "ISBN")
                    self._copy_inline(p, child)
            pages.append(page)
        return pages

    def _division_page(self, el, zone: str, kind_counts: dict, in_part: bool) -> Page | None:
        division = self._div_by_el.get(el)
        kind = division.kind if division is not None else el.tag
        pk = self.cfg["package"]
        div_id = (division.id if division is not None else None) or el.get("id")
        if kind == "index":
            name = pk["index_file"]
        elif kind in ("chapter", "part") and div_id:
            name = fmt(pk["chapter_file"], id=div_id)
        else:
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            name = fmt(pk["front_file"], kind=kind, n=kind_counts[kind])
            div_id = div_id or f"{kind}{kind_counts[kind]}"
        title_el = el.find("title")
        title_text = (
            " ".join("".join(title_el.itertext()).split())
            if title_el is not None and self._has_content(title_el)
            else kind.capitalize()
        )
        etype, role = EPUB_TYPES.get(kind, (kind, "doc-chapter" if kind == "chapter" else "region"))
        matter = {"front": "frontmatter", "body": "bodymatter", "back": "backmatter"}[zone]
        page = self._page(name, "division", kind, title_text, zone, epub_type=matter)
        page.division_id = div_id
        sec = etree.SubElement(page.body, "section")
        sec.set("id", div_id)
        sec.set("epub_type", etype)
        if role != "region":
            sec.set("role", role)
        self._heads = []
        self._depth = 0
        self._ol_end = 0
        self._math_seen = False
        if title_el is not None and self._has_content(title_el):
            h = self._heading(
                1,
                title_el,
                f"{div_id}-t",
                1,
                label=(
                    division.label if division is not None and kind in ("part", "chapter") else None
                ),
                fallback=title_text,
            )
            if kind == "part":
                h.set("class", "part-title")
            sec.append(h)
        if kind == "index":
            self._x_index_body(sec, el)
        elif kind == "part":
            for ch in el:
                if ch.tag in ("title", "chapter"):
                    continue
                sec.extend(self._x_block(ch))
        else:
            self._x_blocks(sec, el)
        page.heads = self._heads
        for head in page.heads:
            head.page = name
            if in_part and kind == "chapter":
                head.nest += 1
        page.math = self._math_seen
        return page

    def _cover_page(self) -> tuple[Page | None, bytes | None]:
        cfg = self.cfg
        if cfg["cover"]["mode"] == "none":
            return None, None
        data = None
        path = (self.settings.data.get("epub") or {}).get("cover_image")
        if path:
            base = Path(self.settings.file).parent if self.settings.file else Path.cwd()
            source = Path(path) if Path(path).is_absolute() else base / path
            if source.is_file():
                ext = Path(cfg["cover"]["image_name"]).suffix.lower()
                data = encode_image(
                    source, "png" if ext == ".png" else "jpg", None, 72, cfg["images"]["quality"]
                )
        if data is None:
            self.reviews.append(
                ReviewEntry(
                    "settings",
                    "front cover image to supply: the PDF has none and no cover_image was given "
                    "in the book settings; the ePub has no cover page (guideline EPUB item 1)",
                    severity="must_check",
                )
            )
            return None, None
        pk = self.cfg["package"]
        page = self._page(
            pk["cover_file"], "cover", "cover", cfg["cover"]["label"], "front", epub_type="cover"
        )
        page.generated = True
        sec = etree.SubElement(page.body, "section")
        sec.set("epub_type", "cover")
        sec.set("class", "cover-page")
        sec.set("aria_label", cfg["cover"]["label"])
        sec.set("role", "region")
        img = etree.SubElement(sec, "img")
        img.set("src", self._image_href(cfg["cover"]["image_name"]))
        img.set("alt", cfg["cover"]["alt"])
        return page, data

    def _package(self, book_el) -> Delivery:
        self._first_last_roles()
        pk = self.cfg["package"]
        pages: list[Page] = []
        cover, cover_bytes = self._cover_page()
        if cover is not None:
            pages.append(cover)
        front_pages = self._build_front_pages(book_el)
        counts: dict = {}
        zone_of = self._zone_map()
        division_pages: list[tuple[Page, str]] = []
        for el in book_el:
            if el.tag in ("bookinfo",):
                continue
            division = self._div_by_el.get(el)
            zone = zone_of.get(id(division), "body") if division is not None else "body"
            if el.tag == "part":
                part_page = self._division_page(el, zone, counts, False)
                if part_page is not None:
                    division_pages.append((part_page, zone))
                for chapter in el.findall("chapter"):
                    cp = self._division_page(chapter, "body", counts, True)
                    if cp is not None:
                        division_pages.append((cp, "body"))
            else:
                page = self._division_page(el, zone, counts, False)
                if page is not None:
                    division_pages.append((page, zone))
        toc_page = self._toc_page() if pk["toc_file"] else None
        # reading order: cover, half title, title page, copyright, leading dedication(s),
        # contents, the rest
        pages += front_pages
        rest = [p for p, _ in division_pages]
        lead = 0
        while lead < len(rest) and rest[lead].kind == "dedication":
            lead += 1
        pages += rest[:lead]
        if toc_page is not None:
            pages.append(toc_page)
        pages += rest[lead:]
        return self._assemble(pages, cover_bytes, book_el)

    def _zone_map(self) -> dict:
        zones = {}
        for d in self.doc.front:
            zones[id(d)] = "front"
        for d in self.doc.body:
            zones[id(d)] = "body"
        for d in self.doc.back + self.doc.after:
            zones[id(d)] = "back"
        return zones

    def _toc_entries(self, pages) -> list[Head]:
        out = []
        for page in pages:
            out += page.heads
        return out

    def _nav_ol(self, heads: list[Head], href_of) -> etree._Element:
        """Nested contents list; a head nests one level below the head before it at most."""
        root = etree.Element("ol")
        stack: list[list] = [[1, root, None]]  # [nest, ol, last li]
        for head in heads:
            nest = max(1, min(head.nest, stack[-1][0] + 1))
            while stack[-1][0] > nest and len(stack) > 1:
                stack.pop()
            if stack[-1][0] < nest and stack[-1][2] is not None:
                stack.append([nest, etree.SubElement(stack[-1][2], "ol"), None])
            li = etree.SubElement(stack[-1][1], "li")
            a = etree.SubElement(li, "a")
            a.set("href", href_of(head))
            a.set("id", f"toc-{head.id}")
            a.text = head.text
            stack[-1][2] = li
        return root

    def _toc_page(self) -> Page:
        pk = self.cfg["package"]
        page = self._page(
            pk["toc_file"],
            "toc",
            "toc",
            self.cfg["nav"]["toc_label"],
            "front",
            epub_type="frontmatter",
        )
        page.generated = True
        return page

    def _fill_toc_page(self, page: Page, pages: list[Page]):
        nav = etree.SubElement(page.body, "nav")
        nav.set("id", self.cfg["nav"]["toc_container_id"])
        nav.set("role", "doc-toc")
        h = etree.SubElement(nav, "h1")
        h.text = self.cfg["nav"]["toc_label"]
        heads = self._toc_entries(pages)
        nav.append(self._nav_ol(heads, lambda hd: f"{hd.page}#{hd.id}"))

    # ------------------------------------------------------------------ assembling

    def _assemble(self, pages: list[Page], cover_bytes: bytes | None, book_el) -> Delivery:
        pk, cfg = self.cfg["package"], self.cfg
        content = pk["content_folder"]
        text_dir = posixpath.join(content, pk["text_folder"]) if pk["text_folder"] else content
        toc_page = next((p for p in pages if p.role == "toc"), None)
        if toc_page is not None:
            self._fill_toc_page(toc_page, [p for p in pages if p.role == "division"])
        # ids and links
        where: dict[str, str] = {}
        for page in pages:
            for el in page.html.iter():
                eid = el.get("id")
                if eid:
                    where.setdefault(eid, page.name)
        broken = self._rewrite_links(pages, where)
        if broken:
            self.reviews.append(
                ReviewEntry(
                    "link",
                    f"{broken[0]} internal link(s) pointed at anchors that are not in the ePub "
                    f"(for example #{broken[1][0]}); the links were removed",
                )
            )
        delivery = Delivery(root=f"{self.isbn}_epub", ledger=self.ledger, reviews=self.reviews)
        files = delivery.files
        files["mimetype"] = b"application/epub+zip"
        package_path = posixpath.join(content, pk["package_file"])
        files["META-INF/container.xml"] = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            f'<rootfiles><rootfile full-path="{package_path}" '
            'media-type="application/oebps-package+xml"/></rootfiles>\n</container>\n'
        ).encode()
        for page in pages:
            files[posixpath.join(text_dir, page.name)] = document(page.html)
        # style sheets
        css_items = []
        for c in cfg["css"]:
            path = posixpath.join(content, pk["style_folder"], c["name"])
            files[path] = self._css_bytes(c)
            css_items.append(path)
        # images
        image_paths = []
        for job in self.images:
            image_paths.append(posixpath.join(content, pk["image_folder"], job.name))
            files[image_paths[-1]] = encode_image(
                self.ctx.book.image_path(job.source),
                cfg["images"]["format"],
                cfg["images"]["max_width"],
                72,
                cfg["images"]["quality"],
            )
        cover_path = None
        if cover_bytes is not None:
            cover_path = posixpath.join(content, pk["image_folder"], cfg["cover"]["image_name"])
            files[cover_path] = cover_bytes
        # navigation document and package document
        landmarks = self._landmarks(pages)
        nav_path = posixpath.join(content, pk["nav_file"])
        files[nav_path] = self._nav_bytes(pages, landmarks)
        files[package_path] = self._opf_bytes(
            pages, css_items, image_paths, cover_path, nav_path, landmarks, text_dir, book_el
        )
        delivery.main_file = package_path
        delivery.images = []
        delivery.alt_placeholders = self.alt_placeholders
        delivery.anchors = self.anchor_of_page
        delivery.generated_files = {posixpath.join(text_dir, p.name) for p in pages if p.generated}
        delivery.spine = [posixpath.join(text_dir, p.name) for p in pages]
        delivery.nav_path = nav_path
        delivery.divisions = self._division_rows(pages)
        delivery.split_files = {
            posixpath.join(text_dir, p.name): p.division_id or p.role for p in pages
        }
        return delivery

    def _division_rows(self, pages) -> list[dict]:
        rows = []
        for division, _el, _part in self.chapter_els:
            if division.kind != "chapter":
                continue
            book = self.ctx.book
            first = book.pages[division.first_page - 1]["label"] if division.first_page else ""
            last = book.pages[division.last_page - 1]["label"] if division.last_page else ""
            rows.append(
                {
                    "id": division.id,
                    "first": first,
                    "last": last,
                    "first_page": division.first_page,
                    "last_page": division.last_page,
                }
            )
        return rows

    def _css_bytes(self, entry: dict) -> bytes:
        from ..engine.paths import profiles_root

        if entry.get("text") is not None:
            text = entry["text"]
        else:
            path = profiles_root() / "css" / entry["source"]
            text = path.read_text("utf-8")
        colour = self.cfg["link_colour"]
        return text.replace("@LINK_COLOUR@", colour).encode("utf-8")

    def _rewrite_links(self, pages: list[Page], where: dict[str, str]):
        broken = 0
        examples: list[str] = []
        for page in pages:
            for a in list(page.html.iter("a")):
                href = a.get("href") or ""
                if not href.startswith("#"):
                    continue
                target = where.get(href[1:])
                if target is None:
                    broken += 1
                    examples.append(href[1:])
                    self._unwrap(a)
                elif target != page.name:
                    a.set("href", f"{target}{href}")
        return (broken, examples) if broken else None

    @staticmethod
    def _unwrap(a):
        """Replace a link by its content."""
        parent = a.getparent()
        idx = parent.index(a)
        prev = parent[idx - 1] if idx > 0 else None
        text, tail, children = a.text or "", a.tail or "", list(a)
        parent.remove(a)

        def after_prev(value: str):
            if prev is not None:
                prev.tail = (prev.tail or "") + value
            else:
                parent.text = (parent.text or "") + value

        after_prev(text)
        for i, child in enumerate(children):
            parent.insert(idx + i, child)
        if tail:
            if children:
                children[-1].tail = (children[-1].tail or "") + tail
            else:
                after_prev(tail)

    # ------------------------------------------------------------------ landmarks, nav, opf

    def _landmarks(self, pages: list[Page]) -> list[dict]:
        pk = self.cfg["package"]
        by_role = {p.role: p for p in pages}
        first_body = next((p for p in pages if p.role == "division" and p.zone == "body"), None)
        first_body = first_body or next((p for p in pages if p.role == "division"), None)
        out = []
        for entry in self.cfg["landmarks"]:
            t = entry["type"]
            page = None
            if t == "cover":
                page = by_role.get("cover")
            elif t == "halftitlepage":
                page = by_role.get("halftitle")
            elif t == "titlepage":
                page = by_role.get("titlepage")
            elif t == "copyright-page":
                page = by_role.get("copyright")
            elif t == "toc":
                page = by_role.get("toc")
            elif t == "bodymatter":
                page = first_body
            elif t in ("frontmatter", "backmatter"):
                zone = "front" if t == "frontmatter" else "back"
                page = next((p for p in pages if p.role == "division" and p.zone == zone), None)
            else:
                page = next((p for p in pages if p.role == "division" and p.kind == t), None)
            if page is not None:
                out.append({"type": t, "label": entry["label"], "page": page})
        _ = pk
        return out

    def _nav_bytes(self, pages: list[Page], landmarks: list[dict]) -> bytes:
        pk, cfg = self.cfg["package"], self.cfg

        # nav.xhtml sits in the content folder: its links go to <text folder>/<file>
        def href(name: str, frag: str | None = None) -> str:
            path = posixpath.join(pk["text_folder"], name) if pk["text_folder"] else name
            return path + (f"#{frag}" if frag else "")

        css = [posixpath.join(pk["style_folder"], c["name"]) for c in cfg["css"]]
        html, body = new_html(self.lang, cfg["nav"]["toc_label"], css)
        nav = etree.SubElement(body, "nav")
        nav.set("epub_type", "toc")
        nav.set("id", cfg["nav"]["toc_container_id"])
        etree.SubElement(nav, "h1").text = cfg["nav"]["toc_label"]
        heads = self._toc_entries([p for p in pages if p.role == "division"])
        nav.append(self._nav_ol(heads, lambda h: href(h.page, h.id)))
        if cfg["nav"]["page_list"]:
            pl = etree.SubElement(body, "nav")
            pl.set("epub_type", "page-list")
            pl.set("hidden", "")
            etree.SubElement(pl, "h1").text = cfg["nav"]["page_list_label"]
            ol = etree.SubElement(pl, "ol")
            for page in pages:
                for span in page.html.iter("span"):
                    if span.get("epub_type") == "pagebreak":
                        li = etree.SubElement(ol, "li")
                        a = etree.SubElement(li, "a")
                        a.set("href", href(page.name, span.get("id")))
                        a.text = span.get("title")
        if cfg["nav"]["landmarks"] and landmarks:
            lm = etree.SubElement(body, "nav")
            lm.set("epub_type", "landmarks")
            lm.set("hidden", "")
            etree.SubElement(lm, "h1").text = cfg["nav"]["landmarks_label"]
            ol = etree.SubElement(lm, "ol")
            for entry in landmarks:
                li = etree.SubElement(ol, "li")
                a = etree.SubElement(li, "a")
                a.set("epub_type", entry["type"])
                a.set("href", href(entry["page"].name))
                a.text = entry["label"]
        return document(html)

    def _metadata(self, pages: list[Page], book_el) -> dict:
        info = book_el.find("bookinfo")
        creators, contributors = [], []
        groups = self.settings.data.get("authorgroups") or []
        if groups:
            for group in groups:
                for person in group:
                    name = " ".join(x for x in (person.get("firstname"), person["surname"]) if x)
                    role = (person.get("contrib") or "").lower()
                    (contributors if "foreword" in role else creators).append(name)
        else:
            for group in self.doc.bookinfo.authors:
                for person in group:
                    parts = [r.plain().strip() for r in (person.firstname, person.surname) if r]
                    role = person.contrib.plain().lower() if person.contrib else ""
                    name = " ".join(x for x in parts if x)
                    if name:
                        (contributors if "foreword" in role else creators).append(name)
        return {"title": self._book_title(info), "creators": creators, "contributors": contributors}

    def _opf_bytes(
        self, pages, css_items, image_paths, cover_path, nav_path, landmarks, text_dir, book_el
    ) -> bytes:
        pk, cfg = self.cfg["package"], self.cfg
        content = pk["content_folder"]
        meta = self._metadata(pages, book_el)
        modified = self.ctx.options.get("modified") or f"{self.ctx.profile.date}T00:00:00Z"
        if self.settings.data.get("isbn"):
            ident = f"urn:isbn:{self.settings.data['isbn']}"
        else:
            ident = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, self.ctx.book.sha256))
        publisher = self.settings.data.get("publisher") or cfg["metadata"]["publisher"]

        def rel(path: str) -> str:
            return posixpath.relpath(path, content)

        L = ['<?xml version="1.0" encoding="UTF-8"?>']
        L.append(
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
            f'unique-identifier="pub-id" xml:lang="{escape(self.lang)}">'
        )
        L.append(
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:opf="http://www.idpf.org/2007/opf">'
        )
        L.append(f'<dc:identifier id="pub-id">{escape(ident)}</dc:identifier>')
        L.append(f"<dc:title>{escape(meta['title'])}</dc:title>")
        L.append(f"<dc:language>{escape(self.lang)}</dc:language>")
        for i, name in enumerate(meta["creators"], 1):
            L.append(f'<dc:creator id="creator{i}">{escape(name)}</dc:creator>')
        for i, name in enumerate(meta["contributors"], 1):
            L.append(f'<dc:contributor id="contributor{i}">{escape(name)}</dc:contributor>')
        if publisher:
            L.append(f"<dc:publisher>{escape(publisher)}</dc:publisher>")
        if cfg["metadata"]["rights"]:
            L.append(f"<dc:rights>{escape(cfg['metadata']['rights'])}</dc:rights>")
        L.append(f'<meta property="dcterms:modified">{escape(modified)}</meta>')
        if cfg["accessibility"]["enabled"]:
            L += self._a11y_meta(pages, image_paths, cover_path)
        L.append("</metadata>")
        L.append("<manifest>")
        ids: dict[str, str] = {}
        L.append(
            f'<item id="nav" href="{escape(rel(nav_path))}" '
            'media-type="application/xhtml+xml" properties="nav"/>'
        )
        for i, path in enumerate(css_items, 1):
            L.append(f'<item id="css{i}" href="{escape(rel(path))}" media-type="text/css"/>')
        for i, page in enumerate(pages, 1):
            ids[page.name] = f"p{i:03d}"
            props = ' properties="mathml"' if page.math else ""
            L.append(
                f'<item id="{ids[page.name]}" href="{escape(rel(posixpath.join(text_dir, page.name)))}" '  # noqa: E501
                f'media-type="application/xhtml+xml"{props}/>'
            )
        for i, path in enumerate(image_paths, 1):
            mt = MEDIA_TYPES[Path(path).suffix.lower()]
            L.append(f'<item id="img{i:04d}" href="{escape(rel(path))}" media-type="{mt}"/>')
        if cover_path:
            mt = MEDIA_TYPES[Path(cover_path).suffix.lower()]
            L.append(
                f'<item id="cover-image" href="{escape(rel(cover_path))}" media-type="{mt}" '
                'properties="cover-image"/>'
            )
        L.append("</manifest>")
        L.append("<spine>")
        for page in pages:
            L.append(f'<itemref idref="{ids[page.name]}"/>')
        L.append("</spine>")
        if cfg["guide"]["enabled"] and landmarks:
            L.append("<guide>")
            for entry in landmarks:
                gtype = GUIDE_TYPES.get(entry["type"])
                if gtype:
                    href = rel(posixpath.join(text_dir, entry["page"].name))
                    L.append(
                        f"<reference type={quoteattr(gtype)} title={quoteattr(entry['label'])} "
                        f"href={quoteattr(href)}/>"
                    )
            L.append("</guide>")
        L.append("</package>")
        return ("\n".join(L) + "\n").encode("utf-8")

    def _a11y_meta(self, pages, image_paths, cover_path) -> list[str]:
        cfg = self.cfg
        has_images = bool(image_paths)
        has_math = any(p.math for p in pages)
        placeholders = bool(self.alt_placeholders)
        features = ["structuralNavigation", "tableOfContents", "readingOrder"]
        if cfg["nav"]["page_list"] and any(
            s.get("epub_type") == "pagebreak" for p in pages for s in p.html.iter("span")
        ):
            features.append("printPageNumbers")
        if any(p.kind == "index" for p in pages):
            features.append("index")
        if has_images and not placeholders:
            features.append("alternativeText")
        if has_math:
            features.append("MathML")
        modes = ["textual"] + (["visual"] if has_images or cover_path else [])
        sufficient = "textual,visual" if has_images and "visual" in modes else "textual"
        summary = [
            "This publication has a table of contents and headings that structure each chapter."
        ]
        if "printPageNumbers" in features:
            summary.append("Print page numbers are marked and listed in the page list.")
        if has_images:
            summary.append(
                "Some images still have placeholder descriptions."
                if placeholders
                else "Images have text descriptions."
            )
        if has_math:
            summary.append("Equations are in MathML.")
        out = []
        for mode in modes:
            out.append(f'<meta property="schema:accessMode">{mode}</meta>')
        out.append(f'<meta property="schema:accessModeSufficient">{sufficient}</meta>')
        for f in features:
            out.append(f'<meta property="schema:accessibilityFeature">{f}</meta>')
        out.append(
            f'<meta property="schema:accessibilityHazard">{cfg["accessibility"]["hazard"]}</meta>'
        )
        out.append(
            f'<meta property="schema:accessibilitySummary">{escape(" ".join(summary))}</meta>'
        )
        if cfg["accessibility"]["conforms_to"]:
            out.append(
                f'<meta property="dcterms:conformsTo">{escape(cfg["accessibility"]["conforms_to"])}</meta>'  # noqa: E501
            )
        return out
