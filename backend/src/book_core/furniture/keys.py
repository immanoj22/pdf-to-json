"""Step 8 cache identity: the furniture producer scope and the book-decision key components.

The scope is declared here instead of in ``caching.SCOPES`` because any edit to ``caching.py``
re-keys every earlier cache (backlog: per-stage cache keys; docs/decisions.md, Step 8). It uses
the same file digest rule (sorted package-relative paths, CRLF normalised) over:

- the Step 7 ``reading_order`` scope (which contains the layout, objects and extraction code);
- this package;
- ``settings.py`` and the Step 6 metadata producer (``document_analysis/metadata.py``).

A book decision's key binds, explicitly and by name: the furniture producer digest, the
reading-order producer digest, the layout and order fingerprints, a Step 6 evidence digest
(book vocabulary and the native document metadata, including PDF page labels), the job
settings, the stage configuration and FURNITURE_VERSION.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from book_core.caching import PACKAGE, SCOPES, code_digest
from book_core.extraction.cache import payload_digest
from book_core.extraction.fingerprints import stable_id
from book_core.reading_order.cache import vocabulary_digest

FURNITURE_SCOPE = (
    *SCOPES["reading_order"],
    "furniture",
    "settings.py",
    "document_analysis/__init__.py",
    "document_analysis/metadata.py",
)
# Modules whose book_core import closure the scope must cover (tested).
FURNITURE_ENTRY_POINTS = ("furniture/cache.py", "document_analysis/metadata.py")


def furniture_scope_files(root=PACKAGE):
    files = set()
    for entry in FURNITURE_SCOPE:
        path = Path(root) / entry
        if path.is_dir():
            files.update(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
        elif path.is_file():
            files.add(path)
    return sorted(p.relative_to(root).as_posix() for p in files)


def furniture_code_digest(root=PACKAGE):
    digest = hashlib.sha256(b"furniture")
    for relative in furniture_scope_files(root):
        data = (Path(root) / relative).read_bytes().replace(b"\r\n", b"\n")
        digest.update(b"\0" + relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def settings_digest(settings):
    return payload_digest(settings.model_dump(mode="json"))


def step6_evidence_digest(vocabulary, metadata):
    """Digest of the Step 6 evidence the stage consumes: vocabulary and document metadata."""
    return stable_id(vocabulary_digest(vocabulary), payload_digest(metadata))


def book_key_components(
    *, furniture, layout_key, order_key, vocabulary, metadata, settings, config, version
):
    return {
        "furniture_producer_sha256": furniture,
        "reading_order_producer_sha256": code_digest("reading_order"),
        "layout_fingerprint": layout_key,
        "order_fingerprint": order_key,
        "step6_evidence_sha256": step6_evidence_digest(vocabulary, metadata),
        "settings_sha256": settings_digest(settings),
        "config_sha256": payload_digest(config),
        "furniture_version": version,
    }


def book_fingerprint(components):
    return stable_id("furniture-book", json.dumps(components, sort_keys=True))
