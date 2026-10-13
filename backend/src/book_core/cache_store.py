"""Versioned compressed JSON, atomic replacement and bounded validated read reuse.

The .json names are retained for existing cache consumers; gzip magic identifies the
new envelope. Legacy JSON is read only. Every disk read verifies the payload checksum.
"""

import copy
import gzip
import hashlib
import json
import os
import uuid
import zlib
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from book_core.atomic import replace_with_retry

FORMAT_VERSION = 2
_READS = ContextVar("validated_cache_reads", default=None)


def read_json(path):
    try:
        data = Path(path).read_bytes()
        if data.startswith(b"\x1f\x8b"):
            data = gzip.decompress(data)
        return json.loads(data)
    except (OSError, EOFError, ValueError, zlib.error) as error:
        raise ValueError(f"Corrupt cache: {path}") from error


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(gzip.compress(data, compresslevel=6, mtime=0))
            stream.flush()
            os.fsync(stream.fileno())
        replace_with_retry(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_payload(path, payload, fingerprint):
    write_json(
        path,
        {
            "format_version": FORMAT_VERSION,
            "fingerprint": fingerprint,
            "sha256": hashlib.sha256(payload.encode("utf8")).hexdigest(),
            "payload": payload,
        },
    )


def write_model(path, value, fingerprint):
    write_payload(path, value.model_dump_json(exclude_defaults=True), fingerprint)


@contextmanager
def validated_reads(budget_bytes=64 * 1024 * 1024):
    """Reuse validation within a run, bounded by serialized size; callers get copies."""
    token = _READS.set({"entries": OrderedDict(), "bytes": 0, "budget": budget_bytes})
    try:
        yield
    finally:
        _READS.reset(token)


def read_model(path, model, fingerprint):
    entry = read_json(path)
    if entry.get("format_version", 1) not in {1, FORMAT_VERSION}:
        raise ValueError("Unsupported cache format version")
    payload = entry["payload"]
    checksum = hashlib.sha256(payload.encode("utf8")).hexdigest()
    if entry["fingerprint"] != fingerprint or checksum != entry["sha256"]:
        raise ValueError("Corrupt object cache checksum or fingerprint")
    state = _READS.get()
    key = (model, fingerprint, checksum)
    if state is not None and key in state["entries"]:
        value, _ = state["entries"].pop(key)
        state["entries"][key] = (value, len(payload))
        return copy.deepcopy(value)
    value = model.model_validate_json(payload)
    if state is not None and len(payload) <= state["budget"]:
        while state["entries"] and state["bytes"] + len(payload) > state["budget"]:
            _, (_, size) = state["entries"].popitem(last=False)
            state["bytes"] -= size
        state["entries"][key] = (copy.deepcopy(value), len(payload))
        state["bytes"] += len(payload)
    return value
