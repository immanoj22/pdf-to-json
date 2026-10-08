"""Step 4a evidence: layout overlays, gold comparison, token gates and the review list.

Reads only fixtures in this repository; writes under experiments/out/step4a.
"""

import json
import time
from collections import Counter
from pathlib import Path

from book_core.debug.layout_overlay import render_layout_overlay
from book_core.evaluation.layout_gold import evaluate, passes
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.layout.pipeline import analyze_layout
from book_core.ledger.accounting import check

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step4a"
OUT.mkdir(parents=True, exist_ok=True)
CACHE = ROOT / ".cache/objects"
backend = PyMuPDFExtractor()

frozen = json.loads((ROOT / "backend/tests/fixtures/expected_counters.json").read_text("utf-8"))
old = {case["fixture"]: Counter(case["counter"]) for case in frozen["cases"]}
phase0 = json.loads((ROOT / "experiments/out/extractor_results.json").read_text("utf-8"))
baseline = {row["id"]: row["tokens"] for row in phase0 if row["extractor"] == "pymupdf"}

evaluations, gates, layouts_summary, review = [], [], [], {}
for source in sorted((ROOT / "experiments/fixtures").glob("*.pdf")):
    name = source.stem
    start = time.perf_counter()
    layout, analysis = analyze_layout(source, 1, backend, cache_dir=CACHE)
    seconds = time.perf_counter() - start
    render_layout_overlay(backend.render_page(source, 1), layout, OUT / f"{name}_regions.png")
    gold = json.loads((ROOT / "backend/tests/gold" / f"columns_{name}.json").read_text("utf-8"))
    result = evaluate(layout, gold)
    result["passes_band_gate"] = passes(result)
    evaluations.append(result)
    document, ledger = provision_page(analysis.native.page)
    report = check(document, ledger, old.get(name))
    assert report.passing and report.node_token_count == baseline[name]
    gates.append({"fixture": name, **report.model_dump(), "passing": report.passing})
    review[name] = {
        "flags": len(layout.review_flags),
        "by_kind": dict(Counter(flag.subject_kind for flag in layout.review_flags)),
        "visual_object_reasons": dict(
            Counter(f.reason for f in layout.review_flags if f.subject_kind == "visual_object")
        ),
        "bands_and_regions": [
            {"kind": f.subject_kind, "id": f.subject_id[:12], "reason": f.reason}
            for f in layout.review_flags
            if f.subject_kind != "visual_object"
        ],
    }
    layouts_summary.append(
        {
            "fixture": name,
            "seconds_with_cached_objects": round(seconds, 3),
            "visual_lines": len(layout.lines),
            "rotated_lines": sum(not line.horizontal and not line.blank for line in layout.lines),
            "split_native_lines": sum(
                any("split" in reason for reason in line.reasons) for line in layout.lines
            ),
            "joined_native_lines": sum(len(line.source_line_ids) > 1 for line in layout.lines),
            "text_directions": dict(Counter(str(line.text_direction) for line in layout.lines)),
            "blocks": dict(Counter(block.kind for block in layout.blocks)),
            "scopes": len(layout.scopes),
            "bands": [
                {
                    "scope": "page" if band.scope_id == layout.scopes[0].id else "callout",
                    "y": [round(band.bbox.y0, 1), round(band.bbox.y1, 1)],
                    "columns": band.column_count,
                    "lanes": [lane.kind for lane in band.lanes],
                    "confidence": round(band.confidence, 3),
                    "review_required": band.review_required,
                }
                for band in layout.bands
            ],
            "regions": dict(Counter(region.type for region in layout.regions)),
            "diagnostics": layout.diagnostics,
        }
    )
    print(name, result["passes_band_gate"], f"{seconds:.2f}s", flush=True)

regression = []
cases = json.loads((ROOT / "backend/tests/fixtures/image_boundary_manifest.json").read_text("utf-8"))
truths = json.loads(
    (ROOT / "backend/tests/fixtures/image_boundary_expected_counters.json").read_text("utf-8")
)["cases"]
for case in cases["cases"]:
    path = ROOT / "backend/tests/fixtures" / case["fixture"]
    page = next(PyMuPDFExtractor().extract_pages(path))
    document, ledger = provision_page(page)
    report = check(document, ledger, Counter(truths[case["fixture"]]["counter"]))
    regression.append({"fixture": case["fixture"], **report.model_dump(), "passing": report.passing})

for filename, value in [
    ("layout_evaluation.json", evaluations),
    ("fixture_gate.json", gates),
    ("regression_gate.json", regression),
    ("layout_summary.json", layouts_summary),
    ("review_flags.json", review),
]:
    (OUT / filename).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", "utf-8")
print(json.dumps([{"fixture": g["fixture"], "tokens": g["node_token_count"],
                   "missing": g["missing_token_count"], "extra": g["extra_token_count"]}
                  for g in gates + regression]))
