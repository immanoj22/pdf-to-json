"""Code identity for derived caches.

A cached result is only valid for the code that produced it. Each derived cache key
therefore includes a digest of the source files of the packages that compute it, on top of
its explicit version constant, dependency versions, configuration and resolved device.
Any edit to a producing module, including comments, changes the key; stale entries are
simply never read again. See docs/caching.md.
"""

import hashlib
import platform
import unicodedata
from importlib.metadata import version
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent

# Package-relative files and directories whose code produces each cache.
COMMON = ("caching.py", "device.py", "extraction", "model", "objects")
SCOPES = {
    "extraction": COMMON,
    "analysis": (*COMMON, "objects"),
    "layout": (*COMMON, "objects", "layout"),
    "detection": (*COMMON, "objects", "layout", "detection"),
    "alignment": (*COMMON, "ledger", "reference"),
    "document": (
        *COMMON,
        "ledger",
        "reference/pdf_tokens.py",
        "reference/__init__.py",
        "document_analysis",
    ),
}
# Modules whose import closure inside book_core must be covered by each scope.
ENTRY_POINTS = {
    "extraction": ("extraction/cache.py", "extraction/pymupdf_backend.py"),
    "analysis": ("objects/analysis.py",),
    "layout": ("layout/pipeline.py",),
    "detection": ("detection/transformers.py", "detection/cache.py"),
    "alignment": ("reference/cache.py",),
    "document": ("document_analysis/cache.py",),
}


def scope_files(scope, root=PACKAGE):
    """Sorted package-relative source files covered by one scope."""
    files = set()
    for entry in SCOPES[scope]:
        path = Path(root) / entry
        if path.is_dir():
            files.update(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
        elif path.is_file():
            files.add(path)
    return sorted(p.relative_to(root).as_posix() for p in files)


def _digest(scope, root):
    digest = hashlib.sha256(scope.encode("utf-8"))
    for relative in scope_files(scope, root):
        # Line endings are normalised so a checkout on another OS keeps the same key.
        data = (Path(root) / relative).read_bytes().replace(b"\r\n", b"\n")
        digest.update(b"\0" + relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


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
