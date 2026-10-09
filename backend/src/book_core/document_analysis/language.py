"""Read-only language evidence over native extraction blocks.

Native blocks and line adjacency are extraction evidence, never paragraph or reading-order
decisions. Scores are detector-specific evidence, not calibrated correctness probabilities.
All source text stays in the span store; artifacts contain references and digests.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from importlib.metadata import distribution, version
from typing import Protocol, runtime_checkable

import regex

from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.model.spans import ExtractedPage

_LETTER = regex.compile(r"\p{L}")


def bundled_model_digest() -> str:
    package = distribution("lingua-language-detector")
    files = sorted(file for file in package.files or () if file.suffix in {".pyd", ".so"})
    if not files:
        raise ValueError("Cannot identify bundled Lingua model binary")
    digest = hashlib.sha256()
    for file in files:
        digest.update(str(file).encode() + b"\0")
        digest.update(source_digest(package.locate_file(file)).encode())
    return digest.hexdigest()


@dataclass(frozen=True)
class LanguageScore:
    language: str
    confidence: float


@dataclass(frozen=True)
class LanguageSegment:
    start: int
    end: int
    language: str
    confidence: float


@dataclass(frozen=True)
class LanguageEvidence:
    language: str
    confidence: float
    candidates: tuple[LanguageScore, ...]
    segments: tuple[LanguageSegment, ...]
    mixed: bool
    reason: str


@runtime_checkable
class LanguageDetector(Protocol):
    @property
    def identity(self) -> dict: ...

    def detect(self, text: str) -> LanguageEvidence: ...


class LinguaLanguageDetector:
    """CPU-only, high-accuracy detector; an empty language set enables all languages.

    Explicit language sets are job configuration, never inferred from OCR defaults.
    Language identifiers in evidence are ISO 639-1 codes, or und for uncertain evidence.
    """

    def __init__(
        self,
        languages: Sequence[str] = (),
        *,
        minimum_letters: int = 10,
        confidence_floor: float = 0.7,
        margin_floor: float = 0.2,
    ):
        from lingua import Language, LanguageDetectorBuilder

        if minimum_letters < 1 or not 0 <= confidence_floor <= 1 or not 0 <= margin_floor <= 1:
            raise ValueError("Invalid language evidence configuration")
        available = list(Language.all())
        by_code = {}
        for language in available:
            by_code[language.iso_code_639_1.name.lower()] = language
            by_code[language.iso_code_639_3.name.lower()] = language
        if len(set(languages)) != len(languages):
            raise ValueError("Duplicate language code")
        try:
            selected = [by_code[code.lower()] for code in languages]
        except KeyError as error:
            raise ValueError(f"Unsupported language code: {error.args[0]}") from error
        if len(set(selected)) != len(selected):
            raise ValueError("Language aliases identify the same language")
        builder = (
            LanguageDetectorBuilder.from_languages(*selected)
            if selected
            else LanguageDetectorBuilder.from_all_languages()
        )
        self.detector = builder.build()
        self.languages = tuple(sorted(self._code(language) for language in selected))
        self.minimum_letters = minimum_letters
        self.confidence_floor = confidence_floor
        self.margin_floor = margin_floor

    @staticmethod
    def _code(language) -> str:
        return language.iso_code_639_1.name.lower()

    @property
    def identity(self) -> dict:
        return {
            "name": "lingua-language-detector",
            "version": version("lingua-language-detector"),
            "license": "Apache-2.0",
            "model": {"source": "bundled_distribution_binary", "sha256": bundled_model_digest()},
            "configuration": {
                "languages": list(self.languages),
                "accuracy": "high",
                "minimum_letters": self.minimum_letters,
                "confidence_floor": self.confidence_floor,
                "margin_floor": self.margin_floor,
                "mixed_language_segments": True,
            },
            "score_interpretation": "library confidence; not calibrated correctness probability",
        }

    def detect(self, text: str) -> LanguageEvidence:
        if not _LETTER.search(text):
            return LanguageEvidence("und", 0.0, (), (), False, "no_letter_evidence")
        scores = self.detector.compute_language_confidence_values(text)
        candidates = tuple(
            LanguageScore(self._code(score.language), round(float(score.value), 6))
            for score in scores[:3]
        )
        if not candidates:
            return LanguageEvidence("und", 0.0, (), (), False, "no_supported_language_evidence")
        top = candidates[0]
        runner_up = candidates[1].confidence if len(candidates) > 1 else 0.0
        if len(_LETTER.findall(text)) < self.minimum_letters:
            return LanguageEvidence(
                "und", top.confidence, candidates, (), False, "short_text_uncertain"
            )
        segments = []
        # Offsets refer to the fingerprinted transient NFKC block string, not source spans.
        for item in self.detector.detect_multiple_languages_of(text):
            start, end = int(item.start_index), int(item.end_index)
            confidence = self.detector.compute_language_confidence(text[start:end], item.language)
            segments.append(
                LanguageSegment(start, end, self._code(item.language), round(float(confidence), 6))
            )
        mixed = len({segment.language for segment in segments}) > 1
        confident = (
            top.confidence >= self.confidence_floor
            and top.confidence - runner_up >= self.margin_floor
        )
        return LanguageEvidence(
            top.language if confident else "und",
            top.confidence,
            candidates,
            tuple(segments),
            mixed,
            "mixed_language_evidence" if mixed else "supported" if confident else "ambiguous",
        )


def native_block_text(page: ExtractedPage, block: dict) -> tuple[str, list[str]]:
    """Resolve a native mapping without guessing boundaries or sorting geometry."""
    if block["page"] != page.geometry.page:
        raise ValueError("Native block belongs to a different page")
    by_id = {line.id: line for line in page.store.lines}
    line_ids = block["line_ids"]
    if len(set(line_ids)) != len(line_ids):
        raise ValueError("Duplicate line in native block")
    try:
        lines = [by_id[line_id] for line_id in line_ids]
    except KeyError as error:
        raise ValueError("Native block references an unknown source line") from error
    text = unicodedata.normalize(
        "NFKC", "\n".join(page.store.raw_line_text(line) for line in lines)
    )
    return text, [sid for line in lines for sid in line.span_ids]


def language_evidence(
    pages: Iterable[ExtractedPage], native_blocks: Sequence[dict], detector: LanguageDetector
) -> dict:
    """Every supplied native block gets evidence; source language fields are untouched."""
    by_page = {}
    sources = set()
    for page in pages:
        if page.geometry.page in by_page:
            raise ValueError("Duplicate source page")
        sources.add(page.source_sha256)
        by_page[page.geometry.page] = page
    if len(sources) > 1:
        raise ValueError("Language evidence cannot mix source documents")
    rows = []
    seen_lines: set[tuple[int, str]] = set()
    seen_blocks = set()
    for block in native_blocks:
        block_key = (block["page"], block["block"])
        if block_key in seen_blocks:
            raise ValueError("Duplicate native block")
        seen_blocks.add(block_key)
        try:
            page = by_page[block["page"]]
        except KeyError as error:
            raise ValueError("Native block references an unknown page") from error
        for line_id in block["line_ids"]:
            key = (block["page"], line_id)
            if key in seen_lines:
                raise ValueError("A source line belongs to multiple native blocks")
            seen_lines.add(key)
        text, span_ids = native_block_text(page, block)
        rows.append(
            {
                "block_id": stable_id(
                    page.source_sha256, "native-block", block["page"], block["block"]
                ),
                "page": block["page"],
                "native_block": block["block"],
                "line_ids": list(block["line_ids"]),
                "span_ids": span_ids,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "letter_count": len(_LETTER.findall(text)),
                **asdict(detector.detect(text)),
            }
        )
    expected = {
        (page.geometry.page, line.id) for page in by_page.values() for line in page.store.lines
    }
    if seen_lines != expected:
        raise ValueError("Native block mapping must cover every source line exactly once")
    return {"detector": detector.identity, "unit_scope": "native_extraction_block", "blocks": rows}
