"""Cache keys do not depend on where the converter, its caches or its OCR assets live.

Step 18: the job settings in every stage key carried the installed backend's absolute path,
and the OCR key carried absolute asset paths and the eligibility evidence's file path.
"""

from types import SimpleNamespace

import pymupdf

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ocr.cache import page_fingerprint
from book_core.ocr.detection import detect_ocr_regions
from book_core.ocr.settings import OcrJobSettings, OcrSettings
from book_core.settings import DEFAULT_REFERENCE_DIALECTS, Settings


def test_job_settings_serialize_relative_to_the_install_and_load_back():
    dumped = Settings().model_dump(mode="json")
    assert dumped["reference_dialects"] == "reference_dialects/dialects.json"
    assert Settings.model_validate(dumped).reference_dialects == DEFAULT_REFERENCE_DIALECTS


def assets(root):
    root.mkdir()
    (root / "tesseract").write_bytes(b"binary")
    (root / "manifest.json").write_text("{}")
    return OcrJobSettings(ocr=OcrSettings(executable=root / "tesseract", tessdata=root,
                                          asset_manifest=root / "manifest.json",
                                          second_reader="off"))  # fmt: skip


def test_the_ocr_page_key_names_assets_by_content_not_location(tmp_path):
    pdf = tmp_path / "page.pdf"
    with pymupdf.open() as doc:
        doc.new_page().insert_text((50, 80), "text", fontsize=10)
        doc.save(pdf)
    native = PyMuPDFExtractor("cpu").extract_object_page(pdf, 1)
    raster = SimpleNamespace(png=b"raster")
    primary = SimpleNamespace(identity={"name": "tesseract", "executable_sha256": "e"},
                              model_fingerprints=lambda packs: {p: "f" for p in packs})  # fmt: skip
    eligibility = detect_ocr_regions(native)
    keys = [
        page_fingerprint(
            native, raster, eligibility, assets(tmp_path / place), primary, None, ("eng",)
        )  # fmt: skip
        for place in ("install_a", "elsewhere_b")
    ]
    assert keys[0] == keys[1]
