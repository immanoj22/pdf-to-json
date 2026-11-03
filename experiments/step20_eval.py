"""Step 20 reference metrics on a Step 20 run (``step20_run.py``): the Step 17 JSON evaluators
(paragraphs, lists, reading order, joined tables) plus tables, in-cell text order, headings,
continuity joins, lossless accounting and review counts, all from the run's own caches.

The development helpers read caches from fixed Step 7-11 roots; ``run_book`` keeps every stage
under one root, so each root is pointed at the run's cache before the helpers are imported.
One book per process.

Step 20 books: ``art_lab`` is scored against its derived gold (Jaypee's delivery,
``step20_gold.py``); ``iap_mec`` and ``trichology`` have no reference, so only the machine
measures run (lossless, review, archive order) and ``step20_checks.py`` adds the rest.

Usage: python step20_eval.py --book medical_anatomy --tag before
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
OUT = ROOT / "experiments/out/step20"
NEW_BOOKS = {"art_lab": "jaypee_art_pdf", "iap_mec": "iap_mec_pdf", "trichology": "trichology_pdf"}
NO_REFERENCE = {"iap_mec", "trichology"}


def point_helpers(record):
    """Point the development cache roots and the capture at this run."""
    root = Path(record["cache"])
    import step7_layouts
    import step13_books

    for book, key in NEW_BOOKS.items():  # this process only; older scripts keep their registry
        step13_books.BOOKS.setdefault(book, (key, "development"))

    step7_layouts.CACHE = root
    import step8_run

    step8_run.CACHE8 = root
    import step9_run

    step9_run.CACHE9 = root
    import step10_run

    step10_run.CACHE10 = root
    import step11_run

    step11_run.CACHE11 = root
    import step14a_common as common
    from book_core.lists.keys import book_fingerprint

    common.CACHE, common.CACHE11 = root, root
    run = record["run"]
    found = dict(run["cache_keys"])
    found["_pages"], found["_capture"] = run["pages"], str(OUT / record["tag"])
    lists = found["lists"]
    found["lists_fp"] = book_fingerprint(lists) if isinstance(lists, dict) else lists
    common.keys = lambda book, capture=None: found
    return common


def tables(book, common, book_json, views, owner):
    """Every reference table segment: detection, TEDS (structure, full), adjacency, headers,
    and the in-cell text order that TEDS ignores."""
    from book_core.evaluation import table_scoring

    gold_rows = common.gold_tables(book)
    if not gold_rows:
        return None
    gold = table_scoring.gold_segments(gold_rows)
    ours, count = {}, Counter()
    for top in book_json["content"]:
        for node in _nodes(top):
            if node.get("type") != "table":
                continue
            page = node["pages"][0]
            grid = _grid(node, page, views)
            if grid["cells"]:
                ours[(page, count[page])] = grid  # the scorer's keys: (page, index)
                count[page] += 1
    scores = table_scoring.score(gold, ours)
    scores.pop("matches", None)
    return scores


def _nodes(node):
    yield node
    for key in ("content", "children", "items"):
        for child in node.get(key) or ():
            if isinstance(child, dict):
                yield from _nodes(child)
    for cell in node.get("cells") or ():
        for child in cell.get("content") or ():
            yield from _nodes(child)


def _grid(table, page, views):
    """Our grid: cells with their tokens, and each cell's tokens in emitted order."""
    tokens_by_line = {}
    span_tokens = {}
    for ordinal, (lid, span_ids) in enumerate(views[page]):
        if lid:
            tokens_by_line.setdefault(lid[:16], []).append((page, ordinal))
        for sid in span_ids:
            span_tokens.setdefault(sid[:16], []).append((page, ordinal))
    cells, sequences = [], {}
    header_rows = 0
    for cell in table["cells"]:
        sequence = []
        for node in cell.get("content") or ():
            for inner in _nodes(node):
                refs = inner.get("refs") or {}
                for prefix in refs.get("lines", []):
                    sequence += [t for t in tokens_by_line.get(prefix, []) if t not in sequence]
                for ref in refs.get("spans", []):
                    sequence += [t for t in span_tokens.get(ref["span"], []) if t not in sequence]
        index = len(cells)
        cells.append((cell["row"], cell["column"], cell.get("row_span", 1),
                      cell.get("column_span", 1), bool(cell.get("header")),
                      frozenset(sequence)))  # fmt: skip
        sequences[index] = sequence
        if cell.get("header"):
            header_rows = max(header_rows, cell["row"] + cell.get("row_span", 1))
    return {"cells": cells, "header_rows": header_rows, "sequences": sequences}


