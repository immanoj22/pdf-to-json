"""Prepare a separately marked OCR source before the existing semantic pipeline."""

import json
from pathlib import Path

from book_core.cache_admin import disk_check, register
from book_core.cache_store import write_json
from book_core.caching import code_digest
from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ocr.cache import recognize_page
from book_core.ocr.detection import detect_ocr_regions
from book_core.ocr.extractor import OcrInput
from book_core.ocr.languages import map_languages


def languages_from_evidence(evidence):
    """Use accepted Lingua languages and mixed segments; never interpret und as English."""
    codes = []
    for block in evidence.get("blocks", []):
        if block.get("language") not in {None, "und"}:
            codes.append(block["language"])
        if block.get("mixed"):
            codes.extend(
                s["language"] for s in block.get("segments", []) if s.get("language") != "und"
            )
    return map_languages(tuple(dict.fromkeys(codes)))


def prepare_book(
    source,
    cache_dir,
    settings,
    primary,
    secondary=None,
    *,
    language_evidence=None,
    extractor=None,
    figure_boxes=None,
    render_checks=None,
    native_page=None,
    visual_checks=None,
):
    """Screen first; OCR only qualified regions. Review-only pages retain native output.

    ``language_evidence`` is the existing Lingua block record for a digital/mixed book.
    A fully scanned book starts with OSD script selection. Caller-supplied eligibility
    evidence is fingerprinted with every OCR page; it cannot silently replace a source.
    """
    source, root = Path(source), Path(cache_dir)
    extractor = extractor or PyMuPDFExtractor(settings.device)
    digest, total = source_digest(source), extractor.page_count(source)
    native_languages = languages_from_evidence(language_evidence or {})
    directory = root / "ocr"
    directory.mkdir(parents=True, exist_ok=True)
    keys, comparisons, images, screenings = {}, {}, {}, []
    for number in range(1, total + 1):
        native = (
            native_page(number) if native_page else extractor.extract_object_page(source, number)
        )
        figures = figure_boxes(number) if figure_boxes else ()
        checks = list(render_checks(number)) if render_checks else []
        eligibility = detect_ocr_regions(native, figure_boxes=figures, render_checks=checks)
        raster = None
        if visual_checks is not None and eligibility.decision == "review":
            raster = extractor.render_page(source, number, settings.ocr.dpi)
            checks.extend(visual_checks(native, raster, eligibility))
            eligibility = detect_ocr_regions(native, figure_boxes=figures, render_checks=checks)
        screenings.append(eligibility.model_dump(mode="json"))
        if eligibility.decision not in {"ocr", "compare_only"}:
            continue
        # Bound a page's raster, working images, recognition evidence and stage cache.
        width, height = native.page.geometry.width, native.page.geometry.height
        disk_check(root, int(width * height * (settings.ocr.dpi / 72) ** 2 * 18) + 2_000_000)
        raster = raster or extractor.render_page(source, number, settings.ocr.dpi)
        record, key, _ = recognize_page(
            native,
            raster,
            eligibility,
            settings,
            primary,
            secondary,
            directory,
            native_languages=native_languages,
        )
        if record is None:
            continue
        # Native layer over any OCR region is preserved for a decision, not silently
        # blended with new words. All native ledger entries remain independently retained.
        overlapping_native = any(
            region.native_span_ids
            for region in eligibility.regions
            if region.action in {"ocr", "compare_only"}
        )
        if eligibility.decision == "compare_only" or overlapping_native:
            comparisons[number] = key
        else:
            keys[number] = key
            images[number] = list(
                dict.fromkeys(
                    i for r in eligibility.regions if r.action == "ocr" for i in r.image_ids
                )
            )
        register(
            root,
            digest,
            "ocr",
            key,
            [directory / key / f"{number}.json", directory / key / "images" / f"{number}.png"],
            producer=code_digest("ocr"),
        )
    fingerprint = stable_id(
        digest, code_digest("ocr"), json.dumps([keys, comparisons, images], sort_keys=True)
    )
    inputs = OcrInput(
        source_sha256=digest,
        fingerprint=fingerprint,
        directory=directory,
        page_keys=keys,
        comparison_keys=comparisons,
        scan_image_ids=images,
    )
    write_json(
        directory / f"{fingerprint}.json",
        {
            "inputs": inputs.model_dump(mode="json"),
            "screening": screenings,
            "native_languages": native_languages,
            "native_ledger_changed": False,
        },
    )
    return inputs
