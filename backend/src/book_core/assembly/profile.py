"""Client profiles: the output settings a client may change, validated and versioned.

A profile is a TOML (or JSON) file. Unknown keys are errors. The profile id, version and the
SHA-256 of its validated, canonical form are written into every output. The default profile
(``assembly/profiles/default.toml``) follows the company's reference XML conventions (for
example the caption after its image, as in the book 1 reference).

Settings that change what earlier stages compute (OCR reader and thresholds) are carried
here so a client sets everything in one place; the run passes them to the OCR stage.
"""

from __future__ import annotations

import hashlib
import json
import string
import tomllib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROFILE_FORMAT = 1
DEFAULT_PROFILE = Path(__file__).with_name("profiles") / "default.toml"
SECTIONS = ("furniture", "navigation", "suppressed", "review", "styles")
NAME_FIELDS = {"label", "n", "index"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _pattern(value, required):
    names = set()
    for _, name, _, conversion in string.Formatter().parse(value):
        if name is None:
            continue
        if name not in NAME_FIELDS or conversion:
            raise ValueError(f"Unknown naming field {name!r}; use {sorted(NAME_FIELDS)}")
        names.add(name)
    if required - names:
        raise ValueError(f"A naming pattern needs {sorted(required - names)}")
    return value


class Header(Strict):
    id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    format: Literal[1] = PROFILE_FORMAT
    description: str = ""


class Images(Strict):
    name_pattern: str = "page_{label}_{n}"
    unlabelled_pattern: str = "page_pdf{index}_{n}"
    photo_format: Literal["jpg", "png"] = "jpg"
    drawing_format: Literal["jpg", "png"] = "png"

    @field_validator("name_pattern")
    @classmethod
    def labelled(cls, value):
        return _pattern(value, {"label", "n"})

    @field_validator("unlabelled_pattern")
    @classmethod
    def unlabelled(cls, value):
        return _pattern(value, {"index", "n"})


class AltTextSettings(Strict):
    # empty: an empty slot marked needs_review; model_draft: SmolVLM drafts (still reviewed).
    mode: Literal["empty", "model_draft"] = "empty"
    # Equation image fallbacks need alt text: prefill the slot with the equation's LaTeX or
    # its original text (still needs_review), or leave it empty.
    equation_fallback: Literal["latex", "original_text", "empty"] = "latex"


class Captions(Strict):
    # Where an adapter places a figure's caption relative to its image.
    placement: Literal["before", "after"] = "after"


class OcrProfile(Strict):
    # tesseract_only: Tesseract reads every page; best_measured: PP-OCRv5 reads first for the
    # (language, script) pairs where it measured better (Tesseract is the fallback and the
    # recorded second reading).
    accuracy_mode: Literal["tesseract_only", "best_measured"] = "best_measured"
    # A word below its reader's threshold is needs_review (thresholds measured per reader).
    word_thresholds: dict[str, Annotated[float, Field(ge=0, le=1)]] = Field(
        default_factory=lambda: {"tesseract": 0.84, "pp_ocrv5": 0.94}
    )
    # A page is must_check when at least this share of its words is below the threshold.
    page_flagged_word_share: Annotated[float, Field(ge=0, le=1)] = 0.092

    @field_validator("word_thresholds")
    @classmethod
    def readers(cls, value):
        unknown = set(value) - {"tesseract", "pp_ocrv5"}
        if unknown:
            raise ValueError(f"Unknown OCR reader {sorted(unknown)}")
        return dict(sorted(value.items()))


class ReviewSettings(Strict):
    # Crop images written for review items: all items, must_check items only, or none.
    crops: Literal["all", "must_check", "none"] = "all"
    crop_dpi: Annotated[int, Field(ge=36, le=300)] = 72
    # A language run shorter than this (letters, words) or less confident keeps its
    # paragraph's language (measured: shorter Lingua runs are mostly names and Latin terms).
    # Language spans inside a paragraph: off by default (Step 17 hand check: 0 of 5 right on
    # the printed page; text with foreign names is read as that language). Unit languages
    # are always recorded.
    language_spans: Literal["off", "on"] = "off"
    language_min_letters: Annotated[int, Field(ge=1)] = 40
    language_min_words: Annotated[int, Field(ge=1)] = 5
    language_min_confidence: Annotated[float, Field(ge=0, le=1)] = 0.95


SPAN_KINDS = (
    "italic",
    "bold",
    "bold_italic",
    "superscript",
    "subscript",
    "small_caps",
    "underline",
    "link",
    "language",
    "math",
    "run_in_heading",
)


class Styling(Strict):
    """What an adapter writes of the inline styling. The JSON always records the styling
    that is printed (never deleted to match a reference); these settings follow the
    reference convention for what the output marks up."""

    # Span kinds an adapter writes as inline markup.
    emit: tuple[str, ...] = SPAN_KINDS
    # Bold/italic inside headings and titles: the references style headings by their
    # element, not with inline emphasis ("omit"), or write it ("emit").
    in_headings: Literal["omit", "emit"] = "omit"

    @field_validator("emit")
    @classmethod
    def kinds(cls, value):
        unknown = set(value) - set(SPAN_KINDS)
        if unknown:
            raise ValueError(f"Unknown span kind {sorted(unknown)}; use {list(SPAN_KINDS)}")
        return tuple(k for k in SPAN_KINDS if k in value)


class Names(Strict):
    # Parse bibliography authors and index personal names into family/given (with
    # confidence, always needs_review); the printed text is always kept. Off by default.
    split: bool = False


class Output(Strict):
    sections: tuple[str, ...] = SECTIONS

    @field_validator("sections")
    @classmethod
    def known(cls, value):
        unknown = set(value) - set(SECTIONS)
        if unknown:
            raise ValueError(f"Unknown output section {sorted(unknown)}; use {list(SECTIONS)}")
        return tuple(s for s in SECTIONS if s in value)


class ClientProfile(Strict):
    profile: Header
    images: Images = Field(default_factory=Images)
    alt_text: AltTextSettings = Field(default_factory=AltTextSettings)
    captions: Captions = Field(default_factory=Captions)
    ocr: OcrProfile = Field(default_factory=OcrProfile)
    review: ReviewSettings = Field(default_factory=ReviewSettings)
    styling: Styling = Field(default_factory=Styling)
    names: Names = Field(default_factory=Names)
    output: Output = Field(default_factory=Output)

    def canonical(self):
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @property
    def sha256(self):
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()


def ocr_settings(profile, settings):
    """``OcrSettings`` with the profile's accuracy mode and per-reader thresholds."""
    calibrations = {
        reader: calibration.model_copy(update={
            "word_threshold": profile.ocr.word_thresholds.get(reader, calibration.word_threshold),
            "page_threshold": profile.ocr.page_flagged_word_share,
        })
        for reader, calibration in settings.calibrations.items()
    }  # fmt: skip
    return settings.model_copy(
        update={"accuracy_mode": profile.ocr.accuracy_mode, "calibrations": calibrations}
    )


def load_profile(path=None):
    """The validated profile of a TOML or JSON file (the default profile without a path)."""
    path = Path(path) if path is not None else DEFAULT_PROFILE
    data = path.read_bytes()
    if path.suffix.lower() == ".json":
        raw = json.loads(data.decode("utf-8"))
    else:
        raw = tomllib.loads(data.decode("utf-8"))
    return ClientProfile.model_validate(raw)
