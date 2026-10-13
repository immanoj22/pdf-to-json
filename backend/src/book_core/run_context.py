"""Run-scoped source identity: one content hash, checked file identity at every use."""

import hashlib
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from book_core.cache_identity import producer_session
from book_core.telemetry import count

_SOURCE = ContextVar("book_source_snapshot", default=None)


def open_source(source):
    import pymupdf

    current = _SOURCE.get()
    if current is not None and current.path == Path(source).resolve():
        current.check()
    count("source_reads")
    return pymupdf.open(source)


def signature(source):
    stat = Path(source).stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    signature: tuple
    digest: str

    def check(self):
        if signature(self.path) != self.signature:
            raise ValueError("Source changed during book run; results must not be accepted")


def hash_source(source):
    source = Path(source).resolve()
    current = _SOURCE.get()
    if current is not None and current.path == source:
        current.check()
        return current.digest
    digest = hashlib.sha256()
    count("asset_hashes" if current is not None else "source_hashes")
    count("asset_reads" if current is not None else "source_reads")
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def source_session(source, snapshot=None):
    source = Path(source).resolve()
    before = signature(source)
    if snapshot is None:
        snapshot = SourceSnapshot(source, before, hash_source(source))
    if snapshot.path != source or snapshot.signature != before:
        raise ValueError("Worker source snapshot mismatch")
    snapshot.check()
    token = _SOURCE.set(snapshot)
    try:
        with producer_session():
            yield snapshot
            snapshot.check()
    finally:
        _SOURCE.reset(token)
