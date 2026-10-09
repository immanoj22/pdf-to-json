"""Step 6: whole-book evidence; development first, hold-outs exactly once after freezing."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from reference_paths import PROJECT_ROOT, reference_path
from step5_run import BOOKS

from book_core.caching import code_digest
from book_core.debug.document_overlay import render_document_overlay
from book_core.document_analysis.cache import DocumentConfig, analyze_book_cached
from book_core.document_analysis.metadata import cached_metadata
from book_core.evaluation.derived_harness import DerivedGold
from book_core.evaluation.document_evidence import evaluate_document
from book_core.extraction.cache import CachedExtractor, atomic_json, payload_digest
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.reference.dialects import load_dialects
from book_core.reference.xml_reader import read_reference
from book_core.settings import Settings

OUT = PROJECT_ROOT / "experiments/out/step6"
CACHE = PROJECT_ROOT / ".cache/step6"


def log_run(row):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "holdout_runs.jsonl").open("a", encoding="utf8", newline="\n") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
        stream.flush()


def reference_titles(spec, gold):
    dialects = load_dialects(Settings().reference_dialects)
    if dialects.digest != gold.manifest["provenance"]["dialect_profiles_sha256"]:
        raise ValueError("Reference dialect profile differs from committed gold")
    doc = read_reference(reference_path(spec["xml"]).read_bytes(), dialects)
    if doc.sha256 != gold.manifest["provenance"]["xml_sha256"]:
        raise ValueError("Reference source hash changed")
    order = list(dict.fromkeys(doc.units))
    tokens = defaultdict(list)
    for token, unit in zip(doc.tokens, doc.units, strict=True):
        tokens[unit].append(token.value)
    if len(order) != len(gold.units):
        raise ValueError("Reference units differ from committed gold")
    if any(doc.elements[order[row["unit"]]].path != row["path"] for row in gold.units):
        raise ValueError("Reference unit paths differ from committed gold")
    return {
        row["unit"]: " ".join(tokens[order[row["unit"]]])
        for row in gold.units
        if row["kind"] == "heading"
    }


def sample_pages(evidence, count=5):
    selected = [r["page"] for r in evidence["navigation"]["toc_pages"][:2]]
    repetitions = Counter(
        r["page"] for c in evidence["repetition"]["candidates"] for r in c["occurrences"]
    )
    selected.extend(p for p, _ in repetitions.most_common(2))
    styles = defaultdict(set)
    for row in evidence["style"]["lines"]:
        styles[row["page"]].add(row["style_cluster_id"])
    selected.extend(sorted(styles, key=lambda p: (-len(styles[p]), p)))
    return list(dict.fromkeys(selected))[:count]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=sorted(BOOKS), required=True)
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--reason", default="frozen Step 6 final hold-out evaluation")
    parser.add_argument("--overlay-pages", nargs="*", type=int)
    parser.add_argument("--overlays", action="store_true")
    args = parser.parse_args(argv)
    spec = BOOKS[args.book]
    holdout = spec["split"] == "holdout"
    if holdout and not args.holdout:
        parser.error("Hold-out extraction requires --holdout, checked before reading a source")
    log_path = OUT / "holdout_runs.jsonl"
    if holdout and log_path.exists():
        previous = [json.loads(line) for line in log_path.read_text("utf8").splitlines()]
        if any(r["book"] == args.book and r["action"] == "started" for r in previous):
            parser.error("This hold-out has already started its single Step 6 run")
    pdf = reference_path(spec["pdf"])
    if source_digest(pdf) != spec["pdf_sha256"]:
        raise ValueError("Approved PDF source digest changed")
    config = DocumentConfig()
    run_id = uuid.uuid4().hex
    run = {
        "run_id": run_id,
        "book": args.book,
        "reason": args.reason,
        "source_sha256": spec["pdf_sha256"],
        "producer_sha256": code_digest("document"),
        "evaluation_producer_sha256": source_digest(
            PROJECT_ROOT / "backend/src/book_core/evaluation/document_evidence.py"
        ),
        "runner_sha256": source_digest(Path(__file__)),
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "config": {
            "language_candidates": list(config.language_candidates),
            "language_minimum_letters": config.minimum_letters,
            "confidence_floor": config.language_confidence_floor,
            "margin_floor": config.language_margin_floor,
            "repetition": config.repetition.__dict__,
        },
    }
    if holdout:
        log_run({**run, "action": "started"})
    start = time.perf_counter()
    print(args.book, "extracting immutable native pages", flush=True)
    backend = PyMuPDFExtractor("auto")
    extractor = CachedExtractor(backend, CACHE / "native")
    pages = list(extractor.extract_pages(pdf))
    metadata = cached_metadata(pdf, backend, CACHE / "metadata")
    blocks = metadata["native_blocks"]
    print(args.book, "analyzing document evidence", len(pages), "pages", flush=True)
    evidence, artifact, hit = analyze_book_cached(
        pages, metadata, blocks, CACHE / "document", config
    )
    gold = DerivedGold.load(PROJECT_ROOT / "backend/tests/gold_derived" / args.book)
    evaluation = evaluate_document(gold, pages, evidence, reference_titles(spec, gold))
    output = OUT / args.book
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / "evaluation.json", evaluation)
    atomic_json(output / "navigation.json", evidence["navigation"])
    atomic_json(output / "repetition_candidates.json", evidence["repetition"])
    overlays = []
    if args.overlays or args.overlay_pages:
        numbers = args.overlay_pages or sample_pages(evidence)
        by_page = {p.geometry.page: p for p in pages}
        for number in numbers:
            target = output / f"evidence_p{number}.png"
            overlay = render_document_overlay(
                backend.render_page(pdf, number), by_page[number], evidence, target
            )
            atomic_json(target.with_suffix(".json"), overlay)
            overlays.append(str(target.relative_to(PROJECT_ROOT).as_posix()))
    body = next(
        (r for r in evidence["style"]["styles"] if r["key"] == evidence["style"]["body_style_key"]),
        None,
    )
    language = evidence["language"]
    summary = {
        "book": args.book,
        "split": spec["split"],
        "notes": spec["notes"],
        "overall": None,
        "pages": len(pages),
        "retained_tokens": evidence["vocabulary"]["total_tokens"],
        "source_sha256": spec["pdf_sha256"],
        "producer_sha256": evidence["provenance"]["producer_sha256"],
        "artifact": artifact.relative_to(PROJECT_ROOT).as_posix(),
        "artifact_key": artifact.stem,
        "artifact_payload_sha256": payload_digest(evidence),
        "artifact_cache_hit": hit,
        "native_cache_hits": extractor.cache_hits,
        "native_cache_misses": extractor.cache_misses,
        "body_style": body,
        "body_style_confidence": evidence["style"]["body_confidence"],
        "style_keys": len(evidence["style"]["styles"]),
        "size_clusters": len(evidence["style"]["size_clusters"]),
        "style_clusters": len(evidence["style"]["style_clusters"]),
        "bookmarks": len(evidence["navigation"]["bookmarks"]),
        "pdf_page_labels": sum(bool(r["label"]) for r in metadata["page_labels"]),
        "toc_pages": evidence["navigation"]["toc_pages"],
        "printed_entries": len(evidence["navigation"]["printed_entries"]),
        "repetition_candidates": len(evidence["repetition"]["candidates"]),
        "language_blocks": len(language["blocks"]),
        "languages": dict(Counter(row["language"] for row in language["blocks"])),
        "mixed_language_blocks": sum(row["mixed"] for row in language["blocks"]),
        "vocabulary_size": evidence["vocabulary"]["unique_tokens"],
        "hyphen_joins": len(evidence["vocabulary"]["hyphen_joins"]),
        "attested_hyphen_joins": sum(
            row["joined_occurs_elsewhere"] for row in evidence["vocabulary"]["hyphen_joins"]
        ),
        "overlays": overlays,
        "seconds": round(time.perf_counter() - start, 2),
        "resolved_device": backend.device.resolved,
    }
    atomic_json(output / "summary.json", summary)
    if source_digest(pdf) != spec["pdf_sha256"]:
        raise ValueError("PDF changed during analysis")
    if holdout:
        log_run(
            {
                **run,
                "action": "completed",
                "artifact_key": artifact.stem,
                "artifact_payload_sha256": summary["artifact_payload_sha256"],
                "seconds": summary["seconds"],
            }
        )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
