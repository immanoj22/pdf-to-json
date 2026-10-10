"""Step 9: paragraphs for one approved book, evaluated per book against derived gold.

Book stage (cached): profile pass, then per-page paragraph units (with inline runs, languages
and anchor proposals) and cross-page joins. Evaluation: paragraph boundaries/exact/splits/
merges (per-page units, as the reference splits paragraphs at page breaks; chained variant
too), column and page joins, hyphen decisions vs reference spelling, gates (every line in
exactly one unit and ordered once), the Step 7 reading-order metric with the emitted order and
with the paragraph-boundary anchor rules, low-confidence list, the "Gobernantes" case (book 1).
Hold-out books need --holdout and run once (experiments/out/step9/holdout_runs.jsonl).

Usage: python step9_run.py --book spanish_us_history [--holdout --reason "..."]
"""

import argparse
import glob
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

OUT = ROOT / "experiments/out/step9"
CACHE9 = ROOT / ".cache/step9"
GOLD = ROOT / "backend/tests/gold_derived"


def alignment_pdf_xml(gold):
    expected = {row["page"]: row["token_digest"] for row in gold.pages}
    for path in glob.glob(str(ROOT / ".cache/step5/alignment/*.json")):
        payload = json.loads(Path(path).read_text("utf-8"))["payload"]
        payload = json.loads(payload) if isinstance(payload, str) else payload
        if payload["xml_sha256"] != gold.manifest["provenance"]["xml_sha256"]:
            continue
        if dict(zip(payload["pages"], payload["page_digests"], strict=True)) == expected:
            return dict(zip(payload["pages"], payload["pdf_xml"], strict=True)), Path(path).name
    return {}, None


