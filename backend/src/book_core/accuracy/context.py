"""Optional read-only source resolution for accuracy providers.

The context owns no semantic text and assigns no reading order. Callers supply SpanRef
order; original Unicode ranges are sliced before normalization. Transient text never
enters a semantic node or a cached request. The concrete artifact is explicitly a
span-store projection, not native glyph or vector-rule evidence.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import TypeAdapter

from book_core.accuracy.models import (
    AccuracyInput,
    ContinuationInput,
    EvidenceReference,
    MathBuildInput,
)
from book_core.extraction.fingerprints import stable_id
from book_core.model.common import Digest, SpanRef
from book_core.model.spans import SpanStore

_DIGEST = TypeAdapter(Digest)


def _digest(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResolvedSourceText:
    """Transient provider input; persistence uses only references and these digests."""

    raw_text: str
    text: str
    raw_sha256: str
    text_sha256: str
    source_sha256: str
    native_artifact_sha256: str
    pages: tuple[int, ...]

    def __post_init__(self):
        _DIGEST.validate_python(self.source_sha256)
        _DIGEST.validate_python(self.native_artifact_sha256)
        if self.raw_sha256 != _text_digest(self.raw_text) or self.text_sha256 != _text_digest(
            self.text
        ):
            raise ValueError("Resolved source text digests differ from actual text")
        if self.text != unicodedata.normalize("NFKC", self.raw_text):
            raise ValueError("Resolved source normalization differs from original text")
        if any(
            isinstance(page, bool) or not isinstance(page, int) or page < 1 for page in self.pages
        ):
            raise ValueError("Resolved source pages must be positive page identifiers")


@runtime_checkable
class SourceEvidenceResolver(Protocol):
    @property
    def source_sha256(self) -> str: ...

    @property
    def native_artifact_sha256(self) -> str: ...

    @property
    def evidence_ref(self) -> EvidenceReference: ...

    def assert_current(self) -> None: ...

    def resolve(
        self, refs: Sequence[SpanRef], *, source_sha256: str, evidence_sha256: str | None = None
    ) -> ResolvedSourceText: ...


class SpanStoreEvidenceResolver:
    """Fingerprint a supplied source store and reject source/range or mutation drift.

    native_artifact_sha256 identifies a span_store artifact only. Per-glyph geometry
    and native vector rules must use separately verified native_objects evidence.
    Source strings stay in the original supplied store; no copied store is created.
    """

    def __init__(self, source_sha256: str, store: SpanStore):
        self._source_sha256 = _DIGEST.validate_python(source_sha256)
        # Validate again because frozen models still contain mutable lists/dictionaries.
        payload = store.model_dump(mode="json")
        SpanStore.model_validate(payload)
        if any(span.provenance.source_sha256 != source_sha256 for span in store.spans.values()):
            raise ValueError("Span store provenance differs from the requested source")
        self._store = store
        self._span_store_sha256 = _digest(payload)
        self._native_artifact_sha256 = _digest(
            {
                "kind": "span_store",
                "version": 1,
                "source_sha256": source_sha256,
                "span_store_sha256": self._span_store_sha256,
            }
        )
        self._evidence_ref = EvidenceReference(
            id=stable_id(source_sha256, "span-store-evidence", self._native_artifact_sha256),
            sha256=self._native_artifact_sha256,
            kind="span_store",
        )

    @property
    def source_sha256(self) -> str:
        return self._source_sha256

    @property
    def span_store_sha256(self) -> str:
        return self._span_store_sha256

    @property
    def native_artifact_sha256(self) -> str:
        return self._native_artifact_sha256

    @property
    def evidence_ref(self) -> EvidenceReference:
        return self._evidence_ref

    def assert_current(self) -> None:
        if _digest(self._store.model_dump(mode="json")) != self._span_store_sha256:
            raise ValueError("Stale source context: the supplied span store changed")

    def resolve(
        self, refs: Sequence[SpanRef], *, source_sha256: str, evidence_sha256: str | None = None
    ) -> ResolvedSourceText:
        self.assert_current()
        if source_sha256 != self.source_sha256:
            raise ValueError("Source context belongs to another source")
        if evidence_sha256 is not None and evidence_sha256 != self.native_artifact_sha256:
            raise ValueError("Source context artifact digest differs")
        parts, pages = [], []
        previous_line = None
        for ref in refs:
            ref = SpanRef.model_validate(ref)
            try:
                span = self._store.spans[ref.span_id]
            except KeyError as error:
                raise ValueError("Source context references an unknown span") from error
            if span.provenance.source_sha256 != self.source_sha256:
                raise ValueError("Source span provenance differs from its context")
            if ref.end is not None and ref.end > len(span.raw_text):
                raise ValueError("Source character range exceeds the original span")
            if previous_line is not None and span.line_id != previous_line:
                parts.append("\n")
            # Half-open offsets are original codepoints, never normalized offsets.
            parts.append(span.raw_text[ref.start : ref.end])
            previous_line = span.line_id
            if span.page not in pages:
                pages.append(span.page)
        raw = "".join(parts)
        text = unicodedata.normalize("NFKC", raw)
        self.assert_current()
        return ResolvedSourceText(
            raw_text=raw,
            text=text,
            raw_sha256=_text_digest(raw),
            text_sha256=_text_digest(text),
            source_sha256=self.source_sha256,
            native_artifact_sha256=self.native_artifact_sha256,
            pages=tuple(pages),
        )


def _resolved_regions(request: AccuracyInput, resolver: SourceEvidenceResolver) -> dict:
    resolver.assert_current()
    if request.source_sha256 != resolver.source_sha256:
        raise ValueError("Accuracy request and source context belong to different sources")
    if resolver.evidence_ref.sha256 != resolver.native_artifact_sha256:
        raise ValueError("Source context reference differs from its actual artifact digest")
    resolved = {}
    for region in request.regions:
        text = resolver.resolve(
            region.source_refs,
            source_sha256=request.source_sha256,
            evidence_sha256=resolver.native_artifact_sha256,
        )
        if (
            text.source_sha256 != request.source_sha256
            or text.native_artifact_sha256 != resolver.native_artifact_sha256
            or any(page != region.page for page in text.pages)
        ):
            raise ValueError("Accuracy region and resolved source page/provenance differ")
        resolved[region.id] = text
    if isinstance(request, MathBuildInput):
        ranges = [glyph.source_ref for glyph in request.glyphs]
        if request.observation is not None:
            ranges.extend(request.observation.source_refs)
        if ranges:
            # Verify original character bounds only. Glyph/rule geometry belongs to
            # a separate native_objects artifact and is not asserted by this store.
            resolver.resolve(
                ranges,
                source_sha256=request.source_sha256,
                evidence_sha256=resolver.native_artifact_sha256,
            )
    return resolved


def bind_source_context[Request: AccuracyInput](
    request: Request, resolver: SourceEvidenceResolver
) -> Request:
    """Return a new bound request; no source text is serialized or caller object changed."""
    resolved = _resolved_regions(request, resolver)
    reference = resolver.evidence_ref
    existing = {item.id: item for item in request.evidence_refs}
    if reference.id in existing and existing[reference.id] != reference:
        raise ValueError("Conflicting source context evidence reference")
    data = request.model_dump(mode="python")
    data["evidence_refs"] = [*request.evidence_refs]
    if reference.id not in existing:
        data["evidence_refs"].append(reference)
    if isinstance(request, ContinuationInput):
        data["first_text_sha256"] = resolved[request.first_region_id].text_sha256
        data["second_text_sha256"] = resolved[request.second_region_id].text_sha256
    return type(request).model_validate(data)


def _validated_regions(request: AccuracyInput, resolver: SourceEvidenceResolver) -> dict:
    resolved = _resolved_regions(request, resolver)
    if resolver.evidence_ref not in request.evidence_refs:
        raise ValueError("Accuracy request lacks the current source context artifact reference")
    if isinstance(request, ContinuationInput):
        if (
            request.first_text_sha256 != resolved[request.first_region_id].text_sha256
            or request.second_text_sha256 != resolved[request.second_region_id].text_sha256
        ):
            raise ValueError("Continuation text digests differ from the supplied source context")
    return resolved


def validate_source_context(request: AccuracyInput, resolver: SourceEvidenceResolver) -> None:
    """Validate actual source/ranges/digests without invoking a model or making decisions."""
    _validated_regions(request, resolver)


def resolve_continuation(
    request: ContinuationInput, resolver: SourceEvidenceResolver
) -> tuple[ResolvedSourceText, ResolvedSourceText]:
    """Resolve the explicitly supplied candidate pair; this does not infer adjacency."""
    resolved = _validated_regions(request, resolver)
    return resolved[request.first_region_id], resolved[request.second_region_id]
