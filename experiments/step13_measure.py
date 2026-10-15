"""Step 13a Task 2: how equations appear in the pipeline today, per book, before any change.

Reads only the baseline caches (books 1-4: the Step 12 final run; the math book: the Step 13
``before`` run). For every page it counts the evidence classes:

- text: lines with a math operator (Unicode Sm), Greek letters in a non-Greek line, raised or
  lowered small spans (scripts) attached to an operand vs after a word (note references),
  spans in a math font (font-program evidence);
- vector glyphs: filled outlines at text scale whose shape recurs in the book, and whether
  layout put them in a figure region, another region, or none (then no unit can hold them);
- images: images at glyph scale on a text line.

For the math book, every located gold equation is followed into the pipeline: the layout
region and Step 12 figure record its objects fall in, and the unit beside it.

Usage: python step13_measure.py --book statistics [--run before]
"""

# ruff: noqa: E402
import argparse
import gzip
import json
import statistics
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step13_books import MATH_BOOK
from step13_equations import stage_inputs

from book_core.equations import glyphs, text
from book_core.equations.fonts import FontEvidence
from book_core.figures.cache import load_page as figure_page
from book_core.run_context import open_source, source_session

OUT = ROOT / "experiments/out/step13/measure"
GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK


def _greek(character):
    return "GREEK" in unicodedata.name(character, "")


def measure(book, run):
    inputs = stage_inputs(book, run)
    keys = inputs["keys"]
    counts = Counter()
    landing = Counter()
    examples = {}
    shapes = Counter()
    page_shapes = {}
    gold_by_page = {}
    if book == MATH_BOOK:
        with gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["status"] == "located":
                    gold_by_page.setdefault(row["page"], []).append(row)
    with source_session(inputs["source"]), open_source(inputs["source"]) as document:
        fonts = FontEvidence(document)
        for page in inputs["pages"]():
            number = page.geometry.page
            layout = inputs["layout_of"](page)
            lines = [line for line in layout.lines if line.inside_content and not line.blank]
            sizes = [s.size for s in page.store.spans.values() if s.raw_text.strip() and s.size]
            size = statistics.median(sizes) if sizes else 10.0
            native = inputs["native_of"](number)
            boxes = [page.store.spans[sid].bbox for line in lines for sid in line.span_ids]
            found, bars, signatures = glyphs.page_glyphs(native, size, boxes)
            shapes.update(signatures.values())
            object_region = {o: r.type for r in layout.regions for o in r.object_ids}
            page_shapes[number] = [(o.id, signatures[o.id], object_region.get(o.id)) for o in found]
            math_fonts = fonts.math_fonts(number)
            units = {lid: u for u in inputs["units_of"](number) for lid in u.line_ids}
            for line in lines:
                raw = "".join(page.store.spans[s].raw_text for s in line.span_ids)
                if any(unicodedata.category(c) == "Sm" for c in raw):
                    counts["text_lines_with_operator"] += 1
                letters = [c for c in raw if c.isalpha()]
                greek = [c for c in letters if _greek(c)]
                if greek and len(greek) < 0.5 * len(letters):
                    counts["text_lines_with_greek_in_other_script"] += 1
                if any(page.store.spans[s].font in math_fonts for s in line.span_ids):
                    counts["text_lines_in_math_font"] += 1
                rows = text.line_characters(page.store, line, native.span_geometry)
                if any(r[4] for r in rows):
                    counts["text_lines_with_script_spans"] += 1
                for run_ in text.line_runs(page.store, line, native.span_geometry, math_fonts):
                    counts["text_runs"] += 1
                    for rule in run_.rules:
                        counts[f"text_runs_rule_{rule}"] += 1
                    unit = units.get(line.id)
                    landing[f"text_run_in_{unit.kind if unit else 'no_unit'}"] += 1
                    sample = "".join(page.store.spans[s].raw_text[a:b] for s, a, b in run_.ranges)
                    examples.setdefault(sample, (number, unit.kind if unit else None))
            for obj in native.objects:
                if obj.kind != "image" or obj.bbox is None:
                    continue
                height = obj.bbox.y1 - obj.bbox.y0
                if height <= glyphs.GLYPH_MAX_HEIGHT * size and any(
                    min(obj.bbox.y1, b.y1) - max(obj.bbox.y0, b.y0) > 0 for b in boxes
                ):
                    counts["glyph_scale_images_on_text_lines"] += 1
            for row in gold_by_page.get(number, []):
                ids = set(row["object_ids"])
                regions = {object_region.get(o, "none") for o in ids} or {"text_tokens"}
                landing[
                    f"gold_{row['presentation']}_layout_region_" + "+".join(sorted(regions))
                ] += 1
            del native
        recurring = glyphs.recurring(shapes)
        for rows in page_shapes.values():
            for _id, signature, region in rows:
                if signature in recurring:
                    counts["vector_glyphs_recurring"] += 1
                    counts[f"vector_glyphs_in_region_{region or 'none'}"] += 1
        counts["vector_glyph_shapes_recurring"] = len(recurring)
        counts["fonts_math"] = sum(1 for r in fonts.by_xref.values() if r.get("math_font"))
        counts["fonts_read"] = sum(1 for r in fonts.by_xref.values() if r.get("readable"))
        counts["fonts"] = len(fonts.by_xref)
    figure_objects = 0
    if book == MATH_BOOK:
        for number, rows in gold_by_page.items():
            figures = figure_page(inputs_cache(), keys["figures"], number).figures
            boxes = [f.bbox for f in figures]
            for row in rows:
                x0, y0, x1, y1 = row["bbox"]
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                if any(b.x0 <= cx <= b.x1 and b.y0 <= cy <= b.y1 for b in boxes):
                    figure_objects += 1
                    landing[f"gold_{row['presentation']}_inside_exported_figure"] += 1
    result = {
        "book": book,
        "run": run,
        "pages": inputs["total"],
        "evidence": dict(sorted(counts.items())),
        "landing": dict(sorted(landing.items())),
        "text_run_examples": [
            {"text": k, "page": v[0], "unit_kind": v[1]} for k, v in list(examples.items())[:60]
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{book}.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False) + "\n", "utf-8", newline="\n"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "text_run_examples"}, indent=1))


def inputs_cache():
    from step7_layouts import CACHE

    return CACHE


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--run", default="step12")
    args = parser.parse_args()
    measure(args.book, args.run)
