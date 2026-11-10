"""Native rawdict extraction; no semantic classification or OCR."""

import json
import unicodedata
from collections.abc import Iterator
from pathlib import Path

import pymupdf
import regex

from book_core.caching import assert_producer_unchanged, code_digest
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
from book_core.run_context import open_source, signature

LOADED_CODE_DIGEST = code_digest("extraction")


def box(values: tuple[float, ...]) -> BBox:
    x0, y0, x1, y1 = values
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


class PyMuPDFExtractor:
    def __init__(self, device: DevicePolicy = "auto"):
        self.device = resolve_device(device)

    def page_count(self, source: Path) -> int:
        assert_producer_unchanged("extraction", LOADED_CODE_DIGEST)
        with open_source(source) as document:
            if document.needs_pass:
                raise ValueError("Encrypted sources require explicit decryption before extraction")
            return len(document)

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
        assert_producer_unchanged("extraction", LOADED_CODE_DIGEST)
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
        with open_source(source) as document:
            if document.needs_pass:
                raise ValueError("Encrypted sources require explicit decryption before extraction")
            for pdf_page in document:
                yield self._page_evidence(pdf_page, digest, namespace, provenance, flags)
        after = source.stat()
        assert_producer_unchanged("extraction", LOADED_CODE_DIGEST)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Source changed during extraction; results must not be accepted")

    def _namespace(self, digest):
        identity = self.identity.model_dump()
        identity["configuration"].pop("resolved_device", None)
        return stable_id(digest, json.dumps(identity, sort_keys=True))

    def _page_evidence(self, pdf_page, digest, namespace, provenance, flags, span_geometry=None):
        """Optional span_geometry receives baseline evidence keyed by the same span IDs."""
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
        symbolic_of = _symbolic_fonts(pdf_page)
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
                        symbolic=symbolic_of.get(span["font"]),
                        provenance=provenance,
                    )
                    if span_geometry is not None:
                        span_geometry[sid] = {
                            "origin": tuple(span["origin"]),
                            "direction": tuple(line["dir"]),
                            "writing_mode": "vertical" if line["wmode"] else "horizontal",
                            "ascender": span["ascender"],
                            "descender": span["descender"],
                        }
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

        assert_producer_unchanged("extraction", LOADED_CODE_DIGEST)
        before = signature(source)
        result = extract_object_page(self, Path(source), page_number)
        if signature(source) != before:
            raise ValueError("Source changed during native object extraction")
        assert_producer_unchanged("extraction", LOADED_CODE_DIGEST)
        return result

    def render_page(self, source: Path, page_number: int, dpi: int = 144):
        from book_core.extraction.native_objects import render_page

        assert_producer_unchanged("extraction", LOADED_CODE_DIGEST)
        before = signature(source)
        result = render_page(Path(source), page_number, dpi)
        if signature(source) != before:
            raise ValueError("Source changed during rendering")
        return result

    def image_repetition(self, source: Path):
        from book_core.extraction.native_objects import image_repetition

        assert_producer_unchanged("extraction", LOADED_CODE_DIGEST)
        return image_repetition(Path(source))

    def extract_navigation(self, source: Path):
        from book_core.extraction.navigation import extract_navigation

        assert_producer_unchanged("extraction", LOADED_CODE_DIGEST)
        return extract_navigation(self, Path(source))

    def extract_native_blocks(self, source: Path):
        from book_core.extraction.navigation import extract_native_blocks

        assert_producer_unchanged("extraction", LOADED_CODE_DIGEST)
        return extract_native_blocks(self, Path(source))


_DESCRIPTOR_REF = regex.compile(r"/FontDescriptor\s+(\d+)\s+0\s+R")
_DESCENDANT_REF = regex.compile(r"/DescendantFonts\s*\[?\s*(\d+)\s+0\s+R")
_DESCENDANT_ARRAY = regex.compile(r"^\s*\[?\s*(\d+)\s+0\s+R")


def _symbolic_fonts(pdf_page) -> dict[str, bool | None]:
    """{span font name: Symbolic flag of its font descriptor} for the page's fonts. A name
    shared by fonts that disagree, or a font without a readable descriptor, maps to None."""
    document = pdf_page.parent
    found: dict[str, set] = {}
    for xref, _ext, _kind, basefont, *_ in pdf_page.get_fonts(full=False):
        name = basefont.split("+", 1)[-1] if "+" in basefont[:7] else basefont
        value = None
        try:
            source = document.xref_object(xref, compressed=True)
            match = _DESCENDANT_REF.search(source)
            if match is None:
                kind, array = document.xref_get_key(xref, "DescendantFonts")
                match = _DESCENDANT_ARRAY.match(array) if kind != "null" else None
            if match is not None:
                source = document.xref_object(int(match[1]), compressed=True)
                if source.lstrip().startswith("["):  # an indirect descendant array
                    match = _DESCENDANT_ARRAY.match(source)
                    source = document.xref_object(int(match[1]), compressed=True) if match else ""
            descriptor = _DESCRIPTOR_REF.search(source)
            if descriptor is not None:
                kind, flags = document.xref_get_key(int(descriptor[1]), "Flags")
                if kind == "int":
                    value = bool(int(flags) & 4)
        except (RuntimeError, ValueError):
            value = None
        found.setdefault(name, set()).add(value)
    return {name: next(iter(values)) if len(values) == 1 else None
            for name, values in found.items()}  # fmt: skip
