"""Hidden text: which retained source text is confirmed not visible, with its proof.

Confirmed hidden text is dropped from content and listed in ``suppressed`` with the reason;
text that is merely small or light is never dropped. Three kinds of evidence:

- **render mode 3** (or zero opacity): lines the layout already set apart as invisible
  (``invisible`` units), when they lie over visible text of the page (an invisible text
  layer over a page-size scan is an OCR layer: compared, never dropped here);
- **covered by later paint**: spans the paint stage proved fully covered by later opaque
  paint (zero changed pixels at two resolutions when suppressed; ``visibility_evidence``);
- **not rendered**: spans that are near-white, smaller than 1 pt or of zero area are render-
  checked the same way: the page region is rendered with and without the span's glyphs at
  two resolutions; only when no pixel changes is the span hidden (white on white, zero size,
  clipped away). Light text on a dark fill changes pixels and stays.

Off-page text (outside the TrimBox) is the ledger's explicit discard; it is listed in
``suppressed`` by the assembly, not decided here.
"""

from __future__ import annotations

from pathlib import Path

LIGHT = 0.85  # relative luminance from which a span is render-checked
TINY = 1.0  # points
VERSION = "hidden-1"


def luminance(color):
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def candidates(store):
    """Span ids worth a render check (near-white, tiny or zero-area, with text)."""
    found = []
    for span in store.spans.values():
        if span.provenance.method != "native" or not span.raw_text.strip():
            continue
        box = span.bbox
        if (
            luminance(span.color) >= LIGHT
            or span.size < TINY
            or box.x1 <= box.x0
            or box.y1 <= box.y0
        ):
            found.append(span.id)
    return sorted(found)


def render_proofs(source, page, span_ids):
    """{span id: evidence} of the candidates proven not rendered; failures keep the span
    visible (the reason is returned under ``_unproven``)."""
    if not span_ids:
        return {}
    import pymupdf

    from book_core.paint.device import inspect_page
    from book_core.paint.proof import attribute, compare_render
    from book_core.run_context import open_source

    proofs, unproven = {}, {}
    with open_source(Path(source)) as document:
        pdf_page = document[page.geometry.page - 1]
        try:
            raw = pdf_page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT, sort=False)
            events = inspect_page(pdf_page)
            matched, _ = attribute(page, raw, events)
        except (AssertionError, ValueError, RuntimeError) as error:
            return {"_unproven": {sid: f"attribution failed: {type(error).__name__}"
                                  for sid in span_ids}}  # fmt: skip
        baselines = {}
        for sid in span_ids:
            pairs = matched.get(sid)
            if not pairs:
                unproven[sid] = "glyphs not attributed"
                continue
            try:
                result = compare_render(pdf_page, pairs, (2, 4), baselines=baselines)
            except (AssertionError, ValueError, RuntimeError) as error:
                unproven[sid] = f"render failed: {type(error).__name__}"
                continue
            if result.get("valid") and result["no_pixel_change"]:
                span = page.store.spans[sid]
                proofs[sid] = {
                    "rule": "suppressing the span's glyphs changes zero pixels at 144 and 288 dpi",
                    "luminance": round(luminance(span.color), 3),
                    "size": round(span.size, 3),
                    "pixels_compared": sum(r["pixels"] for r in result["renders"]),
                }
            elif not result.get("valid"):
                unproven[sid] = result.get("reason", "invalid render")
    if unproven:
        proofs["_unproven"] = unproven
    return proofs
