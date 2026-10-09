"""Configurable job/region OCR requests, a language-pack registry placeholder and data paths."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator

from book_core.model.common import CoreModel

LanguageCode = Annotated[str, Field(min_length=1)]
# Reference-XML dialect profiles are evaluation data kept outside the converter source.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE_DIALECTS = BACKEND_ROOT / "reference_dialects" / "dialects.json"


def validate_languages(value: list[str]) -> list[str]:
    if not value or any(not code.strip() or code != code.strip() for code in value):
        raise ValueError("Use a nonempty list of language codes without surrounding whitespace")
    if len(value) != len(set(value)):
        raise ValueError("Repeated OCR language code")
    return value


class LanguagePack(CoreModel):
    code: LanguageCode
    label: str | None = None
    installed: bool = False


class LanguagePackRegistry(CoreModel):
    """Placeholder only; no discovery, downloads or OCR runtime."""

    packs: dict[str, LanguagePack] = Field(default_factory=dict)


class RegionSettings(CoreModel):
    """None inherits the job's requested languages."""

    ocr_languages: list[LanguageCode] | None = None

    @field_validator("ocr_languages")
    @classmethod
    def languages(cls, value: list[str] | None) -> list[str] | None:
        return validate_languages(value) if value is not None else None


class Settings(CoreModel):
    """One settings object per job, with explicit region overrides."""

    device: Literal["auto", "cpu", "cuda"] = "auto"
    layout_detection_threshold: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.5
    ocr_languages: list[LanguageCode] = Field(default_factory=lambda: ["spa", "eng"])
    regions: dict[str, RegionSettings] = Field(default_factory=dict)
    language_packs: LanguagePackRegistry = Field(default_factory=LanguagePackRegistry)
    reference_dialects: Path = DEFAULT_REFERENCE_DIALECTS

    @field_validator("ocr_languages")
    @classmethod
    def languages(cls, value: list[str]) -> list[str]:
        return validate_languages(value)

    def languages_for_region(self, region_id: str) -> list[str]:
        region = self.regions.get(region_id)
        requested = (
            region.ocr_languages
            if region is not None and region.ocr_languages is not None
            else self.ocr_languages
        )
        return list(requested)
