"""Step 11: lists, index and glossary entries for one book, evaluated per book.

Runs Steps 9-11 on cached inputs: the Step 9 paragraphs (cached; their key must equal the
frozen Step 9 run's), the Step 10 structure (cached evidence; the decision with the current
structure producer, including the Step 11 body-start rule), then the Step 11 lists stage.
Evaluation per book against derived gold:

- paragraphs again (Step 11 units, per page and with chains) next to the same metric on the
  Step 9 units;
- lists: list item exact match, item and list boundary F1, nesting, definition term and
  description, index entries and sub-entry levels, bibliography entries, cross-page entry
  errors; each also on the Step 9 units ("before");
- reading order with the Step 11 order (glossary entry order) vs Step 9, and float anchors
  at paragraph/list boundaries (Task 5, rules ``nearest`` and ``end``);
- Step 10 zones and headings with the current structure producer; page labels for body pages
  and all markers;
- gates: every line in exactly one unit and ordered once on every page, order invariants.

Hold-out books (book 4; book 3 is anecdotal) need --holdout and run once
(experiments/out/step11/holdout_runs.jsonl).

Usage: python step11_run.py --book spanish_us_history [--holdout --reason "..."]
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

from step7_layouts import BOOKS
from step9_run import CACHE9
from step10_run import CACHE10, GOLD, PROMOTED, evidence_for, load_book

OUT = ROOT / "experiments/out/step11"
CACHE11 = ROOT / ".cache/step11"
LOW = 0.65  # lowest-confidence items listed for review (flagged items are below 0.6)
HOLDOUT = {"medical_anatomy": "hold-out", "art_therapy_index": "anecdotal, runs once"}
FURNITURE_KINDS = {
    "running_head",
    "running_foot",
    "folio",
    "production_mark",
    "artifact",
    "invisible",
}


def _log(row):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "holdout_runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def term_tokens(page, layout, unit, line_ordinals):
    """Token ordinals of a unit's term: tokens of the term line counted before the term's
    start and end offsets (the ledger tokenizer over the NFKC line text)."""
    import unicodedata

    from book_core.ledger.tokenization import TOKEN_PATTERN

    spans = {r.span_id for r in unit.term}
    line = next((ln for ln in layout.lines if ln.id in unit.line_ids
                 and spans & set(ln.span_ids)), None)  # fmt: skip
    if line is None:
        return []
    offsets, position = {}, 0
    for sid in line.span_ids:
        offsets[sid] = position
        position += len(page.store.spans[sid].raw_text)
    raw = "".join(page.store.spans[sid].raw_text for sid in line.span_ids)
    starts = [
        offsets[r.span_id] + (r.start or 0) for r in unit.term if r.span_id in offsets
    ]
    ends = [offsets[r.span_id] + (r.end if r.end is not None else
            len(page.store.spans[r.span_id].raw_text)) for r in unit.term
            if r.span_id in offsets]  # fmt: skip

    def count(text):
        return len(TOKEN_PATTERN.findall(unicodedata.normalize("NFKC", text)))

    first, last = count(raw[: min(starts)]), count(raw[: max(ends)])
    return line_ordinals.get(line.id, [])[first:last]


def split_of(book):
    return (
        "development"
        if book in PROMOTED or book == "spanish_us_history"
        else BOOKS[book][1]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=sorted(BOOKS))
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    holdout = args.book in HOLDOUT
    if holdout and not args.holdout:
        raise SystemExit(
            "Hold-out book: pass --holdout --reason (runs once, after freezing)"
        )
    log = OUT / "holdout_runs.jsonl"
    if holdout and log.exists():
        rows = [json.loads(line) for line in log.read_text("utf-8").splitlines()]
        mine = [r["action"] for r in rows if r.get("book") == args.book]
        if mine.count("started") > mine.count("aborted"):
            raise SystemExit("This hold-out already had its single Step 11 run")

    from book_core.evaluation.derived_harness import DerivedGold, evaluate
    from book_core.evaluation.furniture import marker_scores, token_lines
    from book_core.evaluation.lists import (
        Ours,
        bibliography_scores,
        cross_page_scores,
        definition_scores,
        index_scores,
        list_item_scores,
    )
    from book_core.evaluation.paragraphs import paragraph_scores
    from book_core.evaluation.reading_order import ReadingOrderOutput, page_order
    from book_core.evaluation.structure import heading_scores, zone_scores
    from book_core.lists.cache import (
        LOADED_DIGEST,
        analyze_book_lists,
        chains,
        load_page,
    )
    from book_core.lists.models import ENTRY_KINDS, TEXT_KINDS
    from book_core.paragraphs.anchors import move_anchors
    from book_core.paragraphs.cache import chains as step9_chains
    from book_core.paragraphs.cache import load_page as load_step9
    from book_core.paragraphs.keys import book_fingerprint
    from book_core.paragraphs.models import TEXT_KINDS as STEP9_TEXT
    from book_core.paragraphs.text import unit_text
    from book_core.reading_order.graph import check
    from book_core.structure.cache import LOADED_DIGEST as STRUCTURE_DIGEST
    from book_core.structure.cache import analyze_book_structure

    started = time.perf_counter()
    loaded = load_book(args.book)  # preconditions (cached Steps 8 and 9) before logging
    source, extractor, inputs, furniture, _, paragraphs, _, _ = loaded
    if holdout:
        _log({"book": args.book, "action": "started", "lists_producer_sha256": LOADED_DIGEST,
              "structure_producer_sha256": STRUCTURE_DIGEST, "reason": args.reason,
              "time": time.strftime("%Y-%m-%dT%H:%M:%S")})  # fmt: skip
    evidence, evidence_key, _ = evidence_for(args.book, loaded)
    structure, structure_hit = analyze_book_structure(evidence, evidence_key, CACHE10)
    result, hit = analyze_book_lists(
        lambda: extractor.extract_pages(source), inputs, paragraphs, CACHE9, structure,
        furniture, CACHE11,
    )  # fmt: skip
    print(f"lists (cache hit {hit}) {time.perf_counter() - started:.0f}s", flush=True)
    gold = DerivedGold.load(GOLD / args.book)
    digests = {row["page"]: row["token_digest"] for row in gold.pages}
    root11, root9 = chains(result), step9_chains(paragraphs)
    ours = Ours(unit_of={})
    before = Ours(unit_of={})
    per9, chained9, chained11 = {}, {}, {}
    views, views9, moved = {}, {}, {"nearest": {}, "end": {}}
    problems, counts, low = {}, Counter(), []
    kinds, roles_count = Counter(), Counter()
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        layout, _ = inputs(page)
        built = load_page(result, number, CACHE11)
        step9 = load_step9(paragraphs, number, CACHE9)
        issues = check(built.order, layout)
        lines = [lid for u in built.units for lid in u.line_ids]
        expected = {line.id for line in layout.lines}
        if len(lines) != len(set(lines)) or set(lines) != expected:
            issues.append("units do not hold every layout line exactly once")
        if issues:
            problems[number] = issues
        counts["lines"] += len(layout.lines)
        counts["lines_in_units"] += len(lines)
        owners = token_lines(page, layout)
        unit_of = {lid: u for u in built.units for lid in u.line_ids}
        unit9 = {lid: u for u in step9.units for lid in u.line_ids}
        line_ordinals = {}
        for i, lid in enumerate(owners):
            line_ordinals.setdefault(lid, []).append(i)
        for u in built.units:
            if u.term:
                for key in term_tokens(page, layout, u, line_ordinals):
                    ours.terms.add((number, key))
        for i, lid in enumerate(owners):
            unit = unit_of.get(lid)
            if unit is not None and unit.kind in TEXT_KINDS:
                key = (number, i)
                ours.unit_of[key] = unit.id
                chained11[key] = root11.get(unit.id, unit.id)
            old = unit9.get(lid)
            if old is not None and old.kind in STEP9_TEXT:
                per9[(number, i)] = old.id
                chained9[(number, i)] = root9.get(old.id, old.id)
        for u in built.units:
            ours.kind_of[u.id] = u.kind
            if u.list_id:
                ours.list_of[u.id] = u.list_id
            if u.level is not None:
                ours.level_of[u.id] = u.level
            kinds[u.kind] += 1
            if u.kind in ENTRY_KINDS and (u.review_required or u.boundary.confidence <= LOW):
                low.append({"page": number, "unit": u.id, "kind": u.kind,
                            "confidence": u.boundary.confidence, "reasons": u.boundary.reasons,
                            "text": unit_text(page.store, layout, u)[:100]})  # fmt: skip
        for u in step9.units:
            before.kind_of[u.id] = u.kind
        views[number], _ = page_order(page, layout, built.order)
        views9[number], _ = page_order(page, layout, step9.order)
        for rule, pages in moved.items():
            order, _ = move_anchors(built.order, built.units, rule)
            pages[number], _ = page_order(page, layout, order)
        counts["order_changes"] += len(built.order_changes)
    ours.chain_of = root11
    ours.links = [
        (link["from_unit_id"], link["to_unit_id"]) for link in result.page_links
    ]
    before.unit_of = per9
    before.chain_of = root9
    before.links = [(j.from_unit_id, j.to_unit_id) for j in paragraphs.book.page_joins]
    for lst in result.book.lists:
        roles_count[(lst.kind, lst.role)] += 1

    def order_report(pages, paragraph_of=None):
        output = ReadingOrderOutput(
            "lists", args.book,
            {n: [v.stream_of.get(i) for i in range(len(v.stream_of))] for n, v in pages.items()},
            digests, pages, paragraph_of=paragraph_of,
        )  # fmt: skip
        detail = evaluate([gold], {args.book: output}, include_holdout=True)["books"][
            args.book
        ]
        order = detail["reading_order"]
        return {
            "main_flow": order["main_flow"]["pairwise_agreement_pooled"],
            "kendall_tau": order["main_flow"]["kendall_tau_pooled"],
            "float_anchors": order["float_anchors"]["accuracy"],
            "anchors_by_kind": {
                k: v["accuracy"] for k, v in order["float_anchors"]["by_kind"].items()
            },
            "within_floats": order["within_floats"]["pairwise_agreement"],
        }

    index_pages = [n.page for n in structure.navigation_pages if n.kind == "index"]
    glossary_pages = [
        n.page for n in structure.navigation_pages if n.kind == "glossary"
    ]

    def list_metrics(view):
        return {
            "list_items": list_item_scores(gold, view, index_pages),
            "definitions": definition_scores(gold, view),
            "index": index_scores(gold, view, index_pages),
            "bibliography": bibliography_scores(gold, view),
            "cross_page_entries": cross_page_scores(gold, view),
        }

    unit_tokens = {
        u["unit"]: [(p["page"], o) for o in u["token_ordinals"]]
        for p in evidence["pages"]
        for u in p["units"]
    }
    zone_of = {z.page: z.zone for z in structure.page_zones}
    headings = heading_scores(gold, structure.headings, unit_tokens, zone_of)
    freeze10b = json.loads(
        (ROOT / "experiments/out/step10b/freeze.json").read_text("utf-8")
    )
    paragraph_key = book_fingerprint(paragraphs.book.cache_key_inputs)
    summary = {
        "book": args.book,
        "split": split_of(args.book),
        "lists_producer_sha256": LOADED_DIGEST,
        "structure_producer_sha256": STRUCTURE_DIGEST,
        "cache_key_inputs": result.book.cache_key_inputs,
        "cache_hit": {"structure": structure_hit, "lists": hit},
        "gates": {
            "lines": counts["lines"],
            "lines_in_exactly_one_unit": counts["lines_in_units"],
            "invariant_problems": problems,
            "paragraph_book_key": paragraph_key,
            # Step 9 is unchanged when its producer equals the Step 10b freeze; the paragraph
            # book key then names the same cached units the Step 10b runs read.
            "paragraphs_producer_equals_step10b_freeze": paragraphs.book.cache_key_inputs[
                "paragraphs_producer_sha256"
            ]
            == freeze10b["producers"]["paragraphs"],
        },
        "units": dict(kinds.most_common()),
        "lists": {
            "count": len(result.book.lists),
            "by_kind_role": {
                f"{k}/{r}": v for (k, r), v in sorted(roles_count.items())
            },
            "entry_links": len(result.book.entry_links),
            "dropped_page_joins": len(result.book.dropped_page_joins),
            "kept_paragraph_joins": sum(
                link["kind"] == "paragraph" for link in result.page_links
            ),
            "glossary_pages_reordered": counts["order_changes"],
            "glossary_pages": glossary_pages,
            "index_pages": len(index_pages),
        },
        "paragraphs": {
            "step11_per_page": paragraph_scores(gold, ours.unit_of),
            "step11_with_chains": paragraph_scores(gold, chained11),
            "step9_per_page": paragraph_scores(gold, per9),
            "step9_with_chains": paragraph_scores(gold, chained9),
        },
        "list_metrics": {
            "step11": list_metrics(ours),
            "step9_units": list_metrics(before),
        },
        "reading_order": {
            "step11": order_report(views),
            "step9": order_report(views9),
            "anchors_at_boundaries": {
                rule: order_report(pages) for rule, pages in moved.items()
            },
        },
        "zones": {
            k: v
            for k, v in zone_scores(gold, structure.page_zones).items()
            if k != "page_misses"
        },
        "zone_profile": structure.profile.get("zones"),
        "headings": {
            k: headings[k]
            for k in (
                "reference_headings",
                "our_headings",
                "precision",
                "recall",
                "f1",
                "levels",
            )
        },
        "page_labels": {
            k: v
            for k, v in marker_scores(gold, furniture.book.markers).items()
            if k != "misses"
        },
        "low_confidence_items": len(low),
        "low_confidence_by_kind": dict(Counter(r["kind"] for r in low)),
        "seconds": round(time.perf_counter() - started, 1),
    }
    target = OUT / args.book
    target.mkdir(parents=True, exist_ok=True)
    (target / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n", "utf-8"
    )
    with gzip.open(
        target / "low_confidence.jsonl.gz", "wt", encoding="utf-8"
    ) as handle:
        for row in low:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    if holdout:
        _log({"book": args.book, "action": "completed", "lists_producer_sha256": LOADED_DIGEST,
              "time": time.strftime("%Y-%m-%dT%H:%M:%S")})  # fmt: skip
    s11, s9 = (
        summary["paragraphs"]["step11_per_page"],
        summary["paragraphs"]["step9_per_page"],
    )
    short = {
        "gates": {
            k: v for k, v in summary["gates"].items() if k != "invariant_problems"
        },
        "problems": len(problems),
        "paragraph_f1_exact": (
            s9["boundary_f1"],
            s9["exact_unit_match"],
            "->",
            s11["boundary_f1"],
            s11["exact_unit_match"],
        ),
        "merges_splits": (
            s9["merge_errors"],
            s9["split_errors"],
            "->",
            s11["merge_errors"],
            s11["split_errors"],
        ),
        "reading_order": summary["reading_order"],
        "zones": summary["zones"].get("page_accuracy"),
        "seconds": summary["seconds"],
    }
    print(json.dumps(short, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
