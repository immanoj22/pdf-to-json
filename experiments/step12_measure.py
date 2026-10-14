"""Step 12 Task 1: measure figures, captions, credits and figure text before any change.

Per book, from the cached current outputs (no producer runs): the reference figure inventory
(``step12_reference``) next to our layout figure blocks, figure/credit streams and caption
units; per-page figure detection precision/recall on counts; where reference captions,
credits and image-description (figure-internal) tokens end up in our units; geometric figure
text outside figure regions; and failure classes with counts and examples.

Usage: python step12_measure.py --book spanish_us_history [--out before]
"""

# ruff: noqa: E402
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step12_reference as reference

OUT = ROOT / "experiments/out/step12"


def load(book):
    """(gold, pages iterator factory, per-page loader) over the cached current stages."""
    from step9_run import CACHE9
    from step10_run import CACHE10, GOLD, evidence_for, load_book
    from step11_run import CACHE11

    from book_core.evaluation.derived_harness import DerivedGold
    from book_core.lists.cache import analyze_book_lists
    from book_core.lists.cache import load_page as list_page
    from book_core.structure.cache import analyze_book_structure

    loaded = load_book(book)
    source, extractor, inputs, furniture, _, paragraphs, _, _ = loaded
    evidence, evidence_key, _ = evidence_for(book, loaded)
    structure, _ = analyze_book_structure(evidence, evidence_key, CACHE10)
    lists, hit = analyze_book_lists(
        lambda: extractor.extract_pages(source),
        inputs,
        paragraphs,
        CACHE9,
        structure,
        furniture,
        CACHE11,
    )
    if not hit:
        raise SystemExit("Lists were not cached for the current producers")
    gold = DerivedGold.load(GOLD / book)

    def pages():
        for page in extractor.extract_pages(source):
            layout, _ = inputs(page)
            yield page, layout, list_page(lists, page.geometry.page, CACHE11)

    load.context = {"source": source, "extractor": extractor, "inputs": inputs, "lists": lists}
    return gold, pages, furniture, structure


def gold_tokens(gold, inventory):
    """{(page, ordinal): (unit id, kind)} plus credit unit ids (matched by unit path)."""
    credit_paths = {c["unit_path"] for c in inventory["credits"]}
    owner, credit_units = {}, set()
    for unit in gold.units:
        if unit["path"] in credit_paths:
            credit_units.add(unit["unit"])
        for page, first, length in unit["pdf"]:
            for ordinal in range(first, first + length):
                owner[(page, ordinal)] = (unit["unit"], unit["kind"])
    return owner, credit_units


def inside(box, inner):
    cx, cy = (inner.x0 + inner.x1) / 2, (inner.y0 + inner.y1) / 2
    return box.x0 <= cx <= box.x1 and box.y0 <= cy <= box.y1


