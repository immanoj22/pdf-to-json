"""Step 4a-fix verification: overlays, gold, text gates and invariants before/after.

"Before" layouts are the Step 4a / 4a-v JSON sidecars already in experiments/out (written by
layout-proposals-1); "after" layouts are recomputed with the current pipeline. Invariants are
measured on both with the same checker. Writes only under experiments/out/step4afix.
"""

import contextlib
import io
import json
from collections import Counter
from pathlib import Path

from book_core.cli import main as cli_main
from book_core.evaluation.layout_gold import evaluate, passes
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.layout.invariants import INVARIANTS, check
from book_core.layout.models import PageLayout
from book_core.ledger.accounting import check as ledger_check
from book_core.objects.analysis import analyze_page, cached_repetition
from step4av_run import source_page_counter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step4afix"
CACHE = ROOT / ".cache/objects"
UNSEEN = json.loads((ROOT / "experiments/out/step4av/candidates.json").read_text("utf-8"))
FROZEN = json.loads((ROOT / "backend/tests/fixtures/expected_counters.json").read_text("utf-8"))
OLD = {case["fixture"]: Counter(case["counter"]) for case in FROZEN["cases"]}


def summary(layout):
    page = next(s.id for s in layout.scopes if s.kind == "page")
    kind = {s.id: s.kind for s in layout.scopes}
    return {
        "bands": [
            {
                "scope": kind[b.scope_id],
                "bbox": [round(v, 1) for v in (b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1)],
                "columns": b.column_count,
                "lanes": [lane.kind for lane in b.lanes],
                "confidence": round(b.confidence, 3),
                "review_required": b.review_required,
            }
            for b in sorted(
                layout.bands, key=lambda b: (b.scope_id != page, kind[b.scope_id], b.bbox.y0)
            )
        ],
        "regions": dict(Counter(r.type for r in layout.regions)),
        "scopes": dict(Counter(s.kind for s in layout.scopes)),
        "blocks": dict(Counter(b.kind for b in layout.blocks)),
        "review_flags": len(layout.review_flags),
        "diagnostics": layout.diagnostics,
    }


def old_summary(data):
    page = next(s["id"] for s in data["scopes"] if s["kind"] == "page")
    kind = {s["id"]: s["kind"] for s in data["scopes"]}
    return {
        "bands": [
            {
                "scope": kind[b["scope_id"]],
                "bbox": [round(b["bbox"][k], 1) for k in ("x0", "y0", "x1", "y1")],
                "columns": b["column_count"],
                "lanes": [lane["kind"] for lane in b["lanes"]],
                "confidence": round(b["confidence"], 3),
                "review_required": b["review_required"],
            }
            for b in sorted(
                data["bands"],
                key=lambda b: (b["scope_id"] != page, kind[b["scope_id"]], b["bbox"]["y0"]),
            )
        ],
        "regions": dict(Counter(r["type"] for r in data["regions"])),
        "scopes": dict(Counter(s["kind"] for s in data["scopes"])),
        "blocks": dict(Counter(b["kind"] for b in data["blocks"])),
        "review_flags": len(data["review_flags"]),
    }


def flag_causes(layout):
    causes = Counter()
    bands = {b.id: b for b in layout.bands}
    regions = {r.id: r for r in layout.regions}
    for flag in layout.review_flags:
        if flag.subject_kind == "band":
            band = bands[flag.subject_id]
            unknown = any(lane.kind == "unknown" for lane in band.lanes)
            causes[
                f"band - low confidence {band.confidence:.2f}"
                + (" (unknown lane)" if unknown else "")
            ] += 1
        elif flag.subject_kind == "region":
            causes["region - unknown: " + regions[flag.subject_id].reasons[0]] += 1
        else:
            causes["visual object - " + flag.reason] += 1
    return dict(causes.most_common())


def run_page(name, source, before_json, expected=None):
    backend = PyMuPDFExtractor()
    png = OUT / f"{name}_regions.png"
    with contextlib.redirect_stdout(io.StringIO()) as captured:
        cli_main(
            [
                "overlay",
                str(source),
                "--page",
                "1",
                "--regions",
                "--out",
                str(png),
                "--cache-dir",
                str(CACHE),
            ]
        )
    device = json.loads(captured.getvalue())["resolved_device"]
    layout = PageLayout.model_validate_json(png.with_suffix(".json").read_text("utf-8"))
    analysis = analyze_page(source, 1, backend, cached_repetition(source, backend, CACHE), CACHE)
    before = json.loads(Path(before_json).read_text("utf-8"))
    report = ledger_check(*provision_page(analysis.native.page), expected)
    return {
        "page": name,
        "device": device,
        "overlay": str(png.relative_to(ROOT)).replace("\\", "/"),
        "invariants_before": {k: len(v) for k, v in check(before, analysis).items()},
        "invariants_after": {k: len(v) for k, v in check(layout, analysis).items()},
        "violations_before": check(before, analysis),
        "before": old_summary(before),
        "after": summary(layout),
        "flag_causes": flag_causes(layout),
        "text_gate": {
            "tokens": report.node_token_count,
            "missing": report.missing_token_count,
            "extra": report.extra_token_count,
            "expected_missing": report.expected_missing_token_count,
            "expected_extra": report.expected_extra_token_count,
            "passing": report.passing,
            "native_spans": len(analysis.native.page.store.spans),
        },
    }, layout


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pages, gold = [], []
    for source in sorted((ROOT / "experiments/fixtures").glob("*.pdf")):
        name = source.stem
        row, layout = run_page(
            name, source, ROOT / f"experiments/out/step4a/{name}_regions.json", OLD.get(name)
        )
        result = evaluate(
            layout,
            json.loads((ROOT / f"backend/tests/gold/columns_{name}.json").read_text("utf-8")),
        )
        result["passes_band_gate"] = passes(result)
        gold.append(result)
        row["gold_band_gate"] = result["passes_band_gate"]
        pages.append(row)
        print(name, row["invariants_after"], "gold", result["passes_band_gate"], flush=True)
    for candidate in UNSEEN:
        name = candidate["id"]
        source = ROOT / f"experiments/fixtures_unseen/{name}.pdf"
        if not source.exists():
            raise FileNotFoundError(
                f"{source.name} missing: run experiments/recreate_unseen_fixtures.py"
            )
        row, _ = run_page(
            name,
            source,
            ROOT / f"experiments/out/step4av/{name}_regions.json",
            source_page_counter(candidate),
        )
        row["covers"] = candidate["covers"]
        pages.append(row)
        print(name, row["invariants_before"], "->", row["invariants_after"], flush=True)
    totals = {
        "before": {k: sum(p["invariants_before"][k] for p in pages) for k in INVARIANTS},
        "after": {k: sum(p["invariants_after"][k] for p in pages) for k in INVARIANTS},
    }
    for filename, value in [
        ("pages.json", pages),
        ("layout_evaluation.json", gold),
        ("invariant_totals.json", totals),
    ]:
        (OUT / filename).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(json.dumps(totals))


if __name__ == "__main__":
    main()
