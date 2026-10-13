"""Comparable cached-output load profiles. No extraction or accuracy scoring is performed."""

import argparse
import gc
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("label", choices=["before", "after"])
args = parser.parse_args()
sys.path.insert(
    0, str(ROOT / (".cache/step11c/baseline_src" if args.label == "before" else "backend/src"))
)
import book_core  # noqa: E402, F401

sys.path.insert(0, str(ROOT / "experiments"))
from step11c_identity import BOOKS, OUT  # noqa: E402


def main():
    from book_core.furniture.cache import BookDecisions
    from book_core.furniture.models import PageFurniture
    from book_core.layout.models import PageLayout
    from book_core.lists.cache import BookListsResult
    from book_core.lists.keys import book_fingerprint
    from book_core.lists.models import PageLists
    from book_core.objects.analysis import verified_read
    from book_core.objects.models import NativeObjectPage, ObjectAnalysis
    from book_core.paragraphs.cache import BookParagraphResult
    from book_core.paragraphs.models import PageParagraphs
    from book_core.reading_order.models import PageReadingOrder
    from book_core.structure.evidence import _read
    from book_core.structure.models import BookStructure
    from book_core.telemetry import measure

    results = {}
    for book in BOOKS:
        manifest = json.loads((OUT / args.label / f"{book}.json").read_text("utf8"))
        keys = manifest["keys"]
        entries = {}
        for stage, model in (("layout", PageLayout), ("reading_order", PageReadingOrder)):
            root = ROOT / manifest["cache_root"] / stage / keys[stage]
            entries[stage] = [(p, model, keys[stage]) for p in sorted(root.glob("*.json"))]
        for stage, prefix, page_model, book_model, key in (
            ("furniture", "step8", PageFurniture, BookDecisions, keys["furniture"]),
            ("paragraphs", "step9", PageParagraphs, BookParagraphResult, keys["paragraphs"]),
            ("lists", "step11", PageLists, BookListsResult, book_fingerprint(keys["lists"])),
        ):
            root = ROOT / ".cache" / prefix / stage
            entries[stage] = [(root / "book" / f"{key}.json", book_model, key)]
            # Page cache fingerprints differ from the enclosing book key after Step 8.
            for path in sorted((root / "page" / key).glob("*.json")):
                from book_core.extraction.fingerprints import stable_id

                page_key = key if stage == "furniture" else stable_id(key, "page", int(path.stem))
                entries[stage].append((path, page_model, page_key))
        key = keys["lists"]["structure_decision_key"]
        entries["structure"] = [
            (ROOT / ".cache/step10/structure/book" / f"{key}.json", BookStructure, key)
        ]
        for stage, model in (("native", NativeObjectPage), ("analysis", ObjectAnalysis)):
            root = ROOT / manifest["cache_root"] / stage / keys[stage]
            entries[stage] = [(p, model, keys[stage]) for p in sorted(root.glob("*.json"))]
        stats = {}
        for stage, files in entries.items():
            gc.collect()
            with measure(stats, stage):
                for path, model, key in files:
                    value = verified_read(path, model, key)
                    del value
            size = sum(p.stat().st_size for p, _, _ in files)
            stats[stage].update(
                cache_bytes=size,
                cache_bytes_per_page=size / len(manifest["pages"]),
                source_reads=0,
                source_hashes=0,
            )
            print(book, stage, round(stats[stage]["wall_seconds"], 2), flush=True)
        key = keys["structure_evidence"]
        path = ROOT / ".cache/step10/structure/evidence" / f"{key}.json.gz"
        with measure(stats, "structure_evidence"):
            value = _read(path, key)
            del value
        stats["structure_evidence"].update(
            cache_bytes=path.stat().st_size,
            cache_bytes_per_page=path.stat().st_size / len(manifest["pages"]),
            source_reads=0,
            source_hashes=0,
        )
        results[book] = stats
        target = OUT / args.label / "cached_reads.json"
        target.write_text(json.dumps(results, indent=2) + "\n", "utf8")


if __name__ == "__main__":
    main()
