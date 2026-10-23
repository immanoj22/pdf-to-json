"""Explicit local OCR assets and measured review policy; never downloads at runtime."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from book_core.model.common import Confidence, CoreModel, Digest
from book_core.settings import Settings


class Calibration(CoreModel):
    """A fitted threshold is evidence, not a claim that engine scores are probabilities.

    A word below ``word_threshold`` is ``needs_review``. A page is ``must_check`` when the
    share of its words below the word threshold is at least ``page_threshold`` (Step 17:
    the share of flagged words replaced the page's mean confidence, which caught 2 of 61 bad
    pages)."""

    reader: Literal["tesseract", "pp_ocrv5"] = "tesseract"
    sample_sha256: Digest
    word_threshold: Confidence
    page_rule: Literal["flagged_word_share"] = "flagged_word_share"
    page_threshold: Confidence
    training_words: Annotated[int, Field(gt=0)]
    training_pages: Annotated[int, Field(gt=0)]
    method: str


def default_calibrations():
    """The measured defaults per reader (client profiles may override the thresholds)."""
    return {
        "tesseract": Calibration(
            reader="tesseract",
            sample_sha256="1cae08afa38f024a2991d9bc0a4a8f603473975e4f3be0bf1e7d7525672b2ec5",
            word_threshold=0.84,
            page_threshold=0.092,
            training_words=223839,
            training_pages=538,
            method="Step 16 held-out word fit (0.84); Step 17 page rule fitted on all 1,078 "
            "(page, degradation) cases, two-fold cross-fit 0.082/0.088",
        ),
        "pp_ocrv5": Calibration(
            reader="pp_ocrv5",
            sample_sha256="4fb16442a5c5b898657ec5d68a18228d905f1286212ff84d08287d78df5ba996",
            word_threshold=0.94,
            page_threshold=0.092,
            training_words=25088,
            training_pages=52,
            method="Step 17 word fit on the 52 two-reader cases, two-fold 0.942/0.941; page "
            "rule share as Tesseract's (not separately measured)",
        ),
    }


class OcrSettings(CoreModel):
    executable: Path
    tessdata: Path
    asset_manifest: Path
    dpi: Literal[300, 400] = 300
    orientation: bool = True
    deskew: bool = True
    preprocessing: Literal["none"] = "none"
    # Per reader; the primary reader's calibration decides word and page review.
    calibrations: dict[str, Calibration] = Field(default_factory=default_calibrations)
    # tesseract_only: Tesseract reads first everywhere; best_measured: PP-OCRv5 reads first
    # for the languages in ``pp_primary`` (measured better there), Tesseract second.
    accuracy_mode: Literal["tesseract_only", "best_measured"] = "best_measured"
    # Measured in Step 17 on real proofread scans (at least 20% fewer character errors and
    # better on two thirds of the pages): Chinese, simplified and traditional, horizontal
    # print. Greek and Arabic: no consistent margin; Tesseract stays first.
    pp_primary: tuple[str, ...] = ("chi_sim", "chi_tra")
    second_reader: Literal["off", "on"] = "on"
    detector_path: Path | None = None
    recognizer_paths: dict[str, Path] = Field(default_factory=dict)
    model_revisions: dict[str, str] = Field(default_factory=dict)

    def calibration(self, reader):
        return self.calibrations.get(reader)

    @model_validator(mode="after")
    def explicit_assets(self):
        if self.second_reader == "on" and not self.detector_path:
            raise ValueError("Second reader requires an explicitly provisioned detector path")
        if any(len(revision) != 40 for revision in self.model_revisions.values()):
            raise ValueError("Model revisions must be immutable full commit hashes")
        return self


class OcrJobSettings(Settings):
    """Extends job/region language settings without changing the native settings schema."""

    ocr: OcrSettings
