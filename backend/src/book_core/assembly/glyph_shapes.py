"""The drawn shape of a marker glyph, from its rendered ink (never from its font or code).

A symbol font's bullet decodes to whatever character its encoding names ("y", "{", "\\x99"),
so the character does not say what readers see. The glyph is rendered alone (its span's box
at a high resolution) and its ink is classified by geometry:

- several separate ink parts: ``ornament`` (a cluster such as ❖);
- a hollow outline (the centre unlinked, a ring of ink around it): ``hollow_square`` when the
  ink reaches the corners of its box, otherwise ``circle``;
- solid ink: by how much of its box it fills and how it is balanced. Nearly full:
  ``square``; about pi/4 and round: ``bullet``; about half and symmetric on both axes:
  ``diamond``; about half and leaning to one side, or wide and leaning (a shaft and head):
  ``arrow``; a thin open stroke: ``check``.

Anything else (a letter, a digit) is ``None``: no shape claim is made.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

DPI = 600
MIN_PIXELS = 12  # ink pixels below which the render says nothing


def ink_mask(gray: np.ndarray) -> np.ndarray:
    """Ink pixels of a grayscale crop: darker than halfway between the paper and the ink."""
    border = np.concatenate([gray[0], gray[-1], gray[:, 0], gray[:, -1]])
    paper, ink = float(np.median(border)), float(gray.min())
    if paper - ink < 40:
        return np.zeros_like(gray, dtype=bool)
    return gray < (paper + ink) / 2


def classify(mask: np.ndarray) -> str | None:
    """Shape name of the ink in ``mask`` (True = ink), or None."""
    if mask.sum() < MIN_PIXELS:
        return None
    labels, count = ndimage.label(mask, structure=np.ones((3, 3)))
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    parts = [s for s in sizes if s >= 0.05 * sizes.max()]
    ys, xs = np.nonzero(mask)
    box = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    h, w = box.shape
    if len(parts) >= 3:
        return "ornament"
    if len(parts) != 1:
        return None
    aspect = w / h
    fill = box.sum() / box.size
    filled = ndimage.binary_fill_holes(box)
    hole = (filled.sum() - box.sum()) / box.size
    corners = _corner_ink(filled)
    if hole >= 0.15 and 0.7 <= aspect <= 1.4:
        return "hollow_square" if corners >= 0.75 else "circle"
    solid = filled.sum() / filled.size
    rows, cols = np.nonzero(filled)
    lean = abs(cols.mean() / max(w - 1, 1) - 0.5)
    tilt = abs(rows.mean() / max(h - 1, 1) - 0.5)
    if 0.7 <= aspect <= 1.4:
        if solid >= 0.9:
            return "square"
        if 0.7 <= solid < 0.9 and corners < 0.25:
            return "bullet"
        if 0.4 <= solid < 0.7 and lean < 0.06 and tilt < 0.06 and corners < 0.1:
            return "diamond"
    if 0.4 <= solid < 0.75 and 0.6 <= aspect <= 2.5 and lean >= 0.06 and tilt < 0.08:
        return "arrow"
    if aspect >= 1.3 and lean >= 0.03 and tilt < 0.1:
        return "arrow"  # a shaft with its head on one side: the ink leans to the head
    if fill < 0.35 and 0.7 <= aspect <= 1.6 and lean >= 0.05:
        return "check"
    return None


def _corner_ink(filled: np.ndarray) -> float:
    """Share of the box's four corner patches (a tenth of each side) that holds ink."""
    h, w = filled.shape
    a, b = max(1, h // 10), max(1, w // 10)
    patches = [filled[:a, :b], filled[:a, -b:], filled[-a:, :b], filled[-a:, -b:]]
    return float(np.mean([p.mean() for p in patches]))


def render_shape(pdf_page, bbox) -> str | None:
    """Shape of the ink inside ``bbox`` (x0, y0, x1, y1 in page points) on ``pdf_page``."""
    import pymupdf

    x0, y0, x1, y1 = bbox
    pad = 0.5
    clip = pymupdf.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) & pdf_page.rect
    if clip.is_empty:
        return None
    pixmap = pdf_page.get_pixmap(dpi=DPI, clip=clip, colorspace=pymupdf.csGRAY, alpha=False)
    gray = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width)
    return classify(ink_mask(gray))


_BULLETS = frozenset("•‣⁃∙⋅∘◦▪▫●○■□◆◇►▶➢➤✓✔※·")


def marker_candidates(store):
    """Span ids of single glyphs that may be list markers: a glyph of a Symbolic font, or a
    symbol, private-use, control or bullet character standing alone in its span."""
    import unicodedata

    found = []
    for sid, span in store.spans.items():
        text = span.raw_text.strip()
        if len(text) != 1:
            continue
        if span.symbolic or unicodedata.category(text) in {"So", "Co", "Cc"} or text in _BULLETS:
            found.append(sid)
    return found


def marker_shapes(source, page):
    """{span id: shape} of the page's marker candidates (shapes the render could name)."""
    from pathlib import Path

    from book_core.run_context import open_source

    spans = marker_candidates(page.store)
    if not spans:
        return {}
    shapes = {}
    with open_source(Path(source)) as document:
        pdf_page = document[page.geometry.page - 1]
        for sid in spans:
            b = page.store.spans[sid].bbox
            shape = render_shape(pdf_page, (b.x0, b.y0, b.x1, b.y1))
            if shape is not None:
                shapes[sid] = shape
    return shapes
