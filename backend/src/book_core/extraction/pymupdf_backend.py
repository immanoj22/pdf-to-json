"""Native rawdict extraction; no semantic classification or OCR."""

import json
import unicodedata
from collections.abc import Iterator
from pathlib import Path

import pymupdf

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
                "evidence_version": 1,
            },
        )

    def extract_pages(self, source: Path) -> Iterator[ExtractedPage]:
        source = Path(source)
        before = source.stat()
        digest = source_digest(source)
        identity = self.identity
        namespace = stable_id(digest, json.dumps(identity.model_dump(), sort_keys=True))
        provenance = Provenance(
            source_sha256=digest,
            engine=identity.name,
            engine_version=identity.version,
            method="native",
        )
        # Dropping native image blocks also merges otherwise separate nearby text labels.
        # Keep boundaries during parsing; binary image payloads are not placed in the span store.
        flags = pymupdf.TEXTFLAGS_RAWDICT
        with pymupdf.open(source) as document:
            if document.needs_pass:
                raise ValueError("Encrypted sources require explicit decryption before extraction")
            for pdf_page in document:
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
                yield ExtractedPage(
                    source_sha256=digest,
                    extractor=identity,
                    geometry=geometry,
                    store=SpanStore(spans=spans, lines=lines),
                )
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Source changed during extraction; results must not be accepted")
