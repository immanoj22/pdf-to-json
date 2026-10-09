"""Optional accuracy extension contracts; no provider is selected by importing them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

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

if TYPE_CHECKING:
    from book_core.accuracy.context import SourceEvidenceResolver


@runtime_checkable
class AccuracyProvider(Protocol):
    @property
    def metadata(self) -> ExtensionMetadata: ...


@runtime_checkable
class TableStructureRecognizer(AccuracyProvider, Protocol):
    def recognize(self, request: TableStructureInput) -> TableStructureResult: ...


@runtime_checkable
class FormulaRecognizer(AccuracyProvider, Protocol):
    def recognize(self, request: FormulaInput) -> FormulaResult: ...


@runtime_checkable
class MathBuilder(AccuracyProvider, Protocol):
    def build(
        self, request: MathBuildInput, *, context: SourceEvidenceResolver | None = None
    ) -> MathBuildResult: ...


@runtime_checkable
class MathConverter(AccuracyProvider, Protocol):
    def convert(self, request: MathConversionInput) -> MathConversionResult: ...


@runtime_checkable
class ContinuationScorer(AccuracyProvider, Protocol):
    def score(
        self, request: ContinuationInput, *, context: SourceEvidenceResolver | None = None
    ) -> ContinuationResult: ...


@runtime_checkable
class HeadingClassifier(AccuracyProvider, Protocol):
    def classify(self, request: HeadingInput) -> HeadingResult: ...


@runtime_checkable
class PageReviewer(AccuracyProvider, Protocol):
    def review(self, request: PageReviewInput) -> PageReviewResult: ...
