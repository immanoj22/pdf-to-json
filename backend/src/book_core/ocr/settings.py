"""Explicit local OCR assets and measured review policy; never downloads at runtime."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from book_core.model.common import Confidence, CoreModel, Digest
from book_core.settings import Settings


class Calibration(CoreModel):
    """A fitted threshold is evidence, not a claim that engine scores are probabilities."""

    sample_sha256: Digest
    word_threshold: Confidence
    page_threshold: Confidence
    training_words: Annotated[int, Field(gt=0)]
    training_pages: Annotated[int, Field(gt=0)]
    method: str


class OcrSettings(CoreModel):
    executable: Path
    tessdata: Path
    asset_manifest: Path
    dpi: Literal[300, 400] = 300
    orientation: bool = True
    deskew: bool = True
    preprocessing: Literal["none"] = "none"
    calibration: Calibration | None = None
    second_reader: Literal["off", "on"] = "on"
    detector_path: Path | None = None
    recognizer_paths: dict[str, Path] = Field(default_factory=dict)
    model_revisions: dict[str, str] = Field(default_factory=dict)

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
