"""Step 9 cache identity: the paragraph producer scope and the book key components.

Same rule as ``furniture.keys`` (declared here, not in ``caching.SCOPES``; see the per-stage
cache-key backlog in docs/decisions.md). The scope is the Step 8 furniture scope plus this
package and the Step 6 modules it uses (language detector, vocabulary rule, artifact loader).
A book key binds by name: the paragraph and furniture producer digests, the furniture decision
key (which chains the layout and order fingerprints), the Step 6 evidence digest (vocabulary
and printed-navigation entries), the language detector identity, settings, configuration and
PARAGRAPHS_VERSION.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from book_core.caching import PACKAGE
from book_core.extraction.cache import payload_digest
from book_core.extraction.fingerprints import stable_id
from book_core.furniture.keys import FURNITURE_SCOPE, furniture_code_digest
from book_core.reading_order.cache import vocabulary_digest

PARAGRAPH_SCOPE = (
    *FURNITURE_SCOPE,
    "paragraphs",
    "document_analysis/language.py",
    "document_analysis/vocabulary.py",
    "document_analysis/cache.py",
    "document_analysis/navigation.py",
    "document_analysis/repetition.py",
    "document_analysis/styles.py",
)
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
