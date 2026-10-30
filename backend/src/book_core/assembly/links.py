"""Optional Extractor capability: link annotations and drawn underlines, per character.

Kept out of the extraction package (as the paint capability is) so that native extraction
keys do not change.

- ``extract_links``: the page's link annotations, each with its rectangle and destination
  (a URI, or a physical page and point of this document).
- ``extract_marks``: which characters of which stored spans a link rectangle covers (the
  character's box centre inside the rectangle), and which characters a drawn underline
  runs under: a thin horizontal rule (at most 1.6 pt high) just below the characters'
  baseline (within 0.05 font sizes above and 0.35 below it) whose extent does not pass
  the covered characters by more than one font size on either side (a table rule under a
  whole cell is not an underline). Characters come from PyMuPDF's raw extraction, paired
  with the stored spans in extraction order and checked by text (as the paint proof does);
  a page whose spans cannot be paired gets no marks (never guessed);
- ``slanted``: characters drawn slanted by their text matrix (``equations.slant``: synthetic
  italic, which font names and flags cannot show); spaces between two slanted characters
  join the range.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import pymupdf
from pydantic import Field

from book_core.equations import slant
from book_core.extraction.interfaces import Extractor
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.model.common import BBox, CoreModel
from book_core.run_context import open_source, signature

VERSION = "links-4"
# A drawn underline follows its text: it may pass the underlined characters by this many
# font sizes. A rule reaching further spans something else (a column-wide separator under a
# heading that nearly fills its column), not the text.
UNDERLINE_REACH = 0.15


class PageLink(CoreModel):
    rect: BBox  # unrotated crop-box coordinates, as the span store
    kind: Literal["uri", "page", "named", "file", "other"]
    uri: str | None = None
    target_page: int | None = None  # physical page (1-based) of an internal link
    target_point: tuple[float, float] | None = None


class PageLinks(CoreModel):
    source_sha256: str
    page: int = Field(ge=1)
    version: str = VERSION
    links: list[PageLink] = Field(default_factory=list)


@runtime_checkable
class LinkExtractor(Extractor, Protocol):
    def extract_links(self, source: Path, page_number: int) -> list[PageLink]: ...

    def extract_marks(self, source: Path, page_number: int, store, links): ...


class MarkRange(CoreModel):
    span: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    link: int | None = None  # index into the page's links (link ranges)


class PageMarks(CoreModel):
    paired: bool
    links: list[MarkRange] = Field(default_factory=list)
    underlines: list[MarkRange] = Field(default_factory=list)
    slanted: list[MarkRange] = Field(default_factory=list)  # characters drawn slanted


def _slanted(page, stored, raw_spans):
    """[MarkRange] of characters drawn slanted (paired by code point and origin)."""
    found = []
    for sid, flags in slant.character_slants(page, stored, raw_spans).items():
        # Characters without a glyph (spaces) join two slanted neighbours.
        for k, flag in enumerate(flags):
            if flag is None:
                left = next((f for f in reversed(flags[:k]) if f is not None), False)
                right = next((f for f in flags[k + 1 :] if f is not None), False)
                flags[k] = left and right
        for a, b in _ranges(flags):
            found.append(MarkRange(span=sid, start=a, end=b))
    return found


def _ranges(flags):
    """[(start, end)] of consecutive True positions."""
    out, start = [], None
    for index, flag in enumerate([*flags, False]):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            out.append((start, index))
            start = None
    return out


def _underline_rules(drawings, derotate):
    """Actual horizontal strokes or thin filled rectangles, excluding box edges.

    A river/curve can have a shallow bounding box without being a straight rule.
    Some producers paint a filled label rectangle and stroke its edges separately;
    an edge coincident with that rectangle is border evidence, not text styling.
    Tolerances cover coordinate rounding and half the painted stroke width.
    """
    rectangles = []
    for drawing in drawings:
        for item in drawing["items"]:
            if item[0] == "re":
                rect = pymupdf.Rect(item[1]) * derotate
                rect.normalize()
                if rect.height > 1.6:
                    rectangles.append((rect, drawing.get("width") or 0))
    rules = []
    for drawing in drawings:
        rect = pymupdf.Rect(drawing["rect"]) * derotate
        rect.normalize()
        if rect.width <= 2 or rect.height > 1.6:
            continue
        items = drawing["items"]
        straight = bool(items) and drawing.get("color") is not None and all(
            item[0] == "l"
            and abs((item[1] * derotate).y - (item[2] * derotate).y) <= .01
            for item in items
        ) and rect.height <= .01
        filled = (len(items) == 1 and items[0][0] == "re"
                  and drawing.get("fill") is not None)
        if not (straight or filled):
            continue
        centre = (rect.y0 + rect.y1) / 2
        border = False
        for box, width in rectangles:
            tolerance = max(width, drawing.get("width") or 0) / 2 + .01
            if (abs(rect.x0 - box.x0) <= tolerance
                    and abs(rect.x1 - box.x1) <= tolerance
                    and min(abs(centre - box.y0), abs(centre - box.y1)) <= tolerance):
                border = True
                break
        if not border:
            rules.append(rect)
    return rules


class PyMuPDFLinkExtractor(PyMuPDFExtractor):
    def extract_marks(self, source, page_number, store, links):
        """``PageMarks`` of one page; ``store``: the page's span store, ``links``: the
        page's ``PageLink`` list (same order as ``extract_links``)."""
        source = Path(source)
        before = signature(source)
        with open_source(source) as document:
            page = document[page_number - 1]
            raw_spans = slant.raw_spans(page)
            stored = list(store.spans.values())
            if not slant.paired(stored, raw_spans):
                return PageMarks(paired=False)
            derotate = page.derotation_matrix
            rules = _underline_rules(page.get_drawings(), derotate)
            found_links, under_rule = [], {}
            position = {span.id: n for n, span in enumerate(stored)}
            for span, record in zip(stored, raw_spans, strict=True):
                chars = record["chars"]
                if not chars:
                    continue
                boxes = [pymupdf.Rect(c["bbox"]) * derotate for c in chars]
                for index, link in enumerate(links):
                    r = link.rect
                    inside = [r.x0 <= (b.x0 + b.x1) / 2 <= r.x1 and r.y0 <= (b.y0 + b.y1) / 2
                              <= r.y1 for b in boxes]  # fmt: skip
                    for a, b in _ranges(inside):
                        if span.raw_text[a:b].strip():
                            found_links.append(MarkRange(span=span.id, start=a, end=b,
                                                         link=index))  # fmt: skip
                size = max(span.size, 1.0)
                baseline = (pymupdf.Point(chars[0]["origin"]) * derotate).y
                for index, rule in enumerate(rules):
                    centre = (rule.y0 + rule.y1) / 2
                    if not baseline - 0.05 * size <= centre <= baseline + 0.35 * size:
                        continue
                    under = [rule.x0 - 0.5 <= (b.x0 + b.x1) / 2 <= rule.x1 + 0.5 for b in boxes]
                    for a, b in _ranges(under):
                        if span.raw_text[a:b].strip():
                            under_rule.setdefault(index, []).append(
                                (span.id, a, b, boxes[a].x0, boxes[b - 1].x1, size)
                            )
            # A rule underlines the characters it lies under when it does not reach past all
            # of them (whatever spans they are in) by more than UNDERLINE_REACH.
            kept = []
            for index, ranges in under_rule.items():
                rule, reach = rules[index], UNDERLINE_REACH * max(r[5] for r in ranges)
                if rule.x0 >= min(r[3] for r in ranges) - reach and rule.x1 <= (
                    max(r[4] for r in ranges) + reach
                ):
                    kept += [(position[sid], index, a, sid, b) for sid, a, b, *_ in ranges]
            found_rules = [
                MarkRange(span=sid, start=a, end=b) for _, _, a, sid, b in sorted(kept)
            ]
            slanted = _slanted(page, stored, raw_spans)
        if signature(source) != before:
            raise ValueError("Source changed during mark extraction")
        return PageMarks(paired=True, links=found_links, underlines=found_rules,
                         slanted=slanted)  # fmt: skip

    def extract_links(self, source, page_number):
        source = Path(source)
        before = signature(source)
        found = []
        with open_source(source) as document:
            page = document[page_number - 1]
            # Link rectangles are in the rotated page space; map them to the unrotated crop
            # box like the span store (identity for unrotated pages).
            derotate = page.derotation_matrix
            for link in page.get_links():
                rect = pymupdf.Rect(link["from"]) * derotate
                rect.normalize()
                kind = link.get("kind")
                target, point, uri = None, None, None
                if kind == pymupdf.LINK_URI:
                    found_kind, uri = "uri", link.get("uri")
                elif kind == pymupdf.LINK_GOTO and link.get("page", -1) >= 0:
                    found_kind, target = "page", int(link["page"]) + 1
                    if link.get("to") is not None:
                        point = (round(float(link["to"].x), 2), round(float(link["to"].y), 2))
                elif kind == pymupdf.LINK_NAMED:
                    found_kind = "named"
                    if link.get("page", -1) is not None and link.get("page", -1) >= 0:
                        target = int(link["page"]) + 1
                elif kind in (pymupdf.LINK_GOTOR, pymupdf.LINK_LAUNCH):
                    found_kind, uri = "file", link.get("file")
                else:
                    found_kind = "other"
                if rect.is_empty:
                    continue
                found.append(
                    PageLink(
                        rect=BBox(x0=round(rect.x0, 2), y0=round(rect.y0, 2),
                                  x1=round(rect.x1, 2), y1=round(rect.y1, 2)),
                        kind=found_kind, uri=uri, target_page=target, target_point=point,
                    )
                )  # fmt: skip
        if signature(source) != before:
            raise ValueError("Source changed during link extraction")
        return found


def capable(extractor):
    """The extractor itself when it reads links, a PyMuPDF link reader for the plain PyMuPDF
    extractor, else None (no link evidence: no link spans, never guessed)."""
    if isinstance(extractor, LinkExtractor):
        return extractor
    inner = getattr(extractor, "native", None)
    if type(extractor) is PyMuPDFExtractor:
        return PyMuPDFLinkExtractor(extractor.device.resolved)
    if inner is not None and type(inner) is PyMuPDFExtractor:
        return PyMuPDFLinkExtractor(inner.device.resolved)
    return None
