"""Source-hashed native document metadata cache, independent of analysis thresholds."""

import hashlib
import json
from pathlib import Path

from book_core.caching import assert_producer_unchanged, code_digest, runtime_versions
from book_core.extraction.cache import atomic_json, payload_digest
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.interfaces import DocumentExtractor


def _producer():
    return hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


LOADED_PRODUCER = _producer()
LOADED_EXTRACTION = code_digest("extraction")


def cached_metadata(source: Path, extractor: DocumentExtractor, directory: Path) -> dict:
    """Changing navigation inference never reuses stale extraction or reparses its PDF."""
    source = Path(source)
    assert_producer_unchanged("extraction", LOADED_EXTRACTION)
    if _producer() != LOADED_PRODUCER:
        raise RuntimeError("Document metadata producer changed; restart the worker")
    before = source.stat()
    digest = source_digest(source)
    provenance = {
        "version": "native-document-metadata-1",
        "source_sha256": digest,
        "extractor": extractor.identity.model_dump(mode="json"),
        "extraction_producer_sha256": LOADED_EXTRACTION,
        "metadata_producer_sha256": LOADED_PRODUCER,
        "runtime": runtime_versions(),
    }
    key = payload_digest(provenance)
    target = Path(directory) / f"{key}.json"
    if target.exists():
        entry = json.loads(target.read_text("utf8"))
        if (
            entry["provenance"] != provenance
            or payload_digest(entry["payload"]) != entry["payload_sha256"]
        ):
            raise ValueError("Corrupt native document metadata cache")
        result = entry["payload"]
    else:
        result = extractor.extract_navigation(source)
        if result["source_sha256"] != digest or result["extractor"] != provenance["extractor"]:
            raise ValueError("Native document metadata source/configuration mismatch")
        assert_producer_unchanged("extraction", LOADED_EXTRACTION)
        if _producer() != LOADED_PRODUCER:
            raise RuntimeError("Document metadata producer changed; restart the worker")
        atomic_json(
            target,
            {"provenance": provenance, "payload": result, "payload_sha256": payload_digest(result)},
        )
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during document metadata extraction")
    return result
