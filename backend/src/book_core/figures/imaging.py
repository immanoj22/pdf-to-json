"""Crop rendering, measured image evidence, the photo/drawing decision and encoding.

The decision uses only measured evidence: how much of the figure is covered by placed raster
images (source type), and colour/tonal statistics of the rendered crop. Photographs are
raster and rich in colours or grey tones; drawings, maps, diagrams and line art are vector,
or dominated by a few flat colours or tones. Tones are counted on 8-bit grey levels as well
as on quantized colours, so a black-and-white photograph is not mistaken for a drawing.
Anything in between is encoded losslessly as PNG and flagged. Every threshold is a
dimensionless share; file names are never consulted.
"""

import hashlib

import cv2
import numpy as np
from shapely import box as shape
from shapely import union_all

from book_core.figures.models import ExportedImage, ImageEvidence

QUANTIZE_BITS = 5  # bits per channel before counting colours
TOP_COLOURS = 16
FLAT_GRADIENT = 4.0  # Sobel magnitude on 0-255 intensities: no visible change
RASTER = 0.6  # raster share above which a figure is raster-sourced
VECTOR = 0.2  # raster share below which it is vector-sourced
PHOTO_DOMINANT = 0.5  # photographs spread over many colours or grey tones
DRAWING_DOMINANT = 0.7  # drawings are dominated by a few flat colours
DRAWING_FLAT = 0.75  # also the flat-pixel limit of a photograph
UNCERTAIN = "photo/drawing evidence is mixed; encoded as PNG; review"


def crop(raster_rgb, scale, bbox):
    """The figure box in a rendered page (RGB array), at least one pixel."""
    height, width = raster_rgb.shape[:2]
    x0 = min(width - 1, max(0, int(np.floor(bbox.x0 * scale))))
    y0 = min(height - 1, max(0, int(np.floor(bbox.y0 * scale))))
    x1 = max(x0 + 1, min(width, int(np.ceil(bbox.x1 * scale))))
    y1 = max(y0 + 1, min(height, int(np.ceil(bbox.y1 * scale))))
    return raster_rgb[y0:y1, x0:x1]


def decode_png(data):
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Rendered page could not be decoded")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def statistics(rgb):
    pixels = rgb.reshape(-1, 3).astype(np.uint32) >> (8 - QUANTIZE_BITS)
    codes = (pixels[:, 0] << (2 * QUANTIZE_BITS)) | (pixels[:, 1] << QUANTIZE_BITS) | pixels[:, 2]
    counts = np.bincount(codes, minlength=1 << (3 * QUANTIZE_BITS))
    total = max(1, codes.size)
    top = np.sort(counts)[::-1][:TOP_COLOURS].sum()
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    flat = float(np.mean(np.hypot(gx, gy) < FLAT_GRADIENT))
    levels = np.bincount(gray.astype(np.uint8).ravel(), minlength=256)
    tonal = np.sort(levels)[::-1][:TOP_COLOURS].sum() / total
    return {
        "colour_count_ratio": round(min(1.0, int(np.count_nonzero(counts)) / total), 6),
        "dominant_colour_share": round(float(top) / total, 6),
        "dominant_tone_share": round(float(tonal), 6),
        "flat_share": round(flat, 6),
    }


def raster_share(bbox, image_boxes):
    figure = shape(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
    if figure.area <= 0 or not image_boxes:
        return 0.0
    covered = union_all([shape(b.x0, b.y0, b.x1, b.y1) for b in image_boxes]).intersection(figure)
    return round(min(1.0, covered.area / figure.area), 6)


def decide(bbox, rgb, image_boxes, vector_objects):
    """(kind, format, confidence, evidence, review reasons)."""
    share = raster_share(bbox, image_boxes)
    stats = statistics(rgb)
    source = "raster" if share >= RASTER else "vector" if share < VECTOR else "mixed"
    dominant = min(stats["dominant_colour_share"], stats["dominant_tone_share"])
    rich = dominant < PHOTO_DOMINANT and stats["flat_share"] < DRAWING_FLAT
    flat = dominant >= DRAWING_DOMINANT or stats["flat_share"] >= DRAWING_FLAT
    if source == "raster" and rich:
        result = ("photo", "jpg", 0.85, "raster source with many colours or grey tones", [])
    elif source == "vector" or flat:
        why = "vector source" if source == "vector" else "a few flat colours or tones dominate"
        result = ("drawing", "png", 0.85 if source == "vector" and flat else 0.75, why, [])
    else:
        kind = "photo" if source == "raster" else "drawing"
        result = (kind, "png", 0.5, "mixed evidence", [UNCERTAIN])
    kind, fmt, confidence, rule, reasons = result
    evidence = ImageEvidence(
        source_type=source,
        raster_share=share,
        raster_objects=len(image_boxes),
        vector_objects=vector_objects,
        decision_rule=rule,
        **stats,
    )
    return kind, fmt, confidence, evidence, reasons


def encode(rgb, fmt, quality):
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if fmt == "jpg":
        ok, data = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    else:
        ok, data = cv2.imencode(".png", bgr, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise ValueError(f"Could not encode {fmt}")
    return data.tobytes()


def exported(stem, fmt, dpi, rgb, data):
    return ExportedImage(
        file_name=f"{stem}.{fmt}",
        format=fmt,
        dpi=dpi,
        width=int(rgb.shape[1]),
        height=int(rgb.shape[0]),
        sha256=hashlib.sha256(data).hexdigest(),
        bytes=len(data),
    )
