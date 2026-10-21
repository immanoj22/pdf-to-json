"""Step 14a Task 1: measure today's handling of reference tables (before any table stage).

Per book, from the current caches (Step 13c final) and the table gold:

- where table text lands: the unit kind, layout region type and stream kind of the line
  holding each located cell token (titles and notes apart);
- table-cell boundaries: consecutive reference tokens of paragraph-like reference units
  inside table cells, scored like the paragraph metric (tp / fp / fn);
- order inside tables: for pairs of located cells read in one stream, whether our order
  follows the reference (row-major) cell order; the Step 13c within-float metric beside it;
- false figures that are tables: figure records covering at least half of a reference
  table's located box (or the other way round);
- display equation units inside reference tables and their anchor confidence.

Usage: python step14a_measure.py [--book NAME] [--out before]
"""

# ruff: noqa: E402
import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common

from book_core.evaluation.paragraphs import PARAGRAPH_KINDS


def overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def area(a):
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def page_context(book, number):
    layout = common.layout_page(book, number)
    built = common.list_page(book, number)
    owners = common.token_owners(book, number)
    unit_of = {lid: u for u in built.units for lid in u.line_ids}
    region_of = {lid: r for r in layout.regions for lid in r.line_ids}
    position = {}
    for stream in built.order.streams:
        for i, lid in enumerate(stream.line_ids):
            position[lid] = (stream.id, stream.kind, i)
    return layout, built, owners, unit_of, region_of, position


def measure(book, examples=12):
    tables = common.gold_tables(book)
    result = {"tables": len(tables)}
    pages = sorted({p for t in tables for p in t["pages"]})
    context = {n: page_context(book, n) for n in pages}
    landing, title_landing, note_landing = Counter(), Counter(), Counter()
    by_table = []
    order_pairs = Counter()
    cell_unit = {}  # (page, ordinal) -> our unit id, for boundary scoring
    for t in tables:
        if not t["located"]:
            continue
        kinds = Counter()
        for cell in t["cells"]:
            for page, ordinal in cell["tokens"]:
                _, _, owners, unit_of, region_of, _ = context[page]
                line = owners[ordinal] if ordinal < len(owners) else None
                unit = unit_of.get(line)
                region = region_of.get(line)
                key = (
                    unit.kind if unit else "no unit",
                    region.type if region else "no region",
                    unit.stream_kind if unit else "none",
                )
                landing[key] += 1
                kinds[key[0]] += 1
                if unit is not None:
                    cell_unit[(page, ordinal)] = unit.id
        for part, counter in (("title", title_landing), ("notes", note_landing)):
            for page, ordinal in t[part]["tokens"]:
                _, _, owners, unit_of, region_of, _ = context[page]
                line = owners[ordinal] if ordinal < len(owners) else None
                unit, region = unit_of.get(line), region_of.get(line)
                counter[(unit.kind if unit else "no unit", region.type if region else "none")] += 1
        # Cell order: first token of each located cell, reference row-major order.
        firsts = []
        for cell in sorted(t["cells"], key=lambda c: (c["row"], c["column"])):
            if not cell["tokens"]:
                continue
            page, ordinal = cell["tokens"][0]
            _, _, owners, _, _, position = context[page]
            line = owners[ordinal] if ordinal < len(owners) else None
            if line in position:
                firsts.append((page, position[line], ordinal))
        agree = total = 0
        for i in range(len(firsts)):
            for j in range(i + 1, len(firsts)):
                (pa, (sa, _, ia), oa), (pb, (sb, _, ib), ob) = firsts[i], firsts[j]
                if pa != pb or sa != sb:
                    continue
                total += 1
                agree += (ia, oa) <= (ib, ob)
        order_pairs["pairs"] += total
        order_pairs["agree"] += agree
        by_table.append(
            {
                "table": t["table"],
                "pages": t["pages"],
                "rows": t["rows"],
                "columns": t["columns"],
                "unit_kinds": dict(kinds.most_common()),
                "cell_order_agreement": round(agree / total, 4) if total else None,
            }
        )
    result["cell_tokens_by_landing"] = {
        f"{a} | {b} | {c}": n for (a, b, c), n in landing.most_common()
    }
    by_kind = Counter()
    by_region = Counter()
    for (kind, region, _), n in landing.items():
        by_kind[kind] += n
        by_region[region] += n
    total = sum(by_kind.values())
    result["cell_tokens"] = total
    result["cell_tokens_by_unit_kind"] = dict(by_kind.most_common())
    result["cell_tokens_by_region_type"] = dict(by_region.most_common())
    result["share_in_table_regions"] = (
        round(by_region["table_candidate"] / total, 4) if total else None
    )
    result["title_tokens_by_landing"] = {
        f"{a} | {b}": n for (a, b), n in title_landing.most_common()
    }
    result["note_tokens_by_landing"] = {f"{a} | {b}": n for (a, b), n in note_landing.most_common()}
    result["cell_order"] = {
        "pairs_in_one_stream": order_pairs["pairs"],
        "agreement": round(order_pairs["agree"] / order_pairs["pairs"], 4)
        if order_pairs["pairs"]
        else None,
    }
    metrics = common.keys(book)["_capture"]
    summary = Path(metrics) / f"metrics/{book}/summary.json"
    if summary.exists():
        result["within_floats_step13c"] = common.read(summary)["reading_order"]["step11"][
            "within_floats"
        ]
    result["tables_detail"] = by_table
    if book != common.MATH_BOOK and book in common.SHORT and tables:
        result["table_cell_boundaries"] = boundaries(book, tables, examples)
    result["false_figures"] = false_figures(book, tables)
    result["display_equations_in_tables"] = equations_in_tables(book, tables)
    return result


