"""Swappable native extraction and future CPU OCR contracts."""

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, runtime_checkable

from book_core.model.spans import ExtractedPage, ExtractorIdentity, TextSpan


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
