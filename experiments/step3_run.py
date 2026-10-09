"""Run cached product analysis on the nine fixtures; no source PDF writes."""
import json
import time
from collections import Counter
from pathlib import Path

from book_core.debug.overlay import render_overlay
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.objects.analysis import analyze_page, verify_asset_ledger

ROOT=Path(__file__).resolve().parents[1]
backend=PyMuPDFExtractor()
output=ROOT/"experiments/out/step3"
output.mkdir(parents=True,exist_ok=True)
rows=[]
for source in sorted((ROOT/"experiments/fixtures").glob("*.pdf")):
    start=time.perf_counter()
    analysis=analyze_page(source,1,backend,cache_dir=ROOT/".cache/objects")
    runtime=time.perf_counter()-start
    overlay=output/f"{source.stem}_overlay.png"
    render_overlay(backend.render_page(source,1),analysis,overlay)
    row={"fixture":source.stem,"seconds":round(runtime,3),
         "kinds":dict(Counter(obj.kind for obj in analysis.native.objects)),
         "path_items":sum(len(obj.path_items) for obj in analysis.native.objects),
         "compounds":len(analysis.compounds),
         "largest_compound":max((len(obj.member_ids) for obj in analysis.compounds),default=0),
         "roles":dict(Counter(record.role for record in analysis.asset_ledger.records)),
         "asset_ledger":verify_asset_ledger(analysis),"graph_complete":analysis.graph_complete,
         "candidate_pairs":analysis.candidate_pairs_checked,"diagnostics":analysis.diagnostics}
    rows.append(row)
    print(json.dumps(row),flush=True)
(output/"fixture_objects.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
