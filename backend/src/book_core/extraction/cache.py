"""Validated, atomic per-page evidence cache around the Extractor contract."""

import hashlib
import json
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

from book_core.atomic import replace_with_retry
from book_core.cache_store import read_json, write_json
from book_core.caching import assert_producer_unchanged, code_digest, runtime_versions
from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.extraction.interfaces import Extractor
from book_core.model.spans import ExtractedPage, ExtractorIdentity

CACHE_VERSION = "1"
LOADED_CODE_DIGEST = code_digest("extraction")


def atomic_json(target: Path, value: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        replace_with_retry(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def payload_digest(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class CachedExtractor:
    def __init__(self, extractor: Extractor, cache_dir: Path):
        self.extractor = extractor
        self.cache_dir = Path(cache_dir)
        self.cache_hits = 0
        self.cache_misses = 0

    @property
    def identity(self) -> ExtractorIdentity:
        return self.extractor.identity

    def extract_pages(self, source: Path) -> Iterator[ExtractedPage]:
        assert_producer_unchanged("extraction", LOADED_CODE_DIGEST)
        source = Path(source)
        before = source.stat()
        digest = source_digest(source)
        identity = self.identity.model_dump(mode="json")
        namespace = stable_id(
            digest,
            CACHE_VERSION,
            json.dumps(identity, sort_keys=True, separators=(",", ":")),
            code_digest("extraction"),
            json.dumps(runtime_versions(), sort_keys=True),
        )
        directory = self.cache_dir / namespace
        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            if (
                manifest["cache_version"] != CACHE_VERSION
                or manifest["source_sha256"] != digest
                or manifest["extractor"] != identity
            ):
                raise ValueError("Cache manifest fingerprint mismatch")
            for number, expected_hash in enumerate(manifest["page_hashes"], start=1):
                entry = read_json(directory / f"page_{number:06d}.json")
                if (
                    entry["payload_sha256"] != expected_hash
                    or payload_digest(entry["payload"]) != expected_hash
                ):
                    raise ValueError("Corrupt cached extraction payload")
                page = ExtractedPage.model_validate(entry["payload"])
                if (
                    page.source_sha256 != digest
                    or page.extractor != self.identity
                    or page.geometry.page != number
                ):
                    raise ValueError("Cached page identity mismatch")
                self.cache_hits += 1
                yield page
        else:
            hashes: list[str] = []
            for number, page in enumerate(self.extractor.extract_pages(source), start=1):
                if (
                    page.source_sha256 != digest
                    or page.extractor != self.identity
                    or page.geometry.page != number
                ):
                    raise ValueError("Extractor violated source/configuration/page-order contract")
                payload = page.model_dump(mode="json")
                checksum = payload_digest(payload)
                assert_producer_unchanged("extraction", LOADED_CODE_DIGEST)
                write_json(
                    directory / f"page_{number:06d}.json",
                    {"payload_sha256": checksum, "payload": payload},
                )
                hashes.append(checksum)
                self.cache_misses += 1
                yield page
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Source changed during cached extraction")
            write_json(
                manifest_path,
                {
                    "cache_version": CACHE_VERSION,
                    "source_sha256": digest,
                    "extractor": identity,
                    "page_hashes": hashes,
                },
            )
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Source changed during cached extraction")
