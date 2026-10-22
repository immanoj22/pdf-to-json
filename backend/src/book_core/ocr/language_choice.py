"""Language choice for pages with no native-text language evidence.

1. Script.  OSD names a script; every major script model also reads the page.  The OSD
   script is kept unless another script model's mean word confidence beats it by
   ``SCRIPT_MARGIN`` (OSD confuses related scripts, e.g. Greek read as Cyrillic).  When
   OSD names no script, the most confident script model is used.  Job languages are never
   assumed for an unknown script.
2. Language.  Lingua runs on that reading; a confident language with an installed model
   re-reads the page with it.

Every candidate's confidence and the choice are returned, so the decision is auditable.
The margin and the candidate list were measured on the Step 16 real scans (see report).
"""

from dataclasses import dataclass, field
from pathlib import Path

from book_core.ocr.languages import LINGUA_TO_TESSERACT, installed_languages

MAJOR_SCRIPTS = (
    "Latin",
    "Cyrillic",
    "Greek",
    "Arabic",
    "Hebrew",
    "Devanagari",
    "HanS",
    "HanT",
    "Hangul",
    "Japanese",
)
SCRIPT_MARGIN = 0.10


@dataclass(frozen=True)
class LanguageChoice:
    osd_script: str | None
    script_confidences: dict[str, float | None]
    script_languages: tuple[str, ...]
    script_reason: str
    detected: str | None
    final_languages: tuple[str, ...]
    reread: bool
    warnings: tuple[str, ...] = field(default=())


def lingua_detector(codes=None):
    """One detector over every Lingua language that maps to a Tesseract model."""
    from book_core.document_analysis.language import LinguaLanguageDetector

    if codes is None:
        codes = sorted(
            code for code, models in LINGUA_TO_TESSERACT.items() if len(code) == 2 and models
        )
    return LinguaLanguageDetector(codes, minimum_letters=20)


def _score(reading):
    return reading.mean_confidence if reading.words else None


def read_with_language_choice(engine, image, *, detector, orient=True, deskew=False):
    """Return (reading, LanguageChoice); the engine is a TesseractEngine."""
    from book_core.ocr.languages import OSD_TO_TESSERACT, map_languages

    installed = set(installed_languages(Path(engine.tessdata)))
    # The first read fixes orientation and deskew; every other read reuses its transform.
    try:
        first = engine.read(image, languages=[], orient=orient, deskew=deskew)
        osd_script = first.orientation.script
    except ValueError:
        first, osd_script = None, None
    candidates = {}
    if first is not None:
        candidates[tuple(first.languages)] = first
    transform = first.transform if first is not None else None
    for script in MAJOR_SCRIPTS:
        packs = (f"script/{script}",)
        if packs in candidates or packs[0] not in installed:
            continue
        if transform is None:
            reading = engine.read(image, languages=list(packs), orient=orient, deskew=deskew)
            transform = reading.transform
        else:
            reading = engine.read(image, languages=list(packs), transform=transform)
        candidates[packs] = reading
    scores = {"+".join(k): _score(r) for k, r in candidates.items()}
    best = max(candidates, key=lambda k: _score(candidates[k]) or 0.0)
    warnings = []
    if first is not None and osd_script in OSD_TO_TESSERACT:
        chosen, reason = tuple(first.languages), "osd_script"
        if (_score(candidates[best]) or 0.0) - (_score(first) or 0.0) >= SCRIPT_MARGIN:
            chosen, reason = best, "script_confidence_overrides_osd"
    else:
        chosen, reason = best, "osd_unavailable_most_confident_script"
        warnings.append("script chosen by recognition confidence only")
    reading = candidates[chosen]
    text = " ".join(word.text for word in reading.words)
    evidence = detector.detect(text)
    detected = evidence.language if evidence.language != "und" else None
    final, reread = tuple(reading.languages), False
    if detected is not None:
        try:
            wanted = map_languages([detected])
        except ValueError:
            wanted = ()
        if wanted and set(wanted) <= installed and tuple(wanted) != final:
            reading = engine.read(image, languages=list(wanted), transform=reading.transform)
            final, reread = tuple(reading.languages), True
    return reading, LanguageChoice(
        osd_script, scores, chosen, reason, detected, final, reread, tuple(warnings)
    )
