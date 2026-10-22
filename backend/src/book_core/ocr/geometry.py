"""Reversible raster preparation; OCR geometry always maps to the source render.

Angles in ``rotation_clockwise`` are clockwise; ``deskew_degrees`` is the OpenCV
counterclockwise correction. Binarisation is used only to estimate skew and never
changes the recognition raster. No enhancement is enabled by this module.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from book_core.extraction.rasters import RasterPage
from book_core.model.common import BBox


@dataclass(frozen=True)
class ImageTransform:
    input_width: int
    input_height: int
    output_width: int
    output_height: int
    source_to_processed: tuple[float, float, float, float, float, float]
    rotation_clockwise: int = 0
    deskew_degrees: float = 0.0

    @classmethod
    def identity(cls, width: int, height: int) -> ImageTransform:
        return cls(width, height, width, height, (1.0, 0.0, 0.0, 0.0, 1.0, 0.0))


def decode_image(png: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("OCR input is not a decodable image")
    return image


def encode_image(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Cannot encode OCR image")
    return encoded.tobytes()


def _homogeneous(matrix: np.ndarray) -> np.ndarray:
    return np.vstack((matrix, (0.0, 0.0, 1.0)))


def rotation_transform(width: int, height: int, clockwise: int) -> ImageTransform:
    if clockwise not in {0, 90, 180, 270}:
        raise ValueError("OSD rotation must be a multiple of 90 degrees")
    if clockwise == 0:
        return ImageTransform.identity(width, height)
    matrices = {
        90: (0.0, -1.0, float(height), 1.0, 0.0, 0.0),
        180: (-1.0, 0.0, float(width), 0.0, -1.0, float(height)),
        270: (0.0, 1.0, 0.0, -1.0, 0.0, float(width)),
    }
    output = (height, width) if clockwise in {90, 270} else (width, height)
    return ImageTransform(width, height, *output, matrices[clockwise], clockwise)


def apply_transform(image: np.ndarray, transform: ImageTransform) -> np.ndarray:
    if image.shape[1::-1] != (transform.input_width, transform.input_height):
        raise ValueError("Image dimensions do not match OCR transform")
    # Boundary coordinates describe pixel edges. OpenCV transforms pixel centres.
    matrix = np.asarray(transform.source_to_processed, dtype=float).reshape(2, 3).copy()
    matrix[:, 2] += matrix[:, :2] @ np.array((0.5, 0.5)) - 0.5
    return cv2.warpAffine(
        image,
        matrix,
        (transform.output_width, transform.output_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def estimate_deskew(image: np.ndarray, *, limit: float = 5.0, step: float = 0.25) -> float:
    """Projection-profile skew estimate; a bounded geometric search, not a text score.

    An optimum at the search boundary is inconclusive and leaves the image alone.
    The caller must measure whether enabling this correction helps its validation set.
    """
    if limit <= 0 or step <= 0 or step > limit:
        raise ValueError("Invalid deskew search")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scale = min(1.0, 1000 / max(gray.shape))
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    _, ink = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    if not ink.any():
        return 0.0
    height, width = ink.shape
    scores = []
    angles = np.arange(-limit, limit + step / 2, step)
    for angle in angles:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), float(angle), 1.0)
        rotated = cv2.warpAffine(ink, matrix, (width, height), flags=cv2.INTER_NEAREST)
        profile = rotated.sum(axis=1, dtype=np.float64)
        scores.append(float(np.square(np.diff(profile)).sum()))
    # Equal scores prefer the smallest rotation, rather than the first search angle.
    best = max(range(len(scores)), key=lambda index: (scores[index], -abs(angles[index])))
    return 0.0 if best in {0, len(scores) - 1} else round(float(angles[best]), 6)


def prepare_image(
    png: bytes, *, rotation_clockwise: int = 0, deskew: bool = False
) -> tuple[bytes, ImageTransform]:
    image = decode_image(png)
    height, width = image.shape[:2]
    transform = rotation_transform(width, height, rotation_clockwise)
    angle = estimate_deskew(apply_transform(image, transform)) if deskew else 0.0
    if angle:
        rotation = cv2.getRotationMatrix2D(
            (transform.output_width / 2, transform.output_height / 2), angle, 1.0
        )
        # Expand the canvas so rotating never clips a source corner or OCR word.
        corners = np.array(
            [
                [0, 0, 1],
                [transform.output_width, 0, 1],
                [transform.output_width, transform.output_height, 1],
                [0, transform.output_height, 1],
            ],
            dtype=float,
        )
        bounds = corners @ rotation.T
        minimum, maximum = bounds.min(axis=0), bounds.max(axis=0)
        rotation[:, 2] -= minimum
        matrix = _homogeneous(rotation) @ _homogeneous(
            np.asarray(transform.source_to_processed).reshape(2, 3)
        )
        transform = ImageTransform(
            width,
            height,
            int(np.ceil(maximum[0] - minimum[0])),
            int(np.ceil(maximum[1] - minimum[1])),
            tuple(float(item) for item in matrix[:2].reshape(-1)),
            rotation_clockwise,
            angle,
        )
    return encode_image(apply_transform(image, transform)), transform


def source_pixel_box(transform: ImageTransform, bbox: tuple[float, float, float, float]) -> BBox:
    """Invert all four corners; rotated rectangles become enclosing source rectangles."""
    x0, y0, x1, y1 = bbox
    matrix = cv2.invertAffineTransform(
        np.asarray(transform.source_to_processed, dtype=float).reshape(2, 3)
    )
    corners = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]]) @ matrix.T
    minimum, maximum = corners.min(axis=0), corners.max(axis=0)
    return BBox(
        x0=max(0.0, min(float(minimum[0]), transform.input_width)),
        y0=max(0.0, min(float(minimum[1]), transform.input_height)),
        x1=max(0.0, min(float(maximum[0]), transform.input_width)),
        y1=max(0.0, min(float(maximum[1]), transform.input_height)),
    )


def pixel_box_to_pdf(
    transform: ImageTransform, bbox: tuple[float, float, float, float], raster: RasterPage
) -> BBox:
    if (raster.width, raster.height) != (transform.input_width, transform.input_height):
        raise ValueError("Raster dimensions do not match OCR transform")
    box = source_pixel_box(transform, bbox)
    sx, sy = raster.page_width / raster.width, raster.page_height / raster.height
    return BBox(x0=box.x0 * sx, y0=box.y0 * sy, x1=box.x1 * sx, y1=box.y1 * sy)
