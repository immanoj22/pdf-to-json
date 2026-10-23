"""Assemble a final archive into the published book model (``assembly.schema.Book``).

The final archive holds, per page, the source span store, the final unit view (lists-stage
units with table lines taken out), the reading order, figures, equations and MathML, tables
and the continuity breaks; the book record holds furniture, structure, lists, figures,
equations, MathML, tables and continuity. This module turns them into one content tree:

- **Reading order.** Each page opens with a page marker. The main stream is read in order;
  every float (a sidebar, callout or card box, a footnote, a credit, a figure, a table, a
  display equation) is placed at its anchor (after the unit holding the anchor line, at the
  stream start without one). Figures, tables and equations anchored inside a float stream
  are placed inside it. Consecutive items of one list become a list node (a segment);
  a nested list directly after its parent item becomes the item's child.
- **Text** (``assembly.text``): exact source text with spans; list markers are structure.
- **Clean-up** (Step 17 Part 3): confirmed hidden text is moved to ``suppressed``; text that
  belongs to a figure (linked caption, credit, internal text, and figure-text units of the
  figure's stream) is kept in the figure record, not in the paragraph stream; index and
  glossary letter dividers get their own type.
- **Review**: each unit's status and flags come from the stage records (``assembly.review``
  turns them into the review list).

No stage decision is changed here; the assembly only places and labels what the stages
decided, and records where it could not (flags).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import regex

from book_core.assembly import schema as S
from book_core.assembly.fonts import FontTable
from book_core.assembly.names import split_names
from book_core.assembly.text import (
    Segment,
    build_text,
    decorate,
    line_context,
    ordered_spans,
    source_runs,
)
from book_core.extraction.fingerprints import stable_id

FURNITURE = frozenset({"running_head", "running_foot", "folio", "production_mark"})
ENTRY_TYPES = {
    "list_item": "list_item",
    "index_entry": "index_entry",
    "bibliography_entry": "bibliography_entry",
    "contents_entry": "contents_entry",
    "definition_entry": "definition_entry",
}
BOX_KINDS = {"sidebar": "sidebar", "callout": "callout", "card": "card"}
DIVIDER = regex.compile(r"^\s*\p{L}{1,3}(?:\s*[-–—]\s*\p{L}{1,3})?\s*$")
DIVIDER_PAGES = frozenset({"index", "glossary"})
HEX64 = regex.compile(r"^[0-9a-f]{64}$")
DEFAULT_PATTERNS = ("page_{label}_{n}", "page_pdf{index}_{n}")


def sid(value):
    """The 16-hex published id of a stage id (a SHA-256 hex digest, else its digest)."""
    if HEX64.match(value):
        return value[:16]
    return stable_id(value)[:16]


def rnd(value):
    return round(float(value), 2)


def box_of(bboxes, page):
    boxes = [b for b in bboxes if b is not None]
    if not boxes:
        return None
    return S.Box(page=page, x0=rnd(min(b.x0 for b in boxes)), y0=rnd(min(b.y0 for b in boxes)),
                 x1=rnd(max(b.x1 for b in boxes)), y1=rnd(max(b.y1 for b in boxes)))  # fmt: skip


def status(*values):
    found = set(values)
    if "must_check" in found:
        return "must_check"
    if "needs_review" in found:
        return "needs_review"
    return "ok"


@dataclass
class Flagged:
    """Review flags of one unit: (severity, kind, reason)."""

    rows: list = field(default_factory=list)

    def add(self, severity, kind, reason):
        if (severity, kind, reason) not in self.rows:
            self.rows.append((severity, kind, reason))

    @property
    def status(self):
        return status(*(r[0] for r in self.rows))

    @property
    def flags(self):
        return [f"{kind}: {reason}" for _, kind, reason in self.rows]


@dataclass
class Context:
    """Book-level inputs and accumulators shared by all pages."""

    profile: object
    fonts: FontTable
    language: str | None
    book: dict
    headings: dict  # unit id -> heading record
    run_in: dict  # unit id -> [heading record]
    styled: dict  # unit id -> role
    lists: dict  # list id -> StructuredList dict
    navigation: dict  # page -> kind
    markers: dict  # page -> PageMarker dict
    zones: dict  # page -> PageZone dict
    archive: object = None  # the final archive directory (images)
    images: dict = field(default_factory=dict)  # published file -> asset row
    renamed: dict = field(default_factory=dict)  # stage image file -> published file
    used_names: set = field(default_factory=set)
    review: list = field(default_factory=list)  # (unit id|None, page, kind, reason, sev, box)
    suppressed: list = field(default_factory=list)
    furniture: list = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    node_of: dict = field(default_factory=dict)  # stage unit/table id -> node
    page_entries: list = field(default_factory=list)
    link_targets: dict = field(default_factory=dict)  # (page, point) -> published unit id
    flag_rows: dict = field(default_factory=dict)  # published id -> [(severity, kind, reason)]

    def image_name(self, record):
        """The published file of a figure's image: the profile's pattern and format (the
        stage's name when they are the stage's); one file per spread; unique per book."""
        from book_core.figures.names import _stem, safe_label

        key = record.image.file_name
        if key in self.renamed:
            return self.renamed[key]
        images = self.profile.images
        fmt = images.photo_format if record.kind == "photo" else images.drawing_format
        stem = key.rsplit(".", 1)[0]
        if (images.name_pattern, images.unlabelled_pattern) != DEFAULT_PATTERNS:
            label = safe_label(record.page_label) if record.page_label else None
            n, index = record.anchor.reading_index, record.page
            if label is None or record.label_source == "none":
                stem = images.unlabelled_pattern.format(index=index, n=n, label="")
            else:
                stem = images.name_pattern.format(label=label, n=n, index=index)
            stem = _stem("{x}", x=stem)  # file-safe, as the figures stage names files
        base, suffix = stem, 2
        while f"{stem}.{fmt}".casefold() in self.used_names:
            stem = f"{base}_{suffix}"
            suffix += 1
        name = f"{stem}.{fmt}"
        self.used_names.add(name.casefold())
        self.renamed[key] = name
        return name

    def add_image(self, name, kind, original, unit, sha256, size, target_format):
        """Register an asset; an image whose format changes is re-encoded once here (its
        digest is the published file's)."""
        if name in self.images:
            return self.images[name]
        convert = None
        if not original.casefold().endswith("." + target_format):
            from book_core.assembly.imaging import convert_image

            convert = convert_image((self.archive / "images" / original).read_bytes(),
                                    target_format)  # fmt: skip
            sha256, size = hashlib.sha256(convert).hexdigest(), len(convert)
        self.images[name] = {
            "kind": kind,
            "original": original,
            "unit": unit,
            "sha256": sha256,
            "bytes": size,
            "converted": convert,
        }
        return self.images[name]


class PageBuild:
    """One page: its stage records and the nodes built from them."""

    def __init__(self, ctx, number, payload, native, evidence):
        from book_core.equations.models import PageEquations
        from book_core.figures.models import PageFigures
        from book_core.lists.models import ItemUnit
        from book_core.mathml.models import PageMath
        from book_core.model.spans import ExtractedPage
        from book_core.reading_order.models import PageReadingOrder
        from book_core.tables.models import PageTables

        self.ctx, self.number, self.payload = ctx, number, payload
        self.page = ExtractedPage.model_validate(payload["source"])
        self.spans = ordered_spans(self.page.store)
        self.line_spans = payload["line_spans"]
        self.native = native
        self.geometry = native.span_geometry if native is not None else {}
        view = payload["table_view"]
        removed = set(view["removed"])
        units = payload["units"]["units"]
        self.original = {u["id"]: ItemUnit.model_validate(u) for u in units}
        final = [u for u in units if u["id"] not in removed] + view["added"]
        self.units = {u["id"]: ItemUnit.model_validate(u) for u in final}
        self.unit_of = {lid: uid for uid, u in self.units.items() for lid in u.line_ids}
        self.order = PageReadingOrder.model_validate(payload["units"]["order"])
        self.tables = PageTables.model_validate(payload["tables"])
        self.figures = PageFigures.model_validate(payload["figures"])
        self.equations = PageEquations.model_validate(payload["equations"])
        self.math = {e.equation_id: e for e in PageMath.model_validate(payload["mathml"]).equations}
        self.regions = {r.id: r for r in self.equations.regions}
        self.ocr = payload.get("ocr")
        self.links = evidence.get("links", [])
        marks = evidence.get("marks")
        self.link_marks, self.underline_marks = defaultdict(list), defaultdict(list)
        self.slant_marks = defaultdict(list)
        if marks is not None and marks.paired:
            for mark in marks.links:
                self.link_marks[mark.span].append((mark.start, mark.end, mark.link))
            for mark in marks.underlines:
                self.underline_marks[mark.span].append((mark.start, mark.end))
            for mark in marks.slanted:
                self.slant_marks[mark.span].append((mark.start, mark.end))
        self.hidden = {}  # span id -> (reason, evidence)
        for proof in payload.get("visibility_evidence", []):
            if proof["decision"] == "invisible":
                self.hidden[proof["span_id"]] = ("covered_by_paint", {
                    "rule": proof["reason"],
                    "cover_paint": len(proof["cover_paint_seqnos"])})  # fmt: skip
        for span_id, proof in evidence.get("not_rendered", {}).items():
            self.hidden.setdefault(span_id, ("not_rendered", proof))
        self.character_flags = defaultdict(list)
        for flag in payload.get("character_evidence", {}).get("flags", []):
            self.character_flags[flag["span_id"]].append(flag)
        for repair in self.equations.repairs:
            self.character_flags[repair.span_id].append({"repair": repair.corrected})
        self.ocr_words = {}
        if self.ocr is not None:
            for word in self.ocr.get("words", []):
                self.ocr_words[word["span_id"]] = word
        self._contexts = {}
        self.figure_less = set()

    # ----------------------------------------------------------------- text helpers

    def pieces(self, line_ids):
        return [(lid, [(s, None, None) for s in self.line_spans.get(lid, [])]) for lid in line_ids]

    def contexts(self, line_ids):
        for lid in line_ids:
            if lid not in self._contexts:
                self._contexts[lid] = line_context(self.line_spans.get(lid, []), self.spans,
                                                   self.geometry)  # fmt: skip
        return self._contexts

    def link_list(self):
        found = []
        for link in self.links:
            target = None
            if link.target_page is not None and link.target_point is not None:
                target = self.ctx.link_targets.get((link.target_page, link.target_point))
            found.append((link, target))
        return found

    def text(self, line_ids, *, unit=None, exclude=(), pieces=None, math=True, run_in=()):
        """(Built, TextContent) of lines (or explicit pieces) with all decorations."""
        pieces = pieces if pieces is not None else self.pieces(line_ids)
        hidden = {s for _, refs in pieces for s, _, _ in refs if s in self.hidden}
        built = build_text(pieces, self.spans, frozenset(exclude) | frozenset(hidden),
                           source_runs_for={self.spans[s].line_id for s in self.hidden
                                            if s in self.spans})
        lines = built.lines
        math_ranges = self.math_ranges(built, unit) if math else []
        heading_ranges = []
        for heading in run_in:
            for ref in heading["run_in"]:
                found = built.range_of(ref["span_id"], ref.get("start"), ref.get("end"))
                if found:
                    heading_ranges.append(found)
        content = decorate(
            built,
            fonts=self.ctx.fonts,
            contexts=self.contexts(lines),
            geometry=self.geometry,
            links=self.link_list(),
            link_marks=self.link_marks,
            underline_marks=self.underline_marks,
            slant_marks=self.slant_marks,
            math_ranges=math_ranges,
            unit=unit,
            language=self.ctx.language,
            run_in=heading_ranges,
            settings=self.ctx.profile.review,
        )
        content = S.TextContent.model_validate(content.model_dump())
        return built, content

    def math_ranges(self, built, unit):
        """Inline math over the unit's text: text-set regions (span ranges) and drawn
        regions read at an inline place (insertion points)."""
        found = []
        if unit is None:
            return found
        for region in self.equations.regions:
            owner = region.owner
            if owner is None or owner.kind != "text_unit" or owner.unit_id not in {
                unit.id, *unit.source_unit_ids}:  # fmt: skip
                continue
            record = self.math.get(region.id)
            review = "ok"
            if record is not None and record.review_status in {"needs_review", "must_check"}:
                review = record.review_status
            mathml = record.mathml if record is not None else None
            latex = record.latex if record is not None else None
            if region.span_refs:
                ranges = [built.range_of(r.span_id, r.start, r.end) for r in region.span_refs]
                ranges = [r for r in ranges if r]
                if ranges:
                    found.append((min(a for a, _ in ranges), max(b for _, b in ranges),
                                  sid(region.id), mathml, latex, review))  # fmt: skip
            elif owner.place is not None:
                place = owner.place
                at = built.offset_of(place.span_id, place.offset)
                if at is None:
                    whole = built.range_of(place.span_id)
                    at = whole[1] if whole else None
                if at is not None:
                    found.append((at, at, sid(region.id), mathml, latex, review))
        return found

    # ----------------------------------------------------------------- unit evidence

    def source_of(self, span_ids):
        methods = {self.spans[s].provenance.method for s in span_ids if s in self.spans}
        return "ocr" if "ocr" in methods else "native"

    def unit_flags(self, unit, built, flagged):
        if unit.review_required:
            flagged.add("needs_review", "structure", "list or entry decision below confidence")
        if unit.boundary.review_required:
            flagged.add("needs_review", "structure", "unit boundary below confidence")
        if any(j.review_required for j in unit.joins):
            flagged.add("needs_review", "structure", "a line join inside the unit is uncertain")
        span_ids = {seg.span.id for seg in built.segments}
        if any(s in self.character_flags for s in span_ids):
            flagged.add("needs_review", "character", "a character's decoding may not match the "
                        "painted glyph")  # fmt: skip
        words = [self.ocr_words[s] for s in span_ids if s in self.ocr_words]
        if any(w.get("granularity", "word") == "line" for w in words):
            flagged.add("needs_review", "ocr_line", "OCR line scores have no word calibration")
        if any(w.get("review_status") == "needs_review"
               and w.get("granularity", "word") == "word" for w in words):
            flagged.add("needs_review", "ocr_word",
                        "OCR words need review: low confidence, uncalibrated, "
                        "or reader disagreement")
        if self.ocr is not None and self.ocr.get("review_status") == "must_check" and words:
            flagged.add("must_check", "ocr_page", "the page's OCR is unreliable")
        fonts = [self.ctx.fonts.style(seg.span.font) for seg in built.segments]
        if any(f is not None and f.disagreement for f in fonts):
            flagged.add("needs_review", "style", "font name and flags disagree on bold/italic")
        if (
            unit.language not in {"und", None}
            and unit.language != self.ctx.language
            and unit.language_confidence < self.ctx.profile.review.language_min_confidence
            and sum(c.isalpha() for c in built.content.text)
            >= self.ctx.profile.review.language_min_letters
        ):
            flagged.add("needs_review", "language", "the unit's language is uncertain")

    def base(self, unit_id, line_ids, built, flagged, stages, reasons, confidence=None,
             span_refs=()):  # fmt: skip
        boxes = [self.spans[seg.span.id].bbox for seg in built.segments] if built else []
        box = box_of(boxes, self.number)
        refs = S.SourceRefs(
            lines=[sid(lid) for lid in (built.lines if built else line_ids)],
            spans=[S.SpanRange(span=sid(r[0]), start=r[1], end=r[2]) for r in span_refs],
        )
        self.ctx.flag_rows[sid(unit_id)] = list(flagged.rows)
        return dict(
            id=sid(unit_id),
            pages=[self.number],
            boxes=[box] if box else [],
            order=0,
            source=self.source_of([seg.span.id for seg in built.segments]) if built else "native",
            confidence=None if confidence is None else round(confidence, 4),
            review_status=flagged.status,
            flags=flagged.flags,
            provenance=S.Provenance(stages=stages, reasons=list(reasons)[:3]),
            refs=refs,
        )

    # ----------------------------------------------------------------- nodes

    def unit_node(self, unit, *, in_figure_stream=None):
        """The node of one final-view (or cell) unit, or None when its text is all hidden."""
        ctx = self.ctx
        kind = unit.kind
        flagged = Flagged()
        exclude = []
        marker = None
        if unit.marker is not None and _glued(unit.marker, self.page.store):
            flagged.add("needs_review", "structure", "a list marker is glued to the word that "
                        "follows it; kept in the text")  # fmt: skip
        elif unit.marker is not None and all(r.span_id in self.hidden for r in unit.marker.refs):
            flagged.add("needs_review", "structure", "the list marker is hidden text; it is "
                        "listed in suppressed, not kept as the marker")  # fmt: skip
        elif unit.marker is not None:
            for ref in unit.marker.refs:
                span = self.spans[ref.span_id]
                exclude.append(
                    (
                        ref.span_id,
                        ref.start or 0,
                        ref.end if ref.end is not None else len(span.raw_text),
                    )
                )
            marker_text = "".join(
                self.spans[r.span_id].raw_text[r.start or 0 : r.end] for r in unit.marker.refs
            )
            import unicodedata

            marker = S.Marker(text=unicodedata.normalize("NFKC", marker_text).strip(),
                              type=unit.marker.type, value=unit.marker.value,
                              punctuation=unit.marker.punctuation)  # fmt: skip
        built, content = self.text(unit.line_ids, unit=unit, exclude=exclude,
                                   run_in=ctx.run_in.get(unit.id, ()))  # fmt: skip
        if not content.text:
            if built.excluded and any(s in self.hidden for s, _, _ in built.excluded):
                return None
        self.unit_flags(unit, built, flagged)
        reasons = unit.boundary.reasons
        stages = ["lists"]
        heading = ctx.headings.get(unit.id)
        if marker is not None and content.text and content.text[0].isspace():
            stripped = len(content.text) - len(content.text.lstrip())
            content = _shift(content, stripped)
        navigation = ctx.navigation.get(self.number)
        if (
            navigation in DIVIDER_PAGES
            and heading is None
            and not unit.locators
            and len(unit.line_ids) == 1
            and DIVIDER.match(content.text)
        ):
            ctx.counts["index_dividers"] += 1
            return S.IndexDivider(content=content, **self.base(unit.id, unit.line_ids, built,
                                  flagged, stages + ["assembly"],
                                  ["a letter between entries of an index or glossary"],
                                  unit.boundary.confidence))  # fmt: skip
        if heading is not None:
            if heading.get("review_required"):
                flagged.add("needs_review", "heading", "heading decision below confidence")
            ctx.counts["headings"] += 1
            return S.Heading(
                level=heading["level"], role=heading["role"],
                level_method=heading["level_method"],
                section=sid(heading["section_id"]) if heading.get("section_id") else None,
                content=content,
                **self.base(unit.id, unit.line_ids, built, flagged, ["structure", "lists"],
                            heading["reasons"], heading["confidence"]),
            )  # fmt: skip
        if kind in ENTRY_TYPES:
            item_type = ENTRY_TYPES[kind]
            structured = ctx.lists.get(unit.list_id)
            if kind == "definition_entry" and structured and structured["kind"] == "glossary":
                item_type = "glossary_entry"
            term = None
            if unit.term:
                found = [built.range_of(r.span_id, r.start, r.end) for r in unit.term]
                found = [f for f in found if f]
                if found:
                    term = (min(a for a, _ in found), max(b for _, b in found))
            locators = []
            for loc in unit.locators:
                found = [built.range_of(r.span_id, r.start, r.end) for r in loc.refs]
                found = [f for f in found if f]
                if not found:
                    continue
                locators.append(
                    S.Locator(
                        kind=loc.kind,
                        start=min(a for a, _ in found),
                        end=max(b for _, b in found),
                        label=loc.label,
                        end_label=loc.end_label,
                        target_page=loc.target_page,
                        end_target_page=loc.end_target_page,
                        confidence=round(loc.confidence, 4),
                    )
                )
            names = []
            if ctx.profile.names.split and item_type in {"index_entry", "bibliography_entry"}:
                names = split_names(content.text, item_type, term)
                if names:
                    flagged.add("needs_review", "names", "parsed personal names")
            ctx.counts["items"] += 1
            node = S.ListItem(
                type=item_type, marker=marker, item_role=unit.item_role, level=unit.level,
                term=term, locators=locators, names=names, content=content,
                **self.base(unit.id, unit.line_ids, built, flagged, stages, reasons,
                            unit.boundary.confidence),
            )  # fmt: skip
            node._list = (unit.list_id, unit.level or 1)  # grouping hint (not serialised)
            return node
        stream = unit.stream_kind
        if kind == "caption":
            flagged.add("needs_review", "caption", "caption not linked to a figure or table")
            return S.Caption(content=content, **self.base(unit.id, unit.line_ids, built,
                             flagged, stages, reasons, unit.boundary.confidence))  # fmt: skip
        if stream == "note":
            flagged.add("needs_review", "footnote", "note text; its marker in the text is not "
                        "linked")  # fmt: skip
            ctx.counts["footnotes"] += 1
            return S.Footnote(content=content, **self.base(unit.id, unit.line_ids, built,
                              flagged, stages, reasons, unit.boundary.confidence))  # fmt: skip
        role = "body"
        if stream == "credit" or unit.id in self.page_credit_ids():
            role = "credit"
            flagged.add("needs_review", "credit", "credit line not linked to a figure")
        elif kind == "heading_candidate":
            role = ctx.styled.get(unit.id, "heading_candidate")
        elif kind == "list_item_candidate":
            role = "list_item_candidate"
        elif kind == "figure_text":
            role = "figure_text"
            if self.stream_of(unit) in self.figure_less:
                flagged.add("needs_review", "figure", "text of a figure region whose figure "
                            "became a table piece or an equation")  # fmt: skip
            else:
                flagged.add("needs_review", "figure", "figure text not linked to a figure")
        elif kind == "table_text":
            role = "table_text"
        return S.Paragraph(role=role, content=content, **self.base(
            unit.id, unit.line_ids, built, flagged, stages, reasons,
            unit.boundary.confidence))  # fmt: skip

    def table_owned_lines(self):
        return {lid for table in self.tables.tables for lid in table.line_ids}

    def table_owned_units(self):
        return {t.unit_id for table in self.tables.tables
                for t in [table.title, *table.notes] if t is not None and t.unit_id}  # fmt: skip

    def stream_of(self, unit):
        first = unit.line_ids[0]
        return next((s.id for s in self.order.streams if first in s.line_ids), None)

    def page_credit_ids(self):
        return {c.unit_id for c in self.figures.page_credits}

    def figure_text(self, link, review):
        # The final view's unit: lines a table took over, and a table's title or notes,
        # belong to the table (decided after the figures), not here.
        unit = self.units.get(link.unit_id)
        if (
            unit is None
            or unit.id in self.table_owned_units()
            or (set(unit.line_ids) & self.table_owned_lines())
        ):
            return None
        built, content = self.text(unit.line_ids, unit=unit)
        if not content.text:
            return None
        return S.FigureText(id=sid(unit.id), refs=S.SourceRefs(
            lines=[sid(x) for x in built.lines]), content=content,
            review_status="needs_review" if review else "ok")  # fmt: skip

    def figure_node(self, record, extra_text=()):
        ctx = self.ctx
        flagged = Flagged()
        for reason in record.review_flags:
            flagged.add("needs_review", "figure", reason)
        captions = [x for x in (self.figure_text(link, link.review_required)
                                for link in record.captions) if x]  # fmt: skip
        credits = [x for x in (self.figure_text(link, link.review_required)
                               for link in record.credits) if x]  # fmt: skip
        inside = [x for x in (self.figure_text(link, link.review_required)
                              for link in record.internal_text) if x]  # fmt: skip
        inside += list(extra_text)
        image = None
        if record.image is not None:
            name = ctx.image_name(record)
            row = ctx.add_image(
                name,
                "figure",
                record.image.file_name,
                sid(record.id),
                record.image.sha256,
                record.image.bytes,
                _format(name, "png"),
            )
            image = S.Image(
                file=name,
                format=_format(name, record.image.format),
                width=record.image.width,
                height=record.image.height,
                dpi=record.image.dpi,
                sha256=row["sha256"],
                bytes=row["bytes"],
            )
        alt = record.alt_text
        alt_text = S.AltText(text=alt.text, status=alt.status, source=alt.source,
                             language=alt.language, model=alt.model)  # fmt: skip
        if alt.status == "needs_review" and not record.small_artwork:
            flagged.add("needs_review", "alt_text", "the image needs a description")
        equations = [sid(m) for fm in self.equations.figure_math if fm.figure_id == record.id
                     for m in fm.equation_ids]  # fmt: skip
        box = S.Box(page=self.number, x0=rnd(record.bbox.x0), y0=rnd(record.bbox.y0),
                    x1=rnd(record.bbox.x1), y1=rnd(record.bbox.y1))  # fmt: skip
        ctx.counts["figures"] += 1
        ctx.counts["figure_text_units"] += len(inside)
        ctx.flag_rows[sid(record.id)] = list(flagged.rows)
        return S.Figure(
            id=sid(record.id), pages=sorted(set(record.pages)), boxes=[box], order=0,
            source="native", confidence=round(record.confidence, 4),
            review_status=flagged.status, flags=flagged.flags,
            provenance=S.Provenance(stages=["figures"], reasons=record.reasons[:3]),
            refs=S.SourceRefs(),
            kind=record.kind, image=image, name=record.name, label=record.page_label,
            small=record.small_artwork, captions=captions, credits=credits, text=inside,
            alt_text=alt_text,
            spread_with=sid(record.spread_partner_id) if record.spread_partner_id else None,
            equations=equations,
        )  # fmt: skip

    def equation_node(self, unit):
        """A display equation unit (drawn objects at an anchor)."""
        ctx = self.ctx
        region = self.regions.get(unit.equation_id)
        record = self.math.get(unit.equation_id)
        flagged = Flagged()
        output, mathml, latex, image, parts = "image", None, None, None, []
        if record is not None:
            output, mathml, latex = record.output, record.mathml, record.latex
            parts = [p.mathml for p in record.parts]
            if record.review_status in {"needs_review", "must_check"}:
                flagged.add(record.review_status, "mathml",
                            "; ".join(record.flags[:2]) or "MathML readings disagree or "
                            "a check failed")  # fmt: skip
            if record.fallback_image is not None:
                fb = record.fallback_image
                name = fb.file_name
                image = S.Image(
                    file=name,
                    format=_format(name, "png"),
                    width=fb.width,
                    height=fb.height,
                    dpi=fb.dpi,
                    sha256=fb.sha256,
                    bytes=fb.bytes,
                )
                ctx.add_image(
                    name, "equation", name, sid(unit.id), fb.sha256, fb.bytes, _format(name, "png")
                )
        else:
            flagged.add("must_check", "mathml", "no MathML record for the equation")
        if output == "image" and image is None:
            output = "mathml" if mathml else "text"
            if output == "text":
                flagged.add("must_check", "mathml", "no reading and no image of the equation")
        alt = None
        if image is not None:
            mode = ctx.profile.alt_text.equation_fallback
            if mode == "latex" and latex:
                alt = S.AltText(text=latex, source="latex")
            else:
                alt = S.AltText()
            flagged.add("needs_review", "alt_text", "the equation image needs alt text")
        box = None
        if region is not None:
            box = S.Box(page=self.number, x0=rnd(region.bbox.x0), y0=rnd(region.bbox.y0),
                        x1=rnd(region.bbox.x1), y1=rnd(region.bbox.y1))  # fmt: skip
        ctx.counts["equations"] += 1
        ctx.flag_rows[sid(unit.id)] = list(flagged.rows)
        return S.Equation(
            id=sid(unit.id), pages=[self.number], boxes=[box] if box else [], order=0,
            source="native",
            confidence=round(record.confidence, 4) if record is not None else None,
            review_status=flagged.status, flags=flagged.flags,
            provenance=S.Provenance(stages=["equations", "mathml"],
                                    reasons=(region.rules[:3] if region else [])),
            refs=S.SourceRefs(), presentation=region.presentation if region else "display",
            mathml=mathml if output != "image" or mathml else None, latex=latex,
            output=output if not (output == "mathml" and not mathml) else "image",
            parts=parts, image=image, alt_text=alt,
        )  # fmt: skip

    def cell_content(self, cell, table):
        out = []
        for item in cell.content:
            if item.kind in {"paragraph", "list_item"} and item.unit_id:
                unit = self.original.get(item.unit_id) or self.units.get(item.unit_id)
                if unit is not None:
                    unit = _restricted(unit, item.line_ids)
                    node = self.unit_node(unit)
                    if node is not None:
                        out.append(node)
                    continue
            if item.kind == "equation" and item.unit_id:
                eq = next((u for u in self.equations.units if u.id == item.unit_id), None)
                if eq is not None:
                    out.append(self.equation_node(eq))
                continue
            if item.kind == "figure" and item.figure_id:
                fig = next((f for f in self.figures.figures if f.id == item.figure_id), None)
                if fig is not None:
                    out.append(self.figure_node(fig))
                continue
            pieces = [(lid, [(s, None, None) for s in self.line_spans.get(lid, [])])
                      for lid in item.line_ids]  # fmt: skip
            by_line = defaultdict(list)
            for ref in item.span_refs:
                line = self.spans[ref.span_id].line_id
                by_line[_layout_line(self.line_spans, ref.span_id) or line].append(
                    (ref.span_id, ref.start, ref.end)
                )
            pieces += list(by_line.items())
            built, content = self.text([], pieces=pieces)
            if not content.text:
                continue
            out.append(S.TextFragment(refs=S.SourceRefs(
                lines=[sid(x) for x in item.line_ids],
                spans=[S.SpanRange(span=sid(r.span_id), start=r.start, end=r.end)
                       for r in item.span_refs]), content=content))  # fmt: skip
        return group_lists(out, self.ctx)

    def table_text(self, text, table):
        unit = self.units.get(text.unit_id) if text.unit_id else None
        line_ids = unit.line_ids if unit is not None else text.line_ids
        built, content = self.text(line_ids, unit=unit)
        return S.TableText(id=sid(text.unit_id or stable_id(table.id, text.role, *line_ids)),
                           role=text.role, numbered=text.numbered, number=text.number,
                           refs=S.SourceRefs(lines=[sid(x) for x in built.lines]),
                           content=content)  # fmt: skip

    def table_node(self, table):
        ctx = self.ctx
        flagged = Flagged()
        for reason in table.review_flags:
            flagged.add(table.review_status or "needs_review", "table", reason)
        for unlinked in table.unlinked_texts:
            flagged.add("needs_review", "table", f"{unlinked.role} candidate not linked: "
                        f"{unlinked.reason}")  # fmt: skip
        cells = []
        for cell in table.cells:
            cells.append(S.Cell(
                id=sid(cell.id), row=cell.row, column=cell.column, row_span=cell.row_span,
                column_span=cell.column_span, role=cell.role,
                headers=[sid(h) for h in cell.header_cell_ids],
                box=S.Box(page=self.number, x0=rnd(cell.bbox.x0), y0=rnd(cell.bbox.y0),
                          x1=rnd(cell.bbox.x1), y1=rnd(cell.bbox.y1)),
                content=self.cell_content(cell, table)))  # fmt: skip
        title = self.table_text(table.title, table) if table.title else None
        notes = [self.table_text(n, table) for n in table.notes]
        box = S.Box(page=self.number, x0=rnd(table.bbox.x0), y0=rnd(table.bbox.y0),
                    x1=rnd(table.bbox.x1), y1=rnd(table.bbox.y1))  # fmt: skip
        ctx.counts["tables"] += 1
        ctx.flag_rows[sid(table.id)] = list(flagged.rows)
        sources = {self.spans[s].provenance.method for lid in table.line_ids
                   for s in self.line_spans.get(lid, []) if s in self.spans}  # fmt: skip
        return S.Table(
            id=sid(table.id), pages=[self.number], boxes=[box], order=0,
            source="ocr" if "ocr" in sources else "native",
            confidence=round(table.confidence, 4), review_status=flagged.status,
            flags=flagged.flags,
            provenance=S.Provenance(stages=["tables"], reasons=table.reasons[:3]),
            refs=S.SourceRefs(lines=[sid(x) for x in table.line_ids]),
            rows=len(table.rows), columns=len(table.columns), header_rows=table.header_rows,
            row_header_columns=table.row_header_columns, rotation=table.rotation,
            title=title, notes=notes, cells=cells,
        )  # fmt: skip

    # ----------------------------------------------------------------- page assembly

    def build(self):
        """The page's content nodes in reading order (furniture and suppressed recorded)."""
        ctx = self.ctx
        claimed, figure_streams_text = {}, defaultdict(list)
        for record in self.figures.figures:
            for link in (*record.captions, *record.credits, *record.internal_text):
                claimed[link.unit_id] = record.id
        table_texts = {
            t.unit_id
            for table in self.tables.tables
            for t in [table.title, *table.notes]
            if t is not None and t.unit_id
        }
        table_lines = {lid for table in self.tables.tables for lid in table.line_ids}
        streams = {s.id: s for s in self.order.streams}
        stream_figures = defaultdict(list)
        for record in self.figures.figures:
            if record.page == self.number:
                stream_figures[record.anchor.stream_id].append(record)
        # Figure-text units of a figure stream belong to that stream's figure (Part 3).
        for stream in self.order.streams:
            if stream.kind != "figure" or len(stream_figures.get(stream.id, [])) != 1:
                continue
            figure = stream_figures[stream.id][0]
            for lid in stream.line_ids:
                uid = self.unit_of.get(lid)
                unit = self.units.get(uid) if uid else None
                if (unit is not None and uid not in claimed and uid not in table_texts
                        and unit.kind in {"figure_text", "paragraph"}):  # fmt: skip
                    claimed[uid] = figure.id
                    figure_streams_text[figure.id].append(uid)
        # Figure-text units elsewhere whose box centre lies inside exactly one figure.
        page_figures = [f for f in self.figures.figures if f.page == self.number]
        for uid, unit in self.units.items():
            if unit.kind != "figure_text" or uid in claimed or uid in table_texts:
                continue
            boxes = [self.spans[s].bbox for lid in unit.line_ids
                     for s in self.line_spans.get(lid, []) if s in self.spans]  # fmt: skip
            if not boxes:
                continue
            cx = (min(b.x0 for b in boxes) + max(b.x1 for b in boxes)) / 2
            cy = (min(b.y0 for b in boxes) + max(b.y1 for b in boxes)) / 2
            inside = [f for f in page_figures if f.bbox.x0 <= cx <= f.bbox.x1
                      and f.bbox.y0 <= cy <= f.bbox.y1]  # fmt: skip
            if len(inside) == 1:
                claimed[uid] = inside[0].id
                figure_streams_text[inside[0].id].append(uid)
        self.ctx.counts["figure_text_moved"] += sum(map(len, figure_streams_text.values()))
        self.figure_less = {s.id for s in self.order.streams
                            if s.kind == "figure" and not stream_figures.get(s.id)}  # fmt: skip
        self.claimed = claimed
        # Units leaving content: furniture, outside the TrimBox, invisible; hidden spans.
        for unit in self.units.values():
            if unit.kind in FURNITURE:
                self.furniture_record(unit)
            elif unit.kind in {"artifact", "invisible"}:
                self.suppress_unit(unit)
        for span_id, (reason, proof) in sorted(self.hidden.items()):
            span = self.spans.get(span_id)
            if span is None or not span.raw_text:
                continue
            owner = self.unit_of.get(_layout_line(self.line_spans, span_id))
            unit = self.units.get(owner) if owner else None
            if unit is not None and unit.kind in {"artifact", "invisible"}:
                continue
            ctx.suppressed.append(
                S.Suppressed(
                    id=sid(stable_id(span_id, "suppressed")),
                    reason=reason,
                    page=self.number,
                    boxes=[box_of([span.bbox], self.number)],
                    refs=S.SourceRefs(spans=[S.SpanRange(span=sid(span_id))]),
                    text=span.text,
                    source_runs=source_runs(
                        [Segment(0, len(span.text), span, 0, len(span.raw_text), span.line_id)],
                        self.spans),
                    evidence=_evidence(proof),
                    retained_by_ledger=True,
                )
            )
            ctx.review.append((sid(stable_id(span_id, "suppressed")), self.number, "hidden_text",
                               f"hidden text dropped from content ({reason})", "needs_review",
                               box_of([span.bbox], self.number)))  # fmt: skip
            ctx.counts[f"suppressed_{reason}"] += 1
        # Floats anchored per stream.
        anchored = defaultdict(list)  # stream id -> [(position, order, key, builder)]
        for stream in self.order.streams:
            if stream.anchor is not None and stream.kind not in {"figure", "table"}:
                anchored[self.order.main.id].append((stream.anchor.after_line_id,
                                                    stream.anchor.order, stream.id,
                                                    ("stream", stream)))  # fmt: skip
            elif stream.anchor is not None:
                anchored[self.order.main.id].append((stream.anchor.after_line_id,
                                                    stream.anchor.order, stream.id,
                                                    ("inline_stream", stream)))  # fmt: skip
        in_cells = {f for t in self.tables.tables for c in t.cells for f in c.figure_ids}
        in_cells |= {e for t in self.tables.tables for c in t.cells for e in c.equation_unit_ids}
        for record in self.figures.figures:
            if record.page != self.number or record.id in in_cells:
                continue  # a figure a table cell holds is read in its cell
            target = record.anchor.stream_id if record.anchor.stream_id in streams else (
                self.order.main.id)  # fmt: skip
            extra = [self.figure_text(_Link(u), False) for u in figure_streams_text[record.id]]
            anchored[target].append(
                (
                    record.anchor.after_line_id,
                    record.anchor.order,
                    record.id,
                    ("figure", record, [x for x in extra if x]),
                )
            )
        for table in self.tables.tables:
            target = table.anchor.stream_id if table.anchor.stream_id in streams else (
                self.order.main.id)  # fmt: skip
            anchored[target].append((table.anchor.after_line_id, 0, table.id, ("table", table)))
        for unit in self.equations.units:
            if unit.id in in_cells:
                continue
            target = unit.anchor.stream_id if unit.anchor.stream_id in streams else (
                self.order.main.id)  # fmt: skip
            anchored[target].append((unit.anchor.after_line_id, unit.anchor.order, unit.id,
                                     ("equation", unit)))  # fmt: skip
        self.anchored, self.streams, self.table_lines = anchored, streams, table_lines
        self.table_texts = table_texts
        nodes = self.stream_nodes(self.order.main)
        return group_lists(nodes, ctx)

    def stream_nodes(self, stream):
        """Nodes of one stream in order, with the floats anchored in it at their places."""
        entries = []  # [(set of line ids, node)]
        seen = set()
        for lid in stream.line_ids:
            if lid in self.table_lines:
                continue
            uid = self.unit_of.get(lid)
            if uid is None or uid in seen:
                continue
            seen.add(uid)
            unit = self.units[uid]
            if (uid in self.claimed or uid in self.table_texts or unit.kind in FURNITURE
                    or unit.kind in {"artifact", "invisible"}):  # fmt: skip
                entries.append((set(unit.line_ids), None, uid))
                continue
            node = self.unit_node(unit)
            entries.append((set(unit.line_ids), node, uid))
        position = {lid: k for k, lid in enumerate(stream.line_ids)}
        floats = sorted(self.anchored.get(stream.id, []),
                        key=lambda f: (position.get(f[0], -1), f[1], f[2]))  # fmt: skip
        placed = defaultdict(list)
        for after, _, _, builder in floats:
            index = -1
            if after is not None:
                for k, (lines, _, _) in enumerate(entries):
                    if after in lines:
                        index = k
                        break
                else:
                    at = position.get(after, -1)
                    for k, (lines, _, _) in enumerate(entries):
                        if any(position.get(lid, -1) <= at for lid in lines):
                            index = k
            placed[index].extend(self.float_nodes(builder))
        out = list(placed.get(-1, []))
        for k, (_, node, _) in enumerate(entries):
            if node is not None:
                out.append(node)
            out.extend(placed.get(k, []))
        return out

    def float_nodes(self, builder):
        kind = builder[0]
        if kind == "figure":
            return [self.figure_node(builder[1], builder[2])]
        if kind == "table":
            return [self.table_node(builder[1])]
        if kind == "equation":
            return [self.equation_node(builder[1])]
        stream = builder[1]
        children = group_lists(self.stream_nodes(stream), self.ctx)
        if kind == "stream" and stream.kind in BOX_KINDS:
            if not children:
                return []
            boxes = [b for c in children for b in c.boxes]
            box = box_of([b for b in boxes], self.number) if boxes else None
            self.ctx.counts["boxes"] += 1
            flagged = Flagged()
            if stream.anchor is not None and stream.anchor.review_required:
                flagged.add("needs_review", "order", "the box's place in the text is uncertain")
            self.ctx.flag_rows[sid(stream.id)] = list(flagged.rows)
            return [
                S.BoxNode(
                    id=sid(stream.id),
                    pages=[self.number],
                    boxes=[box] if box else [],
                    order=0,
                    source="native",
                    confidence=round(stream.confidence, 4),
                    review_status=flagged.status,
                    flags=flagged.flags,
                    provenance=S.Provenance(stages=["reading_order"], reasons=stream.reasons[:3]),
                    refs=S.SourceRefs(),
                    box_kind=BOX_KINDS[stream.kind],
                    children=children,
                )
            ]
        return children

    def furniture_record(self, unit):
        built, content = self.text(unit.line_ids, unit=None, math=False)
        if not content.text:
            return
        flagged = Flagged()
        if unit.review_required or unit.boundary.review_required:
            flagged.add("needs_review", "furniture", "furniture decision below confidence")
        box = box_of([self.spans[s.span.id].bbox for s in built.segments], self.number)
        self.ctx.furniture.append(S.Furniture(
            id=sid(unit.id), kind=unit.kind, page=self.number, boxes=[box] if box else [],
            refs=S.SourceRefs(lines=[sid(x) for x in built.lines]), content=content,
            confidence=round(unit.boundary.confidence, 4), review_status=flagged.status,
            flags=flagged.flags))  # fmt: skip

    def suppress_unit(self, unit):
        built = build_text(self.pieces(unit.line_ids), self.spans)
        if not built.content.text:
            return
        reason = "outside_trimbox" if unit.kind == "artifact" else "invisible_render_mode"
        box = box_of([self.spans[s.span.id].bbox for s in built.segments], self.number)
        self.ctx.suppressed.append(S.Suppressed(
            id=sid(unit.id), reason=reason, page=self.number, boxes=[box] if box else [],
            refs=S.SourceRefs(lines=[sid(x) for x in built.lines]), text=built.content.text,
            source_runs=source_runs(built.segments, self.spans),
            evidence={"stream": unit.stream_kind},
            retained_by_ledger=unit.kind != "artifact"))  # fmt: skip
        self.ctx.counts[f"suppressed_{reason}"] += 1
        if reason != "outside_trimbox":
            self.ctx.review.append((sid(unit.id), self.number, "hidden_text",
                                    "invisible text dropped from content", "needs_review",
                                    box))  # fmt: skip


@dataclass
class _Link:
    unit_id: str
    review_required: bool = False


def _glued(marker, store):
    """The marker's last character and the next character of its source line are both
    letters or digits: the marker is the start of a word ("I" of "Inspection"), not a list
    marker (the ledger reads one token there)."""
    ref = marker.refs[-1]
    span = store.spans[ref.span_id]
    line = next((ln for ln in store.lines if ln.id == span.line_id), None)
    if line is None:
        return False
    offset = 0
    for sid_ in line.span_ids:
        if sid_ == span.id:
            break
        offset += len(store.spans[sid_].raw_text)
    text = store.raw_line_text(line)
    end = offset + (ref.end if ref.end is not None else len(span.raw_text))
    return 0 < end < len(text) and text[end - 1].isalnum() and text[end].isalnum()


def _restricted(unit, line_ids):
    """The unit over the given lines only (a cell's lines of it), joins kept between them."""
    keep = [lid for lid in unit.line_ids if lid in set(line_ids)]
    if not keep or keep == unit.line_ids:
        return unit
    pairs = set(zip(keep, keep[1:], strict=False))
    joins = [j for j in unit.joins if (j.previous_line_id, j.next_line_id) in pairs]
    return unit.model_copy(update={"line_ids": keep, "joins": joins})


def _layout_line(line_spans, span_id):
    for lid, spans in line_spans.items():
        if span_id in spans:
            return lid
    return None


def _evidence(proof):
    return {k: v for k, v in proof.items() if isinstance(v, (str, int, float, bool)) or v is None}


def _format(name, fallback):
    suffix = name.rsplit(".", 1)[-1].casefold()
    return {"jpg": "jpg", "jpeg": "jpg", "png": "png"}.get(suffix, fallback)


def _shift(content, n):
    """``content`` without its first ``n`` characters (leading space after a marker)."""
    data = content.model_dump()
    data["text"] = data["text"][n:]
    if data.get("raw"):
        data["raw"] = data["raw"][n:] if data["raw"][:n].isspace() else data["raw"]
        if data["raw"] == data["text"]:
            data["raw"] = None
    spans = []
    for span in data["spans"]:
        a, b = max(0, span["start"] - n), max(0, span["end"] - n)
        if b > a or (span["kind"] == "math" and b == a):
            spans.append({**span, "start": a, "end": b})
    data["spans"] = spans
    data["source_runs"] = [
        {**r, "start": max(0, r["start"] - n), "end": r["end"] - n}
        for r in data["source_runs"] if r["end"] > n
    ]
    data["joins"] = [
        {
            **j,
            "at": j["at"] - n,
            "hyphen_at": None if j["hyphen_at"] is None else j["hyphen_at"] - n,
        }
        for j in data["joins"]
        if j["at"] >= n
    ]
    return S.TextContent.model_validate(data)


def group_lists(nodes, ctx):
    """Consecutive items of one list → a list node; a nested list directly after its parent
    item → the item's child."""
    out = []
    stack = []  # [(list id, ListNode dict)] open lists, outermost first

    def close_all():
        stack.clear()

    for node in nodes:
        hint = getattr(node, "_list", None)
        if not isinstance(node, S.ListItem) or hint is None or hint[0] is None:
            close_all()
            out.append(node)
            continue
        list_id, level = hint
        structured = ctx.lists.get(list_id, {})
        parent = structured.get("parent_item_id")
        while stack and stack[-1][0] != list_id and (parent is None or not any(
                it.id == sid(parent) for it in stack[-1][1].items)):  # fmt: skip
            stack.pop()
        if stack and stack[-1][0] == list_id:
            stack[-1][1].items.append(node)
            continue
        segment = ctx.counts[f"segment:{list_id}"]
        ctx.counts[f"segment:{list_id}"] += 1
        new = S.ListNode(
            id=sid(stable_id(list_id, "segment", segment)), pages=list(node.pages),
            boxes=[], order=0, source=node.source,
            confidence=round(structured.get("confidence", 1.0), 4),
            review_status="needs_review" if structured.get("review_required") else "ok",
            flags=["structure: list decision below confidence"]
            if structured.get("review_required") else [],
            provenance=S.Provenance(stages=["lists"], reasons=structured.get("reasons", [])[:3]),
            list_id=sid(list_id), segment=segment, list_type=structured.get("kind", "unmarked"),
            list_role=structured.get("role", "general"),
            marker_type=structured.get("marker_type"), start=structured.get("start"),
            level=structured.get("level", level), items=[node],
        )  # fmt: skip
        if stack and parent is not None and stack[-1][1].items[-1].id == sid(parent):
            stack[-1][1].items[-1].children.append(new)
        else:
            close_all()
            out.append(new)
        stack.append((list_id, new))
    return out


def content_hash(book_dict):
    data = {k: v for k, v in book_dict.items() if k != "metadata"}
    meta = {k: v for k, v in book_dict["metadata"].items() if k not in {"run", "content_sha256"}}
    data["metadata"] = meta
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
