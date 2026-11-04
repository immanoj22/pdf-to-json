"""A read-only view of the semantic tree for the format transformers: metadata, divisions,
page list, images, alt text and equations. Nothing here writes delivery text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

from ..engine.model import ReviewEntry
from .markup import text_of

DIVISION_TAGS = ("preface", "dedication", "appendix", "part", "chapter", "index", "bibliography")
ROMAN = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)


@dataclass
class Person:
    contrib: str = ""
    given: str = ""
    surname: str = ""
    degrees: str = ""
    jobtitle: str = ""
    orgname: str = ""
    orgdiv: list[str] = field(default_factory=list)
    address: str = ""

    @property
    def name(self) -> str:
        return " ".join(x for x in (self.given, self.surname) if x)


@dataclass
class PageRef:
    page: int
    label: str
    zone: str
    id: str

    @property
    def kind(self) -> str:
        """DTBook page type: front (roman numerals of front matter), normal, special."""
        if self.zone == "front" or ROMAN.match(self.label or ""):
            return "front"
        return "normal"


@dataclass
class Media:
    image: str | None
    alt: str
    placeholder: bool
    figure_text: list
    caption: list


class Source:
    def __init__(self, writer, doc, ctx, delivery):
        self.writer = writer
        self.tree = writer.tree
        self.doc = doc
        self.ctx = ctx
        self.profile = ctx.profile
        self.settings = ctx.settings
        self.book = ctx.book
        self.delivery = delivery
        self.reviews: list[ReviewEntry] = writer.reviews
        self.placeholder = self.profile.get("figures.alt_text_placeholder") or ""
        self.ids = {e.get("id") for e in self.tree.iter() if e.get("id")}

    # ------------------------------------------------------------------ metadata

    @property
    def bookinfo(self):
        return self.tree.find("bookinfo")

    def title_el(self):
        return self.bookinfo.find("title")

    def title_text(self) -> str:
        t = self.title_el()
        return text_of(t) if t is not None else ""

    def isbn(self) -> str | None:
        return self.settings.data.get("isbn")

    def edition(self) -> str | None:
        return self.settings.data.get("edition")

    def language(self, default: str = "en") -> str:
        lang = self.settings.data.get("language")
        if lang:
            return lang
        langs = (self.book.data.get("metadata") or {}).get("languages") or []
        if langs:
            return max(langs, key=lambda x: x.get("share", 0))["code"]
        return default

    def people(self) -> list[Person]:
        out = []
        for author in self.bookinfo.iter("author"):
            p = Person()
            for child in author:
                text = text_of(child)
                if child.tag == "contrib":
                    p.contrib = text
                elif child.tag == "firstname":
                    p.given = text
                elif child.tag == "surname":
                    p.surname = text
                elif child.tag == "othername":
                    p.degrees = text
                elif child.tag == "affiliation":
                    for sub in child:
                        if sub.tag == "jobtitle":
                            p.jobtitle = text_of(sub)
                        elif sub.tag == "orgname":
                            p.orgname = text_of(sub)
                        elif sub.tag == "orgdiv":
                            p.orgdiv.append(text_of(sub))
                        elif sub.tag == "address":
                            p.address = ", ".join(text_of(a) for a in sub if text_of(a))
            if p.given or p.surname or p.orgname:
                out.append(p)
        return out

    def legal_blocks(self) -> list:
        return [b for note in self.bookinfo.findall("legalnotice") for b in note]

    # ------------------------------------------------------------------ structure

    def divisions(self) -> list:
        return [c for c in self.tree if c.tag in DIVISION_TAGS]

    def kind(self, division) -> str:
        return division.get("x-kind") or division.tag

    def pages(self) -> list[PageRef]:
        seen, out = set(), []
        for a in self.tree.iter("anchor"):
            pid = a.get("id")
            if not pid or pid in seen or not a.get("x-page"):
                continue
            seen.add(pid)
            page = int(a.get("x-page"))
            label = a.get("x-label") or ""
            if not label:
                label = str(page)
                self.reviews.append(
                    ReviewEntry(
                        "page", f"page {page} has no printed label: its number is used", None, page
                    )
                )
            out.append(PageRef(page, label, a.get("x-zone") or "", pid))
        return out

    # ------------------------------------------------------------------ media

    def media(self, mediaobject) -> Media:
        image = None
        data = mediaobject.find("imageobject/imagedata")
        if data is not None:
            image = data.get("fileref").rsplit("/", 1)[-1]
        alt, placeholder, figure_text = "", False, []
        for to in mediaobject.findall("textobject"):
            if to.get("role") == "figuretext":
                figure_text = list(to)
            else:
                phrase = to.find("phrase")
                alt = (phrase.text or "") if phrase is not None else ""
        if not alt or alt == self.placeholder:
            placeholder = True
        caption = (
            list(mediaobject.find("caption")) if mediaobject.find("caption") is not None else []
        )
        return Media(image, alt, placeholder, figure_text, caption)

    def unit(self, uid: str) -> dict:
        return self.book.units.get(uid) or {}

    def mathml(self, eq) -> etree._Element | None:
        """The equation's MathML as an element, when the equation is written as MathML."""
        if not eq.get("x-mathml"):
            return None
        raw = self.unit(eq.get("x-unit")).get("mathml")
        try:
            return etree.fromstring(raw.encode("utf-8"))
        except (etree.XMLSyntaxError, AttributeError):
            self.reviews.append(
                ReviewEntry(
                    "equation",
                    "MathML of the source is not well-formed: image/LaTeX used",
                    eq.get("x-unit"),
                )
            )
            return None

    def latex(self, eq) -> str:
        return (self.unit(eq.get("x-unit")).get("latex") or "").strip()

    def depth(self, node, tags=("section",)) -> int:
        return sum(1 for a in node.iterancestors() if a.tag in tags)
