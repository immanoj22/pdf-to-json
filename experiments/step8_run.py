"""Step 8: page furniture and printed page labels for one approved book, evaluated per book.

Pass 1 decides the whole book (roles for every line, folio runs, page markers; cached). Pass 2
applies the roles page by page: the unchanged Step 7 builder re-orders a furniture-adjusted
region view, and furniture streams are split by role (cached per page). Then: gates (every
line ordered exactly once, graph checks), page markers vs derived gold, furniture precision by
class, the aligner recall proxy (diagnostic only), repeated boxes, printed-TOC resolution
before/after, and the Step 7 reading-order metric re-run. Hold-out books need --holdout and
run once; each run is appended to experiments/out/step8/holdout_runs.jsonl.

Usage: python step8_run.py --book spanish_us_history [--holdout --reason "..."]
"""

import argparse
import glob
import gzip
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402
from step5_run import BOOKS as REFERENCE_BOOKS  # noqa: E402
from step7_layouts import BOOKS, CACHE  # noqa: E402

OUT = ROOT / "experiments/out/step8"
CACHE8 = ROOT / ".cache/step8"
GOLD = ROOT / "backend/tests/gold_derived"
STEP7 = ROOT / "experiments/out/step7"


def vocabulary_for(book):
    name = (
        "step7_vocabulary.json" if book == "spanish_us_history" else f"step7_vocabulary_{book}.json"
    )
    return json.loads((CACHE / name).read_text("utf-8"))


def step6_artifact(source_sha256):
    from book_core.document_analysis.cache import load_artifact

    for path in sorted(glob.glob(str(ROOT / ".cache/step6/document/*.json"))):
        artifact = load_artifact(Path(path))
        if artifact["provenance"]["source_sha256"] == source_sha256:
            return artifact, Path(path)
    return None, None


