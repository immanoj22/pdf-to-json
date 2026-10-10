"""Fill the Step 9 paragraph cache under the current paragraph producer (no evaluation).

The Step 9 paragraph producer changed after the Step 9 hold-out runs by a logged,
comment-only edit (identical syntax tree; experiments/out/step9/holdout_runs.jsonl). Its cache
key therefore changed. This runs the unchanged Step 9 stage code to fill the cache for one
book; it computes no Step 9 metric and makes no hold-out run. Step 10's gate then compares
every page with the frozen Step 9 run's cached pages (units, joins and order).

Usage: python step10_fill_paragraphs.py --book immigrant_children
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from step7_layouts import BOOKS  # noqa: E402
from step10_run import OUT  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=sorted(BOOKS))
    args = parser.parse_args()
    from reference_paths import reference_path
    from step7_layouts import CACHE
    from step8_run import CACHE8, step6_artifact, vocabulary_for
    from step9_run import CACHE9, navigation_map

    from book_core.document_analysis.metadata import cached_metadata
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.furniture.cache import load_book_furniture
    from book_core.furniture.inputs import PageInputs
    from book_core.objects.analysis import cached_repetition
    from book_core.paragraphs.cache import LOADED_DIGEST, analyze_book_paragraphs

    key, _ = BOOKS[args.book]
    source = reference_path(key)
    extractor = PyMuPDFExtractor(device="cpu")
    inputs = PageInputs(source, extractor, cached_repetition(source, extractor, CACHE), CACHE,
                        vocabulary_for(args.book))  # fmt: skip
    furniture, furniture_key = load_book_furniture(
        inputs, cached_metadata(source, extractor, CACHE8 / "metadata"), CACHE8
    )
    artifact, _ = step6_artifact(inputs.digest)
    _, hit = analyze_book_paragraphs(
        lambda: extractor.extract_pages(source), inputs, furniture, furniture_key, CACHE8,
        navigation_map(artifact), CACHE9,
    )  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "paragraph_cache_fill.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "book": args.book,
                    "paragraphs_producer_sha256": LOADED_DIGEST,
                    "cache_hit": hit,
                    "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "note": "cache fill only; no Step 9 metric computed",
                }
            )
            + "\n"
        )
    print(args.book, "cache hit" if hit else "filled")


if __name__ == "__main__":
    main()
