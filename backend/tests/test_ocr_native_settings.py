"""OCR settings never change native pages; an OCR language request stays in the OCR settings.

Step 17 asked for English OCR on book 2's cover by narrowing the job's language list, which
also decides native language evidence, and 319 native pages changed their language labels.
"""

import cv2
import numpy as np
import pymupdf
import pytest
from pydantic import ValidationError

from book_core.book_run import native_settings
from book_core.ocr import prepare
from book_core.ocr.detection import RenderTextCheck
from book_core.ocr.settings import OcrJobSettings, OcrSettings
from book_core.paragraphs.cache import detector_for
from book_core.settings import Settings


def ocr(tmp_path, **update):
    return OcrSettings(executable=tmp_path / "tesseract", tessdata=tmp_path,
                       asset_manifest=tmp_path / "m.json", second_reader="off",
                       **update)  # fmt: skip


def test_native_stages_see_the_job_settings_without_any_ocr_part(tmp_path):
    plain = Settings()
    for update in ({}, {"languages": ["eng"]}, {"languages": ["ara", "fas"], "dpi": 400}):
        job = OcrJobSettings(ocr=ocr(tmp_path, **update))
        assert native_settings(job) == plain
        assert detector_for(native_settings(job), 10)[1] == detector_for(plain, 10)[1]
    assert native_settings(plain) is plain


def test_ocr_reading_languages_are_validated(tmp_path):
    with pytest.raises(ValidationError):
        ocr(tmp_path, languages=[])
    with pytest.raises(ValidationError):
        ocr(tmp_path, languages=["eng", "eng"])


@pytest.mark.parametrize("requested,read", [(None, ()), (["eng"], ("eng",))])
def test_ocr_reads_its_requested_languages(tmp_path, monkeypatch, requested, read):
    source = tmp_path / "scan.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=240, height=180)
        image = np.full((360, 480, 3), 255, dtype=np.uint8)
        cv2.putText(image, "Printed scan", (25, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)
        page.insert_image(page.rect, stream=cv2.imencode(".png", image)[1].tobytes())
        document.save(source)
    seen = []

    def recognize(*_, native_languages=()):
        seen.append(tuple(native_languages))
        return None, None, False

    monkeypatch.setattr(prepare, "recognize_page", recognize)
    job = OcrJobSettings(device="cpu", ocr=ocr(tmp_path, languages=requested))
    proof = RenderTextCheck(
        bbox=_content(source),
        outcome="text_present",
        method="synthetic generation ground truth",
        evidence=["fixture"],
    )
    prepare.prepare_book(source, tmp_path / "cache", job, None, render_checks=lambda n: [proof])
    assert seen == [read]
    assert job.ocr_languages == ["spa", "eng"]


def _content(source):
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

    return PyMuPDFExtractor("cpu").extract_object_page(source, 1).page.geometry.content_bbox
