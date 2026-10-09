"""Swappable native extraction, visual evidence and future configurable OCR contracts."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from book_core.extraction.rasters import RasterPage
from book_core.model.spans import ExtractedPage, ExtractorIdentity, TextSpan

if TYPE_CHECKING:
    from book_core.objects.models import ImageRepetition, NativeObjectPage


@runtime_checkable
class Extractor(Protocol):
    @property
    def identity(self) -> ExtractorIdentity: ...

    def extract_pages(self, source: Path) -> Iterator[ExtractedPage]: ...


class OcrEngine(Protocol):
    """Interface only; per-job/per-region language codes are supplied by settings.

    Native digital extraction never invokes OCR. No script or direction is assumed.
    """

    def recognize(self, image: bytes, *, languages: list[str]) -> Iterator[TextSpan]: ...


@runtime_checkable
class ObjectExtractor(Extractor, Protocol):
    """Optional visual-evidence capability; no consumer directly opens PDF sources."""

    def extract_object_page(self, source: Path, page_number: int) -> NativeObjectPage: ...

    def render_page(self, source: Path, page_number: int, dpi: int = 144) -> RasterPage: ...

    def image_repetition(self, source: Path) -> ImageRepetition: ...


@runtime_checkable
class DocumentExtractor(Extractor, Protocol):
    """Optional document metadata and native block membership, without semantic claims."""

    def extract_navigation(self, source: Path) -> dict: ...

    def extract_native_blocks(self, source: Path) -> list[dict]: ...
