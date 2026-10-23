"""Per-page OCR cache with input pixels, native evidence, configuration and asset closure."""

import hashlib
import json
import os
import uuid
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np

from book_core.atomic import replace_with_retry
from book_core.cache_store import read_model, write_model
from book_core.caching import assert_producer_unchanged, code_digest, runtime_versions
from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.model.spans import SpanStore
from book_core.ocr.engines import compare_readings
from book_core.ocr.geometry import decode_image, encode_image
from book_core.ocr.language_choice import lingua_detector, read_with_language_choice
from book_core.ocr.languages import map_languages
from book_core.ocr.tokens import OcrPage, build_ocr_page

VERSION = "ocr-page-1"
LOADED_DIGEST = code_digest("ocr")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_DETECTOR = []


def _detector():
    if not _DETECTOR:
        _DETECTOR.append(lingua_detector())
    return _DETECTOR[0]


def mask_region(raster, region):
    """Retain only eligible pixels, whitening every known figure even on a scan."""
    image = decode_image(raster.png)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)

    def bounds(box):
        return (
            max(0, int(np.floor(box.x0 * raster.width / raster.page_width))),
            max(0, int(np.floor(box.y0 * raster.height / raster.page_height))),
            min(raster.width, int(np.ceil(box.x1 * raster.width / raster.page_width))),
            min(raster.height, int(np.ceil(box.y1 * raster.height / raster.page_height))),
        )

    x0, y0, x1, y1 = bounds(region.bbox)
    mask[y0:y1, x0:x1] = 255
    for box in region.excluded_figure_boxes:
        x0, y0, x1, y1 = bounds(box)
        mask[y0:y1, x0:x1] = 0
    return encode_image(np.where(mask[:, :, None] != 0, image, 255).astype(np.uint8))


def page_fingerprint(native, raster, eligibility, settings, primary, secondary, native_languages):
    languages = map_languages(
        tuple(
            dict.fromkeys(
                (
                    *native_languages,
                    *(
                        code
                        for region in settings.regions.values()
                        for code in (region.ocr_languages or [])
                    ),
                )
            )
        )
    )
    # OSD can select any installed script. Pin all candidate packs in that case.
    packs = (
        tuple(dict.fromkeys((*languages, "osd")))
        if languages
        else tuple(primary.identity["installed_languages"])
    )
    inputs = {
        "version": VERSION,
        "producer": code_digest("ocr"),
        "source": native.page.source_sha256,
        "page": native.page.geometry.page,
        "native": hashlib.sha256(native.page.model_dump_json().encode()).hexdigest(),
        "raster": hashlib.sha256(raster.png).hexdigest(),
        "eligibility": eligibility.model_dump(mode="json"),
        "settings": settings.model_dump(mode="json"),
        "primary": primary.identity,
        "primary_models": primary.model_fingerprints(packs),
        "secondary": secondary.identity if secondary else None,
        "asset_manifest": source_digest(settings.ocr.asset_manifest),
        "native_languages": list(native_languages),
        "runtime": runtime_versions(),
    }
    return stable_id(_canonical(inputs))


def _horizontal_han(reading):
    if reading is None or not reading.words:
        return False
    lines = defaultdict(list)
    han = False
    for word in reading.words:
        if word.text_direction == "ttb":
            return False
        han |= word.script == "Hani"
        lines[word.line_key].append(word.pixel_bbox)
    return han and all(
        max(b[2] for b in boxes) - min(b[0] for b in boxes)
        > max(b[3] for b in boxes) - min(b[1] for b in boxes)
        for boxes in lines.values()
    )


def pp_first(ocr_settings, languages, reading=None, primary=None):
    """Promote only the measured horizontal Chinese print, with usable reading evidence.

    Vertical Chinese was measured separately and both readers were unreliable. A
    language code alone therefore cannot justify replacing the primary reading.
    Unknown or ambiguous geometry keeps Tesseract and the second-reader evidence.
    """
    chosen = {code for code in languages if code != "osd"}
    eligible = (
        ocr_settings.accuracy_mode == "best_measured"
        and bool(chosen)
        and chosen <= set(ocr_settings.pp_primary)
        and chosen <= {"chi_sim", "chi_tra"}
    )
    return eligible and _horizontal_han(reading) and _horizontal_han(primary)


def _page_status(parts):
    """The most severe status of the page's regions (each by its reader's calibration)."""
    found = {part.review_status for part in parts}
    if "must_check" in found or not any(part.words for part in parts):
        return "must_check"
    return "needs_review" if "needs_review" in found else None


