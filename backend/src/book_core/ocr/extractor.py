"""Extractor view over native evidence plus separately cached OCR spans.

Only regions explicitly approved by the eligibility screen enter this view. Earlier
invisible OCR layers are comparison evidence and never enter the view twice.
"""

from pathlib import Path

from pydantic import Field, PositiveInt, model_validator

from book_core.cache_store import read_model
from book_core.extraction.fingerprints import source_digest
from book_core.model.common import CoreModel, Digest
from book_core.model.spans import ExtractorIdentity, SpanStore
from book_core.objects.models import NativeObjectPage, PageObject, SpanGeometry
from book_core.ocr.tokens import OcrPage


class OcrInput(CoreModel):
    source_sha256: Digest
    fingerprint: Digest
    directory: Path
    page_keys: dict[PositiveInt, Digest] = Field(default_factory=dict)
    comparison_keys: dict[PositiveInt, Digest] = Field(default_factory=dict)
    scan_image_ids: dict[PositiveInt, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def disjoint_sources(self):
        if set(self.page_keys) & set(self.comparison_keys):
            raise ValueError("A page cannot replace and compare native text at the same time")
        if not set(self.scan_image_ids) <= set(self.page_keys):
            raise ValueError("Only OCR source pages can mark their backing scan images")
        return self

    def read(self, number):
        key = self.page_keys.get(number) or self.comparison_keys.get(number)
        return read_model(self.directory / key / f"{number}.json", OcrPage, key) if key else None

    def raster_path(self, number):
        key = self.page_keys.get(number) or self.comparison_keys.get(number)
        if key is None:
            raise ValueError("Page has no OCR source raster")
        path = self.directory / key / "images" / f"{number}.png"
        if source_digest(path) != self.read(number).raster_sha256:
            raise ValueError("OCR source raster checksum mismatch")
        return path


class OcrExtractor:
    def __init__(self, native, inputs: OcrInput):
        self.native, self.inputs, self.device = native, inputs, native.device

    @property
    def identity(self):
        if not self.inputs.page_keys:
            return self.native.identity
        base = self.native.identity
        return ExtractorIdentity(
            name=base.name + "-ocr",
            version=base.version,
            configuration={**base.configuration, "ocr": self.inputs.fingerprint},
        )

    def page_count(self, source):
        return self.native.page_count(source)

    def extract_object_page(self, source, page_number):
        native = self.native.extract_object_page(source, page_number)
        if native.page.source_sha256 != self.inputs.source_sha256:
            raise ValueError("OCR evidence belongs to a different source")
        if page_number not in self.inputs.page_keys:
            return native
        return add_ocr(native, self.inputs.read(page_number))

    def extract_pages(self, source):
        for number in range(1, self.page_count(source) + 1):
            yield self.extract_object_page(source, number).page

    def render_page(self, source, page_number, dpi=144):
        return self.native.render_page(source, page_number, dpi)

    def image_repetition(self, source):
        return self.native.image_repetition(source)

    def extract_navigation(self, source):
        # Navigation is native evidence; it is stamped with this view's identity, as the
        # metadata cache keys every record by the extractor that produced the run.
        result = self.native.extract_navigation(source)
        return {**result, "extractor": self.identity.model_dump(mode="json")}

    def extract_native_blocks(self, source):
        return self.native.extract_native_blocks(source)


def add_ocr(native: NativeObjectPage, result: OcrPage) -> NativeObjectPage:
    """Add marked spans with distinct IDs. No native span or object can be removed."""
    if (
        native.page.source_sha256 != result.page.source_sha256
        or native.page.geometry != result.page.geometry
    ):
        raise ValueError("OCR and native page identity/geometry disagree")
    old, new = native.page.store, result.page.store
    if set(old.spans) & set(new.spans):
        raise ValueError("OCR span ID collides with native source")
    # The caller must not add OCR over a retained native text layer. Its reading stays
    # comparison-only until the owner chooses a source; this also prevents duplicates.
    for span in new.spans.values():
        if any(
            s.bbox.contains_center(span.bbox) and s.raw_text.strip() for s in old.spans.values()
        ):
            raise ValueError("OCR overlaps retained native text; compare the sources instead")
    store = SpanStore(
        spans={**old.spans, **new.spans},
        lines=[*old.lines, *new.lines],
    )
    objects = [
        *native.objects,
        *(
            PageObject(
                id=s.id,
                kind="text",
                bbox=s.bbox,
                source_page=s.page,
                source_spans=[s.id],
                provenance=s.provenance,
                evidence_notes=["OCR geometry, no native glyph or paint sequence"],
            )
            for s in new.spans.values()
        ),
    ]
    return NativeObjectPage(
        page=native.page.model_copy(update={"store": store}),
        objects=objects,
        paint_commands=native.paint_commands,
        span_geometry={
            **native.span_geometry,
            **{
                word.span_id: SpanGeometry(
                    origin=word.origin,
                    direction=word.direction,
                    writing_mode=word.writing_mode,
                    ascender=1.0,
                    descender=0.0,
                )
                for word in result.words
            },
        }
        if native.span_geometry or not old.spans
        else {},
        diagnostics=[*native.diagnostics, "OCR spans retained as a separate marked source"],
    )


def apply_scan_roles(analysis, inputs, page_number):
    """Mark proven scan backing images, retaining every original asset and its identity."""
    images = set(inputs.scan_image_ids.get(page_number, ()))
    if not images or page_number not in inputs.page_keys:
        return analysis
    records = [
        r.model_copy(
            update={
                "role": "scan_layer",
                "confidence": 1.0,
                "reasons": [
                    "Eligibility evidence identifies this retained raster as OCR scan backing"
                ],
                "review_required": False,
            }
        )
        if r.object_id in images
        else r
        for r in analysis.asset_ledger.records
    ]
    return analysis.model_copy(
        update={"asset_ledger": analysis.asset_ledger.model_copy(update={"records": records})}
    )
