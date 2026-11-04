"""Adapter B gate: the Jaypee profile on the 8 Step 20 publications (read-only) and on the
owner's latest frontend outputs (Dermatology, cancer biology, RSSDI Atlas), with the checks
(DTD, house rules, lossless), the QC report verdict, and the ART compare against Jaypee's
delivery. No book is converted.

Deliveries go to .cache/adapter_b/<tag>/<book> (git-ignored); summaries to
experiments/out/adapter_b/<tag>/.

Usage: python adapter_b_run.py --tag before [book ...]
       python adapter_b_run.py --tag final --rerun   (second run into <tag>_rerun, byte compare)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

from adapter_a_run import summary, tree_sha  # noqa: E402
from reference_paths import reference_path  # noqa: E402

from book_adapters.compare import compare_deliveries  # noqa: E402
from book_adapters.engine.run import run_book  # noqa: E402

STEP20 = ("spanish_us_history", "immigrant_children", "art_therapy_index", "medical_anatomy",
          "statistics", "art_lab", "iap_mec", "trichology")  # fmt: skip
# The owner's frontend outputs (development use allowed); job folders of the main checkout.
FRONTEND = {
    "dermatology": "11c555a8133ebbd55036180e603e354a",
    "cancer_biology": "b8cbf3dbfb209db434de4a98c8926bc2",
    "rssdi_atlas": "7c1e91951724320809ec8b5aa66ecf88",
}
SETTINGS = {"art_lab": ROOT / "books/9789372025262.yaml"}
REFERENCE = {"art_lab": "jaypee_art_delivery"}
MAIN = Path(os.environ.get("BOOK_MAIN_CHECKOUT", ROOT.parent / "pdf_book_converter"))


def book_dir(book: str) -> Path:
    if book in FRONTEND:
        jobs = MAIN / "frontend_temp/runtime/jobs" / FRONTEND[book] / "output"
        return next(jobs.glob("book-*"))
    record = ROOT / "experiments/out/step20/final/performance" / f"{book}.json"
    return Path(json.loads(record.read_text("utf-8"))["run"]["book_json"])


def report_sha(folder: Path) -> str:
    """Hash of the report folder without run.json (it holds the run time)."""
    import hashlib

    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "run.json"):
        h.update(str(path.relative_to(folder)).encode())
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def run_one(book: str, tag: str, out: Path) -> dict:
    settings = SETTINGS.get(book)
    started = time.perf_counter()
    target = ROOT / ".cache/adapter_b" / tag / book
    report = run_book(book_dir(book), target, settings, None if settings else "jaypee_v3",
                      allow_alt_text_placeholders=True)  # fmt: skip
    row = summary(report)
    row["delivery_sha256"] = tree_sha(Path(report["root"]))
    row["report_sha256"] = report_sha(target / "report")
    qc = json.loads((target / "report/qc_report.json").read_text("utf-8"))
    row["qc_verdict"] = qc["verdict"]
    row["character_changes"] = report["checks"]["lossless"].get("character_changes", {})
    if book in REFERENCE:
        cmp = compare_deliveries(Path(report["root"]), reference_path(REFERENCE[book]),
                                 book=book_dir(book))  # fmt: skip
        (out / f"compare_{book}.json").write_text(
            json.dumps(cmp, indent=1, ensure_ascii=False) + "\n", "utf-8")  # fmt: skip
        row["compare"] = {"key": {k: v for k, v in cmp["key_elements"].items() if v["diff"]},
                          "page_info_equal": cmp["page_info"]["equal"]}  # fmt: skip
    row["wall_seconds"] = round(time.perf_counter() - started, 1)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--rerun", action="store_true", help="also rerun into <tag>_rerun")
    parser.add_argument("books", nargs="*")
    args = parser.parse_args()
    books = args.books or list(STEP20) + list(FRONTEND)
    for tag in [args.tag] + ([f"{args.tag}_rerun"] if args.rerun else []):
        out = ROOT / "experiments/out/adapter_b" / tag
        out.mkdir(parents=True, exist_ok=True)
        path = out / "runs.json"
        results = json.loads(path.read_text("utf-8")) if path.exists() else {}
        for book in books:
            row = run_one(book, tag, out)
            results[book] = row
            print(tag, book, row["dtd_errors"], row["house_violations"],
                  row["lossless"]["missing"], row["lossless"]["extra"], row["qc_verdict"],
                  row["wall_seconds"], flush=True)  # fmt: skip
            path.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", "utf-8")
    if args.rerun:
        first = json.loads((ROOT / f"experiments/out/adapter_b/{args.tag}/runs.json").read_text())
        second = json.loads(
            (ROOT / f"experiments/out/adapter_b/{args.tag}_rerun/runs.json").read_text()
        )
        same = {
            b: first[b]["delivery_sha256"] == second[b]["delivery_sha256"]
            and first[b]["report_sha256"] == second[b]["report_sha256"]
            for b in books
        }
        (ROOT / f"experiments/out/adapter_b/{args.tag}/determinism.json").write_text(
            json.dumps(same, indent=1) + "\n", "utf-8"
        )
        print("byte-identical reruns:", same)


if __name__ == "__main__":
    main()
