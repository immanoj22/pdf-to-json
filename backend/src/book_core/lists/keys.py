"""Lists cache identity: own producer, paragraph and structure output keys.
The upstream keys bind consumed furniture, navigation, layout and reading order.
Settings, configuration and version complete the key; the registry is excluded."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from book_core.caching import PACKAGE, SCOPES
from book_core.extraction.cache import payload_digest
from book_core.extraction.fingerprints import stable_id

LISTS_SCOPE = SCOPES["lists"]
LISTS_ENTRY_POINTS = ("lists/cache.py",)


def lists_scope_files(root=PACKAGE):
    files = set()
    for entry in LISTS_SCOPE:
        path = Path(root) / entry
        if path.is_dir():
            files.update(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
        elif path.is_file():
            files.add(path)
    return sorted(p.relative_to(root).as_posix() for p in files)


def lists_code_digest(root=PACKAGE):
    digest = hashlib.sha256(b"lists")
    for relative in lists_scope_files(root):
        data = (Path(root) / relative).read_bytes().replace(b"\r\n", b"\n")
        digest.update(b"\0" + relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def book_key_components(*, lists, structure_key, paragraph_key, settings, config, version):
    return {
        "lists_producer_sha256": lists,
        "structure_decision_key": structure_key,
        "paragraph_book_key": paragraph_key,
        "settings_sha256": payload_digest(settings.model_dump(mode="json")),
        "config_sha256": payload_digest(config),
        "lists_version": version,
    }


def book_fingerprint(components):
    return stable_id("lists-book", json.dumps(components, sort_keys=True))
