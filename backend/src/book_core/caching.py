"""Code identity for derived caches.

A cached result is only valid for the code that produced it. Each derived cache key
therefore includes a digest of the source files of the packages that compute it, on top of
its explicit version constant, dependency versions, configuration and resolved device.
Any edit to a producing module, including comments, changes the key; stale entries are
simply never read again. See docs/caching.md.
"""

import platform
import unicodedata
from importlib.metadata import version
from pathlib import Path

from book_core.cache_identity import files_for, producer_digest

PACKAGE = Path(__file__).resolve().parent

# Package-relative files and directories whose code produces each cache.
COMMON = (
    "atomic.py",
    "cache_identity.py",
    "cache_store.py",
    "run_context.py",
    "telemetry.py",
    "device.py",
    "model",
    "objects/models.py",
    "extraction/fingerprints.py",
    "extraction/interfaces.py",
    "extraction/rasters.py",
)
SCOPES = {
    "extraction": (*COMMON, "extraction", "objects/spatial.py"),
    "analysis": (*COMMON, "objects"),
    "layout": (*COMMON, "layout"),
    "detection": (*COMMON, "detection"),
    "alignment": (*COMMON, "ledger", "reference"),
    "document": (
        *COMMON,
        "ledger",
        "reference/pdf_tokens.py",
        "reference/__init__.py",
        "document_analysis",
        "settings.py",
    ),
}
SCOPES["accuracy"] = (*COMMON, "accuracy")
SCOPES["paint"] = (*COMMON, "paint")
SCOPES["characters"] = (*COMMON, "characters")
SCOPES["figures"] = (*COMMON, "figures")
SCOPES["reading_order"] = (*COMMON, "reading_order")
SCOPES["metadata"] = (*COMMON, "document_analysis/__init__.py", "document_analysis/metadata.py")
SCOPES["furniture"] = (*COMMON, "furniture", "settings.py")
SCOPES["paragraphs"] = (
    *COMMON,
    "paragraphs",
    "settings.py",
    "document_analysis/language.py",
    "document_analysis/vocabulary.py",
)
SCOPES["structure_evidence"] = (
    *COMMON,
    "settings.py",
    "ledger",
    "structure/__init__.py",
    "structure/evidence.py",
    "structure/features.py",
    "structure/keys.py",
    "document_analysis/navigation.py",
)
SCOPES["structure"] = (*COMMON, "structure")
SCOPES["lists"] = (*COMMON, "lists", "settings.py")
SCOPES["final"] = (*COMMON, "book_run.py", "process_metrics.py", "cache_admin.py", "settings.py")

# Import boundaries must be declared, even when upstream data enters through a key.
# Registry edits do not enter producer digests; closure tests audit these declarations.
DEPENDENCIES = {
    "extraction": (),
    "analysis": ("extraction",),
    "paint": ("analysis",),
    "layout": ("analysis", "paint"),
    "reading_order": ("layout",),
    "metadata": ("extraction",),
    "furniture": ("reading_order", "metadata"),
    "paragraphs": ("furniture", "document"),
    "structure_evidence": ("paragraphs",),
    "structure": ("structure_evidence", "accuracy"),
    "lists": ("structure", "paragraphs"),
    "characters": ("lists", "paint"),
    "figures": ("lists", "analysis", "detection"),
    "detection": ("layout",),
    "alignment": ("analysis",),
    "document": ("extraction",),
    "accuracy": ("document",),
    "final": ("lists", "metadata", "characters", "figures"),
}

# Modules whose import closure inside book_core must be covered by each scope.
ENTRY_POINTS = {
    "extraction": ("extraction/cache.py", "extraction/pymupdf_backend.py"),
    "analysis": ("objects/analysis.py",),
    "layout": ("layout/pipeline.py",),
    "paint": ("paint/cache.py", "paint/extractor.py"),
    "detection": ("detection/transformers.py", "detection/cache.py"),
    "alignment": ("reference/cache.py",),
    "document": ("document_analysis/cache.py",),
    "accuracy": ("accuracy/cache.py", "accuracy/stubs.py", "accuracy/adapters.py"),
    "reading_order": ("reading_order/cache.py",),
}
ENTRY_POINTS.update(
    {
        "metadata": ("document_analysis/metadata.py",),
        "furniture": ("furniture/cache.py",),
        "paragraphs": ("paragraphs/cache.py",),
        "structure_evidence": ("structure/evidence.py",),
        "structure": ("structure/cache.py",),
        "lists": ("lists/cache.py",),
        "characters": ("characters/cache.py",),
        "figures": ("figures/cache.py", "figures/alt_text.py", "figures/evidence.py"),
        "final": ("book_run.py",),
    }
)


def scope_files(scope, root=PACKAGE):
    """Sorted package-relative source files covered by one scope."""
    return files_for(SCOPES[scope], root)


def coverage_files(scope, root=PACKAGE):
    """Source closure covered by own producers and explicitly declared input stages."""
    seen, pending, files = set(), [scope], {"caching.py"}
    while pending:
        stage = pending.pop()
        if stage in seen:
            continue
        seen.add(stage)
        files.update(scope_files(stage, root))
        pending.extend(DEPENDENCIES[stage])
    return sorted(files)


def _digest(scope, root):
    return producer_digest(scope, scope_files(scope, root), root)


def code_digest(scope):
    """Digest of installed producer sources, re-read even in a long-lived process."""
    return _digest(scope, PACKAGE)


def code_digest_at(scope, root):
    """Uncached digest of a scope under another package root (tests, audits)."""
    return _digest(scope, Path(root))


def assert_producer_unchanged(scope, loaded_digest):
    """A worker must restart after source edits; old loaded code cannot populate new keys."""
    if code_digest(scope) != loaded_digest:
        raise RuntimeError(f"{scope} producer source changed; restart the worker")
    pending, seen = list(DEPENDENCIES[scope]), set()
    while pending:
        upstream = pending.pop()
        if upstream in seen:
            continue
        seen.add(upstream)
        if code_digest(upstream) != LOADED_PRODUCERS[upstream]:
            raise RuntimeError(f"{upstream} producer source changed; restart the worker")
        pending.extend(DEPENDENCIES[upstream])


def runtime_versions():
    """Native schemas, geometry and NFKC depend on runtime and package versions."""
    return {
        "python": platform.python_version(),
        "unicode": unicodedata.unidata_version,
        **{
            name: version(name)
            for name in (
                "pymupdf",
                "pydantic",
                "regex",
                "numpy",
                "shapely",
                "networkx",
                "opencv-python-headless",
            )
        },
    }


# Read before producer modules are imported. Guards cover loaded upstream implementations
# without incorporating the registry itself into any cache fingerprint.
LOADED_PRODUCERS = {scope: code_digest(scope) for scope in SCOPES}
