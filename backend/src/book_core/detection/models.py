"""Region observations only: no source text, span ownership, bands or reading order."""

from typing import Annotated

from pydantic import Field, PositiveInt, model_validator

from book_core.device import DeviceResolution
from book_core.extraction.rasters import RasterPage
from book_core.layout.models import RegionType
from book_core.model.common import (
    BBox,
    Confidence,
    CoreModel,
    Digest,
    Finite,
    Identifier,
    Provenance,
)


class DetectionInput(CoreModel):
    """Rendered image and its source-coordinate frame, supplied through the Extractor.

    The raster covers page_bbox, which may have a nonzero origin. Its pixel dimensions
    determine the transform; no page size, script or text direction is presumed.
    """

    source_sha256: Digest
    page: PositiveInt
    raster: RasterPage
    page_bbox: BBox

    @model_validator(mode="after")
    def positive_frame(self):
        if self.page_bbox.x0 >= self.page_bbox.x1 or self.page_bbox.y0 >= self.page_bbox.y1:
            raise ValueError("A detection render must cover a positive page frame")
        return self

    @classmethod
    def from_raster(cls, source_sha256: str, page: int, raster: RasterPage):
        """Build input for the extractor's unrotated zero-origin crop frame."""
        return cls(
            source_sha256=source_sha256,
            page=page,
            raster=raster,
            page_bbox=BBox(x0=0, y0=0, x1=raster.page_width, y1=raster.page_height),
        )


class DetectorRegion(CoreModel):
    id: Identifier
    type: RegionType
    bbox: BBox
    raw_label: str
    label_id: int
    confidence: Confidence
    polygon: list[tuple[Finite, Finite]] = Field(default_factory=list)
    # Raw emission position is diagnostic evidence, never semantic reading order.
    emission_index: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def positive_geometry(self):
        if self.bbox.x0 >= self.bbox.x1 or self.bbox.y0 >= self.bbox.y1:
            raise ValueError("A detector region must have positive area")
        return self


class DetectionResult(CoreModel):
    source_sha256: Digest
    page: PositiveInt
    detector: Identifier
    repo_id: Identifier
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    threshold: Confidence
    regions: list[DetectorRegion] = Field(default_factory=list)
    dependency_versions: dict[str, str]
    device: DeviceResolution
    provenance: Provenance

    @model_validator(mode="after")
    def identity_and_device(self):
        if len({region.id for region in self.regions}) != len(self.regions):
            raise ValueError("Duplicate detector region")
        if self.provenance.source_sha256 != self.source_sha256:
            raise ValueError("Detector provenance must identify the source")
        if (
            self.provenance.resolved_device != self.device.resolved
            or self.provenance.execution_device != self.device.resolved
        ):
            raise ValueError("Detector provenance must record the actual execution device")
        return self
