"""Book-1 language evidence only, from verified historical native caches.

No extraction, reference evaluation, hold-out inference, or Step 6 output writes. A missing
or corrupt cache fails closed rather than triggering a PDF parser. Model confidence is
conditional on configured candidates and is not a calibrated correctness probability.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime

from reference_paths import PROJECT_ROOT, reference_path

from book_core.caching import runtime_versions
from book_core.document_analysis.cache import (
    DocumentConfig,
    book_language_threshold,
    load_artifact,
)
from book_core.document_analysis.language import LinguaLanguageDetector, language_evidence
from book_core.extraction.cache import atomic_json, payload_digest
from book_core.extraction.fingerprints import source_digest
from book_core.model.spans import ExtractedPage
from book_core.settings import Settings

BOOK = "spanish_us_history"
OUT = PROJECT_ROOT / "experiments/out/step6b/language"
ARTIFACT_CACHE = PROJECT_ROOT / ".cache/step6b/language"
CACHE = PROJECT_ROOT / ".cache/step6"
PRODUCERS = (
    "backend/src/book_core/document_analysis/language.py",
    "backend/src/book_core/document_analysis/cache.py",
    "backend/src/book_core/settings.py",
    "experiments/step6b_language.py",
)


def _producer() -> dict:
    return {name: source_digest(PROJECT_ROOT / name) for name in PRODUCERS}


def _historical_inputs(previous: dict) -> tuple[list[ExtractedPage], list[dict], dict]:
    """Match the exact earlier input digests, not the current producer namespace."""
    provenance = previous["provenance"]
    manifests = []
    for path in (CACHE / "native").glob("*/manifest.json"):
        manifest = json.loads(path.read_text("utf-8"))
        if (
            manifest["source_sha256"] == provenance["source_sha256"]
            and manifest["extractor"] == provenance["extractor"]
            and payload_digest({"pages": manifest["page_hashes"]}) == provenance["pages_sha256"]
        ):
            manifests.append((path, manifest))
    if not manifests:
        raise ValueError("No historical native cache matches the original Step 6 inputs")
    path, manifest = sorted(manifests, key=lambda item: str(item[0]))[0]
    pages = []
    for number, digest in enumerate(manifest["page_hashes"], 1):
        entry = json.loads((path.parent / f"page_{number:06d}.json").read_text("utf-8"))
        if entry["payload_sha256"] != digest or payload_digest(entry["payload"]) != digest:
            raise ValueError("Corrupt historical native page cache")
        page = ExtractedPage.model_validate(entry["payload"])
        if (
            page.source_sha256 != provenance["source_sha256"]
            or page.extractor.model_dump(mode="json") != provenance["extractor"]
            or page.geometry.page != number
        ):
            raise ValueError("Historical native page source/configuration mismatch")
        pages.append(page)
    if (
        payload_digest({"pages": [payload_digest(p.model_dump(mode="json")) for p in pages]})
        != provenance["pages_sha256"]
    ):
        raise ValueError("Historical page serialization differs from original evidence")
    metadata_matches = []
    for target in (CACHE / "metadata").glob("*.json"):
        entry = json.loads(target.read_text("utf-8"))
        if entry.get("payload_sha256") != provenance["metadata_sha256"]:
            continue
        if payload_digest(entry["payload"]) != entry["payload_sha256"]:
            raise ValueError("Corrupt historical metadata cache")
        if payload_digest(entry["provenance"]) != target.stem:
            raise ValueError("Historical metadata cache key differs")
        metadata_matches.append((target, entry))
    if not metadata_matches:
        raise ValueError("No metadata cache matches original Step 6 input")
    metadata_path, metadata_entry = sorted(metadata_matches, key=lambda item: str(item[0]))[0]
    metadata = metadata_entry["payload"]
    blocks = metadata["native_blocks"]
    if (
        metadata["source_sha256"] != provenance["source_sha256"]
        or metadata["extractor"] != provenance["extractor"]
        or metadata["page_count"] != len(pages)
        or payload_digest({"blocks": blocks}) != provenance["native_blocks_sha256"]
    ):
        raise ValueError("Historical metadata/native-block mismatch")
    return (
        pages,
        blocks,
        {
            "native_manifest": path.relative_to(PROJECT_ROOT).as_posix(),
            "native_manifest_sha256": source_digest(path),
            "metadata_artifact": metadata_path.relative_to(PROJECT_ROOT).as_posix(),
            "metadata_provenance": metadata_entry["provenance"],
            "pages_sha256": provenance["pages_sha256"],
            "metadata_sha256": provenance["metadata_sha256"],
            "native_blocks_sha256": provenance["native_blocks_sha256"],
        },
    )


def _summary(evidence: dict) -> dict:
    blocks = evidence["blocks"]
    return {
        "blocks": len(blocks),
        "languages": dict(sorted(Counter(row["language"] for row in blocks).items())),
        "unknown": sum(row["language"] == "und" for row in blocks),
        "mixed_segment_evidence": sum(row["mixed"] for row in blocks),
        "reasons": dict(sorted(Counter(row["reason"] for row in blocks).items())),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--add-language", action="append", default=[])
    parser.add_argument("--minimum-letter-median-fraction", type=float, default=0.25)
    parser.add_argument("--minimum-letters", type=int, default=10)
    args = parser.parse_args(argv)
    settings = Settings()
    config = DocumentConfig.from_settings(
        settings,
        additional_languages=args.add_language,
        minimum_letters=args.minimum_letters,
        minimum_letter_median_fraction=args.minimum_letter_median_fraction,
    )
    previous_summary_path = PROJECT_ROOT / "experiments/out/step6" / BOOK / "summary.json"
    previous_summary = json.loads(previous_summary_path.read_text("utf-8"))
    previous_path = PROJECT_ROOT / previous_summary["artifact"]
    previous = load_artifact(previous_path)
    if (
        previous_summary["book"] != BOOK
        or previous["provenance"]["source_sha256"] != previous_summary["source_sha256"]
        or payload_digest(previous) != previous_summary["artifact_payload_sha256"]
    ):
        raise ValueError("Original Step 6 book-1 evidence does not verify")
    source = reference_path("spanish_pdf")
    if source_digest(source) != previous_summary["source_sha256"]:
        raise ValueError("Book-1 source differs from original verified evidence")
    start = time.perf_counter()
    print("Verifying historical book-1 native page and metadata caches", flush=True)
    pages, blocks, inputs = _historical_inputs(previous)
    threshold = book_language_threshold(pages, blocks, config)
    detector = LinguaLanguageDetector(
        config.language_candidates,
        minimum_letters=threshold["resolved_minimum_letters"],
        confidence_floor=config.language_confidence_floor,
        margin_floor=config.language_margin_floor,
    )
    producer_files = _producer()
    provenance = {
        "version": "step6b-native-block-language-1",
        "source_sha256": previous_summary["source_sha256"],
        "extractor": previous["provenance"]["extractor"],
        "inputs": inputs,
        "previous_document_artifact": previous_path.relative_to(PROJECT_ROOT).as_posix(),
        "previous_document_payload_sha256": payload_digest(previous),
        "previous_language_sha256": payload_digest(previous["language"]),
        "settings_ocr_languages": settings.ocr_languages,
        "explicit_added_languages": args.add_language,
        "configuration": asdict(config),
        "threshold": threshold,
        "config_sha256": payload_digest({"config": asdict(config), "threshold": threshold}),
        "producer_files": producer_files,
        "producer_sha256": payload_digest(producer_files),
        "detector": detector.identity,
        "model_sha256": detector.identity["model"]["sha256"],
        "runtime": runtime_versions(),
        "execution_device": "cpu",
        "scope": "all native extraction blocks, including explicit TrimBox-excluded evidence",
    }
    key = payload_digest(provenance)
    target = ARTIFACT_CACHE / f"{key}.json"
    if target.exists():
        raise ValueError(
            "This language configuration already has a Step 6b artifact; refusing overwrite"
        )
    print(
        "Running restricted language evidence only",
        len(blocks),
        "native blocks",
        threshold,
        flush=True,
    )
    evidence = language_evidence(pages, blocks, detector)
    evidence["minimum_letter_evidence"] = threshold
    old_rows = {row["block_id"]: row for row in previous["language"]["blocks"]}
    if set(old_rows) != {row["block_id"] for row in evidence["blocks"]}:
        raise ValueError("Language evidence native block identities differ")
    for row in evidence["blocks"]:
        if any(
            row[field] != old_rows[row["block_id"]][field]
            for field in ("text_sha256", "span_ids", "line_ids", "letter_count")
        ):
            raise ValueError("Native text evidence changed")
    comparison = {
        "before": _summary(previous["language"]),
        "after": _summary(evidence),
        "language_transitions": dict(
            sorted(
                Counter(
                    f"{old_rows[row['block_id']]['language']}->{row['language']}"
                    for row in evidence["blocks"]
                ).items()
            )
        ),
        "counts_are_accuracy": False,
        "note": (
            "Restricted candidate-set evidence; not a calibrated accuracy improvement. "
            "No gold evaluation."
        ),
    }
    if _producer() != producer_files:
        raise RuntimeError("Language producer changed during execution; restart the worker")
    if source_digest(source) != previous_summary["source_sha256"]:
        raise ValueError("Book-1 source changed during execution")
    payload = {"provenance": provenance, "language": evidence, "comparison": comparison}
    atomic_json(target, {"key": key, "payload": payload, "payload_sha256": payload_digest(payload)})
    summary = {
        "book": BOOK,
        "scope": "book-1 language-only; verified historical caches; no hold-outs or other analysis",
        "utc": datetime.now(UTC).isoformat(),
        "artifact": target.relative_to(PROJECT_ROOT).as_posix(),
        "key": key,
        "payload_sha256": payload_digest(payload),
        "seconds": round(time.perf_counter() - start, 3),
        "pages": len(pages),
        "native_cache_hits": len(pages),
        "native_cache_misses": 0,
        "threshold": threshold,
        "comparison": comparison,
    }
    atomic_json(OUT / "summary.json", summary)
    with (OUT / "runs.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(summary, ensure_ascii=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    main()
