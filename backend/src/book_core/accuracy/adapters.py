"""Opt-in metadata bridges for legacy language/OCR contracts; delegates stay unchanged.

Bare legacy protocols do not require device, model or provenance metadata. These bridges
supply that envelope for new consumers without changing current callers or pipelines.
"""

import hashlib
from collections.abc import Iterator

from pydantic import Field, model_validator

from book_core.accuracy.cache import accuracy_fingerprint, request_digest
from book_core.accuracy.models import AccuracyInput, AccuracyResult, ExtensionMetadata
from book_core.caching import assert_producer_unchanged, code_digest
from book_core.device import DeviceResolution
from book_core.document_analysis.language import LanguageDetector, LanguageEvidence
from book_core.extraction.interfaces import OcrEngine
from book_core.model.common import Digest, Identifier, Provenance, SpanRef
from book_core.model.spans import TextSpan

LOADED_CODE_DIGEST = code_digest("accuracy")


class LanguageInput(AccuracyInput):
    text_sha256: Digest


class LanguageResult(AccuracyResult):
    evidence: LanguageEvidence | None = None


class OcrInput(AccuracyInput):
    languages: list[Identifier] = Field(min_length=1)

    @model_validator(mode="after")
    def image_required(self):
        if self.raster is None:
            raise ValueError("OCR evidence requires extractor-supplied image pixels")
        if len(self.languages) != len(set(self.languages)):
            raise ValueError("Repeated OCR language code")
        return self


class OcrResult(AccuracyResult):
    source_refs: list[SpanRef] = Field(default_factory=list)


def metadata_from_language(detector: LanguageDetector) -> ExtensionMetadata:
    """Known Lingua implementation only; custom providers supply their own audited metadata."""
    identity = detector.identity
    if identity.get("name") != "lingua-language-detector":
        raise ValueError("Custom language providers require explicit extension metadata")
    return ExtensionMetadata(
        name=identity["name"],
        version=identity["version"],
        configuration=identity["configuration"],
        producer_source_sha256=LOADED_CODE_DIGEST,
        model_sha256=identity["model"]["sha256"],
        dependency_versions={identity["name"]: identity["version"]},
        device=DeviceResolution(requested="cpu", resolved="cpu"),
    )


def _envelope(request, provider, *, confidence=None):
    assert_producer_unchanged("accuracy", LOADED_CODE_DIGEST)
    metadata = provider.metadata
    return {
        "source_sha256": request.source_sha256,
        "request_sha256": request_digest(request),
        "cache_key": accuracy_fingerprint(request, provider),
        "metadata": metadata,
        "status": "evidence",
        "reason": "provider_evidence",
        "confidence": confidence,
        "provenance": Provenance(
            source_sha256=request.source_sha256,
            engine=metadata.name,
            engine_version=metadata.version,
            method="derived",
            resolved_device=metadata.device.resolved,
            execution_device=metadata.device.resolved,
        ),
    }


class MetadataLanguageDetector:
    def __init__(self, detector: LanguageDetector, metadata: ExtensionMetadata | None = None):
        self.detector = detector
        self._metadata = metadata

    @property
    def identity(self) -> dict:
        return self.detector.identity

    @property
    def metadata(self) -> ExtensionMetadata:
        return self._metadata or metadata_from_language(self.detector)

    def detect(self, text: str) -> LanguageEvidence:
        return self.detector.detect(text)

    def detect_with_context(self, text: str, request: LanguageInput) -> LanguageResult:
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != request.text_sha256:
            raise ValueError("Transient language text differs from its source request")
        evidence = self.detect(text)
        return LanguageResult(
            **_envelope(request, self, confidence=evidence.confidence), evidence=evidence
        )


class MetadataOcrEngine:
    """The legacy recognize method delegates unchanged; nothing invokes OCR implicitly."""

    def __init__(self, engine: OcrEngine, metadata: ExtensionMetadata):
        self.engine = engine
        self._metadata = metadata

    @property
    def metadata(self) -> ExtensionMetadata:
        return self._metadata

    def recognize(self, image: bytes, *, languages: list[str]) -> Iterator[TextSpan]:
        return self.engine.recognize(image, languages=languages)

    def recognize_with_context(self, request: OcrInput) -> tuple[tuple[TextSpan, ...], OcrResult]:
        # The explicit opt-in request is raster evidence, never normal digital extraction.
        spans = tuple(self.recognize(request.raster.png, languages=request.languages))
        pages = {region.page for region in request.regions}
        if any(
            span.page not in pages or span.provenance.source_sha256 != request.source_sha256
            for span in spans
        ):
            raise ValueError("OCR output differs from requested source evidence")
        if len({span.id for span in spans}) != len(spans):
            raise ValueError("OCR emitted repeated span identifiers")
        envelope = _envelope(request, self)
        envelope["provenance"] = envelope["provenance"].model_copy(update={"method": "ocr"})
        return spans, OcrResult(
            **envelope, source_refs=[SpanRef(span_id=span.id) for span in spans]
        )
