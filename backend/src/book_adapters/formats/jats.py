"""JATS 1.4 (ANSI/NISO Z39.96-2024) Journal Publishing tag set, MathML 3, from the semantic
tree: the book as one ``article`` (front, body, back), or one ``article`` per division.

Authors, title and legal notice are the text the book prints; journal data, dates and
identifiers come from the profile and the book settings, and anything missing is listed as to
supply, never made up."""

from __future__ import annotations

from lxml import etree

from .jatsbase import MML, PREFIXES, XLINK, JatsBase
from .markup import add_text, text_of

PUBLIC_ID = "-//NLM//DTD JATS (Z39.96) Journal Publishing DTD with MathML3 v1.4 20241031//EN"
SYSTEM_ID = "JATS-journalpublishing1-4-mathml3.dtd"
SEC_TYPES = {"preface": "preface", "dedication": "dedication", "chapter": "chapter",
             "part": "part", "index": "index", "bibliography": "bibliography",
             "appendix": "appendix"}  # fmt: skip


class JatsConverter(JatsBase):
    # ------------------------------------------------------------------ whole book

    def build(self) -> list[tuple[str, etree._Element]]:
        """[(file key, article element)]: one, or one per division."""
        s = self.src
        divisions = s.divisions()
        if self.cfg["mode"] == "per_article":
            self.article_ids = {}
            for e in s.bookinfo.iter():
                if e.get("id"):
                    self.article_ids[e.get("id")] = "front"
            for k, d in enumerate(divisions, 1):
                for e in d.iter():
                    if e.get("id"):
                        self.article_ids[e.get("id")] = f"{k:03d}"
            self.current_key = "front"
            out = [("front", self.article(None, divisions=[]))]
            for k, d in enumerate(divisions, 1):
                self.current_key = f"{k:03d}"
                out.append((self.current_key, self.article(d, divisions=[d])))
            return out
        return [("book", self.article(None, divisions=divisions))]

    def article(self, division, divisions):
        s = self.src
        self.page_list = []
        art = etree.Element("article", {"article-type": self.cfg["article_type"]})
        front = etree.SubElement(art, "front")
        self.journal_meta(front)
        meta = etree.SubElement(front, "article-meta")
        self.article_meta(meta, division)
        body = etree.SubElement(art, "body")
        back = etree.Element("back")
        if division is None:
            self.title_page_sections(body)
        for d in divisions:
            zone = d.get("x-zone")
            if self.cfg["mode"] == "per_article":
                self.division_body(d, body)
                continue
            self.division(d, back if zone == "back" else body, back)
        if not len(body):
            etree.SubElement(body, "p")
        if len(back):
            art.append(back)
        self.page_labels(meta)
        if self.broken_links:
            self.review(
                "link",
                f"{self.broken_links} internal link(s) pointed at anchors that are not in the "
                f"output (for example #{self.broken_examples[0]}); the links were removed",
            )
        _ = s
        return art

    # ------------------------------------------------------------------ front

    def journal_meta(self, front):
        j = self.cfg["journal"]
        s = self.src
        meta = etree.SubElement(front, "journal-meta")
        jid = j["id"] or "TO_SUPPLY"
        etree.SubElement(meta, "journal-id", {"journal-id-type": "publisher-id"}).text = jid
        grp = etree.SubElement(meta, "journal-title-group")
        etree.SubElement(grp, "journal-title").text = j["title"] or s.title_text() or "TO_SUPPLY"
        issn = etree.SubElement(meta, "issn")
        issn.text = j["issn"] or None
        pub = self.src.settings.data.get("publisher") or j["publisher"]
        if pub:
            etree.SubElement(etree.SubElement(meta, "publisher"), "publisher-name").text = pub
        for field, value in (("journal id", j["id"]), ("ISSN", j["issn"]), ("publisher", pub)):
            if not value:
                self.review(
                    "settings",
                    f"JATS {field} to supply (jats.journal in the profile or the book settings)",
                )

    def article_meta(self, meta, division):
        s = self.src
        tg = etree.SubElement(meta, "title-group")
        at = etree.SubElement(tg, "article-title")
        if division is None:
            title = s.title_el()
            if title is not None:
                self.inline_into(title, at)
        else:
            t = division.find("title")
            if t is not None:
                self.label_inline(at, division.get("label"))
                self.inline_into(t, at)
        if division is None:
            self.contribs(meta)
        isbn = s.isbn()
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
                "settings", "JATS pub-date to supply (publication_date in the book settings)"
            )
        if isbn:
            etree.SubElement(meta, "isbn").text = isbn

    def label_inline(self, parent, label):
        if label and label.strip():
            span = etree.SubElement(parent, "named-content", {"content-type": "label"})
            span.text = label
            span.tail = " "

    def contribs(self, meta):
        s = self.src
        info = s.bookinfo
        groups = info.findall("authorgroup")
        for g in groups:
            cg = etree.SubElement(meta, "contrib-group")
            for author in g.findall("author"):
                self.contrib(cg, author)
            if not len(cg):
                meta.remove(cg)

    def contrib(self, cg, author):
        types = self.cfg["contrib_types"]
        role = next((c for c in author if c.tag == "contrib"), None)
        kind = "author"
        if role is not None:
            kind = types.get(text_of(role).lower(), "author")
        c = etree.SubElement(cg, "contrib", {"contrib-type": kind})
        sn = etree.SubElement(c, "string-name")
        for child in author:
            if child.tag == "contrib":
                self.inline_into(child, sn)
                add_text(sn, " ")
            elif child.tag == "firstname":
                n = etree.SubElement(sn, "given-names")
                self.inline_into(child, n)
                n.tail = " "
            elif child.tag == "surname":
                n = etree.SubElement(sn, "surname")
                self.inline_into(child, n)
        for child in author:
            if child.tag == "othername":
                d = etree.SubElement(c, "degrees")
                self.inline_into(child, d)
        for child in author:
            if child.tag == "affiliation":
                aff = etree.SubElement(c, "aff")
                for sub in child.iter():
                    if sub is child or sub.tag == "address":
                        continue
                    node = etree.SubElement(aff, self.aff_tag(sub.tag), self.aff_attrs(sub.tag))
                    self.inline_into(sub, node)
                    node.tail = " "
                if len(aff):
                    aff[-1].tail = None
        if len(sn) == 0 and not sn.text:
            c.remove(sn)

    @staticmethod
    def aff_tag(tag):
        return {"city": "city", "state": "state", "country": "country"}.get(tag, "institution")

    @staticmethod
    def aff_attrs(tag):
        return {} if tag in ("city", "state", "country") else {"content-type": tag}

    def page_labels(self, meta):
        if not self.page_list:
            return
        grp = etree.SubElement(meta, "custom-meta-group")
        for p in self.page_list:
            cm = etree.SubElement(grp, "custom-meta", {"specific-use": "page-label"})
            etree.SubElement(cm, "meta-name").text = p.id
            etree.SubElement(cm, "meta-value").text = p.label

    # ------------------------------------------------------------------ body

    def title_page_sections(self, body):
        info = self.src.bookinfo
        legal = [c for c in info if c.tag in ("legalnotice", "isbn")]
        if not legal:
            return
        sec = etree.SubElement(body, "sec", {"sec-type": "copyright"})
        etree.SubElement(sec, "title")
        for c in legal:
            if c.tag == "legalnotice":
                self.blocks(c, sec)
            else:
                p = etree.SubElement(self.slot(sec, "para"), "p", {"content-type": "isbn"})
                self.inline_into(c, p)

    def division(self, el, body, back):
        kind = self.src.kind(el)
        if kind == "bibliography" or el.tag == "bibliography":
            self.b_bibliography(el, back if body is back else body)
            return
        attrs = {"sec-type": SEC_TYPES.get(kind, kind)}
        if el.get("id"):
            attrs["id"] = el.get("id")
        parent = body
        if kind == "appendix" and body is back:
            group = back.find("app-group")
            if group is None:
                group = etree.SubElement(back, "app-group")
            parent = group
            sec = etree.SubElement(group, "app", {k: v for k, v in attrs.items() if k == "id"})
        else:
            sec = etree.SubElement(self.slot(parent, "sec"), "sec", attrs)
        self.label(sec, el.get("label"))
        t = el.find("title")
        title = etree.SubElement(sec, "title")
        if t is not None:
            self.inline_into(t, title)
        self.division_content(el, sec)

    def division_body(self, el, body):
        self.division_content(el, body)

    def division_content(self, el, sec):
        kind = self.src.kind(el)
        if kind == "index" or el.tag == "index":
            self.index_body(el, sec)
        elif el.tag == "bibliography":
            self.refs_into(el, sec)
        elif el.tag == "part":
            for ch in el:
                if ch.tag == "title":
                    continue
                if ch.tag == "chapter":
                    self.division(ch, sec, sec)
                else:
                    self.block(ch, sec)
        else:
            self.blocks(el, sec)
        if sec.tag in ("sec", "app") and not [c for c in sec if c.tag not in ("title", "label")]:
            etree.SubElement(sec, "p")
            self.review("structure", f"{kind} has no content (an empty p was written)")

    def refs_into(self, el, sec):
        rl = etree.SubElement(sec, "ref-list")
        self.refs(el, rl)
        self.blocks(el, sec, skip=("title", "bibliomixed"))

    # --- index as nested lists

    def index_body(self, el, sec):
        for ch in el:
            if ch.tag == "title":
                continue
            if ch.tag == "indexdiv":
                t = ch.find("title")
                holder = sec
                if t is not None and (t.text or len(t)):
                    holder = etree.SubElement(
                        self.slot(sec, "sec"), "sec", {"sec-type": "indexdiv"}
                    )
                    self.title(holder, t)
                self.index_entries(ch, holder)
            elif ch.tag == "indexentry":
                self.index_entries(el, sec)
                break
            else:
                self.block(ch, sec)

    def index_entries(self, src, parent):
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
        lst = etree.SubElement(
            self.slot(parent, "para"), "list", {"list-type": "simple", "specific-use": "index"}
        )
        for ie in entries:
            li = sub = tert = sec_li = None
            for part in ie:
                if part.tag == "primaryie":
                    li = etree.SubElement(lst, "list-item")
                    self.inline_into(part, etree.SubElement(li, "p"))
                    sub = tert = None
                elif part.tag == "secondaryie":
                    if sub is None:
                        sub = etree.SubElement(li, "list", {"list-type": "simple"})
                    sec_li = etree.SubElement(sub, "list-item")
                    self.inline_into(part, etree.SubElement(sec_li, "p"))
                    tert = None
                elif part.tag == "tertiaryie":
                    if tert is None:
                        tert = etree.SubElement(sec_li, "list", {"list-type": "simple"})
                    t_li = etree.SubElement(tert, "list-item")
                    self.inline_into(part, etree.SubElement(t_li, "p"))


_ = (XLINK, MML, PREFIXES)
