"""Source-hashed cache for reference alignments (same key discipline as Step 4b caches).

The key covers the reference XML bytes, the PDF source, the extractor identity, every producing
source file of the alignment scope (including extraction, objects, ledger and reference code),
runtime/dependency versions, the aligner version and its configuration. A changed producer
requires a worker restart. Entries are checksummed and written atomically.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

from book_core.caching import assert_producer_unchanged, code_digest, runtime_versions
from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.extraction.interfaces import Extractor, ObjectExtractor
from book_core.model.common import BBox
from book_core.objects.consolidation import consolidate
from book_core.reference.aligner import ALIGNMENT_VERSION, AlignerConfig, AlignmentResult, align
from book_core.reference.dialects import DialectSet
from book_core.reference.pdf_tokens import PdfPage, book_tokens
from book_core.reference.xml_reader import ReferenceDocument, read_reference

ALIGNMENT_CACHE_VERSION = "alignment-cache-1"
BACKGROUND_FRACTION = 0.5
LOADED_CODE_DIGEST = code_digest("alignment")


def figure_regions(
    extractor: ObjectExtractor, source: Path, page_numbers: Iterable[int]
) -> dict[int, list[BBox]]:
    """Native image placements and consolidated vector compounds: figure-text evidence only.

    A box covering at least ``BACKGROUND_FRACTION`` of the page is page-background evidence, not
    a figure, so it is left out (relative to the page; no fixed coordinates).
    """
    regions: dict[int, list[BBox]] = {}
    for number in page_numbers:
        native = extractor.extract_object_page(source, number)
        geometry = native.page.geometry
        limit = BACKGROUND_FRACTION * geometry.width * geometry.height
        boxes = [obj.bbox for obj in native.objects if obj.kind == "image" and obj.bbox]
        boxes += [compound.bbox for compound in consolidate(native) if compound.bbox]
        regions[number] = [box for box in boxes if (box.x1 - box.x0) * (box.y1 - box.y0) < limit]
    return regions


def cached_figure_regions(
    extractor: ObjectExtractor,
    source: Path,
    pdf_sha256: str,
    page_numbers: list[int],
    cache_dir: Path | None,
) -> dict[int, list[BBox]]:
    """Figure regions keyed by source, object extractor, object/extraction code and runtime."""
    identity = {
        "pdf_sha256": pdf_sha256,
        "extractor": extractor.identity.model_dump(mode="json"),
        "producer_sha256": code_digest("analysis"),
        "runtime": runtime_versions(),
        "background_fraction": BACKGROUND_FRACTION,
        "pages": page_numbers,
    }
    fingerprint = stable_id(json.dumps(identity, sort_keys=True, separators=(",", ":")))
    path = Path(cache_dir) / "figures" / f"{fingerprint}.json" if cache_dir else None
    if path is not None and path.exists():
        stored = _read(path, fingerprint)
        return {int(page): [BBox(**box) for box in boxes] for page, boxes in stored.items()}
    regions = figure_regions(extractor, source, page_numbers)
    if path is not None:
        payload = {
            str(page): [box.model_dump() for box in boxes] for page, boxes in regions.items()
        }
        _write(path, payload, fingerprint)
    return regions


def alignment_fingerprint(
    xml_sha256: str,
    pdf_sha256: str,
    extractor: Extractor,
    config: AlignerConfig,
    figure_source: dict | None,
    dialects_digest: str,
) -> str:
    identity = {
        "xml_sha256": xml_sha256,
        "pdf_sha256": pdf_sha256,
        "extractor": extractor.identity.model_dump(mode="json"),
        "producer_sha256": code_digest("alignment"),
        "runtime": runtime_versions(),
        "alignment_version": ALIGNMENT_VERSION,
        "cache_version": ALIGNMENT_CACHE_VERSION,
        "config": asdict(config),
        "figure_evidence": figure_source,
        "dialects_sha256": dialects_digest,
    }
    return stable_id(json.dumps(identity, sort_keys=True, separators=(",", ":")))


def _write(path: Path, payload: dict, fingerprint: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    entry = {
        "fingerprint": fingerprint,
        "sha256": hashlib.sha256(data.encode("utf-8")).hexdigest(),
        "payload": data,
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(entry, handle)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _read(path: Path, fingerprint: str) -> dict:
    entry = json.loads(path.read_text(encoding="utf-8"))
    checksum = hashlib.sha256(entry["payload"].encode("utf-8")).hexdigest()
    if entry["fingerprint"] != fingerprint or checksum != entry["sha256"]:
        raise ValueError("Corrupt alignment cache checksum or fingerprint")
    return json.loads(entry["payload"])


def validate(result: AlignmentResult, doc: ReferenceDocument, pages: Sequence[PdfPage]) -> None:
    """Stored references must still point at exactly the same tokens on both sides."""
    if result.xml_sha256 != doc.sha256 or len(result.xml_page) != len(doc.tokens):
        raise ValueError("Alignment does not belong to this reference XML")
    if result.pages != [p.page for p in pages] or result.page_digests != [p.digest for p in pages]:
        raise ValueError("Alignment does not belong to these PDF tokens")


def align_cached(
    xml_path: Path,
    pdf_path: Path,
    extractor: Extractor,
    dialects: DialectSet,
    cache_dir: Path | None,
    config: AlignerConfig | None = None,
    *,
    object_extractor: ObjectExtractor | None = None,
) -> tuple[ReferenceDocument, list[PdfPage], AlignmentResult]:
    assert_producer_unchanged("alignment", LOADED_CODE_DIGEST)
    config = config or AlignerConfig()
    xml_path, pdf_path = Path(xml_path), Path(pdf_path)
    doc = read_reference(xml_path.read_bytes(), dialects)
    before = pdf_path.stat()
    pdf_sha = source_digest(pdf_path)
    pages = book_tokens(extractor.extract_pages(pdf_path))
    figure_source = object_extractor.identity.model_dump(mode="json") if object_extractor else None
    fingerprint = alignment_fingerprint(
        doc.sha256, pdf_sha, extractor, config, figure_source, dialects.digest
    )
    path = Path(cache_dir) / "alignment" / f"{fingerprint}.json" if cache_dir else None
    if path is not None and path.exists():
        result = AlignmentResult.from_payload(_read(path, fingerprint))
    else:
        regions: Mapping[int, list[BBox]] | None = None
        if object_extractor is not None:
            regions = cached_figure_regions(
                object_extractor, pdf_path, pdf_sha, [p.page for p in pages], cache_dir
            )
        result = align(doc, pages, config, regions)
        assert_producer_unchanged("alignment", LOADED_CODE_DIGEST)
        if path is not None:
            _write(path, result.to_payload(), fingerprint)
    after = pdf_path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during alignment")
    validate(result, doc, pages)
    return doc, pages, result