def measure(book, examples=3):
    from book_core.evaluation.furniture import token_lines
    from book_core.paragraphs.text import unit_text

    inv = reference.inventory(book)
    ref = reference.summary(book, inv)
    gold, pages, _, _ = load(book)
    owner, credit_units = gold_tokens(gold, inv)
    totals = Counter()
    per_page = {}
    caption_fate = defaultdict(Counter)  # reference caption unit -> our (stream kind, unit kind)
    credit_fate = defaultdict(Counter)
    description_fate = Counter()
    geometric = Counter()
    failures = defaultdict(list)
    for page, layout, built in pages():
        number = page.geometry.page
        figures = [b for b in layout.blocks if b.kind == "figure"]
        regions = {r.id: r for r in layout.regions}
        region_of = {lid: r for r in layout.regions for lid in r.line_ids}
        stream_of = {lid: s for s in built.order.streams for lid in s.line_ids}
        unit_of = {lid: u for u in built.units for lid in u.line_ids}
        lines = {line.id: line for line in layout.lines}
        streams = Counter(s.kind for s in built.order.streams)
        ref_row = ref["per_page"].get(str(number), {})
        ref_images = ref_row.get("page_images", 0)
        ours = len(figures)
        totals["our_figures"] += ours
        totals["reference_page_images"] += ref_images
        totals["matched_by_count"] += min(ours, ref_images)
        totals["figure_streams"] += streams["figure"]
        totals["credit_streams"] += streams["credit"]
        totals["caption_units"] += sum(u.kind == "caption" for u in built.units)
        totals["figure_text_units"] += sum(u.kind == "figure_text" for u in built.units)
        totals["captions_in_figure_streams"] += sum(
            u.kind == "caption" and stream_of[u.line_ids[0]].kind in {"figure", "table"}
            for u in built.units
        )
        totals["credit_regions"] += sum(r.type == "credit_candidate" for r in layout.regions)
        totals["credits_in_figure_streams"] += sum(
            r.type == "credit_candidate"
            and r.line_ids
            and stream_of[r.line_ids[0]].kind == "figure"
            for r in layout.regions
        )
        if ours != ref_images and len(failures["count_mismatch"]) < 400:
            failures["count_mismatch"].append(
                {"page": number, "ours": ours, "reference": ref_images}
            )
        # Lines inside a figure block that are not embedded figure text.
        for line in layout.lines:
            if line.blank:
                continue
            box = next((f for f in figures if inside(f.bbox, line.bbox)), None)
            if box is None:
                continue
            region = region_of[line.id]
            unit = unit_of[line.id]
            geometric[f"{region.type}:{unit.kind}"] += 1
            if region.type != "figure" and unit.kind in {"paragraph", "list_item"}:
                failures["figure_text_in_paragraph"].append(
                    {"page": number, "line": line.id[:12], "unit_kind": unit.kind,
                     "text": unit_text(page.store, layout, unit)[:90]}
                )  # fmt: skip
        # Reference tokens: captions, credits and image descriptions.
        for ordinal, lid in enumerate(token_lines(page, layout)):
            hit = owner.get((number, ordinal))
            if hit is None or lid is None:
                continue
            unit_id, kind = hit
            stream, unit = stream_of.get(lid), unit_of.get(lid)
            fate = (stream.kind if stream else None, unit.kind if unit else None)
            if kind == "caption":
                caption_fate[unit_id][fate] += 1
            if unit_id in credit_units:
                credit_fate[unit_id][fate] += 1
            if kind == "image_description":
                description_fate[f"{fate[0]}:{fate[1]}"] += 1
        per_page[number] = {"ours": ours, "reference": ref_images, "streams": dict(streams)}
        # Unknown rotated lines in the main flow beside a figure (the p724 class).
        for line in layout.lines:
            region = region_of[line.id]
            stream = stream_of[line.id]
            if region.type == "unknown" and not line.horizontal and stream.kind == "main":
                near = any(_gap(f.bbox, line.bbox) <= 4 * line.font_size for f in figures)
                totals["unknown_rotated_in_main"] += 1
                totals["unknown_rotated_in_main_near_figure"] += near
                if near:
                    failures["unknown_rotated_in_main_near_figure"].append(
                        {"page": number, "line": line.id[:12],
                         "text": " ".join(page.store.spans[s].raw_text
                                          for s in line.span_ids)[:90]}
                    )  # fmt: skip
        del regions, lines

    def fate_summary(fates):
        rows = Counter()
        for counts in fates.values():
            rows[max(counts, key=counts.get)] += 1
        return {f"{s}:{k}": v for (s, k), v in rows.most_common()}

    linked_captions = sum(
        1
        for counts in caption_fate.values()
        if max(counts, key=counts.get)[0] in {"figure", "table"}
    )
    attached_credits = sum(
        1 for counts in credit_fate.values() if max(counts, key=counts.get)[0] == "figure"
    )
    detection = {
        "precision": _ratio(totals["matched_by_count"], totals["our_figures"]),
        "recall": _ratio(totals["matched_by_count"], totals["reference_page_images"]),
    }
    for page_row in failures["count_mismatch"]:
        cls = "missed" if page_row["ours"] < page_row["reference"] else "extra_or_split"
        failures[cls].append(page_row)
    description_total = sum(description_fate.values())
    in_paragraphs = sum(
        v for k, v in description_fate.items()
        if k.split(":")[1] in {"paragraph", "list_item", "heading_candidate"}
    )  # fmt: skip
    return {
        "book": book,
        "reference": {k: v for k, v in ref.items() if k != "per_page"},
        "ours": dict(totals),
        "figure_detection_by_page_counts": detection,
        "captions": {
            "reference_caption_units_scored": len(caption_fate),
            "linked_to_figure_or_table": linked_captions,
            "link_rate": _ratio(linked_captions, len(caption_fate)),
            "fate": fate_summary(caption_fate),
        },
        "credits": {
            "reference_credit_units_scored": len(credit_fate),
            "attached_to_figure": attached_credits,
            "attach_rate": _ratio(attached_credits, len(credit_fate)),
            "fate": fate_summary(credit_fate),
        },
        "figure_internal_text": {
            "reference_description_tokens": description_total,
            "in_paragraph_like_units": in_paragraphs,
            "share_in_paragraph_like_units": _ratio(in_paragraphs, description_total),
            "by_stream_and_unit": dict(description_fate.most_common()),
            "lines_inside_figure_boxes_by_region_and_unit": dict(geometric.most_common()),
        },
        "failure_classes": {
            name: {"count": len(rows), "examples": rows[:examples]}
            for name, rows in failures.items()
            if name != "count_mismatch"
        },
        "per_page": per_page,
    }


def _gap(a, b):
    dx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    dy = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    return (dx * dx + dy * dy) ** 0.5


def _ratio(a, b):
    return round(a / b, 6) if b else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=sorted(reference.XML_KEYS))
    parser.add_argument("--out", default="before")
    args = parser.parse_args()
    result = measure(args.book)
    target = OUT / "measure" / args.out / f"{args.book}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({k: v for k, v in result.items() if k not in {"per_page"}}, indent=1,
                     ensure_ascii=False)[:6000])  # fmt: skip


if __name__ == "__main__":
    main()
