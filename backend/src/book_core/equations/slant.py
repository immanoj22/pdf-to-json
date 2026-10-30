"""Characters drawn slanted by their text matrix (synthetic italic: an upright font sheared
when painted, which font names and flags cannot show; one span can mix upright and slanted
glyphs).

MuPDF's interpreter reports each glyph's full matrix; a glyph is slanted when the angle
between its x and y axes departs from a right angle by at least ``SLANT`` (cosine). Glyphs
pair with stored characters by code point and origin, through PyMuPDF's raw extraction in
extraction order and checked by text; a page whose spans cannot be paired gets no slant
evidence (never guessed). Shared by equation detection (a slanted variable) and assembly
(italic styling).
"""

import math

import pymupdf
from pymupdf import mupdf as m

SLANT = 0.1  # |cos| of the angle between a glyph's axes (about 6 degrees of shear)


class _SlantDevice(m.FzDevice2):
    """Records (code point, origin, shear) of every painted glyph; draws nothing."""

    def __init__(self):
        super().__init__()
        self.glyphs = []
        self.use_virtual_fill_text()
        self.use_virtual_stroke_text()

    def _record(self, text, matrix):
        span = text.head
        while span:
            wrapper = m.FzTextSpan(span)
            for i in range(span.len):
                item = wrapper.items(i)
                trm = wrapper.trm()
                trm.e, trm.f = item.x, item.y
                t = m.fz_concat(trm, m.FzMatrix(matrix))
                u, v = math.hypot(t.a, t.b), math.hypot(t.c, t.d)
                shear = (t.a * t.c + t.b * t.d) / (u * v) if u and v else 0.0
                origin = m.fz_transform_point(m.FzPoint(item.x, item.y), m.FzMatrix(matrix))
                self.glyphs.append((item.ucs, round(origin.x, 2), round(origin.y, 2), shear))
            span = span.next

    def fill_text(self, _ctx, text, ctm, *args):
        self._record(text, ctm)

    def stroke_text(self, _ctx, text, stroke, ctm, *args):
        self._record(text, ctm)


def raw_spans(page):
    """PyMuPDF's raw spans of a page, in extraction order."""
    raw = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT, sort=False)
    blocks = [b for b in raw["blocks"] if b["type"] == 0]
    return [s for b in blocks for line in b["lines"] for s in line["spans"]]


def paired(stored, raw):
    """The stored spans and the raw spans are the same spans, in the same order."""
    return len(raw) == len(stored) and all(
        span.raw_text == "".join(c["c"] for c in record["chars"])
        for span, record in zip(stored, raw, strict=True)
    )


def character_slants(page, stored, raw):
    """{span id: [True/False/None per character]}: drawn slanted or upright; None for a
    character without a painted glyph of its own (a space). ``{}`` when the page cannot be
    interpreted."""
    device = _SlantDevice()
    try:
        m.fz_run_page(page.this, device, m.FzMatrix(), m.FzCookie())
        m.fz_close_device(device)
    except Exception:  # noqa: BLE001 - an unreadable page gets no slant evidence
        return {}
    shear = {}
    for ucs, x, y, value in device.glyphs:
        shear.setdefault((ucs, x, y), value)
    found = {}
    for span, record in zip(stored, raw, strict=True):
        flags = []
        for c in record["chars"]:
            key = (ord(c["c"]), round(c["origin"][0], 2), round(c["origin"][1], 2))
            value = shear.get(key) if len(c["c"]) == 1 else None
            flags.append(None if value is None or not c["c"].strip() else abs(value) >= SLANT)
        found[span.id] = flags
    return found


def slanted_characters(page, store) -> frozenset:
    """{(span id, offset)} of the page's characters drawn slanted; empty when unpaired."""
    stored, raw = list(store.spans.values()), raw_spans(page)
    if not paired(stored, raw):
        return frozenset()
    return frozenset(
        (sid, offset)
        for sid, flags in character_slants(page, stored, raw).items()
        for offset, flag in enumerate(flags)
        if flag
    )
