"""Retained token gates and per-fixture role review metrics; no combined accuracy score."""
import json
from collections import Counter
from pathlib import Path

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.ledger.accounting import check
from book_core.objects.models import ObjectAnalysis

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"experiments/out/step3"
cases=json.loads((ROOT/"backend/tests/fixtures/expected_counters.json").read_text("utf-8"))["cases"]
old={case["fixture"]:Counter(case["counter"]) for case in cases}
phase0=json.loads((ROOT/"experiments/out/extractor_results.json").read_text("utf-8"))
baseline={row["id"]:row["tokens"] for row in phase0 if row["extractor"]=="pymupdf"}
rows=[]
roles=[]
for source in sorted((ROOT/"experiments/fixtures").glob("*.pdf")):
    name=source.stem
    page=next(PyMuPDFExtractor().extract_pages(source))
    document,ledger=provision_page(page)
    result=check(document,ledger,old.get(name))
    assert result.passing
    assert result.node_token_count==baseline[name]
    rows.append({"fixture":name,**result.model_dump(),"passing":result.passing,
                 "baseline":"frozen old cache counter" if name in old else "Phase 0 rawdict token total"})
    analysis=ObjectAnalysis.model_validate_json((OUT/f"{name}_overlay.json").read_text("utf-8"))
    decisions={record.object_id:record for record in analysis.asset_ledger.records}
    gold=json.loads((ROOT/"backend/tests/gold"/f"roles_{name}.json").read_text("utf-8"))
    matches=0
    known=0
    cases=[]
    for obj in gold["objects"]:
        found=decisions[obj["object_id"]]
        expected=obj["expected_role"]
        if expected is not None:
            known+=1
            matches+=expected==found.role
        cases.append({**obj,"found":found.role,"confidence":found.confidence,
                      "found_review_required":found.review_required,"reasons":found.reasons})
    roles.append({"fixture":name,"matched":matches,"certain_samples":known,
                  "uncertain_samples":sum(obj["expected_role"] is None for obj in gold["objects"]),
                  "sample_accuracy":matches/known if known else None,
                  "human_approved":False,"objects":cases})
(OUT/"fixture_gate.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
(OUT/"role_evaluation.json").write_text(json.dumps(roles,indent=2),encoding="utf-8")
print(json.dumps([{"fixture":row["fixture"],"tokens":row["node_token_count"],
                  "missing":row["missing_token_count"],"extra":row["extra_token_count"]} for row in rows]))
print(json.dumps([{"fixture":row["fixture"],"matched":row["matched"],"samples":row["certain_samples"],
                  "uncertain":row["uncertain_samples"]} for row in roles]))
