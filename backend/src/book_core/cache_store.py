"""Versioned compressed JSON, atomic replacement and bounded validated read reuse.

The .json names are retained for existing cache consumers; gzip magic identifies the
new envelope. Legacy JSON is read only. Every disk read verifies the payload checksum.
"""

import copy
import ctypes
import ctypes.util
import gzip
import hashlib
import json
import os
import uuid
import zlib
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache
from pathlib import Path
from typing import get_args, get_origin

from pydantic import TypeAdapter

from book_core.atomic import replace_with_retry

FORMAT_VERSION = 2
_READS = ContextVar("validated_cache_reads", default=None)
# A payload this large (a vector-heavy page: millions of path items and glyphs) is validated
# one top-level list element at a time, so the parse holds one element rather than the whole
# document; the freed parse buffers are then handed back to the operating system.
LARGE_PAYLOAD_BYTES = 64 * 1024 * 1024
_DECODER = json.JSONDecoder()
_HEAP = []


def release_free_memory():
    """Return freed C-heap pages to the operating system where the allocator keeps them
    (glibc); elsewhere the allocator returns large blocks itself and this does nothing."""
    if not _HEAP:
        name = ctypes.util.find_library("c") if os.name == "posix" else None
        library = ctypes.CDLL(name) if name else None
        _HEAP.append(getattr(library, "malloc_trim", None))
    if _HEAP[0] is not None:
        _HEAP[0](0)


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
    size = len(payload)
    if size > LARGE_PAYLOAD_BYTES:
        del entry
        value = _validate_by_element(model, payload)
        del payload
        release_free_memory()
    else:
        value = model.model_validate_json(payload)
        del entry, payload
    if state is not None and size <= state["budget"]:
        while state["entries"] and state["bytes"] + size > state["budget"]:
            _, (_, cached) = state["entries"].popitem(last=False)
            state["bytes"] -= cached
        state["entries"][key] = (copy.deepcopy(value), size)
        state["bytes"] += size
    return value


@cache
def _element_adapter(model, name):
    annotation = model.model_fields[name].annotation
    return TypeAdapter(get_args(annotation)[0]) if get_origin(annotation) is list else None


def _validate_by_element(model, payload):
    """``model.model_validate_json(payload)`` for a JSON object, with each element of a
    top-level list field decoded and validated on its own; the model is then validated from
    the built fields."""
    fields, position, end = {}, _skip(payload, 0), len(payload)
    if payload[position] != "{":
        return model.model_validate_json(payload)
    position = _skip(payload, position + 1)
    while payload[position] != "}":
        name, position = _DECODER.raw_decode(payload, position)
        position = _skip(payload, _skip(payload, position) + 1)  # past the colon
        adapter = _element_adapter(model, name) if name in model.model_fields else None
        if adapter is not None and payload[position] == "[":
            items, position = [], _skip(payload, position + 1)
            while payload[position] != "]":
                raw, position = _DECODER.raw_decode(payload, position)
                items.append(adapter.validate_python(raw))
                position = _skip(payload, position)
                if payload[position] == ",":
                    position = _skip(payload, position + 1)
            fields[name], position = items, position + 1
        else:
            fields[name], position = _DECODER.raw_decode(payload, position)
        position = _skip(payload, position)
        if payload[position] == ",":
            position = _skip(payload, position + 1)
    if _skip(payload, position + 1) != end:
        raise ValueError("Trailing data after the cached object")
    return model.model_validate(fields)


def _skip(text, position):
    while position < len(text) and text[position] in " \t\r\n":
        position += 1
    return position
