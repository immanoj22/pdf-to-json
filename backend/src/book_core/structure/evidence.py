"""Pass 1 of the structure stage: cached per-unit evidence for a whole book.

Every page is read once (native page through the Extractor, cached Step 4 layout, Step 8 page
furniture, Step 9 paragraphs) and its units are described by ``structure.features``. The result
is cached (gzip JSON with a checksum) under the evidence key (``structure.keys``), which depends
only on the pass-1 producers, so decision rules can change without re-reading the book.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
from pathlib import Path

from book_core.atomic import replace_with_retry
from book_core.document_analysis.navigation import resolve_title
from book_core.furniture.cache import page_furniture
from book_core.ledger.tokenization import line_tokens
from book_core.paragraphs.cache import load_page
from book_core.paragraphs.keys import book_fingerprint
from book_core.settings import Settings
from book_core.structure.features import page_evidence
from book_core.structure.keys import (
    evidence_code_digest,
    evidence_fingerprint,
    evidence_key_components,
)

EVIDENCE_VERSION = "structure-evidence-1"
LOADED_DIGEST = evidence_code_digest()


def assert_unchanged():
    if evidence_code_digest() != LOADED_DIGEST:
        raise RuntimeError("structure evidence producer source changed; restart the worker")


def token_owners(page, layout):
    """Visual line id of each retained token ordinal (the ledger's token order)."""
    span_line = {sid: line.id for line in layout.lines for sid in line.span_ids}
    owners = []
    for line in page.store.lines:
        raw = page.store.raw_line_text(line)
        if not raw.strip() or not page.geometry.content_bbox.contains_center(line.bbox):
            continue
        for token in line_tokens(page.store, line):
            owners.append(next((span_line[s] for s in token.span_ids if s in span_line), None))
    return owners


def _write(path, payload, key):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    entry = {"fingerprint": key, "sha256": hashlib.sha256(data).hexdigest()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(gzip.compress(json.dumps(entry).encode() + b"\n" + data, mtime=0))
        replace_with_retry(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _read(path, key):
    header, data = gzip.decompress(path.read_bytes()).split(b"\n", 1)
    entry = json.loads(header)
    if entry["fingerprint"] != key or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError("Corrupt structure evidence checksum or fingerprint")
    return json.loads(data)


def book_evidence(
    pages,
    inputs,
    furniture,
    furniture_key,
    furniture_cache,
    paragraphs,
    paragraph_cache,
    navigation,
    cache_dir,
    settings=None,
):
    """Pass 1 for a book: ({"pages": [...], ...}, evidence key, cache hit).

    ``pages``: callable returning a fresh native page iterator; ``paragraphs``: the Step 9
    ``BookParagraphResult``; ``navigation``: the Step 6 navigation artifact (may be empty).
    """
    assert_unchanged()
    settings = settings or Settings()
    navigation = navigation or {}
    components = evidence_key_components(
        structure=LOADED_DIGEST,
        paragraph_key=book_fingerprint(paragraphs.book.cache_key_inputs),
        navigation=navigation,
        settings=settings,
        version=EVIDENCE_VERSION,
    )
    key = evidence_fingerprint(components)
    path = Path(cache_dir) / "structure" / "evidence" / f"{key}.json.gz"
    if path.exists():
        evidence = _read(path, key)
        if evidence["source_sha256"] != inputs.digest:
            raise ValueError("Structure evidence belongs to another source")
        return evidence, key, True
    entries_by_page = {}
    for entry in navigation.get("printed_entries", []):
        entries_by_page.setdefault(entry["source_page"], []).append(entry)
    result = []
    for page in pages():
        number = page.geometry.page
        layout, _ = inputs(page)
        page_result = page_furniture(page, inputs, furniture, furniture_key, furniture_cache)
        built = load_page(paragraphs, number, paragraph_cache)
        entries = [
            {**entry, "title": resolve_title(entry, [page])}
            for entry in entries_by_page.get(number, [])
        ]
        result.append(
            page_evidence(page, layout, built, page_result, token_owners(page, layout), entries)
        )
    evidence = {
        "source_sha256": inputs.digest,
        "pages": result,
        "runs": [run.model_dump() for run in furniture.book.runs],
        "bookmarks": [
            {k: b.get(k) for k in ("id", "title", "target_page", "level_evidence")}
            for b in navigation.get("bookmarks", [])
        ],
        "toc_pages": navigation.get("toc_pages", []),
        "cache_key_inputs": components,
    }
    assert_unchanged()
    _write(path, evidence, key)
    return evidence, key, False
