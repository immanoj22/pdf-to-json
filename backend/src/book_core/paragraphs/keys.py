"""Paragraph cache identity: own producers plus explicit upstream output keys.
Furniture, vocabulary/navigation and detector identities bind consumed evidence;
settings, configuration and version complete the key. Registry edits are independent."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from book_core.caching import PACKAGE, SCOPES
from book_core.extraction.cache import payload_digest
from book_core.extraction.fingerprints import stable_id
from book_core.furniture.keys import furniture_code_digest
from book_core.reading_order.cache import vocabulary_digest

PARAGRAPH_SCOPE = SCOPES["paragraphs"]
PARAGRAPH_ENTRY_POINTS = ("paragraphs/cache.py",)


def paragraph_scope_files(root=PACKAGE):
    files = set()
    for entry in PARAGRAPH_SCOPE:
        path = Path(root) / entry
        if path.is_dir():
            files.update(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
        elif path.is_file():
            files.add(path)
    return sorted(p.relative_to(root).as_posix() for p in files)


def paragraph_code_digest(root=PACKAGE):
    digest = hashlib.sha256(b"paragraphs")
    for relative in paragraph_scope_files(root):
        data = (Path(root) / relative).read_bytes().replace(b"\r\n", b"\n")
        digest.update(b"\0" + relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def navigation_digest(navigation):
    rows = sorted((page, line, entry) for page, lines in navigation.items()
                  for line, entry in lines.items())  # fmt: skip
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def book_key_components(
    *, paragraphs, furniture_key, vocabulary, navigation, detector, settings, config, version
):
    return {
        "paragraphs_producer_sha256": paragraphs,
        "furniture_producer_sha256": furniture_code_digest(),
        "furniture_decision_key": furniture_key,
        "step6_evidence_sha256": stable_id(
            vocabulary_digest(vocabulary), navigation_digest(navigation)
        ),
        "language_detector_sha256": payload_digest(detector),
        "settings_sha256": payload_digest(settings.model_dump(mode="json")),
        "config_sha256": payload_digest(config),
        "paragraphs_version": version,
    }


def book_fingerprint(components):
    return stable_id("paragraphs-book", json.dumps(components, sort_keys=True))
