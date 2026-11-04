"""BITS 2.2 (Book Interchange Tag Suite, the JATS extension for books) from the semantic tree.

``book`` with ``book-meta`` (title, contributors, ISBN, publisher, date), ``front-matter``
(title page notices, prefaces, dedication), ``book-body`` of ``book-part`` (parts and chapters),
``book-back`` (appendices, index, reference lists). The block mapping is JATS's
(:mod:`jatsbase`); the index is ``index`` / ``index-entry`` with page-number cross-references."""

from __future__ import annotations

from lxml import etree

from .jats import JatsConverter
from .markup import text_of

PUBLIC_ID = "-//NLM//DTD BITS Book Interchange DTD v2.2 20250930//EN"
SYSTEM_ID = "BITS-book2-2.dtd"


class BitsConverter(JatsConverter):
    def build(self):
        s = self.src
        book = etree.Element("book", {"book-type": self.cfg["book_type"]})
        meta = etree.SubElement(book, "book-meta")
        self.book_meta(meta)
        front = etree.Element("front-matter")
        body = etree.Element("book-body")
        back = etree.Element("book-back")
        self.title_page_part(front)
        divisions = s.divisions()
        if not any(d.get("x-zone") == "body" for d in divisions):
            zones = {id(d): "body" for d in divisions if d.get("x-zone") != "back"}
        else:
            zones = {}
        for d in divisions:
            zone = zones.get(id(d), d.get("x-zone"))
            if zone == "front":
                self.front_part(d, front)
            elif zone == "back":
                self.back_part(d, back)
            else:
                self.book_part(d, body)
        if len(front):
            book.append(front)
        if len(body):
            book.append(body)
        if len(back):
            book.append(back)
        self.page_labels(meta)
        if self.broken_links:
            self.review(
                "link",
                f"{self.broken_links} internal link(s) pointed at anchors that are not in the "
                f"output (for example #{self.broken_examples[0]}); the links were removed",
            )
        return [("book", book)]

    # ------------------------------------------------------------------ book-meta

    def book_meta(self, meta):
        s = self.src
        grp = etree.SubElement(meta, "book-title-group")
        t = s.title_el()
        bt = etree.SubElement(grp, "book-title")
        if t is not None:
            self.inline_into(t, bt)
        self.contribs(meta)
        pd = s.settings.data.get("publication_date")
        if pd:
            parts = pd.split("-")
            node = etree.SubElement(
                meta, "pub-date", {"publication-format": "print", "date-type": "pub"}
            )
            if len(parts) == 3:
                etree.SubElement(node, "day").text = parts[2]
            if len(parts) >= 2:
                etree.SubElement(node, "month").text = parts[1]
            etree.SubElement(node, "year").text = parts[0]
        else:
            etree.SubElement(meta, "pub-date-not-available")
            self.review(
                "settings", "BITS pub-date to supply (publication_date in the book settings)"
            )
        if s.isbn():
            etree.SubElement(meta, "isbn", {"publication-format": "print"}).text = s.isbn()
        pub = s.settings.data.get("publisher") or self.cfg["publisher"]
        if pub:
            etree.SubElement(etree.SubElement(meta, "publisher"), "publisher-name").text = pub
        else:
            self.review(
                "settings",
                "BITS publisher to supply (publisher in the book settings or bits.publisher)",
            )
        if s.edition():
            etree.SubElement(meta, "edition").text = s.edition()

    # ------------------------------------------------------------------ parts

    def part_meta(self, part, el, kind):
        title = el.find("title")
        if title is None and not el.get("label"):
            return
        pm = etree.SubElement(part, "book-part-meta")
        grp = etree.SubElement(pm, "title-group")
        self.label(grp, el.get("label"))
        t = etree.SubElement(grp, "title")
        if title is not None:
            self.inline_into(title, t)

    def title_page_part(self, front):
        info = self.src.bookinfo
        legal = [c for c in info if c.tag in ("legalnotice", "isbn")]
        if not legal:
            return
        fmp = etree.SubElement(front, "front-matter-part", {"book-part-type": "copyright"})
        body = etree.SubElement(fmp, "named-book-part-body")
        for c in legal:
            if c.tag == "legalnotice":
                self.blocks(c, body)
            else:
                p = etree.SubElement(body, "p", {"content-type": "isbn"})
                self.inline_into(c, p)
        if not len(body):
            fmp.getparent().remove(fmp)

    def b_bibliography(self, el, parent):
        """A reference list inside a part: BITS puts it in the part's ``back``."""
        host = parent
        if (
            parent.tag == "body"
            and parent.getparent() is not None
            and parent.getparent().tag == "book-part"
        ):
            part = parent.getparent()
            host = part.find("back")
            if host is None:
                host = etree.SubElement(part, "back")
        elif parent.tag == "named-book-part-body":
            part = parent.getparent()
            host = part.find("back")
            if host is None:
                host = etree.SubElement(part, "back")
        rl = etree.SubElement(host, "ref-list", {"id": el.get("id")} if el.get("id") else {})
        t = el.find("title")
        if t is not None and (t.text or len(t)):
            self.title(rl, t)
        self.blocks(el, rl, skip=("title", "bibliomixed"))
        self.refs(el, rl)

    def fill_body(self, el, body):
        kind = self.src.kind(el)
        if kind == "index" or el.tag == "index":
            return
        if el.tag == "part":
            for ch in el:
                if ch.tag in ("title", "chapter"):
                    continue
                self.block(ch, body)
        else:
            self.blocks(el, body)

    def front_part(self, el, front):
        kind = self.src.kind(el)
        if el.tag == "bibliography":
            self.b_bibliography(el, front)
            return
        if kind == "index":
            self.index(el, front)
            return
        attrs = {"book-part-type": kind}
        if el.get("id"):
            attrs["id"] = el.get("id")
        part = etree.SubElement(front, "front-matter-part", attrs)
        self.part_meta(part, el, kind)
        body = etree.SubElement(part, "named-book-part-body")
        self.fill_body(el, body)
        if el.tag == "part":  # front matter holds no book-part: its chapters become sections
            for ch in el.findall("chapter"):
                self.division(ch, body, body)
        if not len(body):
            etree.SubElement(body, "p")
            self.review("structure", f"{kind} has no content (an empty p was written)")

    def book_part(self, el, body):
        kind = self.src.kind(el)
        if el.tag == "bibliography":
            self.b_bibliography(el, body)
            return
        if kind == "index":
            self.index(el, body)
            return
        attrs = {"book-part-type": kind}
        if el.get("id"):
            attrs["id"] = el.get("id")
        part = etree.SubElement(body, "book-part", attrs)
        self.part_meta(part, el, kind)
        pbody = etree.SubElement(part, "body")
        self.fill_body(el, pbody)
        if el.tag == "part":
            for ch in el.findall("chapter"):
                self.book_part(ch, pbody)
        if not len(pbody):
            etree.SubElement(pbody, "p")
            self.review("structure", f"{kind} has no content (an empty p was written)")

    def back_part(self, el, back):
        kind = self.src.kind(el)
        if el.tag == "bibliography":
            rl = etree.SubElement(back, "ref-list", {"id": el.get("id")} if el.get("id") else {})
            t = el.find("title")
            if t is not None and (t.text or len(t)):
                self.title(rl, t)
            self.refs(el, rl)
            return
        if kind == "index":
            self.index(el, back)
            return
        attrs = {"book-part-type": kind}
        if el.get("id"):
            attrs["id"] = el.get("id")
        part = etree.SubElement(back, "book-part", attrs)
        self.part_meta(part, el, kind)
        body = etree.SubElement(part, "body")
        self.fill_body(el, body)
        if el.tag == "part":
            for ch in el.findall("chapter"):
                self.book_part(ch, body)
        if not len(body):
            etree.SubElement(body, "p")

    # ------------------------------------------------------------------ index

    def index(self, el, parent):
        attrs = {"id": el.get("id")} if el.get("id") else {}
        idx = etree.SubElement(parent, "index", attrs)
        t = el.find("title")
        if t is not None and (t.text or len(t) or el.get("label")):
            grp = etree.SubElement(idx, "index-title-group")
            self.label(grp, el.get("label"))
            self.title(grp, t)
        before = len(idx)
        for ch in el:
            if ch.tag == "title":
                continue
            if ch.tag == "indexdiv":
                div = etree.SubElement(idx, "index-div")
                dt = ch.find("title")
                if dt is not None and (dt.text or len(dt)):
                    g = etree.SubElement(div, "index-title-group")
                    self.title(g, dt)
                self.entries(ch, div)
                if not [c for c in div if c.tag in ("index-entry", "index-div")]:
                    idx.remove(div)
            elif ch.tag == "indexentry":
                self.entries(el, idx)
                break
            else:
                self.block(ch, idx)
        if not [c for c in idx if c.tag in ("index-entry", "index-div")]:
            etree.SubElement(etree.SubElement(idx, "index-entry"), "term")
            self.review("structure", "index without entries")
        _ = before

    def entries(self, src, parent):
        for ie in src:
            if ie.tag == "indexentry":
                top = cur2 = cur3 = None
                for part in ie:
                    if part.tag == "primaryie":
                        top = etree.SubElement(parent, "index-entry")
                        self.inline_into(part, etree.SubElement(top, "term"))
                        cur2 = cur3 = None
                    elif part.tag == "secondaryie":
                        cur2 = etree.SubElement(top, "index-entry")
                        self.inline_into(part, etree.SubElement(cur2, "term"))
                        cur3 = None
                    elif part.tag == "tertiaryie":
                        cur3 = etree.SubElement(cur2, "index-entry")
                        self.inline_into(part, etree.SubElement(cur3, "term"))
            elif ie.tag not in ("title",):
                self.block(ie, parent)


_ = text_of