def navigation_map(artifact):
    mapping = {}
    if artifact is None:
        return mapping
    for entry in artifact["navigation"]["printed_entries"]:
        for line in entry["line_ids"]:
            mapping.setdefault(entry["source_page"], {})[line] = entry["id"]
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=sorted(BOOKS))
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    key, split = BOOKS[args.book]
    if split == "holdout" and not args.holdout:
        raise SystemExit("Hold-out book: pass --holdout --reason (runs once, after freezing)")
    log = OUT / "holdout_runs.jsonl"
    if split == "holdout" and log.exists():
        rows = [json.loads(line) for line in log.read_text("utf-8").splitlines()]
        if any(row["book"] == args.book for row in rows):
            raise SystemExit("This hold-out already had its single Step 9 run")

    from book_core.caching import code_digest
    from book_core.document_analysis.metadata import cached_metadata
    from book_core.evaluation.derived_harness import DerivedGold, evaluate
    from book_core.evaluation.furniture import token_lines
    from book_core.evaluation.paragraphs import hyphen_scores, join_scores, paragraph_scores
    from book_core.evaluation.reading_order import ReadingOrderOutput, page_order
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.furniture.cache import load_book_furniture
    from book_core.furniture.inputs import PageInputs
    from book_core.objects.analysis import cached_repetition
    from book_core.paragraphs.anchors import move_anchors
    from book_core.paragraphs.cache import (
        LOADED_DIGEST,
        analyze_book_paragraphs,
        chains,
        load_page,
    )
    from book_core.paragraphs.models import TEXT_KINDS
    from book_core.paragraphs.segment import LANE_CHANGES
    from book_core.paragraphs.text import unit_text
    from book_core.reading_order.graph import check

    started = time.perf_counter()
    source = reference_path(key)
    extractor = PyMuPDFExtractor(device="cpu")
    inputs = PageInputs(
        source, extractor, cached_repetition(source, extractor, CACHE), CACHE,
        vocabulary_for(args.book),
    )  # fmt: skip
    metadata = cached_metadata(source, extractor, CACHE8 / "metadata")
    furniture, furniture_key = load_book_furniture(inputs, metadata, CACHE8)
    if furniture is None:
        raise SystemExit("Run the Step 8 furniture stage first (no cached decision)")
    artifact, artifact_path = step6_artifact(inputs.digest)
    navigation = navigation_map(artifact)
    if split == "holdout":
        OUT.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "book": args.book, "action": "started",
                "paragraphs_producer_sha256": LOADED_DIGEST,
                "reading_order_producer_sha256": code_digest("reading_order"),
                "reason": args.reason, "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }) + "\n")  # fmt: skip
    result, hit = analyze_book_paragraphs(
        lambda: extractor.extract_pages(source),
        inputs,
        furniture,
        furniture_key,
        CACHE8,
        navigation,
        CACHE9,
    )
    print(f"paragraphs (cache hit {hit}) {time.perf_counter() - started:.0f}s", flush=True)
    gold = DerivedGold.load(GOLD / args.book)
    pdf_xml, alignment_file = alignment_pdf_xml(gold)
    root = chains(result)
    per_page, chained, views, proposals = {}, {}, {}, {"nearest": {}, "end": {}}
    joins, hyphens, problems, low = [], [], {}, []
    counts = Counter()
    hyphen_counts, style_counts, languages = Counter(), Counter(), Counter()
    units_by_page, texts_needed = {}, {}
    page_join_by_unit = {j.from_unit_id: j for j in result.book.page_joins}
    last_main, first_main = {}, {}
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        built = load_page(result, number, CACHE9)
        layout, _ = inputs(page)
        units_by_page[number] = built.units
        issues = check(built.order, None)
        lines = [lid for u in built.units for lid in u.line_ids]
        if sorted(lines) != sorted(line.id for line in layout.lines) or len(lines) != len(
            set(lines)
        ):
            issues.append("units do not hold every layout line exactly once")
        if issues:
            problems[number] = issues
        counts["lines"] += len(layout.lines)
        counts["lines_in_units"] += len(lines)
        owners = token_lines(page, layout)
        first, last = {}, {}
        for i, lid in enumerate(owners):
            first.setdefault(lid, i)
            last[lid] = i
        unit_of = {lid: u for u in built.units for lid in u.line_ids}
        for i, lid in enumerate(owners):
            unit = unit_of.get(lid)
            if unit is not None and unit.kind in TEXT_KINDS:
                per_page[(number, i)] = unit.id
                chained[(number, i)] = root.get(unit.id, unit.id)
        edge = {(e.source, e.target): e.kind for e in built.order.edges}
        joined = {(j.previous_line_id, j.next_line_id): j for u in built.units for j in u.joins}
        for stream in built.order.streams:
            for a, b in zip(stream.line_ids, stream.line_ids[1:], strict=False):
                if edge.get((a, b)) in LANE_CHANGES and a in last and b in first:
                    joins.append(
                        ("column", (a, b) in joined, (number, last[a]), (number, first[b]))
                    )
        for (a, b), join in joined.items():
            if join.hyphen is not None:
                hyphen_counts[join.hyphen.choice] += 1
                if a in last and b in first:
                    hyphens.append((join.hyphen.choice, (number, last[a]), (number, first[b])))
            if join.word is not None:
                hyphen_counts["word_join"] += 1
        main_text = [u for u in built.units if u.stream_kind == "main" and u.kind in TEXT_KINDS]
        if main_text:
            for lid in reversed(main_text[-1].line_ids):
                if lid in last:
                    last_main[number] = (main_text[-1].id, last[lid])
                    break
            for lid in main_text[0].line_ids:
                if lid in first:
                    first_main[number] = (main_text[0].id, first[lid])
                    break
        for unit in built.units:
            counts[f"units_{unit.kind}"] += 1
            if unit.kind in TEXT_KINDS:
                languages[unit.language] += 1
                counts["mixed_language_units"] += bool(unit.language_runs)
                for run in unit.style_runs:
                    for name in ("bold", "italic", "superscript", "subscript", "small_caps"):
                        style_counts[name] += getattr(run, name)
                    style_counts["color"] += run.color is not None
            if unit.review_required:
                reasons = list(unit.boundary.reasons) if unit.boundary.review_required else []
                reasons += [r for j in unit.joins if j.review_required for r in j.reasons[:2]]
                low.append({
                    "page": number, "unit": unit.id, "kind": unit.kind,
                    "boundary_confidence": unit.boundary.confidence,
                    "weakest_join": min((j.confidence for j in unit.joins), default=None),
                    "reasons": reasons[:4],
                    "text": unit_text(page.store, layout, unit)[:100],
                })  # fmt: skip
        counts["anchor_proposals"] += len(built.anchor_moves)
        views[number], _ = page_order(page, layout, built.order)
        for rule in proposals:
            moved, _ = move_anchors(built.order, built.units, rule)
            proposals[rule][number], _ = page_order(page, layout, moved)
        if args.book == "spanish_us_history" and number == 26:
            for unit in built.units:
                text = unit_text(page.store, layout, unit)
                if text.startswith("Gobernantes"):
                    texts_needed["gobernantes"] = {
                        "unit": unit.id, "lines": len(unit.line_ids), "text": text,
                        "boundary": unit.boundary.reasons,
                        "next_boundary": next(
                            (u.boundary.reasons for u in built.units
                             if u.stream_kind == "main" and u.line_ids[0] not in unit.line_ids
                             and built.units.index(u) > built.units.index(unit)), None),
                    }  # fmt: skip
    for number, (unit_id, ordinal) in last_main.items():
        if number + 1 in first_main:
            next_id, next_ordinal = first_main[number + 1]
            joined = page_join_by_unit.get(unit_id)
            joins.append((
                "page", joined is not None and joined.to_unit_id == next_id,
                (number, ordinal), (number + 1, next_ordinal),
            ))  # fmt: skip
    for join in result.book.page_joins:
        if join.join.hyphen is not None:
            hyphen_counts[join.join.hyphen.choice] += 1
    digests = {row["page"]: row["token_digest"] for row in gold.pages}
    holdout = split == "holdout"

    def order_report(pages):
        output = ReadingOrderOutput(
            "reading_order", args.book,
            {n: [v.stream_of.get(i) for i in range(len(v.stream_of))] for n, v in pages.items()},
            digests, pages,
        )  # fmt: skip
        detail = evaluate([gold], {args.book: output}, include_holdout=holdout)
        detail = detail["books"][args.book]["reading_order"]
        return {
            k: v
            for k, v in detail.items()
            if k not in {"per_page", "anchor_misses", "reference_conventions"}
        }

    step8 = json.loads(
        (ROOT / f"experiments/out/step9/furniture/{args.book}/summary.json").read_text("utf-8")
    )["reading_order"]["step8"]
    harness = evaluate(
        [gold],
        {args.book: ReadingOrderOutput("paragraphs", args.book,
                                       {n: [v.stream_of.get(i) for i in range(len(v.stream_of))]
                                        for n, v in views.items()},
                                       digests, views, paragraph_of=per_page)},
        include_holdout=holdout,
    )["books"][args.book]  # fmt: skip
    candidates = result.book.page_join_candidates
    summary = {
        "book": args.book,
        "split": split,
        "paragraphs_producer_sha256": LOADED_DIGEST,
        "cache_key_inputs": result.book.cache_key_inputs,
        "cache_hit": hit,
        "gates": {
            "lines": counts["lines"],
            "lines_in_exactly_one_unit": counts["lines_in_units"],
            "invariant_problems": problems,
        },
        "units": {k[6:]: v for k, v in sorted(counts.items()) if k.startswith("units_")},
        "paragraphs_per_page_units": harness["paragraph_boundaries"],
        "paragraphs_with_page_chains": paragraph_scores(gold, chained),
        "joins": join_scores(gold, joins),
        "page_joins": len(result.book.page_joins),
        "page_join_candidates": {
            "pairs": len(candidates),
            "joined": sum(c.get("joined", False) for c in candidates),
            "flagged_neutral": sum(c.get("review_required", False) for c in candidates),
            "verdicts": dict(Counter(c["verdict"] for c in candidates)),
        },
        "hyphenation": {
            "decisions": dict(hyphen_counts),
            "vs_reference": hyphen_scores(hyphens, pdf_xml),
            "alignment": alignment_file,
            "dictionary": "none (Step 6 vocabulary and the book's compound lexicon only)",
        },
        "inline": {
            "style_runs": dict(style_counts),
            "unit_languages": dict(languages.most_common()),
            "mixed_language_units": counts["mixed_language_units"],
            "language_profile": result.book.profile.get("language_detector"),
        },
        "reading_order": {
            "emitted": order_report(views),
            "step8": step8,
            "proposal_nearest": order_report(proposals["nearest"]),
            "proposal_end": order_report(proposals["end"]),
            "anchor_proposals": counts["anchor_proposals"],
        },
        "low_confidence_units": len(low),
        "low_confidence_by_kind": dict(Counter(row["kind"] for row in low)),
        "profile": result.book.profile,
        "navigation_artifact": artifact_path.name if artifact_path else None,
        "gobernantes": texts_needed.get("gobernantes"),
        "seconds": round(time.perf_counter() - started, 1),
    }
    target = OUT / args.book
    target.mkdir(parents=True, exist_ok=True)
    (target / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    with gzip.open(target / "low_confidence.jsonl.gz", "wt", encoding="utf-8") as handle:
        for row in low:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (target / "page_joins.json").write_text(
        json.dumps([j.model_dump() for j in result.book.page_joins], indent=0,
                   ensure_ascii=False) + "\n", "utf-8",
    )  # fmt: skip
    if holdout:
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "book": args.book, "action": "completed",
                "paragraphs_producer_sha256": LOADED_DIGEST,
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }) + "\n")  # fmt: skip
    short = {
        "gates": summary["gates"],
        "paragraphs": {k: v for k, v in summary["paragraphs_per_page_units"].items()
                       if k != "by_kind"},
        "joins": summary["joins"],
        "hyphen": summary["hyphenation"]["vs_reference"],
        "order": (summary["reading_order"]["emitted"]["main_flow"]["pairwise_agreement_pooled"],
                  summary["reading_order"]["emitted"]["float_anchors"]["accuracy"],
                  step8["float_anchors"]["accuracy"]),
        "seconds": summary["seconds"],
    }  # fmt: skip
    print(json.dumps(short, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
