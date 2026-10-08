"""Content-addressed source and configuration identities, independent of any backend."""

import hashlib
from pathlib import Path


def source_digest(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(namespace: str, *parts: object) -> str:
    payload = "/".join([namespace, *(str(part) for part in parts)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
