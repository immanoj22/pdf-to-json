"""Per-page results of a whole-book stage, kept by what the page's own work read.

A book stage (figures, equations, tables, characters) is keyed by the keys of the stages before
it, so any change upstream - a corrected book part re-reads the structure and the lists -
gives it a new key and it runs again for every page. Most pages read exactly what they read
before: the same layout, the same units, the same native objects. Their expensive per-page work
(rendering, image measurement, glyph and table analysis) is kept here under a key made of the
producing code, the configuration and the digests of the inputs that page's work read, so a
page whose inputs did not change is read back and a page whose inputs changed is computed.

The stage itself still runs: its whole-book decisions are recomputed from the per-page
results, so the stage output is exactly what a full run computes. Nothing here depends on the
book parts; a page memo key never names them.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from book_core.cache_store import read_json, write_json
from book_core.extraction.fingerprints import stable_id

FORMAT = "page-memo-1"


def jsonable(value):
    """A JSON value: pydantic models dumped (also inside lists, tuples and dicts)."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    return value


def digest(value) -> str:
    """Digest of a JSON-able value (pydantic models are dumped first)."""
    value = jsonable(value)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=str)  # fmt: skip
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class PageMemo:
    """``get(key)`` / ``put(key, value)`` of JSON values under ``<cache>/page_memo/<stage>/``.
    ``key(*parts)`` binds the stage, its producer digest and the given input digests."""

    def __init__(self, cache_dir, stage: str, producer: str, *identity):
        self.stage = stage
        self.directory = Path(cache_dir) / "page_memo" / stage
        self.base = stable_id(FORMAT, stage, producer, *identity)
        self.hits = self.misses = 0

    def key(self, *parts) -> str:
        return stable_id(self.base, *parts)

    def _path(self, key: str) -> Path:
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str):
        path = self._path(key)
        if not path.exists():
            self.misses += 1
            return None
        entry = read_json(path)
        if entry.get("format") != FORMAT or entry.get("key") != key:
            raise ValueError(f"Corrupt page memo entry for {self.stage}")
        if entry.get("sha256") != digest(entry["value"]):
            raise ValueError(f"Page memo checksum mismatch for {self.stage}")
        self.hits += 1
        return entry["value"]

    def put(self, key: str, value) -> None:
        write_json(self._path(key), {"format": FORMAT, "key": key, "value": value,
                                     "sha256": digest(value)})  # fmt: skip

    def write_bytes(self, key: str, data: bytes) -> None:
        """A binary result (an encoded image) beside its entry; written before the entry."""
        from book_core.atomic import replace_with_retry
        import os
        import tempfile

        path = self._path(key).with_suffix(".bin")
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
            replace_with_retry(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def read_bytes(self, key: str) -> bytes | None:
        path = self._path(key).with_suffix(".bin")
        return path.read_bytes() if path.exists() else None

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses}


__all__ = ["PageMemo", "digest", "jsonable"]
