"""HTML5 writer: one accessible page per division, a contents page (``index.html``), a style
sheet and the images.

The conversion of the content tree into (X)HTML elements is the ePub writer's, unchanged
(headings, lists, tables with caption and ``th scope``, figures with ``alt``, MathML, page
breaks as ``span role="doc-pagebreak"`` with the printed label, notes, ``lang``): the same
text hosts, so the ledger and the lossless check hold. This writer sets the file layout from
the profile's ``html`` section and writes the pages in HTML syntax."""

from __future__ import annotations

import copy
import dataclasses

from lxml import etree

from ..engine.format_profile import format_section, has_section
from ..engine.model import ReviewEntry
from ..engine.profile import epub_section
from .base import Delivery, WriteContext
from .docbook import DocBookWriter
from .epub3 import Epub3Writer, Page
from .xhtml import BLOCKS, CONTAINERS, new_html

ATTRS = {
    "aria_label": "aria-label",
    "aria_hidden": "aria-hidden",
    "aria_labelledby": "aria-labelledby",
}
DROP_ATTRS = ("epub_type", "xml_lang")


def html_cfg(profile) -> dict:
    """The converter's settings for an HTML run: its defaults, with the ``html`` section on
    top. The profile's ``epub`` section is not read."""
    bare = dataclasses.replace(profile, data={k: v for k, v in profile.data.items() if k != "epub"})
    cfg = epub_section(bare)
    h = format_section(profile, "html")
    pk = cfg["package"]
    pk.update(
        content_folder="",
        text_folder="",
        style_folder="",
        image_folder=profile.get("delivery.images_folder") or "images",
        toc_file=h["package"]["index_file"],
        title_page_file=h["package"]["title_file"],
        copyright_file=h["package"]["copyright_file"],
        chapter_file=h["package"]["chapter_file"],
        front_file=h["package"]["front_file"],
        index_file=h["package"]["book_index_file"],
    )
    cfg["css"] = h["css"]
    cfg["link_colour"] = h["link_colour"]
    cfg["half_title"]["enabled"] = False
    cfg["cover"]["mode"] = "none"
    cfg["nav"].update(
        toc_depth=h["nav"]["toc_depth"],
        toc_label=h["nav"]["toc_label"],
        toc_return="none",
        page_list=h["nav"]["page_list"],
        page_list_label=h["nav"]["page_list_label"],
    )
    cfg["math"]["mathml"] = h["math"]["mathml"]
    cfg["metadata"]["language"] = h["language"]
    cfg["title_page"]["label"] = h["labels"]["title_page"]
    cfg["copyright"]["label"] = h["labels"]["copyright"]
    cfg["_html"] = h
    return cfg


class HtmlWriter(Epub3Writer):
    name = "html"

    def write(self, doc, ctx: WriteContext) -> Delivery:
        self.cfg = html_cfg(ctx.profile)
        self.has_html_section = has_section(ctx.profile, "html")
        self._div_by_el: dict = {}
        self._depth = 0
        self._heads = []
        self._footnotes = 0
        self._ol_end = 0
        self._math_seen = False
        self.lang = self._language(ctx)
        return DocBookWriter.write(self, doc, ctx)

    def _page(self, name, role, kind, title, zone, **body_attrs) -> Page:
        html, body = new_html(self.lang, title or kind, self._css_hrefs())
        head = html.find("head")
        meta = etree.Element("meta")
        meta.set("name", "viewport")
        meta.set("content", "width=device-width, initial-scale=1")
        head.insert(1, meta)
        body_attrs.pop("epub_type", None)
        for k, v in body_attrs.items():
            body.set(k.rstrip("_"), v)
        return Page(name, role, kind, title or kind, html, body, zone)

    def _build_front_pages(self, book_el) -> list[Page]:
        pages = super()._build_front_pages(book_el)
        for page in pages:  # every page has a main heading (a hidden one where the book has none)
            if page.body.find(".//h1") is None:
                sec = page.body.find("section")
                h = etree.Element("h1")
                h.set("class", "hidden-heading")
                span = etree.SubElement(h, "span")
                span.set("class", "label")
                span.text = page.title
                (sec if sec is not None else page.body).insert(0, h)
        return pages

    def _css_hrefs(self) -> list[str]:
        return [c["name"] for c in self.cfg["css"]]

    def _assemble(self, pages, cover_bytes, book_el) -> Delivery:
        cfg = self.cfg
        toc_page = next((p for p in pages if p.role == "toc"), None)
        if toc_page is not None:
            self._fill_toc_page(toc_page, [p for p in pages if p.role == "division"])
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
                    f"{broken[0]} internal link(s) pointed at anchors that are not in the "
                    f"pages (for example #{broken[1][0]}); the links were removed",
                )
            )
        if toc_page is not None and cfg["nav"]["page_list"]:
            self._page_list(toc_page, pages)
        delivery = Delivery(root=f"{self.isbn}_html", ledger=self.ledger, reviews=self.reviews)
        for page in pages:
            delivery.files[page.name] = self._document(page)
        for c in cfg["css"]:
            delivery.files[c["name"]] = self._css_bytes(c)
        delivery.main_file = cfg["package"]["toc_file"]
        delivery.images = self.images
        delivery.alt_placeholders = self.alt_placeholders
        delivery.anchors = self.anchor_of_page
        delivery.generated_files = {p.name for p in pages if p.generated}
        delivery.spine = [p.name for p in pages]
        delivery.divisions = self._division_rows(pages)
        delivery.split_files = {p.name: p.division_id or p.role for p in pages}
        return delivery

    def _page_list(self, toc_page: Page, pages: list[Page]):
        nav = etree.SubElement(toc_page.body, "nav")
        nav.set("id", "page-list")
        nav.set("role", "doc-pagelist")
        h = etree.SubElement(nav, "h2")
        h.text = self.cfg["nav"]["page_list_label"]
        ol = etree.SubElement(nav, "ol")
        for page in pages:
            for span in page.html.iter("span"):
                if span.get("role") == "doc-pagebreak":
                    li = etree.SubElement(ol, "li")
                    a = etree.SubElement(li, "a")
                    a.set("href", f"{page.name}#{span.get('id')}")
                    a.text = span.get("title") or ""

    def _document(self, page: Page) -> bytes:
        from ..formats.markup import serialize

        html = copy.deepcopy(page.html)
        html.set("lang", html.get("lang") or self.lang)
        for node in html.iter():
            if not isinstance(node.tag, str):
                continue
            for key in DROP_ATTRS:
                node.attrib.pop(key, None)
            for key, new in ATTRS.items():
                if key in node.attrib:
                    node.set(new, node.attrib.pop(key))
        return (
            "<!DOCTYPE html>\n"
            + serialize(html, CONTAINERS, html=True, only_children=BLOCKS)
            + "\n"
        ).encode("utf-8")
