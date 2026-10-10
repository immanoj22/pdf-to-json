"""Step 10: headings, levels and roles, printed navigation and book parts for one book.

Pass 1 (cached evidence) reads every page once; pass 2 (cached decision) decides the whole
book. Evaluation per book against derived gold: heading detection, levels (by gold level
method), role confusion, reference conventions, zones per unit and page, and contents links.
Gates: every line in exactly one unit and ordered once on every page; Step 10 reads the
Step 9 units and order without changing them (same paragraph cache key), so the reading-order
and paragraph metrics are unchanged. Hold-out books need --holdout and run once
(experiments/out/step10/holdout_runs.jsonl).

Usage: python step10_run.py --book spanish_us_history [--holdout --reason "..."]
       python step10_run.py --book spanish_us_history --evidence-only
"""

import argparse
import gzip
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402
from step7_layouts import BOOKS, CACHE  # noqa: E402
from step8_run import CACHE8, step6_artifact, vocabulary_for  # noqa: E402
from step9_run import CACHE9, navigation_map  # noqa: E402

OUT = ROOT / "experiments/out/step10"
CACHE10 = ROOT / ".cache/step10"
GOLD = ROOT / "backend/tests/gold_derived"
OWNER_CASE = ("Authors", "Mapas", "Biografías")


def load_book(book):
    """(source, extractor, inputs, furniture, furniture key, paragraphs, artifact, path)."""
    from book_core.document_analysis.metadata import cached_metadata
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.furniture.cache import load_book_furniture
    from book_core.furniture.inputs import PageInputs
    from book_core.objects.analysis import cached_repetition
    from book_core.paragraphs.cache import analyze_book_paragraphs

    key, _ = BOOKS[book]
    source = reference_path(key)
    extractor = PyMuPDFExtractor(device="cpu")
    inputs = PageInputs(
        source, extractor, cached_repetition(source, extractor, CACHE), CACHE,
        vocabulary_for(book),
    )  # fmt: skip
    metadata = cached_metadata(source, extractor, CACHE8 / "metadata")
    furniture, furniture_key = load_book_furniture(inputs, metadata, CACHE8)
    if furniture is None:
        raise SystemExit("Run the Step 8 furniture stage first (no cached decision)")
    artifact, artifact_path = step6_artifact(inputs.digest)
    paragraphs, hit = analyze_book_paragraphs(
        lambda: extractor.extract_pages(source), inputs, furniture, furniture_key, CACHE8,
        navigation_map(artifact), CACHE9,
    )  # fmt: skip
    if not hit:
        raise SystemExit("Step 9 paragraphs were not cached: run step9_run.py first")
    return source, extractor, inputs, furniture, furniture_key, paragraphs, artifact, artifact_path


def heading_classifier():
    """The book-1 heading classifier with its frozen threshold, or None (rules decide)."""
    from book_core.structure.classifier import DEFAULT_MODEL, load_default

    return load_default(DEFAULT_MODEL)


def evidence_for(book, loaded=None):
    from book_core.structure.evidence import book_evidence

    loaded = loaded or load_book(book)
    source, extractor, inputs, furniture, furniture_key, paragraphs, artifact, _ = loaded
    navigation = artifact["navigation"] if artifact else {}
    return book_evidence(
        lambda: extractor.extract_pages(source), inputs, furniture, furniture_key, CACHE8,
        paragraphs, CACHE9, navigation, CACHE10,
    )  # fmt: skip


def _log(row):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "holdout_runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def frozen_paragraphs(book):
    """The Step 9 paragraph result of the frozen Step 9 run (its summary's key), or None."""
    from book_core.objects.analysis import verified_read
    from book_core.paragraphs.cache import BookParagraphResult
    from book_core.paragraphs.keys import book_fingerprint

    summary = json.loads((ROOT / f"experiments/out/step9/{book}/summary.json").read_text("utf-8"))
    key = book_fingerprint(summary["cache_key_inputs"])
    path = CACHE9 / "paragraphs" / "book" / f"{key}.json"
    return verified_read(path, BookParagraphResult, key) if path.exists() else None


