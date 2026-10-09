"""Step 7: reading order for every page of one approved book, evaluated against derived gold.

Steps: Step 6 vocabulary rule over the book's pages (continuation evidence) -> cached reading
order per page (unchanged Step 4 layouts) -> invariants (every line exactly once, graph chains)
-> derived-gold reading-order metric (main flow and float anchors separately) -> cross-page
continuation candidates -> low-confidence decision list. Hold-out books need --holdout and run
once; each hold-out run is appended to experiments/out/step7/holdout_runs.jsonl.

Usage: python step7_run.py --book spanish_us_history [--workers 6] [--holdout --reason "..."]
"""

import argparse
import gzip
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402
from step7_layouts import BOOKS, CACHE, _pages  # noqa: E402

OUT = ROOT / "experiments/out/step7"
GOLD = ROOT / "backend/tests/gold_derived"


def _vocabulary(source, pages):
    """Casefolded Step 6 vocabulary counts for some pages (the caller sums them over the book).

    build_vocabulary's frequencies are per-line sums, so per-page counts add up exactly.
    """
    from book_core.document_analysis.vocabulary import build_vocabulary
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.layout.pipeline import analyze_layout
    from book_core.objects.analysis import cached_repetition

    extractor = PyMuPDFExtractor(device="cpu")
    repetition = cached_repetition(source, extractor, CACHE)
    counts = Counter()
    for page in pages:
        native = analyze_layout(source, page, extractor, repetition, CACHE)[1].native.page
        counts.update(build_vocabulary([native])["casefold_frequencies"])
    return counts


