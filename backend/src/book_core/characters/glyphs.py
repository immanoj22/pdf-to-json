"""Named glyph occurrences, attributed to native spans by the paint audit's exact matching."""

from pymupdf import mupdf as m

from book_core.paint.device import PaintDevice
from book_core.paint.proof import attribute


class GlyphNameDevice(PaintDevice):
    """The read-only paint audit, additionally reading each glyph's name from its font."""

    def text_items(self, text, matrix):
        rows = super().text_items(text, matrix)
        fonts, span, index = {}, text.head, 0
        while span:
            fonts[index] = m.FzTextSpan(span).font()
            span, index = span.next, index + 1
        for row in rows:
            gid = row["glyph_id"]
            row["glyph_name"] = (
                m.fz_get_glyph_name2(fonts[row["index"][0]], gid) if gid >= 0 else None
            ) or None
        return rows


def glyph_events(pdf_page):
    device = GlyphNameDevice()
    m.fz_run_page(pdf_page.this, device, m.FzMatrix(), m.FzCookie())
    m.fz_close_device(device)
    if device.errors:
        raise RuntimeError("; ".join(device.errors))
    return device.events


def span_glyphs(page, raw, events):
    """{span id: [(offset, decoded codepoints, glyph)]} for exactly attributed spans.

    A glyph that decodes to several characters is followed by items without a glyph; those
    characters belong to the preceding glyph. Offsets index the span's original text.
    """
    matches, _ = attribute(page, raw, events)
    records = [
        s for b in raw["blocks"] if b["type"] == 0 for line in b["lines"] for s in line["spans"]
    ]
    result = {}
    for span, record in zip(page.store.spans.values(), records, strict=True):
        pairs = matches.get(span.id)
        if pairs is None:
            continue
        offsets = [
            i
            for i, c in enumerate(record["chars"])
            if not (c.get("synthetic", False) and c["c"].isspace())
        ]
        if len(offsets) != len(pairs):
            raise ValueError("Glyph attribution does not align with span characters")
        groups = []
        for offset, (_, glyph) in zip(offsets, pairs, strict=True):
            if glyph["glyph_id"] < 0 and groups:
                groups[-1][1].append(glyph["unicode"])
                continue
            groups.append((offset, [glyph["unicode"]], glyph))
        result[span.id] = groups
    return result
