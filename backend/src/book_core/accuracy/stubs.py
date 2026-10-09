"""Explicitly unavailable providers; importing or constructing them loads no model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from book_core.accuracy.cache import accuracy_fingerprint, request_digest
from book_core.accuracy.models import (
    ContinuationInput,
    ContinuationResult,
    ExtensionMetadata,
    FormulaInput,
    FormulaResult,
    HeadingInput,
    HeadingResult,
    MathBuildInput,
    MathBuildResult,
    MathConversionInput,
    MathConversionResult,
    PageReviewInput,
    PageReviewResult,
    TableStructureInput,
    TableStructureResult,
)
from book_core.caching import assert_producer_unchanged, code_digest
from book_core.device import DeviceResolution
from book_core.model.common import Provenance

if TYPE_CHECKING:
    from book_core.accuracy.context import SourceEvidenceResolver

LOADED_CODE_DIGEST = code_digest("accuracy")


class UnavailableProvider:
    """A no-operation provider executes on CPU without probing or importing GPU libraries."""

    name = "unavailable-accuracy-provider"

    def __init__(self, *, device="auto", configuration=None):
        self._metadata = ExtensionMetadata(
            name=self.name,
            version="1",
            configuration=dict(configuration or {}),
            producer_source_sha256=LOADED_CODE_DIGEST,
            device=DeviceResolution(
                requested=device,
                resolved="cpu",
                fallback_reason="provider_unavailable" if device != "cpu" else None,
            ),
        )

    @property
    def metadata(self):
        return self._metadata

    def _result(self, request, result_type, **fields):
        assert_producer_unchanged("accuracy", LOADED_CODE_DIGEST)
        return result_type(
            source_sha256=request.source_sha256,
            request_sha256=request_digest(request),
            cache_key=accuracy_fingerprint(request, self),
            metadata=self.metadata,
            status="unavailable",
            reason="provider_not_configured",
            provenance=Provenance(
                source_sha256=request.source_sha256,
                engine=self.metadata.name,
                engine_version=self.metadata.version,
                method="derived",
                notes=["No inference performed; evidence remains unavailable"],
                resolved_device="cpu",
                execution_device="cpu",
            ),
            **fields,
        )


class UnavailableTableStructureRecognizer(UnavailableProvider):
    name = "unavailable-table-structure"

    def recognize(self, request: TableStructureInput) -> TableStructureResult:
        return self._result(request, TableStructureResult)


class UnavailableFormulaRecognizer(UnavailableProvider):
    name = "unavailable-formula-recognition"

    def recognize(self, request: FormulaInput) -> FormulaResult:
        return self._result(request, FormulaResult)


class UnavailableMathBuilder(UnavailableProvider):
    name = "unavailable-math-builder"

    def build(
        self, request: MathBuildInput, *, context: SourceEvidenceResolver | None = None
    ) -> MathBuildResult:
        if context is not None:
            from book_core.accuracy.context import validate_source_context

            validate_source_context(request, context)
        return self._result(request, MathBuildResult)


class UnavailableMathConverter(UnavailableProvider):
    name = "unavailable-math-converter"

    def convert(self, request: MathConversionInput) -> MathConversionResult:
        return self._result(request, MathConversionResult, target_format=request.target_format)


class UnavailableContinuationScorer(UnavailableProvider):
    name = "unavailable-continuation"

    def score(
        self, request: ContinuationInput, *, context: SourceEvidenceResolver | None = None
    ) -> ContinuationResult:
        if context is not None:
            from book_core.accuracy.context import validate_source_context

            validate_source_context(request, context)
        return self._result(request, ContinuationResult)


class UnavailableHeadingClassifier(UnavailableProvider):
    name = "unavailable-heading-classifier"

    def classify(self, request: HeadingInput) -> HeadingResult:
        return self._result(request, HeadingResult)


class UnavailablePageReviewer(UnavailableProvider):
    name = "unavailable-page-reviewer"

    def review(self, request: PageReviewInput) -> PageReviewResult:
        return self._result(request, PageReviewResult)