def _order_pages(source, pages, vocabulary):
    from book_core.evaluation.reading_order import page_order
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.objects.analysis import cached_repetition
    from book_core.reading_order.cache import analyze_reading_order
    from book_core.reading_order.graph import check

    extractor = PyMuPDFExtractor(device="cpu")
    repetition = cached_repetition(source, extractor, CACHE)
    rows = []
    for number in pages:
        order, layout, analysis = analyze_reading_order(
            source, number, extractor, repetition, CACHE, vocabulary
        )
        page = analysis.native.page
        view, _ = page_order(page, layout, order)
        store = page.store
        lines = {line.id: line for line in layout.lines}
        regions = {lid: r.type for r in layout.regions for lid in r.line_ids}

        def text(lid, store=store, lines=lines):
            return "".join(store.spans[s].raw_text for s in lines[lid].span_ids)

        main = order.main.line_ids
        rows.append(
            {
                "page": number,
                "problems": check(order, layout),
                "lines": len(layout.lines),
                "view": view,
                "streams": Counter(s.kind for s in order.streams),
                "stream_lines": Counter(s.kind for s in order.streams for _ in s.line_ids),
                "edges": Counter(e.kind for e in order.edges),
                "decisions": [
                    {
                        "kind": d.kind,
                        "choice": d.choice,
                        "confidence": d.confidence,
                        "reasons": d.reasons,
                        "subjects": d.subject_ids,
                        "text": text(d.subject_ids[0])[:80] if d.subject_ids[0] in lines else None,
                    }
                    for d in order.decisions
                    if d.review_required
                ],
                "decision_counts": Counter(d.kind for d in order.decisions),
                "first": (text(main[0]), regions[main[0]]) if main else None,
                "last": (text(main[-1]), regions[main[-1]], main[-1]) if main else None,
                "first_id": main[0] if main else None,
                "digest": None,
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=sorted(BOOKS))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--reason", default="")
    parser.add_argument(
        "--vocabulary", type=Path, help="reuse saved casefold counts (same Step 6 rule) by path"
    )
    args = parser.parse_args()
    from book_core.caching import code_digest
    from book_core.evaluation.derived_harness import DerivedGold, evaluate
    from book_core.evaluation.reading_order import ReadingOrderOutput
    from book_core.reading_order.cache import vocabulary_digest
    from book_core.reading_order.continuation import continuation
    from book_core.reference.pdf_tokens import page_tokens  # noqa: F401

    key, split = BOOKS[args.book]
    if split == "holdout" and not args.holdout:
        raise SystemExit("Hold-out book: pass --holdout --reason (runs once, after freezing)")
    started = time.perf_counter()
    source = reference_path(key)
    total = _pages(source)
    chunks = [list(range(s, total + 1, args.workers)) for s in range(1, args.workers + 1)]
    with ProcessPoolExecutor(args.workers) as pool:
        if args.vocabulary:
            vocabulary = json.loads(args.vocabulary.read_text("utf-8"))
        else:
            parts = pool.map(_vocabulary, [source] * len(chunks), chunks)
            vocabulary = dict(sum(parts, Counter()))
            (CACHE / f"step7_vocabulary_{args.book}.json").write_text(
                json.dumps(vocabulary, ensure_ascii=False), "utf-8"
            )
        print(
            f"vocabulary {len(vocabulary)} forms, {time.perf_counter() - started:.0f}s",
            flush=True,
        )
        rows = [
            r
            for part in pool.map(
                _order_pages, [source] * len(chunks), chunks, [vocabulary] * len(chunks)
            )
            for r in part
        ]
    rows.sort(key=lambda r: r["page"])
    gold = DerivedGold.load(GOLD / args.book)
    digests = {row["page"]: row["token_digest"] for row in gold.pages}
    owners = {
        r["page"]: [r["view"].stream_of.get(i) for i in range(len(r["view"].stream_of))]
        for r in rows
    }
    output = ReadingOrderOutput(
        "reading_order",
        args.book,
        owners,
        digests,
        {r["page"]: r["view"] for r in rows},
    )
    report = evaluate([gold], {args.book: output}, include_holdout=args.holdout)
    book_report = report["books"][args.book]
    cross = []
    for previous, following in zip(rows, rows[1:], strict=False):
        if previous["last"] is None or following["first"] is None:
            continue
        evidence = continuation(
            previous["last"][0],
            following["first"][0],
            previous_type=previous["last"][1],
            following_type=following["first"][1],
            vocabulary=vocabulary,
        )
        cross.append(
            {
                "kind": "continues_across_page",
                "candidate": True,
                "from_page": previous["page"],
                "to_page": following["page"],
                "source_line": previous["last"][2],
                "target_line": following["first_id"],
                "score": evidence.score,
                "verdict": evidence.verdict,
                "reasons": evidence.reasons,
            }
        )
    low = [{"page": r["page"], **d} for r in rows for d in r["decisions"]]
    summary = {
        "book": args.book,
        "split": split,
        "pages": total,
        "producer_sha256": code_digest("reading_order"),
        "vocabulary_sha256": vocabulary_digest(vocabulary),
        "invariant_problems": {r["page"]: r["problems"] for r in rows if r["problems"]},
        "lines": sum(r["lines"] for r in rows),
        "lines_ordered": sum(sum(r["stream_lines"].values()) for r in rows),
        "streams": dict(sum((r["streams"] for r in rows), Counter())),
        "stream_lines": dict(sum((r["stream_lines"] for r in rows), Counter())),
        "edges": dict(sum((r["edges"] for r in rows), Counter())),
        "decisions": dict(sum((r["decision_counts"] for r in rows), Counter())),
        "low_confidence": len(low),
        "low_confidence_by_kind": dict(Counter(d["kind"] for d in low)),
        "cross_page_candidates": dict(Counter(c["verdict"] for c in cross)),
        "seconds": round(time.perf_counter() - started, 1),
        "evaluation": {k: v for k, v in book_report.items() if k != "reading_order"},
        "reading_order": {
            k: v
            for k, v in book_report.get("reading_order", {}).items()
            if k not in {"per_page", "anchor_misses"}
        },
    }
    target = OUT / args.book
    target.mkdir(parents=True, exist_ok=True)
    (target / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    detail = book_report.get("reading_order", {})
    (target / "per_page.json").write_text(
        json.dumps(detail.get("per_page", {}), indent=0) + "\n", "utf-8"
    )
    (target / "anchor_misses.json").write_text(
        json.dumps(detail.get("anchor_misses", []), indent=0) + "\n", "utf-8"
    )
    with gzip.open(target / "low_confidence.jsonl.gz", "wt", encoding="utf-8") as handle:
        for row in low:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (target / "cross_page_candidates.json").write_text(
        json.dumps(cross, indent=0, ensure_ascii=False) + "\n", "utf-8"
    )
    if split == "holdout":
        with (OUT / "holdout_runs.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "book": args.book,
                        "producer_sha256": summary["producer_sha256"],
                        "reason": args.reason,
                        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                )
                + "\n"
            )
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "lines",
                    "lines_ordered",
                    "low_confidence",
                    "invariant_problems",
                    "seconds",
                )
            },
            indent=1,
        )
    )
    print(json.dumps(summary["reading_order"], indent=1))


if __name__ == "__main__":
    main()
