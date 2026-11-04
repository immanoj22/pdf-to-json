"""The shared content pass of the format writers.

HTML, DTBook, DAISY, JATS and BITS all need what the DocBook writer already decides: which
text goes where, the character rules, links, ids, labels, numbering, image names, alt-text
placeholders and the emission ledger. This writer runs that pass and keeps the resulting
element tree (its own, never delivered) with a few extra attributes (``x-*``): the printed
page label of a page mark, the paragraph kind, the equation unit. A format transformer
(:mod:`book_adapters.formats`) then moves the already-written text into its own vocabulary,
so text is never copied or changed there and the ledger stays true."""

from __future__ import annotations

import copy
import dataclasses

from lxml import etree

from ..engine.model import Division, Equation, PageMark, Para
from .base import Delivery, WriteContext
from .docbook import DocBookWriter

# The inline vocabulary the format transformers read, whatever a client profile (which
# extends a format base profile) maps for DocBook output.
CANONICAL_INLINE = {
    "bold": {"element": "emphasis", "role": "bold"},
    "italic": {"element": "emphasis", "role": "italic"},
    "bold_italic": {"element": "emphasis", "role": "bolditalic"},
    "superscript": {"element": "superscript", "role": None},
    "subscript": {"element": "subscript", "role": None},
    "small_caps": {"element": "emphasis", "role": "smallcaps"},
    "underline": {"element": "emphasis", "role": "underline"},
    "link": {"element": "ulink", "role": None},
}


def canonical_profile(profile):
    data = copy.deepcopy(profile.data)
    data.setdefault("inline", {})["map"] = copy.deepcopy(CANONICAL_INLINE)
    data["inline"]["bold_italic"] = "single_role"
    data.setdefault("links", {})["email"] = "ulink"
    return dataclasses.replace(profile, data=data)


class SemanticWriter(DocBookWriter):
    name = "semantic"

    def write(self, doc, ctx: WriteContext) -> Delivery:
        ctx = WriteContext(canonical_profile(ctx.profile), ctx.settings, ctx.rules_on, ctx.book)
        return super().write(doc, ctx)

    def _write_division(self, parent, division: Division):
        el = super()._write_division(parent, division)
        el.set("x-kind", division.kind)
        zone = (
            "front"
            if any(division is d for d in self.doc.front)
            else "back"
            if any(division is d for d in self.doc.back + self.doc.after)
            else "body"
        )
        el.set("x-zone", zone)
        return el

    def _anchor(self, el, mark: PageMark):
        if not mark.keep or not self.p.get("anchors.enabled"):
            return
        a = etree.SubElement(el, "anchor")
        a.set("id", mark.anchor_id)
        if mark.role:
            a.set("role", mark.role)
        a.set("x-page", str(mark.page))
        if mark.label:
            a.set("x-label", mark.label)
        if mark.zone:
            a.set("x-zone", mark.zone)

    def _write_block(self, parent, block, container: str):
        before = len(parent)
        super()._write_block(parent, block, container)
        if isinstance(block, Para) and len(parent) > before and parent[-1].tag == "para":
            parent[-1].set("x-kind", block.kind)

    def _write_equation(self, parent, eq: Equation):
        before = len(parent)
        n_alt, n_rev = len(self.alt_placeholders), len(self.reviews)
        super()._write_equation(parent, eq)
        if len(parent) > before and parent[-1].tag == "informalequation":
            parent[-1].set("x-unit", eq.unit["id"])
            if eq.unit.get("mathml") and eq.unit.get("output") in ("mathml", "mathml_parts"):
                # the formats write MathML: the equation is accessible without alt text
                del self.alt_placeholders[n_alt:]
                self.reviews[n_rev:] = [
                    r for r in self.reviews[n_rev:] if r.kind not in ("alt_text", "equation")
                ]
                parent[-1].set("x-mathml", "1")

    def _package(self, book) -> Delivery:
        self._first_last_roles()
        delivery = Delivery(root="", ledger=self.ledger, reviews=self.reviews)
        delivery.images = self.images
        delivery.anchors = self.anchor_of_page
        delivery.alt_placeholders = self.alt_placeholders
        self.tree = book
        return delivery