def boundaries(book, tables, examples):
    """Paragraph-metric boundary pairs whose reference tokens both lie in table cells."""
    gold = common.derived_gold(book)
    in_cells = {(p, o) for t in tables for c in t["cells"] for p, o in c["tokens"]}
    sequence = []
    for unit in gold.units:
        if unit["kind"] not in PARAGRAPH_KINDS:
            continue
        for page, first, length in unit["pdf"]:
            for ordinal in range(first, first + length):
                sequence.append((page, ordinal, unit["unit"]))
    logical = {}
    pages = sorted({p for p, _, _ in sequence if any(p in t["pages"] for t in tables)})
    for page in pages:
        _, built, owners, unit_of, _, _ = page_context(book, page)
        from book_core.lists.models import TEXT_KINDS

        for ordinal, line in enumerate(owners):
            unit = unit_of.get(line)
            if unit is not None and unit.kind in TEXT_KINDS:
                logical[(page, ordinal)] = unit.id
    scored = [(p, o, u) for p, o, u in sequence if (p, o) in logical]
    counts, missed = Counter(), defaultdict(int)
    for (p1, o1, u1), (p2, o2, u2) in zip(scored, scored[1:], strict=False):
        if (p1, o1) not in in_cells or (p2, o2) not in in_cells:
            continue
        ref = u1 != u2
        ours = logical[(p1, o1)] != logical[(p2, o2)]
        counts["pairs"] += 1
        counts["tp"] += ref and ours
        counts["fp"] += ours and not ref
        counts["fn"] += ref and not ours
        if ref and not ours:
            missed[p1] += 1
    return {
        **dict(counts),
        "missed_by_page_top": dict(sorted(missed.items(), key=lambda kv: -kv[1])[:examples]),
    }


def false_figures(book, tables):
    """Figures overlapping a reference table's located cell box by half of either box."""
    found = []
    pages = {int(p): [] for t in tables for p in t.get("boxes", {})}
    for t in tables:
        for page, parts in t.get("boxes", {}).items():
            if "cells" in parts:
                pages[int(page)].append((t["table"], parts["cells"]))
    for number, boxes in sorted(pages.items()):
        from book_core.equations.ownership import final_figures

        figures = final_figures(
            common.figure_page(book, number), common.equation_page(book, number)
        ).figures
        for figure in figures:
            fb = [figure.bbox.x0, figure.bbox.y0, figure.bbox.x1, figure.bbox.y1]
            for table, tb in boxes:
                shared = overlap(fb, tb)
                if shared >= 0.5 * min(area(fb), area(tb)) and area(tb) > 0:
                    found.append(
                        {
                            "page": number,
                            "figure": figure.name,
                            "table": table,
                            "share_of_table": round(shared / area(tb), 3),
                            "share_of_figure": round(shared / max(area(fb), 1e-9), 3),
                            "flags": figure.review_flags,
                        }
                    )
    return {"count": len(found), "figures": found}


def equations_in_tables(book, tables):
    rows = Counter()
    examples = []
    boxes = defaultdict(list)
    for t in tables:
        for page, parts in t.get("boxes", {}).items():
            if "cells" in parts:
                boxes[int(page)].append(parts["cells"])
    for number in range(1, common.pages(book) + 1):
        equations = common.equation_page(book, number)
        if not equations.units:
            continue
        layout = common.layout_page(book, number)
        table_regions = [
            [r.bbox.x0, r.bbox.y0, r.bbox.x1, r.bbox.y1]
            for r in layout.regions
            if r.type == "table_candidate"
        ]
        regions = {r.id: r for r in equations.regions}
        for unit in equations.units:
            box = regions[unit.equation_id].bbox
            b = [box.x0, box.y0, box.x1, box.y1]
            in_gold = any(overlap(b, g) >= 0.5 * area(b) for g in boxes.get(number, []))
            in_layout = any(overlap(b, g) >= 0.5 * area(b) for g in table_regions)
            confidence = unit.anchor.confidence
            rows[(round(confidence, 2), in_gold, in_layout)] += 1
            if in_gold and len(examples) < 10:
                examples.append({"page": number, "unit": unit.id, "confidence": confidence})
    return {
        "display_units_by_confidence_in_gold_table_in_layout_table": {
            f"{c} | gold_table={g} | layout_table={lay}": n
            for (c, g, lay), n in sorted(rows.items())
        },
        "examples": examples,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--out", default="before")
    args = parser.parse_args()
    target = common.OUT / "measure" / args.out
    for book in [args.book] if args.book else common.BOOK_ORDER:
        result = measure(book)
        common.write(target / f"{book}.json", result)
        print(
            book,
            {
                k: result.get(k)
                for k in (
                    "tables",
                    "cell_tokens",
                    "share_in_table_regions",
                    "cell_tokens_by_unit_kind",
                    "cell_order",
                    "table_cell_boundaries",
                )
            },  # fmt: skip
            "false figures",
            result["false_figures"]["count"],
            flush=True,
        )


if __name__ == "__main__":
    main()
