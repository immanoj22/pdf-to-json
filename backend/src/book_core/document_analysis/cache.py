"""Atomic, source-hashed whole-book evidence cache, independent of semantic ownership."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from importlib.metadata import version
from pathlib import Path

from book_core.caching import assert_producer_unchanged, code_digest, runtime_versions
from book_core.document_analysis.language import (
    LinguaLanguageDetector,
    bundled_model_digest,
    language_evidence,
    native_block_text,
    relative_letter_threshold,
)
from book_core.document_analysis.navigation import analyze_navigation
from book_core.document_analysis.repetition import RepetitionConfig, build_repetition
from book_core.document_analysis.styles import build_style_profile
from book_core.document_analysis.vocabulary import build_vocabulary
from book_core.extraction.cache import atomic_json, payload_digest
from book_core.model.spans import ExtractedPage
from book_core.settings import Settings

VERSION = "document-evidence-1"
# A worker loaded before a deployment must not populate a new producer's cache.
LOADED_DIGEST = code_digest("document")


@dataclass(frozen=True)
class DocumentConfig:
    """Job candidates come from Settings.ocr_languages, plus explicit additions.

    minimum_letters is an absolute floor; minimum_letter_median_fraction scales it
    against positive native-block letter counts. Both parameters enter cache keys.
    """

    repetition: RepetitionConfig = field(default_factory=RepetitionConfig)
    language_candidates: tuple[str, ...] = field(
        default_factory=lambda: tuple(Settings().ocr_languages)
    )
    minimum_letters: int = 10
    minimum_letter_median_fraction: float = 0.25
    language_confidence_floor: float = 0.7
    language_margin_floor: float = 0.2

    def __post_init__(self):
        if not self.language_candidates:
            raise ValueError("Document language candidates must be nonempty")
        relative_letter_threshold(
            (), floor=self.minimum_letters, median_fraction=self.minimum_letter_median_fraction
        )

    @classmethod
    def from_settings(
        cls, settings: Settings, *, additional_languages: Sequence[str] = (), **parameters
    ) -> DocumentConfig:
        """Use job languages; region overrides require an explicit native-region mapping later.

        Additions extend, rather than replace, the job candidate set. Candidate code
        support and aliases are validated by the optional detector at invocation,
        so constructing configuration does not require a model dependency.
        """
        codes = (*settings.ocr_languages, *additional_languages)
        if any(not code.strip() or code != code.strip() for code in codes):
            raise ValueError("Use language codes without surrounding whitespace")
        candidates = tuple(dict.fromkeys(code.lower() for code in codes))
        return cls(language_candidates=candidates, **parameters)


def book_language_threshold(pages, blocks, config: DocumentConfig) -> dict:
    by_page = {page.geometry.page: page for page in pages}
    return relative_letter_threshold(
        (
            sum(character.isalpha() for character in native_block_text(by_page[b["page"]], b)[0])
            for b in blocks
        ),
        floor=config.minimum_letters,
        median_fraction=config.minimum_letter_median_fraction,
    )


def fingerprint(pages, metadata, blocks, config):
    if not pages:
        raise ValueError("Document evidence requires the complete nonempty page sequence")
    source = pages[0].source_sha256
    identity = pages[0].extractor.model_dump(mode="json")
    if any(
        p.source_sha256 != source
        or p.extractor.model_dump(mode="json") != identity
        or p.geometry.page != number
        for number, p in enumerate(pages, 1)
    ):
        raise ValueError("Mixed source/configuration or incomplete page sequence")
    if metadata["source_sha256"] != source or metadata["page_count"] != len(pages):
        raise ValueError("Navigation and pages belong to different sources")
    model_digest = bundled_model_digest()
    provenance = {
        "version": VERSION,
        "source_sha256": source,
        "extractor": identity,
        "producer_sha256": code_digest("document"),
        "runtime": runtime_versions(),
        "libraries": {name: version(name) for name in ("lingua-language-detector", "RapidFuzz")},
        "config": {**asdict(config), "language_candidates": list(config.language_candidates)},
        "language_model_sha256": model_digest,
        "metadata_sha256": payload_digest(metadata),
        "native_blocks_sha256": payload_digest({"blocks": blocks}),
        "pages_sha256": payload_digest(
            {"pages": [payload_digest(p.model_dump(mode="json")) for p in pages]}
        ),
    }
    return payload_digest(provenance), provenance


def analyze_book_cached(
    pages: list[ExtractedPage],
    metadata: dict,
    blocks: list[dict],
    directory: Path,
    config: DocumentConfig | None = None,
) -> tuple[dict, Path, bool]:
    """Cache evidence only. All original objects stay read-only. Returns artifact/path/hit."""
    import json

    assert_producer_unchanged("document", LOADED_DIGEST)
    config = config or DocumentConfig()
    key, provenance = fingerprint(pages, metadata, blocks, config)
    target = Path(directory) / f"{key}.json"
    if target.exists():
        entry = json.loads(target.read_text("utf8"))
        if entry.get("key") != key or payload_digest(entry["payload"]) != entry["payload_sha256"]:
            raise ValueError("Corrupt whole-book evidence cache")
        if payload_digest(entry["payload"]["provenance"]) != key:
            raise ValueError("Whole-book evidence provenance mismatch")
        return entry["payload"], target, True
    threshold = book_language_threshold(pages, blocks, config)
    detector = LinguaLanguageDetector(
        config.language_candidates,
        minimum_letters=threshold["resolved_minimum_letters"],
        confidence_floor=config.language_confidence_floor,
        margin_floor=config.language_margin_floor,
    )
    payload = {
        "provenance": provenance,
        "style": build_style_profile(pages),
        "navigation": analyze_navigation(pages, metadata),
        "repetition": build_repetition(pages, config.repetition),
        "language": language_evidence(pages, blocks, detector),
        "vocabulary": build_vocabulary(pages, blocks),
        "decisions": {"heading_levels": None, "furniture_removal": None, "zones": None},
    }
    payload["language"]["minimum_letter_evidence"] = threshold
    assert_producer_unchanged("document", LOADED_DIGEST)
    atomic_json(target, {"key": key, "payload": payload, "payload_sha256": payload_digest(payload)})
    return payload, target, False


def load_artifact(path: Path) -> dict:
    """Verify a stored artifact for read-only overlay/review, including historical producers."""
    import json

    entry = json.loads(Path(path).read_text("utf8"))
    payload = entry["payload"]
    if payload_digest(payload) != entry["payload_sha256"]:
        raise ValueError("Corrupt whole-book evidence cache")
    if payload_digest(payload["provenance"]) != entry["key"]:
        raise ValueError("Whole-book evidence provenance mismatch")
    return payload