def headings(book, record, common):
    """Heading precision/recall, levels and roles against the derived gold (Step 10 scorer),
    and how many heading decisions are flagged for review."""
    from book_core.evaluation.structure import heading_scores
    from book_core.objects.analysis import verified_read
    from book_core.structure.evidence import _read
    from book_core.structure.models import BookStructure

    root, keys = Path(record["cache"]), record["run"]["cache_keys"]
    evidence = _read(
        root / "structure/evidence" / f"{keys['structure_evidence']}.json.gz",
        keys["structure_evidence"],
    )
    structure = verified_read(
        root / "structure/book" / f"{keys['structure']}.json", BookStructure, keys["structure"]
    )
    unit_tokens = {u["unit"]: [(p["page"], o) for o in u["token_ordinals"]]
                   for p in evidence["pages"] for u in p["units"]}  # fmt: skip
    zone_of = {z.page: z.zone for z in structure.page_zones}
    scores = heading_scores(common.derived_gold(book), structure.headings, unit_tokens, zone_of)
    scores["headings"] = len(structure.headings)
    scores["review_required"] = sum(h.review_required for h in structure.headings)
    return scores


def heading_flags(book, common, book_json, owner, units):
    """Heading errors against the derived gold and whether a heading review item marks them:
    missed headings (the owning node), false headings and wrong levels. Every heading flag is
    also classified by what it points at (a real error, a correct heading, correct body text
    or unaligned text), overall and per reason, for flag precision; wrong levels are listed."""
    gold = common.derived_gold(book)
    reasons = {}
    for item in book_json["review"]["items"]:
        if item["kind"] == "heading":
            reasons.setdefault(item["unit"], set()).add(item["reason"])
    flagged = set(reasons)
    gold_of = {}
    for unit in gold.units:
        for page, first, length in unit["pdf"]:
            for ordinal in range(first, first + length):
                gold_of[(page, ordinal)] = unit
    rows, verdict, wrong_levels = Counter(), {}, []
    for unit in gold.units:
        if unit["kind"] != "heading" or not unit["pdf"]:
            continue
        tokens = [(p, o) for p, f, n in unit["pdf"] for o in range(f, f + n)]
        held = Counter(owner[t] for t in tokens if t in owner)
        if not held:
            continue
        node = held.most_common(1)[0][0]
        if units[node]["type"] != "heading":
            kind = "missed"
        elif units[node]["node"].get("level") != unit["heading_level"]:
            kind = "wrong_level"
            wrong_levels.append({"page": units[node]["page"], "unit": node,
                                 "gold_level": unit["heading_level"],
                                 "our_level": units[node]["node"].get("level"),
                                 "flagged": node in flagged})  # fmt: skip
        else:
            kind = "correct"
        rows[kind] += 1
        rows[f"{kind}_flagged"] += node in flagged
        verdict.setdefault(node, kind)
    by_node = {}
    for token, node in owner.items():
        if token in gold_of:
            by_node.setdefault(node, Counter())[gold_of[token]["kind"] == "heading"] += 1
    for node, kinds in by_node.items():
        if units[node]["type"] == "heading" and kinds[True] * 2 < sum(kinds.values()):
            rows["false"] += 1
            rows["false_flagged"] += node in flagged
            verdict[node] = "false"
    errors = rows["missed"] + rows["wrong_level"] + rows["false"]
    caught = rows["missed_flagged"] + rows["wrong_level_flagged"] + rows["false_flagged"]
    targets, per_reason = Counter(), {}
    for node, found in reasons.items():
        kind = verdict.get(node) or ("correct_text" if node in by_node else "unaligned")
        targets[kind] += 1
        for reason in found:
            per_reason.setdefault(reason, Counter())[kind] += 1
    on_error = sum(targets[k] for k in ("missed", "wrong_level", "false"))
    aligned = on_error + targets["correct"] + targets["correct_text"]
    return {**rows, "errors": errors, "errors_flagged": caught,
            "flag_recall": round(caught / errors, 4) if errors else None,
            "heading_items": len(flagged), "flag_targets": dict(targets),
            "flag_precision": round(on_error / aligned, 4) if aligned else None,
            "by_reason": {r: dict(c) for r, c in per_reason.items()},
            "wrong_levels": sorted(wrong_levels, key=lambda r: r["page"])}  # fmt: skip


