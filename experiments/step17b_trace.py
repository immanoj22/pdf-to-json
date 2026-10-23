"""Read-only causal traces for Step 17b; no cache writes or production monkeypatches."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.assembly.text import _source_grouped, build_text, ordered_spans
from book_core.cache_store import read_json
from book_core.model.spans import ExtractedPage
from step7_layouts import CACHE
from step17_json_eval import walk
from step17b_investigate import OUT, write


def ownership():
    results = {}
    for book, data in json.loads((OUT / "inputs.json").read_text()).items():
        doc = json.loads(Path(data["json"]).read_text("utf-8"))
        counts = Counter()
        samples = []
        for top in doc["content"]:
            for node, *_ in walk(top):
                if node.get("type") != "paragraph" or node.get("role") != "figure_text":
                    continue
                counts["flagged"] += 1
                counts["in_table_cell" if node.get("_cell") else "outside_table_cell"] += 1
                samples.append({"unit": node['id'], "page": node['pages'][0],
                                "table": node.get('_table'), "cell": node.get('_cell')})
        results[book] = {"counts": dict(counts), "units": samples}
        print(book, dict(counts), flush=True)
    write(OUT / "figure_ownership_trace.json", results)


def rotations():
    data = json.loads((OUT / "inputs.json").read_text())["spanish_us_history"]
    rows = []
    for path in sorted(Path(data["archive"]).glob("page_*.json.gz")):
        payload = read_json(path)
        page = ExtractedPage.model_validate(payload['source'])
        spans = ordered_spans(page.store)
        for unit in payload['units']['units']:
            pieces = [(lid, [(s, None, None) for s in payload['line_spans'].get(lid, [])])
                      for lid in unit['line_ids']]
            regrouped = _source_grouped(pieces, spans)
            if pieces == regrouped:
                continue
            # Explicit identity assembly of the pre-regrouping evidence, no runtime patch.
            text, previous = '', None
            for _, refs in pieces:
                for sid, _, _ in refs:
                    if previous is not None and spans[sid].line_id != previous:
                        text += '\n'
                    text += spans[sid].text
                    previous = spans[sid].line_id
            after = build_text(pieces, spans).content.text
            rows.append({"page": page.geometry.page, "unit": unit['id'], "kind": unit['kind'],
                         "before": text, "after": after, "span_count": sum(len(r) for _, r in pieces)})
        if page.geometry.page % 100 == 0:
            print('rotation trace', page.geometry.page, flush=True)
    write(OUT / "rotation_trace.json", {"primary_split_letter_rule":
                                       "equations.text.line_runs: _split_at_scripts only on line.horizontal",
                                       "secondary_assembly_rule": "assembly.text._source_grouped",
                                       "changed_units": len(rows), "rows": rows,
                                       "existing_direct_angle_regression_tests": [],
                                       "test_gap": "Step 17 has no dedicated 90/270/arbitrary-angle label regression; page-rotation and rotated-math tests do not cover it."})
    print('rotation trace changed', len(rows), flush=True)


def underline_paths():
    rows = json.loads((OUT / "style_verdicts.json").read_text("utf-8"))
    traced = []
    for row in rows:
        if row['verdict'] != 'wrong':
            continue
        run = json.loads((ROOT / f"experiments/out/step17/final/performance/{row['book']}.json").read_text())['run']
        data = json.loads(read_json(CACHE / 'native' / run['cache_keys']['native'] / f"{row['page']}.json")['payload'])
        x0, y0, x1, _y1 = row['box']
        spans = data['page']['store']['spans']
        targets = [p for p in spans.values() if abs(p['bbox']['x0']-x0)<1 and abs(p['bbox']['y0']-y0)<1]
        matches = []
        for p in targets[:1]:
            base = data['span_geometry'][p['id']]['origin'][1]
            size = p['size']
            for obj in data['objects']:
                z = obj.get('bbox')
                if (obj['kind'] == 'drawing' and z and z['y1']-z['y0'] <= 1.6 and z['x1']-z['x0'] > 2
                        and base-.05*size <= (z['y0']+z['y1'])/2 <= base+.35*size
                        and z['x0'] >= x0-size and z['x1'] <= x1+size):
                    matches.append({k: obj.get(k) for k in ('bbox', 'stroke_width', 'fill', 'stroke', 'path_items')})
        traced.append({"sample_id": row['sample_id'], "matched_drawing_primitives": matches})
    write(OUT / 'underline_path_trace.json', traced)


def target_boxes():
    """Disambiguate repeated styled text in ID-less cells by exact source references."""
    import gzip

    import pymupdf
    from book_core.assembly.build import sid
    from reference_paths import reference_path
    from step17b_investigate import render_crop

    rows = json.loads((OUT / "style_verdicts.json").read_text("utf-8"))
    inputs = json.loads((OUT / "inputs.json").read_text("utf-8"))
    results = []
    for row in rows:
        if row["unit"] is not None or row["box_matches"] <= 1:
            continue
        book = inputs[row["book"]]
        payload = read_json(Path(book["archive"]) / f"page_{row['page']:06d}.json.gz")
        page = ExtractedPage.model_validate(payload["source"])
        spans = ordered_spans(page.store)
        line_of = {sid(k): k for k in payload["line_spans"]}
        span_of = {sid(k): k for k in spans}
        pieces = [(line_of[k], [(s, None, None) for s in payload["line_spans"][line_of[k]]])
                  for k in row["refs"]["lines"]]
        pieces += [(spans[span_of[r["span"]]].line_id,
                    [(span_of[r["span"]], r["start"], r["end"])]) for r in row["refs"]["spans"]]
        built = build_text(pieces, spans)
        assert built.content.text == row["unit_text"], row["sample_id"]
        selected = [s.span.bbox for s in built.segments
                    if s.start < row["end"] and s.end > row["start"]]
        box = [min(b.x0 for b in selected), min(b.y0 for b in selected),
               max(b.x1 for b in selected), max(b.y1 for b in selected)]
        with gzip.open(ROOT / f"experiments/out/step17/styling/{row['book']}_spans.json.gz",
                       "rt", encoding="utf-8") as stream:
            candidates = [r["box"] for r in json.load(stream) if
                          (r["page"], r["kind"], r["text"]) ==
                          (row["page"], row["kind"], row["text"])]
        chosen = min(candidates, key=lambda b: sum(abs(a-c) for a, c in zip(b, box, strict=True)))
        dest = OUT / "target_recheck" / f"{row['sample_id']}.png"
        dest.parent.mkdir(exist_ok=True)
        corrected = {**row, "box": chosen}
        with pymupdf.open(reference_path(book["pdf_key"])) as document:
            render_crop(document, corrected, dest)
        results.append({"sample_id": row["sample_id"], "original_box": row["box"],
                        "source_ref_box": box, "chosen_box": chosen,
                        "crop_changed": chosen != row["box"], "crop": str(dest.relative_to(OUT))})
    write(OUT / "target_disambiguation.json", results)
    print(json.dumps(results), flush=True)


def index_page_styles():
    """Distinguish spans on index pages from spans nested in index-entry lists."""
    from collections import Counter

    from step17b_investigate import CELLS, walk

    inputs = json.loads((OUT / "inputs.json").read_text("utf-8"))
    indexes = json.loads((OUT / "index_sample.json").read_text("utf-8"))
    results = {}
    for book, kinds in CELLS.items():
        data = json.loads(Path(inputs[book]["json"]).read_text("utf-8"))
        index_pages = set(indexes[book]["index_pages"])
        counts = Counter()
        for top in data["content"]:
            for node, _, pages in walk(top):
                if not pages or pages[0] not in index_pages or not isinstance(node.get("content"), dict):
                    continue
                for span in node["content"]["spans"]:
                    counts.update(("bold", "italic") if span["kind"] == "bold_italic"
                                  else (span["kind"],))
        for kind in kinds:
            results[book + "-" + kind] = {"on_index_pages": counts[kind],
                                          "index_pages": sorted(index_pages)}
    write(OUT / "index_page_style_census.json", {"cells": results,
          "scope": "All content spans whose first source page is an index page, including letter/title headings outside entry lists. Furniture is separate."})
    print({k: v["on_index_pages"] for k, v in results.items()}, flush=True)


if __name__ == '__main__':
    {"ownership": ownership, "rotations": rotations, "underlines": underline_paths,
     "target_boxes": target_boxes, "index_page_styles": index_page_styles}[sys.argv[1]]()
