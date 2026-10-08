"""Swappable region evidence without access to the span store or text ledger."""

from typing import Protocol, runtime_checkable

from book_core.detection.models import DetectionInput, DetectionResult
from book_core.device import DeviceResolution


@runtime_checkable
class RegionDetector(Protocol):
    name: str
    repo_id: str
    revision: str
    threshold: float

    @property
    def producer_source_sha256(self) -> str: ...

    @property
    def dependency_versions(self) -> dict[str, str]: ...

    @property
    def device(self) -> DeviceResolution: ...

    def detect(self, page: DetectionInput) -> DetectionResult: ...