def recognize_page(
    native, raster, eligibility, settings, primary, secondary, directory, *, native_languages=()
):
    """Return (record, cache key, hit); no eligible region means no OCR invocation."""
    assert_producer_unchanged("ocr", LOADED_DIGEST)
    regions = [r for r in eligibility.regions if r.action in {"ocr", "compare_only"}]
    if not regions:
        return None, None, False
    if (
        eligibility.source_sha256 != native.page.source_sha256
        or eligibility.page != native.page.geometry.page
    ):
        raise ValueError("OCR eligibility belongs to another source/page")
    key = page_fingerprint(
        native, raster, eligibility, settings, primary, secondary, native_languages
    )
    path = Path(directory) / key / f"{eligibility.page}.json"
    raster_path = path.parent / "images" / f"{eligibility.page}.png"
    if path.exists():
        record = read_model(path, OcrPage, key)
        if (
            record.page.source_sha256 != native.page.source_sha256
            or record.page.geometry != native.page.geometry
        ):
            raise ValueError("OCR cache contains another source/page")
        if record.raster_sha256 != source_digest(raster_path):
            raise ValueError("OCR source raster checksum mismatch")
        return record, key, True
    readings, warnings = [], []
    for index, region in enumerate(regions):
        region_id = stable_id(
            native.page.source_sha256, native.page.geometry.page, region.bbox.model_dump_json()
        )
        override = settings.regions.get(region_id)
        languages = (
            override.ocr_languages
            if override and override.ocr_languages is not None
            else list(native_languages)
        )
        # No native language evidence deliberately requests OSD script fallback.
        image = mask_region(raster, region)
        if languages:
            reading = primary.read(
                image,
                languages=languages,
                orient=settings.ocr.orientation,
                deskew=settings.ocr.deskew,
            )
        else:
            reading, choice = read_with_language_choice(
                primary,
                image,
                detector=_detector(),
                orient=settings.ocr.orientation,
                deskew=settings.ocr.deskew,
            )
            warnings.append(f"region {index}: language choice {asdict(choice)}")
        reader = "tesseract"
        if secondary is not None and secondary.supports(list(reading.languages)):
            second = secondary.read(
                image, languages=list(reading.languages), transform=reading.transform
            )
            if pp_first(settings.ocr, reading.languages, second, reading):
                # Measured better for these languages: PP-OCRv5's reading is kept,
                # Tesseract's is the recorded second reading.
                reading, reader = compare_readings(second, reading), "pp_ocrv5"
                warnings.append(f"region {index}: PP-OCRv5 primary ({settings.ocr.accuracy_mode})")
            else:
                reading = compare_readings(reading, second)
        else:
            warnings.append(f"region {index}: second reader unavailable for selected languages")
        readings.append((reading, reader))
    parts = [
        build_ocr_page(
            native.page, raster, reading, stable_id(key, index),
            settings.ocr.calibration(reader),
        )
        for index, (reading, reader) in enumerate(readings)
    ]  # fmt: skip
    readings = [reading for reading, _ in readings]
    words = [
        word.model_copy(update={"region_index": index})
        for index, part in enumerate(parts)
        for word in part.words
    ]
    mean = sum(word.confidence for word in words) / len(words) if words else None
    record = parts[0].model_copy(
        update={
            "page": parts[0].page.model_copy(
                update={
                    "store": SpanStore(
                        spans={
                            sid: span
                            for part in parts
                            for sid, span in part.page.store.spans.items()
                        },
                        lines=[line for part in parts for line in part.page.store.lines],
                    )
                }
            ),
            "words": words,
            "mean_confidence": mean,
            "review_status": _page_status(parts),
            "warnings": warnings + [w for part in parts for w in part.warnings],
            "model_fingerprints": {
                k: v for part in parts for k, v in part.model_fingerprints.items()
            },
            "unmatched_secondary": [w for part in parts for w in part.unmatched_secondary],
            "orientation": {"regions": [asdict(r.orientation) for r in readings]},
            "transform": {
                "regions": [asdict(r.transform) for r in readings],
                "words_frame": "PDF coordinates; alternatives in region processed raster",
            },
            "raster_asset": f"ocr_{native.page.source_sha256[:16]}_{eligibility.page:06d}.png",
            "raster_sha256": hashlib.sha256(raster.png).hexdigest(),
        }
    )
    assert_producer_unchanged("ocr", LOADED_DIGEST)
    raster_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = raster_path.with_name(f".{raster_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(raster.png)
            stream.flush()
            os.fsync(stream.fileno())
        replace_with_retry(temporary, raster_path)
    finally:
        temporary.unlink(missing_ok=True)
    write_model(path, record, key)
    return record, key, False