def unit_gate(loaded, structure, book):
    """Every layout line in exactly one Step 9 unit and ordered once; headings name units;
    the Step 9 units, joins and order equal those of the frozen Step 9 run, page by page."""
    from book_core.paragraphs.cache import load_page
    from book_core.paragraphs.models import TEXT_KINDS
    from book_core.reading_order.graph import check

    source, extractor, inputs, _, _, paragraphs, _, _ = loaded
    frozen = frozen_paragraphs(book)
    identical = differing = 0
    problems, lines_total, unit_kinds = {}, 0, {}
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        built = load_page(paragraphs, number, CACHE9)
        layout, _ = inputs(page)
        issues = check(built.order, None)
        lines = [lid for u in built.units for lid in u.line_ids]
        ordered = [lid for s in built.order.streams for lid in s.line_ids]
        expected = {line.id for line in layout.lines}
        if len(lines) != len(set(lines)) or set(lines) != expected:
            issues.append("units do not hold every layout line exactly once")
        if len(ordered) != len(set(ordered)) or set(ordered) != expected:
            issues.append("order does not hold every layout line exactly once")
        if issues:
            problems[number] = issues
        lines_total += len(layout.lines)
        unit_kinds.update({u.id: u.kind for u in built.units})
        if frozen is not None:
            old = load_page(frozen, number, CACHE9)
            same = [u.model_dump() for u in old.units] == [u.model_dump() for u in built.units]
            same = same and old.order.model_dump() == built.order.model_dump()
            identical += same
            differing += not same
    bad = [u for h in structure.headings for u in h.unit_ids
           if unit_kinds.get(u) not in TEXT_KINDS]  # fmt: skip
    bad += [u for h in structure.styled for u in h.unit_ids
            if unit_kinds.get(u) not in TEXT_KINDS]  # fmt: skip
    return {"lines": lines_total, "invariant_problems": problems,
            "heading_units_not_text_units": len(bad),
            "frozen_step9_found": frozen is not None,
            "pages_identical_to_frozen_step9": identical,
            "pages_differing_from_frozen_step9": differing}  # fmt: skip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=sorted(BOOKS))
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--reason", default="")
    parser.add_argument("--evidence-only", action="store_true")
    args = parser.parse_args()
    _, split = BOOKS[args.book]
    holdout = split == "holdout"
    if holdout and not args.holdout:
        raise SystemExit("Hold-out book: pass --holdout --reason (runs once, after freezing)")
    log = OUT / "holdout_runs.jsonl"
    if holdout and not args.evidence_only and log.exists():
        rows = [json.loads(line) for line in log.read_text("utf-8").splitlines()]
        started = sum(r.get("book") == args.book and r["action"] == "started" for r in rows)
        aborted = sum(r.get("book") == args.book and r["action"] == "aborted" for r in rows)
        if started > aborted:
            raise SystemExit("This hold-out already had its single Step 10 run")

    from book_core.evaluation.derived_harness import DerivedGold
    from book_core.evaluation.structure import heading_scores, toc_scores, zone_scores
    from book_core.paragraphs.keys import book_fingerprint
    from book_core.structure.cache import LOADED_DIGEST, analyze_book_structure

    started = time.perf_counter()
    loaded = load_book(args.book)  # preconditions (cached Step 8 and Step 9) before logging
    if holdout and not args.evidence_only:
        _log({"book": args.book, "action": "started", "structure_producer_sha256": LOADED_DIGEST,
              "reason": args.reason, "time": time.strftime("%Y-%m-%dT%H:%M:%S")})  # fmt: skip
    evidence, evidence_key, evidence_hit = evidence_for(args.book, loaded)
    print(f"evidence (cache hit {evidence_hit}) {time.perf_counter() - started:.0f}s", flush=True)
    if args.evidence_only:
        return
    classifier = heading_classifier()
    rules_only, _ = analyze_book_structure(evidence, evidence_key, CACHE10)
    structure, hit = analyze_book_structure(evidence, evidence_key, CACHE10, classifier=classifier)
    print(f"structure (cache hit {hit}) {time.perf_counter() - started:.0f}s", flush=True)
    gold = DerivedGold.load(GOLD / args.book)
    unit_tokens = {u["unit"]: [(p["page"], o) for o in u["token_ordinals"]]
                   for p in evidence["pages"] for u in p["units"]}  # fmt: skip
    texts = {u["unit"]: u["text"] for p in evidence["pages"] for u in p["units"]}
    zone_of = {z.page: z.zone for z in structure.page_zones}
    headings = heading_scores(gold, structure.headings, unit_tokens, zone_of)
    rules_zone_of = {z.page: z.zone for z in rules_only.page_zones}
    rules_headings = heading_scores(gold, rules_only.headings, unit_tokens, rules_zone_of)
    zones = zone_scores(gold, structure.page_zones)
    links = toc_scores(gold, structure.toc_links, unit_tokens)
    gates = unit_gate(loaded, structure, args.book)
    step9_path = ROOT / f"experiments/out/step9/{args.book}/summary.json"
    step9 = json.loads(step9_path.read_text("utf-8"))

    def heading_row(h):
        return {"page": h.page, "level": h.level, "role": h.role, "method": h.level_method,
                "confidence": h.confidence, "review": h.review_required,
                "style_group": h.style_group, "run_in": bool(h.run_in),
                "text": " | ".join(texts.get(u, "")[:80] for u in h.unit_ids)[:200],
                "reasons": h.reasons[:6]}  # fmt: skip

    owner = []
    for h in structure.headings:
        text = " ".join(texts.get(u, "") for u in h.unit_ids)
        if any(text.strip().startswith(name) for name in OWNER_CASE):
            owner.append(heading_row(h))
    sections = [
        {"zone": s.zone, "kind": s.kind, "first_page": s.first_page, "last_page": s.last_page,
         "logical_index": s.logical_index, "confidence": s.confidence, "reasons": s.reasons}
        for s in structure.sections
    ]  # fmt: skip
    summary = {
        "book": args.book,
        "split": split,
        "structure_producer_sha256": LOADED_DIGEST,
        "cache_key_inputs": structure.cache_key_inputs,
        "cache_hit": {"evidence": evidence_hit, "structure": hit},
        "gates": {
            **gates,
            "paragraph_book_key": book_fingerprint(loaded[5].book.cache_key_inputs),
            "reading_order_main_flow_step9": step9["reading_order"]["emitted"]["main_flow"][
                "pairwise_agreement_pooled"
            ],
            "float_anchors_step9": step9["reading_order"]["emitted"]["float_anchors"]["accuracy"],
            "paragraph_boundary_f1_step9": step9["paragraphs_per_page_units"]["boundary_f1"],
            "note": "Step 10 only reads Step 9 units and order; pages identical to the frozen "
            "Step 9 run imply identical reading-order and paragraph metrics",
        },  # fmt: skip
        "body_style": structure.body_style,
        "navigation_pages": dict(Counter(n.kind for n in structure.navigation_pages)),
        "navigation_page_list": [
            (n.page, n.kind, n.confidence) for n in structure.navigation_pages
        ],
        "rejected_navigation_pages": structure.profile.get("rejected_navigation_pages"),
        "toc_links": links,
        "heading_classifier": classifier.identity() if classifier else None,
        "headings": {k: v for k, v in headings.items() if k != "misses"},
        "headings_rules_only": {k: v for k, v in rules_headings.items() if k != "misses"},
        "styled": dict(Counter(s.role for s in structure.styled)),
        "styled_rules_only": dict(Counter(s.role for s in rules_only.styled)),
        "heading_misses": headings["misses"],
        "heading_roles": dict(Counter(h.role for h in structure.headings)),
        "heading_levels": dict(sorted(Counter(h.level for h in structure.headings).items())),
        "level_methods": dict(Counter(h.level_method for h in structure.headings)),
        "low_confidence_headings": sum(h.review_required for h in structure.headings),
        "zones": {k: v for k, v in zones.items() if k != "page_misses"},
        "zone_page_misses": zones["page_misses"],
        "sections": sections,
        "profile": structure.profile,
        "style_groups": structure.style_groups[:25],
        "owner_case": owner,
        "seconds": round(time.perf_counter() - started, 1),
    }
    target = OUT / args.book
    target.mkdir(parents=True, exist_ok=True)
    (target / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n", "utf-8"
    )
    with gzip.open(target / "headings.jsonl.gz", "wt", encoding="utf-8") as handle:
        for h in structure.headings:
            handle.write(json.dumps(heading_row(h), ensure_ascii=False) + "\n")
    with gzip.open(target / "low_confidence.jsonl.gz", "wt", encoding="utf-8") as handle:
        for h in structure.headings:
            if h.review_required:
                handle.write(json.dumps(heading_row(h), ensure_ascii=False) + "\n")
    if holdout:
        _log({"book": args.book, "action": "completed", "structure_producer_sha256": LOADED_DIGEST,
              "time": time.strftime("%Y-%m-%dT%H:%M:%S")})  # fmt: skip
    short = {
        "gates": {k: v for k, v in summary["gates"].items() if k != "note"},
        "headings": {k: headings[k] for k in ("reference_headings", "our_headings", "precision",
                                              "recall", "f1",
                                              "precision_without_convention_classes")},
        "headings_rules_only": {k: rules_headings[k] for k in ("our_headings", "precision",
                                                               "recall", "f1")},
        "levels": headings["levels"],
        "zones": {k: zones[k] for k in ("unit_accuracy", "page_accuracy",
                                        "page_accuracy_metadata_as_front")},
        "toc": links,
        "seconds": summary["seconds"],
    }  # fmt: skip
    print(json.dumps(short, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
