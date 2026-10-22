"""Eligibility safety: digital text retained, figures excluded, scans need visual proof."""

import cv2
import numpy as np
import pymupdf
import pytest

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.model.common import BBox
from book_core.ocr.detection import (
    OcrEligibility,
    RenderTextCheck,
    detect_ocr_regions,
    unusable_codepoint,
)


def native(tmp_path, text=None, *, raster=True, render_mode=0, image_rect=None):
    source = tmp_path / "source.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=240, height=180)
        if raster:
            image = np.full((360, 480, 3), 255, dtype=np.uint8)
            cv2.putText(
                image, "Printed scan text", (25, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1
            )
            page.insert_image(
                image_rect or page.rect, stream=cv2.imencode(".png", image)[1].tobytes()
            )
        if text:
            page.insert_text((20, 50), text, render_mode=render_mode)
        document.save(source)
    return PyMuPDFExtractor("cpu").extract_object_page(source, 1)


def proof(page, outcome):
    return RenderTextCheck(
        bbox=page.page.geometry.content_bbox,
        outcome=outcome,
        method="synthetic generation ground truth",
        evidence=["fixture"],
    )


def test_native_digital_text_is_not_ocred_even_over_full_page_raster(tmp_path):
    page = native(tmp_path, "ordinary native text")
    before = page.model_dump_json()
    result = detect_ocr_regions(page, render_checks=[proof(page, "text_present")])
    assert result.decision == "native"
    assert result.native_retained
    assert result.unmeasured_checks
    assert page.model_dump_json() == before


def test_blank_page_is_not_a_scan(tmp_path):
    assert detect_ocr_regions(native(tmp_path, raster=False)).decision == "native"


def test_raster_scan_requires_text_proof_and_never_ocr_figures(tmp_path):
    page = native(tmp_path)
    result = detect_ocr_regions(page)
    assert result.decision == "review"
    assert "raster_text_vs_figure_content_not_visually_adjudicated" in result.unmeasured_checks
    verified = detect_ocr_regions(page, render_checks=[proof(page, "text_present")])
    assert verified.decision == "ocr"
    assert all(r.retain_native for r in verified.regions)
    figure = detect_ocr_regions(
        page,
        figure_boxes=[page.page.geometry.content_bbox],
        render_checks=[proof(page, "text_present")],
    )
    assert figure.decision == "native"
    assert figure.excluded_figure_image_ids
    assert not figure.regions
    assert detect_ocr_regions(page, render_checks=[proof(page, "no_text")]).decision == "native"


def test_local_raster_figure_without_native_text_stays_out_of_scope(tmp_path):
    page = native(tmp_path, image_rect=pymupdf.Rect(50, 60, 150, 120))
    assert detect_ocr_regions(page).decision == "native"


def test_earlier_invisible_ocr_is_comparison_only_and_text_is_unchanged(tmp_path):
    page = native(tmp_path, "Earlier OCR reading", render_mode=3)
    before = page.model_dump_json()
    result = detect_ocr_regions(page)
    assert result.decision == "compare_only"
    assert result.invisible_glyphs == len("Earlier OCR reading")
    assert all(r.retain_native for r in result.regions)
    assert (
        detect_ocr_regions(page, render_checks=[proof(page, "mismatch")]).decision == "compare_only"
    )
    assert page.model_dump_json() == before


def test_mismatch_requires_adjudicated_render_evidence(tmp_path):
    page = native(tmp_path, "wrong mapping", raster=False)
    assert detect_ocr_regions(page, render_checks=[proof(page, "unresolved")]).decision == "native"
    assert detect_ocr_regions(page, render_checks=[proof(page, "mismatch")]).decision == "ocr"
    complete = detect_ocr_regions(page, render_checks=[proof(page, "matches")])
    assert not complete.unmeasured_checks


def test_private_use_math_marker_never_invalidates_usable_page(make_page):
    from book_core.objects.models import NativeObjectPage, PageObject

    source = make_page(("ordinary ", "\ue000"))
    page = NativeObjectPage(
        page=source,
        objects=[
            PageObject(
                id=s.id,
                kind="text",
                bbox=s.bbox,
                source_page=1,
                source_spans=[s.id],
                provenance=s.provenance,
            )
            for s in source.store.spans.values()
        ],
        paint_commands=[],
    )
    result = detect_ocr_regions(page)
    assert result.decision == "native" and result.unusable_characters == 1
    assert result.unusable_span_ids == ["span-1"]
    assert OcrEligibility.model_validate_json(result.model_dump_json()) == result
    wholly_bad = source.model_copy(update={"store": make_page(("\ue000\ufffd",)).store})
    bad_page = NativeObjectPage(page=wholly_bad, objects=page.objects[:1], paint_commands=[])
    assert detect_ocr_regions(bad_page).decision == "review"


@pytest.mark.parametrize(
    "text", ["العربية", "हिन्दी", "中文", "Ελληνικά", "Русский", "\u200f", "\u0301"]
)
def test_mapping_check_never_assumes_script_or_left_to_right(text):
    assert not any(unusable_codepoint(ord(c)) for c in text)


def test_checks_cannot_reference_missing_spans_and_screen_is_bounded(tmp_path):
    page = native(tmp_path)
    with pytest.raises(ValueError, match="unknown native spans"):
        detect_ocr_regions(
            page,
            render_checks=[
                proof(page, "mismatch").model_copy(update={"native_span_ids": ["missing"]})
            ],
        )
    with pytest.raises(ValueError, match="Large raster share"):
        detect_ocr_regions(page, large_raster_share=0)


def test_rectangle_union_does_not_double_count_overlapping_images():
    from book_core.ocr.detection import _union_area

    a = BBox(x0=0, y0=0, x1=10, y1=10)
    b = BBox(x0=5, y0=0, x1=15, y1=10)
    assert _union_area([a, a, b]) == 150


def test_partial_figures_are_named_as_required_ocr_masks(tmp_path):
    page = native(tmp_path)
    figure = BBox(x0=150, y0=100, x1=200, y1=140)
    result = detect_ocr_regions(
        page, figure_boxes=[figure], render_checks=[proof(page, "text_present")]
    )
    assert result.decision == "ocr"
    assert result.regions[0].excluded_figure_boxes == [figure]


def test_ocr_view_stamps_native_navigation_with_its_own_identity():
    from types import SimpleNamespace

    from book_core.model.spans import ExtractorIdentity
    from book_core.ocr.extractor import OcrExtractor, OcrInput

    base = ExtractorIdentity(name="pymupdf", version="1", configuration={})
    native = SimpleNamespace(
        device=None,
        identity=base,
        extract_navigation=lambda source: {"source_sha256": "a" * 64, "extractor": "native"},
    )
    inputs = OcrInput(
        source_sha256="a" * 64, fingerprint="b" * 64, directory=".", page_keys={1: "c" * 64}
    )
    view = OcrExtractor(native, inputs)
    result = view.extract_navigation("book.pdf")
    assert result["extractor"] == view.identity.model_dump(mode="json")
    assert result["extractor"]["name"] == "pymupdf-ocr"
    assert result["source_sha256"] == "a" * 64
