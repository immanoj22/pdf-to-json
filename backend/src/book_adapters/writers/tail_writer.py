"""Tail writer: the numbered reference list as reference XML (see :mod:`book_adapters.formats.tail`).

Two kinds of source, told apart by the book parts the converter recorded:

* a **references-only** book (the whole PDF is one reference list): every text of the book, in
  reading order; the list starts at the last ``[1]`` marker, text before it is not a reference;
* a **full book**: the entries of every bibliography the adapter tree holds, one reference per
  entry (a printed ``[n]`` is the number, else the entry's position).

Every source line is accounted for: written in a reference, or omitted with a reason (running
header, page number, text outside the list), so the lossless check reads 0 missing / 0 extra.
A reference that does not fit the journal pattern is written best-effort and is a review item,
fixable in Browse (the writer reads the edited book)."""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass

from ..engine.format_profile import format_section
from ..engine.ledger import Entry, Ledger
from ..engine.model import Bibliography, Document, Omission, ReviewEntry
from ..formats import anystyle, hybrid, tail, vancouver
from .base import Delivery, WriteContext

SOURCE_PARTS = ("front", "body", "appendix", "glossary", "index")
OUTSIDE = "text outside the reference list"


@dataclass
class Line:
    addr: str
    start: int
    end: int
    text: str
    group: int  # the entry it belongs to (full book); 0 for a references-only book
    parent: Line | None = None  # the whole line this is a part of
    is_marker: bool = False  # the printed number of an entry, kept apart by the converter

    @property
    def root(self) -> Line:
        return self.parent or self

    @property
    def unit(self) -> str:
        return self.addr.split("#", 1)[0].split("/", 1)[0]


def references_only(book) -> bool:
    """True when the converter was told the whole PDF is one reference list."""
    parts = (book.data.get("metadata") or {}).get("book_parts") or {}
    return bool(parts.get("bibliography")) and not any(parts.get(k) for k in SOURCE_PARTS)


def _find(node, kind):
    """Every ``kind`` instance in the adapter tree, in document order."""
    out = []
    if isinstance(node, kind):
        out.append(node)
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        for f in dataclasses.fields(node):
            out += _find(getattr(node, f.name), kind)
    elif isinstance(node, (list, tuple)):
        for item in node:
            out += _find(item, kind)
    return out


def _lines_of(addr: str, content: dict, ranges, group: int, marker: bool = False) -> list[Line]:
    text = content["text"]
    out = []
    for start, end in ranges:
        pos = start
        for raw in text[start:end].split("\n"):
            out.append(Line(addr, pos, pos + len(raw), raw, group, None, marker))
            pos += len(raw) + 1
    return out


def source_lines(doc: Document, book) -> tuple[str, list[Line]]:
    """(``document`` | ``bibliography``, the lines that may hold references, in order)."""
    if references_only(book):
        order = sorted(doc.records, key=lambda a: doc.order[a])
        return "document", [ln for a in order for ln in _lines_of(a, doc.records[a], [(0, len(doc.records[a]["text"]))], 0)]
    lines, group = [], 0
    for bib in _find([*doc.front, *doc.body, *doc.back, *doc.after], Bibliography):
        for entry in bib.entries:
            group += 1
            if entry.marker_ref is not None:
                ref = entry.marker_ref
                lines += _lines_of(ref.addr, ref.content, ref.ranges, group, True)
            for part in entry.parts:
                if hasattr(part, "addr"):
                    lines += _lines_of(part.addr, part.content, part.ranges, group)
    return "bibliography", lines


@dataclass
class Item:
    """One reference as the source prints it."""

    number: int | None
    marker: list[Line]  # the printed number (a part of a line, or a line)
    body: list[Line]


def _items(lines: list[Line]) -> tuple[list[Item], list[Line]]:
    """The numbered list in ``lines``: (items, the lines before the first marker)."""
    text = "\n".join(ln.text for ln in lines)
    starts, pos = [], 0
    for ln in lines:
        starts.append(pos)
        pos += len(ln.text) + 1

    def at(offset: int) -> int:  # index of the line holding the offset
        lo, hi = 0, len(lines) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo

    blocks = vancouver.numbered_blocks(text)
    if not blocks:
        return [], lines
    items = []
    for b in blocks:
        first = at(b.marker[0])
        ln = lines[first]
        cut = min(b.marker[1] - starts[first], len(ln.text))  # the marker's part of its line
        marker = [Line(ln.addr, ln.start, ln.start + cut, ln.text[:cut], ln.group, ln)]
        body = []
        if cut < len(ln.text):  # "[1] Newman ...": the rest of the line is the reference
            body.append(Line(ln.addr, ln.start + cut, ln.end, ln.text[cut:], ln.group, ln))
        last = at(b.body[1]) - 1 if b.body[1] < len(text) else len(lines) - 1
        body += lines[first + 1 : last + 1]
        items.append(Item(b.number, marker, body))
    return items, lines[: at(blocks[0].marker[0])]


NUMBER = re.compile(r"^\(?(\d{1,4})[.)\]]\s+")  # "12. ", "12) ", "(12) ": a printed number


