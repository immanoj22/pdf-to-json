"""Optional scan-text screen from two layout readers and text-only detection.

Layout confidence is not an accuracy probability.  Agreement supplies a conservative
text-region proposal, with every figure found by either reader masked.  Native readable
text, unsupported regions and disputed figure/text areas stay untouched.  Model revisions,
pixels and full observations are persisted as independent eligibility evidence.
"""

import hashlib
import json
from pathlib import Path

import numpy as np

from book_core.cache_store import write_json
from book_core.detection.cache import detect_page
from book_core.extraction.fingerprints import stable_id
from book_core.figures.evidence import supported
from book_core.model.common import BBox
from book_core.ocr.detection import RenderTextCheck, _intersection, unusable_codepoint
from book_core.ocr.geometry import decode_image, encode_image

TEXT_TYPES = frozenset(
    {
        "main_text",
        "title_candidate",
        "heading_candidate",
        "caption_candidate",
        "footnote_candidate",
        "header_footer_candidate",
        "sidebar",
    }
)


def _union(a, b):
    return BBox(x0=min(a.x0, b.x0), y0=min(a.y0, b.y0), x1=max(a.x1, b.x1), y1=max(a.y1, b.y1))


def _merged(boxes):
    """Merge intersecting candidate crops so OCR can never duplicate their words."""
    result = []
    for box in boxes:
        while any(_intersection(box, other) is not None for other in result):
            remaining = []
            for other in result:
                if _intersection(box, other) is not None:
                    box = _union(box, other)
                else:
                    remaining.append(other)
            result = remaining
        result.append(box)
    return result


def agreed_text_checks(native, eligibility, first, second, text_boxes, *, evidence):
    """Pure decision over observations in PDF coordinates; existing 50%-smaller matcher.

    Both layout readers must call the area textual; PP text-only detection must support
    it, and neither reader may call the same text box a figure.  A small PP text box in a
    photograph therefore cannot authorize figure OCR.  No language/font/page is special.
    """
    for result in (first, second):
        if (result.source_sha256, result.page) != (
            native.page.source_sha256,
            native.page.geometry.page,
        ):
            raise ValueError("Visual eligibility evidence belongs to another source/page")
    if first.detector == second.detector:
        raise ValueError("Visual eligibility requires two independent layout readers")
    figures = _merged(
        [
            region.bbox
            for result in (first, second)
            for region in result.regions
            if region.type == "figure"
        ]
        + [box for region in eligibility.regions for box in region.excluded_figure_boxes]
    )
    candidates = []
    for a in first.regions:
        if a.type not in TEXT_TYPES or supported(a.bbox, figures):
            continue
        for b in second.regions:
            if b.type not in TEXT_TYPES or supported(b.bbox, figures):
                continue
            if not supported(a.bbox, [b.bbox]):
                continue
            box = _union(a.bbox, b.bbox)
            if not any(
                _intersection(box, region.bbox) is not None
                for region in eligibility.regions
                if region.action in {"review", "compare_only"}
            ):
                continue
            if not supported(box, text_boxes):
                continue
            spans = [s for s in native.page.store.spans.values() if box.contains_center(s.bbox)]
            if any(
                not unusable_codepoint(ord(c)) for s in spans for c in s.raw_text if not c.isspace()
            ):
                continue
            candidates.append(box)
    return [
        RenderTextCheck(
            bbox=box,
            outcome="text_present",
            method="two_layout_readers_agree_text_and_pp_text_detection_outside_any_figure",
            evidence=list(evidence),
            excluded_figure_boxes=figures,
            native_span_ids=[
                s.id for s in native.page.store.spans.values() if box.contains_center(s.bbox)
            ],
        )
        for box in _merged(candidates)
    ]


class LearnedVisualTextChecks:
    """``prepare_book`` callback; all source rendering remains behind the Extractor.

    ``detectors`` are the existing pinned Heron and PP-DocLayoutV3 instances.  They use
    their established thresholds and 72-dpi caches. ``text_detector`` supplies the new
    PP-OCRv5 ``detect_text`` interface without invoking a text recognizer.  Sources, model
    directories and evidence roots are explicit caller configuration, never global paths.
    """

    def __init__(self, source, extractor, detectors, text_detector, cache_dir, evidence_dir):
        if len(detectors) != 2:
            raise ValueError("Visual eligibility needs exactly two layout readers")
        self.source, self.extractor = Path(source), extractor
        self.detectors, self.text_detector = tuple(detectors), text_detector
        self.cache_dir, self.evidence_dir = Path(cache_dir), Path(evidence_dir)
        self.last_evidence = None

    def __call__(self, native, raster, eligibility):
        if eligibility.decision not in {"review", "compare_only"}:
            return []
        layouts = [
            detect_page(
                self.source, native.page.geometry.page, self.extractor, detector, self.cache_dir
            )
            for detector in self.detectors
        ]
        figures = _merged(
            [r.bbox for result in layouts for r in result.regions if r.type == "figure"]
        )
        figures += [b for r in eligibility.regions for b in r.excluded_figure_boxes]
        pixels = decode_image(raster.png)
        for box in figures:
            x0 = max(0, int(np.floor(box.x0 * raster.width / raster.page_width)))
            x1 = min(raster.width, int(np.ceil(box.x1 * raster.width / raster.page_width)))
            y0 = max(0, int(np.floor(box.y0 * raster.height / raster.page_height)))
            y1 = min(raster.height, int(np.ceil(box.y1 * raster.height / raster.page_height)))
            pixels[y0:y1, x0:x1] = 255
        masked = encode_image(pixels)
        pixel_boxes = self.text_detector.detect_text(masked)
        boxes = [
            BBox(
                x0=b.x0 * raster.page_width / raster.width,
                x1=b.x1 * raster.page_width / raster.width,
                y0=b.y0 * raster.page_height / raster.height,
                y1=b.y1 * raster.page_height / raster.height,
            )
            for b in pixel_boxes
        ]
        evidence = {
            "source_sha256": native.page.source_sha256,
            "page": native.page.geometry.page,
            "raster_sha256": hashlib.sha256(raster.png).hexdigest(),
            "masked_raster_sha256": hashlib.sha256(masked).hexdigest(),
            "layout_readers": [r.model_dump(mode="json") for r in layouts],
            "pp_detector": self.text_detector.identity,
            "text_boxes": [b.model_dump() for b in boxes],
            "figure_masks": [b.model_dump() for b in figures],
            "calibration": (
                "existing layout thresholds and overlap rule; "
                "OCR eligibility accuracy not calibrated"
            ),
        }
        key = stable_id(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
        path = self.evidence_dir / key / f"{eligibility.page}.json.gz"
        checks = agreed_text_checks(native, eligibility, *layouts, boxes, evidence=[str(path)])
        evidence["checks"] = [c.model_dump(mode="json") for c in checks]
        write_json(path, evidence)
        self.last_evidence = evidence
        return checks
