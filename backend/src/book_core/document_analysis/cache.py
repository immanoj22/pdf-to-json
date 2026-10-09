"""Atomic, source-hashed whole-book evidence cache, independent of semantic ownership."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from importlib.metadata import version
from pathlib import Path

from book_core.caching import assert_producer_unchanged, code_digest, runtime_versions
from book_core.document_analysis.language import (
    LinguaLanguageDetector,
    bundled_model_digest,
    language_evidence,
)
from book_core.document_analysis.navigation import analyze_navigation
from book_core.document_analysis.repetition import RepetitionConfig, build_repetition
from book_core.document_analysis.styles import build_style_profile
from book_core.document_analysis.vocabulary import build_vocabulary
from book_core.extraction.cache import atomic_json, payload_digest
from book_core.model.spans import ExtractedPage

VERSION = "document-evidence-1"
# A worker loaded before a deployment must not populate a new producer's cache.
LOADED_DIGEST = code_digest("document")


@dataclass(frozen=True)
class DocumentConfig:
    repetition: RepetitionConfig = field(default_factory=RepetitionConfig)
    language_candidates: tuple[str, ...] = ()
    minimum_letters: int = 10
    language_confidence_floor: float = 0.7
    language_margin_floor: float = 0.2


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
    provenance = {
        "version": VERSION,
        "source_sha256": source,
        "extractor": identity,
        "producer_sha256": code_digest("document"),
        "runtime": runtime_versions(),
        "libraries": {name: version(name) for name in ("lingua-language-detector", "RapidFuzz")},
        "config": {**asdict(config), "language_candidates": list(config.language_candidates)},
        "language_model_sha256": bundled_model_digest(),
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
    detector = LinguaLanguageDetector(
        config.language_candidates,
        minimum_letters=config.minimum_letters,
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
