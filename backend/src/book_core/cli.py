"""CLI for extraction evidence and token-ledger gates only."""

import argparse
import json
from pathlib import Path

from book_core.evaluation.cached_benchmark import CachedBenchmark
from book_core.extraction.cache import CachedExtractor
from book_core.extraction.interfaces import Extractor
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.ledger.accounting import check


def ledger_check(
    source: Path, extractor: Extractor, expected: CachedBenchmark | None = None
) -> dict:
    totals = {
        "pages": 0,
        "source_line_count": 0,
        "excluded_line_count": 0,
        "retained_line_count": 0,
        "source_token_count": 0,
        "retained_token_count": 0,
        "node_token_count": 0,
        "discard_token_count": 0,
        "missing_token_count": 0,
        "extra_token_count": 0,
        "retained_missing_token_count": 0,
        "retained_extra_token_count": 0,
        "expected_missing_token_count": 0,
        "expected_extra_token_count": 0,
    }
    failures: list[dict] = []
    for page in extractor.extract_pages(source):
        if expected is not None and expected.source_sha256 != page.source_sha256:
            raise ValueError("Benchmark source fingerprint does not match the input PDF")
        document, ledger = provision_page(page)
        baseline = expected.expected_page(page.geometry.page) if expected is not None else None
        result = check(document, ledger, baseline)
        totals["pages"] += 1
        for key in totals.keys() - {"pages"}:
            totals[key] += getattr(result, key) or 0
        if not result.passing:
            failures.append({"page": page.geometry.page, **result.model_dump()})
    return {
        **totals,
        "passing": not failures,
        "external_benchmark_checked": expected is not None,
        "order_checked": False,
        "semantic_structure_checked": False,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    gate = subparsers.add_parser("ledger-check")
    gate.add_argument("source", type=Path)
    gate.add_argument("--cache-dir", required=True, type=Path)
    gate.add_argument("--expected-cache", type=Path)
    gate.add_argument("--report", type=Path)
    overlay = subparsers.add_parser("overlay")
    overlay.add_argument("source", type=Path)
    overlay.add_argument("--page", required=True, type=int)
    overlay.add_argument("--out", required=True, type=Path)
    overlay.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    overlay.add_argument("--cache-dir", type=Path, default=Path(".cache/objects"))
    overlay.add_argument("--all-objects", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "overlay":
        from book_core.debug.overlay import render_overlay
        from book_core.objects.analysis import analyze_page, cached_repetition

        backend = PyMuPDFExtractor(device=args.device)
        repetitions = cached_repetition(args.source, backend, args.cache_dir)
        analysis = analyze_page(args.source, args.page, backend, repetitions, args.cache_dir)
        result = render_overlay(
            backend.render_page(args.source, args.page), analysis, args.out, args.all_objects
        )
        result["resolved_device"] = backend.device.resolved
        result["device_fallback_reason"] = backend.device.fallback_reason
        print(json.dumps(result, indent=2))
        return 0
    extractor = CachedExtractor(PyMuPDFExtractor(), args.cache_dir)
    benchmark = CachedBenchmark(args.expected_cache) if args.expected_cache else None
    result = ledger_check(args.source, extractor, benchmark)
    result["cache_hits"] = extractor.cache_hits
    result["cache_misses"] = extractor.cache_misses
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if result["passing"] else 1
