"""Step 4a-v: the unchanged 4a pipeline on 15 approved unseen pages.

Cuts single-page fixtures into experiments/fixtures_unseen/, renders --regions overlays through
the CLI, and writes layout summaries, grouped review flags and text gates to
experiments/out/step4av/. No pipeline code or threshold is changed here.
"""

import contextlib
import hashlib
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf
from book_core.cli import main as cli_main
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.layout.models import PageLayout
from book_core.ledger.accounting import check
from book_core.ledger.tokenization import token_counter
from book_core.objects.analysis import analyze_page, cached_repetition
from recreate_unseen_fixtures import cut as cut_page
from step4av_scan import SOURCES

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step4av"
FIX = ROOT / "experiments/fixtures_unseen"
CACHE = ROOT / ".cache/objects"
FIX.mkdir(parents=True, exist_ok=True)
CANDIDATES = json.loads((OUT / "candidates.json").read_text("utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cut(row):
    dest = FIX / f"{row['id']}.pdf"
    cut_page(SOURCES[row["source_key"]], row["physical_page"], dest)
    with pymupdf.open(SOURCES[row["source_key"]]) as doc:
        page = doc[row["physical_page"] - 1]
        geometry = {
            "width": page.rect.width,
            "height": page.rect.height,
            "rotation": page.rotation,
            "trimbox": list(page.trimbox),
        }
    return dest, geometry


def source_page_counter(row):
    """Independent cross-check: tokens of the original source page read directly with PyMuPDF,
    lines kept by line centre inside the TrimBox (the benchmark frame policy)."""
    with pymupdf.open(SOURCES[row["source_key"]]) as doc:
        page = doc[row["physical_page"] - 1]
        frame = page.trimbox
        counter = Counter()
        data = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT)
        for block in data["blocks"]:
            for line in block.get("lines", []):
                text = "".join(c["c"] for s in line["spans"] for c in s["chars"])
                if not text.strip():
                    continue
                x0, y0, x1, y1 = line["bbox"]
                if frame.contains(pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)):
                    counter.update(token_counter(text))
    return counter


CAUSES = [
    (r"clip|group|graphics-state", "clip / group graphics state"),
    (r"insufficient|unknown role|no confident", "unknown role (insufficient native evidence)"),
    (r"blend", "non-normal blend"),
    (r"overpaint", "overpainted image"),
    (r"paint association", "paint association unavailable"),
    (r"bounds", "no visible bounds"),
    (r"confidence|uncertain", "low confidence"),
]


def cause(flag, layout):
    if flag.subject_kind == "band":
        band = next(b for b in layout.bands if b.id == flag.subject_id)
        unknown = any(lane.kind == "unknown" for lane in band.lanes)
        return f"band - low confidence {band.confidence:.2f}" + (
            " (unknown lane)" if unknown else ""
        )
    if flag.subject_kind == "region":
        region = next(r for r in layout.regions if r.id == flag.subject_id)
        return "region - unknown: " + "; ".join(region.reasons)
    if flag.subject_kind == "visual_object":
        for pattern, label in CAUSES:
            if re.search(pattern, flag.reason, re.I):
                return f"visual object - {label}"
        return f"visual object - {flag.reason}"
    return f"{flag.subject_kind} - {flag.reason}"


def main():
    backend = PyMuPDFExtractor()
    manifest, summaries, gates, flags_by_cause, per_page_causes = [], [], [], Counter(), {}
    for row in CANDIDATES:
        fid = row["id"]
        dest, geometry = cut(row)
        png = OUT / f"{fid}_regions.png"
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            cli_main(
                [
                    "overlay",
                    str(dest),
                    "--page",
                    "1",
                    "--regions",
                    "--out",
                    str(png),
                    "--cache-dir",
                    str(CACHE),
                ]
            )
        cli_result = json.loads(captured.getvalue())
        layout = PageLayout.model_validate_json(png.with_suffix(".json").read_text("utf-8"))
        analysis = analyze_page(dest, 1, backend, cached_repetition(dest, backend, CACHE), CACHE)
        store = analysis.native.page.store
        document, ledger = provision_page(analysis.native.page)
        expected = source_page_counter(row)
        report = check(document, ledger, expected)
        roles = Counter(d.role for d in analysis.asset_ledger.records)
        invisible = sum(
            1
            for o in analysis.native.objects
            if o.kind == "text"
            and o.render_info
            and all(i.render_type == 3 or i.opacity == 0 for i in o.render_info)
        )
        gates.append(
            {
                "fixture": fid,
                **report.model_dump(),
                "passing": report.passing,
                "native_spans": len(store.spans),
                "native_text_chars": sum(len(s.text) for s in store.spans.values()),
            }
        )
        page_scope = layout.scopes[0].id
        summaries.append(
            {
                "fixture": fid,
                "source_key": row["source_key"],
                "physical_page": row["physical_page"],
                "covers": row["covers"],
                "resolved_device": cli_result.get("resolved_device"),
                "visual_lines": len(layout.lines),
                "rotated_lines": sum(not ln.horizontal and not ln.blank for ln in layout.lines),
                "text_directions": dict(Counter(str(ln.text_direction) for ln in layout.lines)),
                "blocks": dict(Counter(b.kind for b in layout.blocks)),
                "scopes": len(layout.scopes),
                "bands": [
                    {
                        "scope": "page" if band.scope_id == page_scope else "callout",
                        "y": [round(band.bbox.y0, 1), round(band.bbox.y1, 1)],
                        "x": [round(band.bbox.x0, 1), round(band.bbox.x1, 1)],
                        "columns": band.column_count,
                        "lanes": [lane.kind for lane in band.lanes],
                        "lane_x": [[round(lane.x0), round(lane.x1)] for lane in band.lanes],
                        "confidence": round(band.confidence, 3),
                        "review_required": band.review_required,
                        "reasons": band.reasons,
                    }
                    for band in layout.bands
                ],
                "regions": dict(Counter(r.type for r in layout.regions)),
                "unknown_regions_proposed_as": dict(
                    Counter(str(r.proposed_type) for r in layout.regions if r.type == "unknown")
                ),
                "asset_roles": dict(roles),
                "invisible_text_objects": invisible,
                "diagnostics": layout.diagnostics,
            }
        )
        causes = Counter(cause(f, layout) for f in layout.review_flags)
        per_page_causes[fid] = dict(causes)
        flags_by_cause.update(causes)
        manifest.append(
            {
                **row,
                **geometry,
                "fixture": str(dest.relative_to(ROOT)).replace("\\", "/"),
                "fixture_sha256": sha(dest),
                "source_sha256": sha(SOURCES[row["source_key"]]),
            }
        )
        print(
            fid,
            len(layout.bands),
            "bands",
            report.passing,
            report.expected_missing_token_count,
            report.expected_extra_token_count,
            flush=True,
        )
    for name, value in [
        ("fixtures_manifest.json", manifest),
        ("layout_summary.json", summaries),
        ("text_gate.json", gates),
        (
            "review_flags_by_cause.json",
            {"total": dict(flags_by_cause.most_common()), "per_page": per_page_causes},
        ),
    ]:
        (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", "utf-8")


if __name__ == "__main__":
    sys.exit(main())
