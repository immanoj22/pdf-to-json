"""Structure cache identities: separate evidence and decision producers.
Evidence binds the paragraph key and consumed navigation; decisions bind the evidence
key and configuration. Own source scopes exclude upstream producers and the registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from book_core.caching import PACKAGE, SCOPES
from book_core.extraction.cache import payload_digest
from book_core.extraction.fingerprints import stable_id
from book_core.paragraphs.keys import paragraph_code_digest

# Pass 1 (evidence) depends on its own modules only, so decision rules can change without
# re-reading the book; pass 2 binds the whole package.
EVIDENCE_SCOPE = SCOPES["structure_evidence"]
STRUCTURE_SCOPE = SCOPES["structure"]
EVIDENCE_ENTRY_POINTS = ("structure/evidence.py",)
STRUCTURE_ENTRY_POINTS = ("structure/cache.py",)


def structure_scope_files(root=PACKAGE, scope=STRUCTURE_SCOPE):
    files = set()
    for entry in scope:
        path = Path(root) / entry
        if path.is_dir():
            files.update(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
        elif path.is_file():
            files.add(path)
    return sorted(p.relative_to(root).as_posix() for p in files)


def structure_code_digest(root=PACKAGE, scope=STRUCTURE_SCOPE):
    digest = hashlib.sha256(b"structure" if scope is STRUCTURE_SCOPE else b"evidence")
    for relative in structure_scope_files(root, scope):
        data = (Path(root) / relative).read_bytes().replace(b"\r\n", b"\n")
        digest.update(b"\0" + relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def navigation_artifact_digest(navigation):
    """Step 6 navigation evidence: printed entries, TOC pages, bookmarks and page labels."""
    keep = {k: navigation.get(k) for k in ("printed_entries", "toc_pages", "bookmarks",
                                            "page_labels")}  # fmt: skip
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()


def evidence_code_digest(root=PACKAGE):
    return structure_code_digest(root, EVIDENCE_SCOPE)


def evidence_key_components(*, structure, paragraph_key, navigation, settings, version):
    return {
        "evidence_producer_sha256": structure,
        "paragraphs_producer_sha256": paragraph_code_digest(),
        "paragraph_book_key": paragraph_key,
        "step6_navigation_sha256": navigation_artifact_digest(navigation),
        "settings_sha256": payload_digest(settings.model_dump(mode="json")),
        "structure_version": version,
    }


def evidence_fingerprint(components):
    return stable_id("structure-evidence", json.dumps(components, sort_keys=True))


def decision_fingerprint(structure, evidence_key, config, version):
    return stable_id(
        "structure-book", structure, evidence_key, json.dumps(config, sort_keys=True), version
    )
