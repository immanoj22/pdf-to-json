"""Equation images: the region rendered through the Extractor, its own marks kept.

A region box can overlap neighbouring text or drawings; everything outside the region's own
marks (its drawn objects and character boxes, widened by a small share of the book's text
size) is painted white, so a recognizer reads only the equation. The same crop is the
fallback image of a low-confidence equation.
"""

import cv2
import numpy as np

PAD = 0.3  # crop margin around the region, in book text sizes
MASK_MARGIN = 0.12  # kept margin around each own mark, in book text sizes


def _decode(png):
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Rendered page could not be decoded")
    return image


class RegionImages:
    """Renders pages through the extractor (one page held) and crops equation regions."""

    def __init__(self, extractor, source, dpi):
        self.extractor, self.source, self.dpi = extractor, source, dpi
        self._page, self._image, self._scale = None, None, None

    def _render(self, number):
        if self._page != number:
            raster = self.extractor.render_page(self.source, number, self.dpi)
            self._image = _decode(raster.png)
            self._scale = raster.width / raster.page_width
            self._page = number
        return self._image, self._scale

    def crop(self, number, box, marks, book_size, direction=(1.0, 0.0)):
        """PNG bytes of ``box`` (x0, y0, x1, y1) on page ``number`` with only ``marks`` kept,
        turned so that a line written in ``direction`` reads left to right."""
        image, scale = self._render(number)
        height, width = image.shape[:2]
        pad = PAD * book_size

        def pixels(x0, y0, x1, y1):
            return (
                max(0, int(np.floor(x0 * scale))),
                max(0, int(np.floor(y0 * scale))),
                min(width, int(np.ceil(x1 * scale))),
                min(height, int(np.ceil(y1 * scale))),
            )

        cx0, cy0, cx1, cy1 = pixels(box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
        if cx1 <= cx0 or cy1 <= cy0:
            raise ValueError("Equation region lies outside the rendered page")
        keep = np.zeros((height, width), np.uint8)
        margin = MASK_MARGIN * book_size
        for x0, y0, x1, y1 in marks:
            px0, py0, px1, py1 = pixels(x0 - margin, y0 - margin, x1 + margin, y1 + margin)
            keep[py0:py1, px0:px1] = 1
        crop = image[cy0:cy1, cx0:cx1].copy()
        crop[keep[cy0:cy1, cx0:cx1] == 0] = 255
        crop = _upright(crop, direction)
        ok, data = cv2.imencode(".png", crop, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        if not ok:
            raise ValueError("Could not encode the equation image")
        return data.tobytes()


def _upright(crop, direction):
    """The crop turned so that the writing direction points right (quarter turns only; a
    line at another angle keeps the page orientation)."""
    dx, dy = direction
    if dx > 0.9:
        return crop
    if dy < -0.9:  # written upwards (rotated a quarter turn counter-clockwise)
        return cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
    if dy > 0.9:  # written downwards
        return cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if dx < -0.9:
        return cv2.rotate(crop, cv2.ROTATE_180)
    return crop


def region_direction(region, text):
    """Writing direction of a region's characters (drawn regions: the page's)."""
    from book_core.mathml.symbols import direction_of

    if not region.span_refs or text is None:
        return (1.0, 0.0)
    return direction_of(text.geometry, region.span_refs[0].span_id)


def region_marks(region, objects, text):
    """Boxes of a region's own marks: its drawn objects and its characters' glyph boxes."""
    marks = [
        (o.bbox.x0, o.bbox.y0, o.bbox.x1, o.bbox.y1)
        for oid in region.object_ids
        if (o := objects.get(oid)) is not None and o.bbox is not None
    ]
    for ref in region.span_refs:
        marks += [s.box for s in text.span_symbols(ref.span_id, ref.start, ref.end)]
    return marks
