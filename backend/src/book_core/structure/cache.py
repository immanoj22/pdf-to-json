"""Pass 2 of the structure stage: cached book decisions from the pass-1 evidence.

``structure.decide`` decides the whole book from the evidence (``structure.evidence``):
printed-navigation kinds, TOC links, headings with levels and roles, and book parts. The
result is cached with a checksum under the decision key (``structure.keys``), which binds the
whole structure package, the evidence key, the configuration and the version.
"""

from __future__ import annotations

from pathlib import Path

from book_core.model.common import Provenance
from book_core.objects.analysis import atomic_write, verified_read
from book_core.structure.decide import DEFAULT_CONFIG, decide_book
from book_core.structure.keys import decision_fingerprint, structure_code_digest
from book_core.structure.models import BookStructure

STRUCTURE_VERSION = "structure-1"
LOADED_DIGEST = structure_code_digest()


def assert_unchanged():
    if structure_code_digest() != LOADED_DIGEST:
        raise RuntimeError("structure producer source changed; restart the worker")


def analyze_book_structure(
    evidence, evidence_key, cache_dir, config=None, device="cpu", classifier=None
):
    """Pass 2: (BookStructure, cache hit) decided from the book evidence.

    ``classifier``: an optional HeadingClassifier provider (``structure.classifier``); its
    identity (model digest, threshold) enters the decision key through the configuration.
    """
    assert_unchanged()
    config = {
        **DEFAULT_CONFIG,
        **(config or {}),
        "heading_classifier": classifier.identity() if classifier else None,
    }
    key = decision_fingerprint(LOADED_DIGEST, evidence_key, config, STRUCTURE_VERSION)
    path = Path(cache_dir) / "structure" / "book" / f"{key}.json"
    if path.exists():
        book = verified_read(path, BookStructure, key)
        if book.source_sha256 != evidence["source_sha256"]:
            raise ValueError("Structure cache belongs to another source")
        return book, True
    decided = decide_book(evidence, config, classifier)
    decided.pop("_candidates", None)
    book = BookStructure(
        source_sha256=evidence["source_sha256"],
        structure_version=STRUCTURE_VERSION,
        pages=len(evidence["pages"]),
        config=config,
        cache_key_inputs={
            **evidence["cache_key_inputs"],
            "evidence_key": evidence_key,
            "structure_producer_sha256": LOADED_DIGEST,
        },
        provenance=Provenance(
            source_sha256=evidence["source_sha256"],
            engine="book_core.structure",
            engine_version=STRUCTURE_VERSION,
            method="derived",
            resolved_device=device,
        ),
        **decided,
    )
    assert_unchanged()
    atomic_write(path, book, key)
    return book, False
