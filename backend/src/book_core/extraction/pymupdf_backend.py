"""Native rawdict extraction; no semantic classification or OCR."""

import json
import unicodedata
from collections.abc import Iterator
from pathlib import Path

import pymupdf

from book_core.device import DevicePolicy, resolve_device
from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.model.common import BBox, Provenance
from book_core.model.spans import (
    ExtractedPage,
    ExtractorIdentity,
    PageGeometry,
    SourceLine,
    SpanStore,
    TextSpan,
)


def box(values: tuple[float, ...]) -> BBox:
    x0, y0, x1, y1 = values
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


class PyMuPDFExtractor:
    def __init__(self, device: DevicePolicy = "auto"):
        self.device = resolve_device(device)

    @property
    def identity(self) -> ExtractorIdentity:
        return ExtractorIdentity(
            name="pymupdf",
            version=pymupdf.VersionBind,
            configuration={
                "format": "rawdict",
                "sort": False,
                "preserve_images": True,
                "normalization": "NFKC",
                "frame_policy": "explicit_trimbox_line_center_in_unrotated_cropbox",
                "evidence_version": 2,
                "resolved_device": self.device.resolved,
            },
        )

    def extract_pages(self, source: Path) -> Iterator[ExtractedPage]:
        source = Path(source)
        before = source.stat()
        digest = source_digest(source)
        identity = self.identity
        namespace = self._namespace(digest)
        provenance = Provenance(
            source_sha256=digest,
            engine=identity.name,
            engine_version=identity.version,
            method="native",
            resolved_device=self.device.resolved,
        )
        # Dropping native image blocks also merges otherwise separate nearby text labels.
        # Keep boundaries during parsing; binary image payloads are not placed in the span store.
        flags = pymupdf.TEXTFLAGS_RAWDICT
        with pymupdf.open(source) as document:
            if document.needs_pass:
                raise ValueError("Encrypted sources require explicit decryption before extraction")
            for pdf_page in document:
                yield self._page_evidence(pdf_page, digest, namespace, provenance, flags)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Source changed during extraction; results must not be accepted")

    def _namespace(self, digest):
        identity = self.identity.model_dump()
        identity["configuration"].pop("resolved_device", None)
        return stable_id(digest, json.dumps(identity, sort_keys=True))

    def _page_evidence(self, pdf_page, digest, namespace, provenance, flags):
        page_number = pdf_page.number + 1
        crop, trim = pdf_page.cropbox, pdf_page.trimbox
        bounds = (
            max(0.0, trim.x0 - crop.x0),
            max(0.0, trim.y0 - crop.y0),
            min(crop.width, trim.x1 - crop.x0),
            min(crop.height, trim.y1 - crop.y0),
        )
        if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
            raise ValueError("Explicit printed frame does not intersect the source crop")
        geometry = PageGeometry(
            page=page_number,
            width=crop.width,
            height=crop.height,
            rotation=pdf_page.rotation,
            content_bbox=box(bounds),
        )
        spans: dict[str, TextSpan] = {}
        lines: list[SourceLine] = []
        raw = pdf_page.get_text("rawdict", flags=flags, sort=False)
        for block_index, block in enumerate(raw["blocks"]):
            if block["type"] != 0:
                continue
            for line_index, line in enumerate(block["lines"]):
                line_id = stable_id(namespace, "line", page_number, block_index, line_index)
                span_ids: list[str] = []
                for span_index, span in enumerate(line["spans"]):
                    sid = stable_id(line_id, "span", span_index)
                    text = "".join(character["c"] for character in span["chars"])
                    spans[sid] = TextSpan(
                        id=sid,
                        line_id=line_id,
                        page=page_number,
                        raw_text=text,
                        text=unicodedata.normalize("NFKC", text),
                        bbox=box(span["bbox"]),
                        font=span["font"],
                        size=span["size"],
                        color=span["color"],
                        flags=span["flags"],
                        provenance=provenance,
                    )
                    span_ids.append(sid)
                lines.append(
                    SourceLine(
                        id=line_id,
                        page=page_number,
                        bbox=box(line["bbox"]),
                        span_ids=span_ids,
                    )
                )
        return ExtractedPage(
            source_sha256=digest,
            extractor=self.identity,
            geometry=geometry,
            store=SpanStore(spans=spans, lines=lines),
        )

    def extract_object_page(self, source: Path, page_number: int):
        from book_core.extraction.native_objects import extract_object_page

        return extract_object_page(self, Path(source), page_number)

    def render_page(self, source: Path, page_number: int, dpi: int = 144):
        from book_core.extraction.native_objects import render_page

        return render_page(Path(source), page_number, dpi)

    def image_repetition(self, source: Path):
        from book_core.extraction.native_objects import image_repetition

        return image_repetition(Path(source))