def _items_grouped(lines: list[Line]) -> list[Item]:
    """A full book: the items of each bibliography entry. The number is the entry's printed
    marker; an entry with none is numbered by its position."""
    groups: dict[int, list[Line]] = {}
    for ln in lines:
        groups.setdefault(ln.group, []).append(ln)
    out: list[Item] = []
    for _, members in sorted(groups.items()):
        marks = [ln for ln in members if ln.is_marker]
        rest = [ln for ln in members if not ln.is_marker]
        items, before = _items(rest) if rest else ([], [])
        lead = before if items else rest
        if lead:
            number = None
            found = re.search(r"\d+", " ".join(ln.text for ln in marks))
            if found:
                number = int(found.group())
            peeled = []
            m = NUMBER.match(lead[0].text) if not marks else None
            if m:
                ln, cut = lead[0], m.end()
                number = int(m.group(1))
                peeled = [Line(ln.addr, ln.start, ln.start + cut, ln.text[:cut], ln.group, ln)]
                lead = [Line(ln.addr, ln.start + cut, ln.end, ln.text[cut:], ln.group, ln), *lead[1:]]
            out.append(Item(number, [*marks, *peeled], lead))
        out += items
    return out


class TailWriter:
    name = "tail"

    @staticmethod
    def learn(ctx, ref, unit: str) -> None:
        """A reference a person corrected in the review and that is now read without a flag is a
        training sample (one local file, with the job id; see :mod:`book_adapters.refmodel`)."""
        folder = (ctx.options or {}).get("training_dir")
        reasons = ((ctx.book.units.get(unit) or {}).get("provenance") or {}).get("reasons") or []
        if folder and not ref.flags and any(r.startswith("text corrected by") for r in reasons):
            from .. import refmodel

            refmodel.record(folder, (ctx.options or {}).get("job_id") or "", ref)

    def write(self, doc: Document, ctx: WriteContext) -> Delivery:
        cfg = self.cfg = format_section(ctx.profile, "tail")
        options = (ctx.settings.data.get("options") or {}) if ctx.settings else {}
        mode = options.get("accents") or cfg["accents"]
        if mode not in tail.ACCENT_MODES:
            mode = cfg["accents"]
        scope, lines = source_lines(doc, ctx.book)
        if scope == "document":
            items, _ = _items(lines)
        else:
            items = _items_grouped(lines)
        used = {id(ln.root) for it in items for ln in (*it.marker, *it.body)}
        headers = vancouver.detect_headers("\n".join(ln.text for ln in lines))

        delivery = Delivery(root="")
        ledger = Ledger()
        omitted: dict[tuple[str, str], list[tuple[int, int]]] = {}
        references = []

        def omit(ln: Line, reason: str):
            omitted.setdefault((ln.addr, reason), []).append((ln.start, ln.end))

        for ln in lines:
            if id(ln) not in used:
                omit(ln, OUTSIDE)
        counter = 0
        pending = []  # (number, printed text, its lines)
        for it in items:
            kept = []
            for ln in it.body:
                why = vancouver.line_kind(ln.text, headers)
                if why is None:
                    kept.append(ln)
                else:
                    omit(ln, why)
            for ln in it.marker:
                ledger.entries.append(
                    Entry("structure", "", -1, ln.addr, [(ln.start, ln.end)], doc.order.get(ln.addr), None,
                          "reference number")
                )
            if not kept:
                continue
            counter += 1
            text = vancouver.tidy(vancouver.join_lines([ln.text.strip() for ln in kept]))
            pending.append((it.number if it.number is not None else counter, text, kept))
        # each reference is read by the trained parser and by the rules; the validators decide
        for ref, (_, _, kept) in zip(hybrid.resolve_all([(n, t) for n, t, _ in pending]), pending, strict=True):
            block = ledger.block_id(ref)
            for ln in kept:
                ledger.entries.append(
                    Entry("text", tail.written(ln.text + " ", mode), block, ln.addr,
                          [(ln.start, ln.end)], doc.order.get(ln.addr))
                )
            references.append((ref, kept[0]))
            self.learn(ctx, ref, kept[0].unit)

        # every record text of the book that no reference holds is omitted, with its reason
        covered = {ln.addr for ln in lines}
        for addr, content in doc.records.items():
            if addr not in covered:
                doc.omissions.append(Omission(addr, [(0, len(content["text"]))], OUTSIDE, content))
        doc.omissions.extend(
            Omission(addr, sorted(spans), reason, doc.records.get(addr))
            for (addr, reason), spans in omitted.items()
        )

        refs = [r for r, _ in references]
        numbers = [r.number for r in refs]
        if scope == "document" and numbers != list(range(1, len(numbers) + 1)):
            delivery.reviews.append(
                ReviewEntry("reference", "the reference numbers are not 1..N in order "
                            f"(first: {numbers[:6]}): check that none is missing or repeated",
                            severity="must_check")
            )
        for ref, first in references:
            if ref.flags:
                unit = first.unit
                page = (ctx.book.units.get(unit) or {}).get("pages", [None])[0]
                delivery.reviews.append(
                    ReviewEntry("reference", f"[{ref.number}] {'; '.join(ref.flags)}: {ref.full[:110]}",
                                unit, page, "tail_reference", "needs_review")
                )
        isbn = (ctx.settings.data.get("isbn") if ctx.settings else None) or ""
        delivery.root = f"{isbn}_tail" if isbn else "tail"
        name = cfg["files"]["tail"]
        delivery.files[name] = tail.document(refs, mode)
        delivery.main_file = name
        delivery.spine = [name]
        delivery.split_files = {name: "tail"}
        delivery.ledger = ledger
        delivery.tail = {"parser": "anystyle" if anystyle.available() else "rules only", "scope": scope, "mode": mode, "references": len(refs),
                         "flagged": sum(1 for r in refs if r.flags)}
        return delivery