def joins(book, common, owner, units):
    """Published continuation links. Column links are scored against the derived gold (a
    link is correct when both endpoints' tokens lie mostly in one reference unit, wrong when
    in different units, unscored when either side is unaligned). The reference often splits
    a paragraph at a page marker, so page links are not scored here: their endpoints (first
    token of each side) are listed for a before/after difference and a hand check."""
    gold = common.derived_gold(book)
    gold_of = {}
    for unit in gold.units:
        for page, first, length in unit["pdf"]:
            for ordinal in range(first, first + length):
                gold_of[(page, ordinal)] = unit["unit"]
    tokens_of = {}
    for token, node in owner.items():
        tokens_of.setdefault(node, []).append(token)

    def reference(node):
        held = Counter(gold_of[t] for t in tokens_of.get(node, ()) if t in gold_of)
        return held.most_common(1)[0][0] if held else None

    rows, endpoints = Counter(), []
    for node, row in units.items():
        link = row["node"].get("continues_to")
        if not link or link.get("unit") not in units:
            continue
        kind = link.get("kind", "page")
        rows[f"{kind}_links"] += 1
        first = [min(tokens_of.get(n, [(0, 0)])) for n in (node, link["unit"])]
        endpoints.append([kind, *first])
        if kind == "page":
            continue
        a, b = reference(node), reference(link["unit"])
        if a is None or b is None:
            rows[f"{kind}_unscored"] += 1
        else:
            rows[f"{kind}_{'correct' if a == b else 'wrong'}"] += 1
    scored = rows["column_correct"] + rows["column_wrong"]
    precision = round(rows["column_correct"] / scored, 4) if scored else None
    return {**rows, "column_precision": precision, "endpoints": sorted(endpoints)}


def lossless(record):
    from book_core.assembly.lossless import compare
    from book_core.cache_store import read_json
    from book_core.ledger.tokenization import token_counter
    from book_core.model.spans import ExtractedPage

    retained, discarded = Counter(), Counter()
    for path in sorted(Path(record["run"]["output"]).glob("page_*.json.gz")):
        page = ExtractedPage.model_validate(read_json(path)["source"])
        for line in page.store.lines:
            tokens = token_counter(page.store.raw_line_text(line))
            (retained if page.geometry.content_bbox.contains_center(line.bbox)
             else discarded).update(tokens)  # fmt: skip
    data = json.loads((Path(record["run"]["book_json"]) / "book.json").read_text("utf-8"))
    result = compare(data, retained, discarded)
    return {k: v for k, v in result.items() if not isinstance(v, (dict, list)) or len(v) < 50}


def review(record):
    data = json.loads((Path(record["run"]["book_json"]) / "book.json").read_text("utf-8"))
    items = data["review"]["items"]
    per_target = Counter((i["unit"], i["page"] if i["unit"] is None else None, i["reason"])
                         for i in items)  # fmt: skip
    return {
        "items": len(items),
        "targets": len({(i["unit"], i["page"]) for i in items}),
        "duplicate_target_reason": sum(n - 1 for n in per_target.values() if n > 1),
        "by_kind": dict(Counter(i["kind"] for i in items).most_common()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    record = json.loads((OUT / args.tag / "performance" / f"{args.book}.json").read_text("utf-8"))
    record["tag"] = args.tag
    common = point_helpers(record)
    import step17_json_eval as json_eval

    book_json = json.loads((Path(record["run"]["book_json"]) / "book.json").read_text("utf-8"))
    archive = Path(record["run"]["output"])
    lines, spans, units = json_eval.json_view(book_json)
    owner, views = json_eval.owners_of(args.book, lines, spans, record["run"]["pages"])
    result = {"book": args.book, "tag": args.tag, "owned_tokens": len(owner)}
    if args.book != common.MATH_BOOK and args.book not in NO_REFERENCE:
        result["paragraphs"] = json_eval.paragraphs(args.book, owner, book_json)
        result["lists"] = json_eval.lists(args.book, owner, units, book_json, views)
        result["reading_order"] = json_eval.reading_order(args.book, owner, book_json, views)
        result["tables"] = tables(args.book, common, book_json, views, owner)
        result["headings"] = headings(args.book, record, common)
        result["joins"] = joins(args.book, common, owner, units)
        result["heading_flags"] = heading_flags(args.book, common, book_json, owner, units)
    result["main_flow_order_vs_archive"] = json_eval.order_agreement(
        args.book, owner, book_json, archive
    )
    result["lossless"] = lossless(record)
    result["review"] = review(record)
    common.write(OUT / args.tag / "eval" / f"{args.book}.json", result)
    print(json.dumps({k: v for k, v in result.items() if k in {"lossless", "review"}}, default=str))


if __name__ == "__main__":
    main()
