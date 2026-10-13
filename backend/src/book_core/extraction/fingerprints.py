"""Content-addressed source and configuration identities, independent of any backend."""

import hashlib
from pathlib import Path

from book_core.run_context import hash_source


def source_digest(source: Path) -> str:
    return hash_source(Path(source))


def stable_id(namespace: str, *parts: object) -> str:
    payload = "/".join([namespace, *(str(part) for part in parts)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
