"""Step 12: are missed reference figures on scanned pages (a later OCR step)?

For every page where the reference holds more figures than our final records, reads the
cached object analysis and reports whether the page carries a scan layer (Step 3 role
``scan_layer``) or no native text at all.

Usage: STEP12_OUT=final python step12_scanned.py
"""

# ruff: noqa: E402
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step7_layouts import CACHE
from step12_evaluate import reference_view

from book_core.cache_store import read_json
from book_core.objects.analysis import verified_read
from book_core.objects.models import ObjectAnalysis

RUN = ROOT / "experiments/out/step12" / os.environ.get("STEP12_OUT", "run")
BOOKS = ("spanish_us_history", "immigrant_children", "medical_anatomy")


def main():
    result = {}
    for book in BOOKS:
        run = json.loads((RUN / f"performance/{book}.json").read_text("utf-8"))["run"]
        output, key = Path(run["output"]), run["cache_keys"]["analysis"]
        _, ref_pages, _ = reference_view(book)
        rows = []
        for page, ref in sorted((p, n) for p, n in ref_pages.items() if p):
            ours = len(read_json(output / f"page_{page:06d}.json.gz")["figures"]["figures"])
            if ours >= ref:
                continue
            analysis = verified_read(CACHE / "analysis" / key / f"{page}.json", ObjectAnalysis, key)
            roles = {r.role for r in analysis.asset_ledger.records}
            rows.append(
                {
                    "page": page,
                    "reference": ref,
                    "ours": ours,
                    "scan_layer": "scan_layer" in roles,
                    "native_text_spans": len(analysis.native.page.store.spans),
                }
            )
            del analysis
        result[book] = {
            "pages_with_missed_figures": len(rows),
            "missed_figures": sum(r["reference"] - r["ours"] for r in rows),
            "on_scanned_pages": sum(r["reference"] - r["ours"] for r in rows if r["scan_layer"]),
            "scanned_pages": [r["page"] for r in rows if r["scan_layer"]],
            "pages": rows,
        }
        print(book, {k: v for k, v in result[book].items() if k != "pages"})
    (RUN / "missed_on_scanned_pages.json").write_text(
        json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