def alignment_causes(gold):
    """Per-token aligner PDF causes from the Step 5b alignment matching the gold digests."""
    expected = {row["page"]: row["token_digest"] for row in gold.pages}
    xml = gold.manifest["provenance"]["xml_sha256"]
    found = []
    for path in glob.glob(str(ROOT / ".cache/step5/alignment/*.json")):
        payload = json.loads(Path(path).read_text("utf-8"))["payload"]
        payload = json.loads(payload) if isinstance(payload, str) else payload
        if payload["xml_sha256"] != xml:
            continue
        digests = dict(zip(payload["pages"], payload["page_digests"], strict=True))
        if digests != expected:
            continue
        found.append((os.path.getmtime(path), path, payload))
    if not found:
        return {}, None
    _, path, payload = max(found)
    return dict(zip(payload["pages"], payload["pdf_cause"], strict=True)), Path(path).name


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
        previous = [json.loads(line) for line in log.read_text("utf-8").splitlines()]
        if any(row["book"] == args.book for row in previous):
            raise SystemExit("This hold-out already had its single Step 8 run")

    from book_core.caching import code_digest
    from book_core.document_analysis.metadata import cached_metadata
    from book_core.evaluation.derived_harness import DerivedGold, evaluate
    from book_core.evaluation.document_evidence import _navigation
    from book_core.evaluation.furniture import (
        furniture_precision,
        marker_scores,
        recall_proxy,
        toc_resolution,
        token_lines,
    )
    from book_core.evaluation.reading_order import ReadingOrderOutput, page_order
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.furniture.cache import (
        LOADED_DIGEST,
        analyze_book_furniture,
        page_furniture,
    )
    from book_core.furniture.inputs import PageInputs
    from book_core.objects.analysis import cached_repetition
    from book_core.reading_order.graph import check

    started = time.perf_counter()
    source = reference_path(key)
    extractor = PyMuPDFExtractor(device="cpu")
    repetition = cached_repetition(source, extractor, CACHE)
    vocabulary = vocabulary_for(args.book)
    inputs = PageInputs(source, extractor, repetition, CACHE, vocabulary)
    if split == "holdout":
        OUT.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "book": args.book,
                        "action": "started",
                        "furniture_producer_sha256": LOADED_DIGEST,
                        "reading_order_producer_sha256": code_digest("reading_order"),
                        "reason": args.reason,
                        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                )
                + "\n"
            )
    print(f"inputs ready {time.perf_counter() - started:.0f}s", flush=True)
    metadata = cached_metadata(source, extractor, CACHE8 / "metadata")
    print(f"metadata {time.perf_counter() - started:.0f}s", flush=True)
    decisions, book_key, hit = analyze_book_furniture(
        extractor.extract_pages(source), inputs, metadata, CACHE8
    )
    print(f"book decisions (cache hit {hit}) {time.perf_counter() - started:.0f}s", flush=True)
    book = decisions.book

    gold = DerivedGold.load(GOLD / args.book)
    token_roles, token_groups, views, problems = {}, {}, {}, {}
    lines_total = lines_ordered = 0
    role_lines = Counter()
    stream_lines = Counter()
    rebuilt_pages = 0
    flagged = []
    box_stream_kinds = Counter()
    texts = {}
    furniture_stream_roles = Counter()
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        result = page_furniture(page, inputs, decisions, book_key, CACHE8)
        layout, _ = inputs(page)
        issues = check(result.order, None)
        ordered = [lid for s in result.order.streams for lid in s.line_ids]
        if sorted(ordered) != sorted(line.id for line in layout.lines):
            issues.append("ordered lines differ from layout lines")
        if issues:
            problems[number] = issues
        lines_total += len(layout.lines)
        lines_ordered += len(ordered)
        rebuilt_pages += "rebuilt" in result.provenance.notes[0]
        role_of = {r.line_id: r for r in result.roles}
        stream_of = {lid: s.kind for s in result.order.streams for lid in s.line_ids}
        for role in result.roles:
            role_lines[role.role] += 1
            if role.review_required:
                flagged.append((number, role))
            if role.role == "repeated_box":
                box_stream_kinds[stream_of[role.line_id]] += 1
        for kind_role, stream_id in result.furniture_streams.items():
            stream = next(s for s in result.order.streams if s.id == stream_id)
            furniture_stream_roles[kind_role] += len(stream.line_ids)
        for stream in result.order.streams:
            stream_lines[stream.kind] += len(stream.line_ids)
        owners = token_lines(page, layout)
        token_roles[number] = [role_of[lid].role if lid else None for lid in owners]
        token_groups[number] = [role_of[lid].group_id if lid else None for lid in owners]
        store = page.store
        for line in layout.lines:
            group = role_of[line.id].group_id
            if group and (role_of[line.id].role, group) not in texts:
                texts[(role_of[line.id].role, group)] = (
                    number,
                    "".join(store.spans[s].raw_text for s in line.span_ids)[:80],
                )
        views[number], _ = page_order(page, layout, result.order)
    digests = {row["page"]: row["token_digest"] for row in gold.pages}
    output = ReadingOrderOutput(
        "reading_order",
        args.book,
        {n: [v.stream_of.get(i) for i in range(len(token_roles[n]))] for n, v in views.items()},
        digests,
        views,
    )
    report = evaluate([gold], {args.book: output}, include_holdout=split == "holdout")
    order_detail = report["books"][args.book]["reading_order"]
    order_now = {
        k: v
        for k, v in order_detail.items()
        if k not in {"per_page", "anchor_misses", "reference_conventions"}
    }
    step7 = json.loads((STEP7 / args.book / "summary.json").read_text("utf-8"))["reading_order"]

    precision = furniture_precision(
        gold, token_roles, token_groups, lambda role, group: texts.get((role, group))
    )
    causes, alignment_file = alignment_causes(gold)
    recall = recall_proxy(token_roles, causes) if causes else None
    markers = marker_scores(gold, book.markers)

    artifact, artifact_path = step6_artifact(inputs.digest)
    navigation = None
    if artifact is not None:
        printed = [e for e in artifact["navigation"]["entries"] if e["kind"] == "printed_toc"]
        counts, resolved = toc_resolution(printed, book.markers)
        navigation = {"artifact": artifact_path.name, "printed_toc": counts}
        spec = REFERENCE_BOOKS[args.book]
        try:
            from step6_run import reference_titles

            titles = reference_titles(spec, gold)
            pages = list(extractor.extract_pages(source))
            headings = [u for u in gold.units if u["kind"] == "heading"]
            before = _navigation(printed, headings, titles, pages, 90.0)
            after = _navigation(resolved, headings, titles, pages, 90.0)
            navigation["title_and_target"] = {
                "before": {k: v for k, v in before.items() if k != "matches"},
                "after": {k: v for k, v in after.items() if k != "matches"},
            }
        except Exception as error:  # reference XML unavailable: counts still stand
            navigation["title_and_target_error"] = repr(error)

    boxes = [g for g in book.groups if g.role == "repeated_box"]
    summary = {
        "book": args.book,
        "split": split,
        "pages": book.pages,
        "furniture_producer_sha256": LOADED_DIGEST,
        "book_cache_key": book_key,
        "book_cache_hit": hit,
        "cache_key_inputs": book.cache_key_inputs,
        "gates": {
            "lines": lines_total,
            "lines_ordered_once": lines_ordered,
            "invariant_problems": problems,
            "pages_rebuilt": rebuilt_pages,
        },
        "body_style": book.body_style,
        "role_lines": dict(role_lines),
        "stream_lines": dict(stream_lines),
        "furniture_stream_lines": dict(furniture_stream_roles),
        "runs": [r.model_dump() for r in book.runs],
        "marker_sources": dict(Counter(m.source for m in book.markers)),
        "marker_review": sum(m.review_required for m in book.markers),
        "unlabelled_pages": [m.page for m in book.markers if m.label is None],
        "inferred_pages": [m.page for m in book.markers if m.source == "inferred"],
        "metadata_comparison": book.metadata_comparison,
        "groups": [
            {
                "id": g.id,
                "role": g.role,
                "edge": g.edge,
                "pages": len(g.pages),
                "page_range": [g.pages[0], g.pages[-1]],
                "lines": len(g.line_ids),
                "confidence": g.confidence,
                "sample": texts.get((g.role, g.id)),
                "evidence": g.evidence,
            }
            for g in book.groups
        ],
        "repeated_boxes": {
            "groups": len(boxes),
            "lines": role_lines["repeated_box"],
            "pages": sorted({p for g in boxes for p in g.pages}),
            "stream_kinds": dict(box_stream_kinds),
            "stays_content": "furniture" not in box_stream_kinds,
        },
        "flagged_for_review": len(flagged),
        "flagged_by_role": dict(Counter(r.role for _, r in flagged)),
        "page_markers": {k: v for k, v in markers.items() if k != "misses"},
        "page_marker_misses": markers["misses"][:50],
        "furniture_precision": precision,
        "recall_proxy": {"alignment": alignment_file, "causes": recall},
        "navigation": navigation,
        "reading_order": {"step8": order_now, "step7": step7},
        "seconds": round(time.perf_counter() - started, 1),
    }
    target = OUT / args.book
    target.mkdir(parents=True, exist_ok=True)
    (target / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    (target / "page_markers.json").write_text(
        json.dumps([m.model_dump() for m in book.markers], indent=0, ensure_ascii=False) + "\n",
        "utf-8",
    )
    (target / "anchor_misses.json").write_text(
        json.dumps(order_detail["anchor_misses"], indent=0) + "\n", "utf-8"
    )
    (target / "per_page_order.json").write_text(
        json.dumps(order_detail["per_page"], indent=0) + "\n", "utf-8"
    )
    with gzip.open(target / "flagged.jsonl.gz", "wt", encoding="utf-8") as handle:
        for number, role in flagged:
            handle.write(json.dumps({"page": number, **role.model_dump()}, ensure_ascii=False))
            handle.write("\n")
    if split == "holdout":
        with log.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "book": args.book,
                        "action": "completed",
                        "furniture_producer_sha256": LOADED_DIGEST,
                        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                )
                + "\n"
            )
    short = {
        k: summary[k]
        for k in ("gates", "role_lines", "marker_sources", "page_markers", "repeated_boxes")
    }
    short["precision"] = precision["precision_proxy"]
    short["order"] = order_now["main_flow"], order_now["float_anchors"]["accuracy"]
    short["step7"] = step7["main_flow"]["pairwise_agreement_pooled"], step7["float_anchors"]
    print(json.dumps(short, indent=1, ensure_ascii=False, default=str)[:6000])


if __name__ == "__main__":
    main()
