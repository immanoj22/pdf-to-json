"""Count PDF hashing/open calls in the preserved, fully cached book setup path.

One native page is consumed: the old extractor hashes/opens once at iterator entry,
not once per yielded page. This is an input-I/O probe, not a book run or accuracy score.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".cache/step11c/baseline_src"))
import book_core  # noqa: E402, F401
from book_core.settings import Settings  # noqa: E402

# Relocating the read-only producer snapshot must not relocate job configuration.
# Preserve the original repository's default data path without editing the snapshot.
Settings.model_fields["reference_dialects"].default = (
    ROOT / "backend/reference_dialects/dialects.json"
)
Settings.model_rebuild(force=True)

sys.path.insert(0, str(ROOT / "experiments"))
from step10_run import load_book  # noqa: E402
from step11c_identity import BOOKS, OUT  # noqa: E402


def main():
    import pymupdf
    from reference_paths import reference_path
    from step7_layouts import BOOKS as SOURCES

    from book_core.extraction import fingerprints

    original_hash, original_open = fingerprints.source_digest, pymupdf.open
    results = {}
    for book in BOOKS:
        source = reference_path(SOURCES[book][0]).resolve()
        counts = {"pdf_hashes": 0, "pdf_opens": 0, "native_pages_consumed": 1}

        def counted_hash(path, source=source, counts=counts):
            if Path(path).resolve() == source:
                counts["pdf_hashes"] += 1
            return original_hash(path)

        def counted_open(*args, source=source, counts=counts, **kwargs):
            path = args[0] if args else kwargs.get("filename")
            if path is not None and Path(path).resolve() == source:
                counts["pdf_opens"] += 1
            return original_open(*args, **kwargs)

        replaced = []
        for module in list(sys.modules.values()):
            if module is not None and getattr(module, "source_digest", None) is original_hash:
                replaced.append(module)
                module.source_digest = counted_hash
        pymupdf.open = counted_open
        try:
            loaded = load_book(book)
            iterator = loaded[1].extract_pages(source)
            next(iterator)
            iterator.close()
        finally:
            pymupdf.open = original_open
            for module in list(sys.modules.values()):
                if module is not None and getattr(module, "source_digest", None) is counted_hash:
                    module.source_digest = original_hash
        results[book] = counts
        print(book, counts, flush=True)
    (OUT / "before/source_reads.json").write_text(json.dumps(results, indent=2) + "\n", "utf8")


if __name__ == "__main__":
    main()
