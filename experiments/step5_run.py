"""Step 5: align an approved reference pair and report coverage (read-only on all sources).

Hold-out discipline: only the development book may be run freely. A hold-out book runs only
with --holdout, and each such run is appended to experiments/out/step5/holdout_runs.jsonl
together with the alignment producer digest, so later aligner changes can be audited.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter

from reference_paths import PROJECT_ROOT, reference_path

from book_core.caching import code_digest
from book_core.extraction.cache import CachedExtractor
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.reference.cache import align_cached
from book_core.reference.dialects import load_dialects
from book_core.settings import Settings

OUT = PROJECT_ROOT / "experiments/out/step5"
CACHE = PROJECT_ROOT / ".cache/step5"
DIALECTS = Settings().reference_dialects
BOOKS = {
    "spanish_us_history": {
        "pdf": "spanish_pdf",
        "xml": "spanish_xml",
        "split": "development",
        "xml_sha256": "a16f3ed0646e1923ebf02109a977fa78fabd06858d943703765947abe09a89f5",
        "pdf_sha256": "de9d916687ecbe556f7a01f1d871048ec89f362ae5c4b399bd08098b1fddc951",
        "notes": [],
    },
    "immigrant_children": {
        "pdf": "small_pdf",
        "xml": "immigrant_xml",
        "split": "holdout",
        "xml_sha256": "b8be7a91bcf2385a4f0415e4cef84cd0534bc547373d4ea3e3f7405e59ab6acd",
        "pdf_sha256": "4825a40c9905048df0cee7eb173802438e5c7b71fe2d768255dc09314baa593f",
        "notes": ["identity by text only (XML lists no web-PDF ISBN)"],
    },
    "art_therapy_index": {
        "pdf": "art_index_pdf",
        "xml": "art_index_xml",
        "split": "holdout",
        "xml_sha256": "6313f7705615bd431812acfec93cdca0a2d6ea0b2a5acad9e843fd4659b18d3f",
        "pdf_sha256": "d13497d3d53938a07e29963e48d96c0d25ae83d09db3fef534c3a013e5952525",
        "notes": ["9 pages: anecdotal", "page markers low confidence; excluded from gates"],
    },
}


def summarize(book, doc, pages, result, seconds) -> dict:
    pdf_total = sum(len(p.tokens) for p in pages)
    pdf_aligned = sum(1 for row in result.pdf_xml for x in row if x >= 0)
    xml_total = len(doc.tokens)
    xml_aligned = sum(1 for p in result.xml_page if p >= 0)
    pdf_causes = Counter(c for row in result.pdf_cause for c in row if c)
    xml_causes = Counter(c for c in result.xml_cause if c)
    methods = Counter(m for m in result.xml_method if m)
    pairs = zip(result.xml_confidence, result.xml_page, strict=True)
    confidence = sorted(c for c, p in pairs if p >= 0)
    segments = result.segments
    jumps = []
    previous = None
    for segment in segments:
        if not segment["count"] or segment["page"] is None:
            continue
        if previous is not None and segment["page"] not in (previous["page"], previous["page"] + 1):
            jumps.append(
                {
                    "after_label": previous["label"],
                    "after_page": previous["page"],
                    "label": segment["label"],
                    "page": segment["page"],
                    "containment": segment["containment"],
                    "tokens": segment["count"],
                }
            )
        previous = segment
    located = [s for s in segments if s["count"]]
    return {
        "book": book,
        "split": BOOKS[book]["split"],
        "notes": BOOKS[book]["notes"],
        "dialect": doc.dialect.name,
        "repairs": result.repairs,
        "pdf_pages": len(pages),
        "pdf_tokens": pdf_total,
        "pdf_aligned": pdf_aligned,
        "pdf_aligned_fraction": round(pdf_aligned / max(pdf_total, 1), 4),
        "pdf_unaligned_by_cause": dict(pdf_causes.most_common()),
        "xml_tokens": xml_total,
        "xml_aligned": xml_aligned,
        "xml_aligned_fraction": round(xml_aligned / max(xml_total, 1), 4),
        "xml_unaligned_by_cause": dict(xml_causes.most_common()),
        "methods": dict(methods.most_common()),
        "extra_links": len(result.extra_links),
        "refused_links": result.refused_links,
        "confidence_quartiles": [
            confidence[int(q * (len(confidence) - 1))] for q in (0, 0.25, 0.5, 0.75, 1)
        ]
        if confidence
        else [],
        "segments": len(segments),
        "segments_with_tokens": len(located),
        "segments_located": sum(1 for s in located if s["located"]),
        "placement_jumps": jumps,
        "alignment_producer_sha256": code_digest("alignment"),
        "seconds": round(seconds, 1),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=sorted(BOOKS), required=True)
    parser.add_argument("--holdout", action="store_true", help="explicitly run a hold-out book")
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--reason", default="initial run", help="recorded in the hold-out log")
    args = parser.parse_args(argv)
    spec = BOOKS[args.book]
    if spec["split"] == "holdout" and not args.holdout:
        parser.error(f"{args.book} is a hold-out book; pass --holdout to run it")
    pdf, xml = reference_path(spec["pdf"]), reference_path(spec["xml"])
    for path, key in ((pdf, "pdf_sha256"), (xml, "xml_sha256")):
        if source_digest(path) != spec[key]:
            raise SystemExit(f"{path}: SHA-256 differs from the approved reference pair")
    extractor = CachedExtractor(PyMuPDFExtractor("cpu"), CACHE / "native")
    objects = None if args.no_figures else PyMuPDFExtractor("cpu")
    start = time.perf_counter()
    dialects = load_dialects(DIALECTS)
    doc, pages, result = align_cached(
        xml, pdf, extractor, dialects, CACHE, object_extractor=objects
    )
    summary = summarize(args.book, doc, pages, result, time.perf_counter() - start)
    out = OUT / args.book
    out.mkdir(parents=True, exist_ok=True)
    (out / "alignment_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", "utf-8"
    )
    if spec["split"] == "holdout":
        with (OUT / "holdout_runs.jsonl").open("a", encoding="utf-8") as log:
            record = {
                "book": args.book,
                "reason": args.reason,
                "alignment_producer_sha256": summary["alignment_producer_sha256"],
                "pdf_aligned_fraction": summary["pdf_aligned_fraction"],
                "xml_aligned_fraction": summary["xml_aligned_fraction"],
            }
            log.write(json.dumps(record) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "placement_jumps"}, indent=1))
    print("jumps:", len(summary["placement_jumps"]))
    for jump in summary["placement_jumps"][:30]:
        print("  ", jump)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
