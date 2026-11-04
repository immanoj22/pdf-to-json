"""Formats gate: one standard format writer on the 11 publications (read-only), twice (byte
comparison), with the checks. No book is converted.

Deliveries go to .cache/formats/<run>/<format>/<book> (git-ignored); the summary to
experiments/out/formats/<format>.json.

Usage: python formats_run.py FORMAT [--profile NAME] [book ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

import yaml  # noqa: E402

from book_adapters.engine.formats_run import run_format  # noqa: E402

STEP20 = ("spanish_us_history", "immigrant_children", "art_therapy_index", "medical_anatomy",
          "statistics", "art_lab", "iap_mec", "trichology")  # fmt: skip
FRONTEND = {
    "dermatology": "11c555a8133ebbd55036180e603e354a",
    "cancer_biology": "b8cbf3dbfb209db434de4a98c8926bc2",
    "rssdi_atlas": "7c1e91951724320809ec8b5aa66ecf88",
}
MAIN = Path(os.environ.get("BOOK_MAIN_CHECKOUT", ROOT.parent / "pdf_book_converter"))
DEFAULT_PROFILE = {"html": "html_base", "dtbook": "dtbook_nimas_base", "daisy3": "daisy3_base",
                   "jats": "jats_base", "bits": "bits_base"}  # fmt: skip


def book_dir(book: str) -> Path:
    if book in FRONTEND:
        jobs = MAIN / "frontend_temp/runtime/jobs" / FRONTEND[book] / "output"
        return next(jobs.glob("book-*"))
    record = MAIN / "experiments/out/step20/final/performance" / f"{book}.json"
    return Path(json.loads(record.read_text("utf-8"))["run"]["book_json"])


def tree_sha(root: Path, skip=("run.json",)) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file() and x.name not in skip):
        h.update(str(p.relative_to(root)).encode())
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def settings_for(book: str, tmp: Path) -> Path | None:
    if book != "art_lab":
        return None
    data = yaml.safe_load((ROOT / "books/9789372025262.yaml").read_text("utf-8"))
    data.pop("options", None)  # the Jaypee profile's book options
    path = tmp / "art_lab.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), "utf-8")
    return path


def run_one(fmt: str, profile: str, book: str, tag: str, tmp: Path) -> dict:
    started = time.perf_counter()
    target = ROOT / ".cache/formats" / tag / fmt / book
    report = run_format(fmt, book_dir(book), target, settings_for(book, tmp), profile,
                        allow_alt_text_placeholders=True)  # fmt: skip
    checks = report["checks"]
    loss = checks["lossless"]
    return {
        "book": book,
        "verdict": report["qc_verdict"],
        "schema_errors": checks["dtd"]["errors"],
        "rule_findings": checks["house_rules"]["violations"],
        "rule_findings_by_check": {
            k: v["violations"]
            for k, v in checks["house_rules"]["checks"].items()
            if v["violations"]
        },
        "lossless_missing": loss["missing"],
        "lossless_extra": loss["extra"],
        "matches_ledger": loss["output"]["matches_ledger"],
        "out_of_order": loss["order"]["undeclared_out_of_order"],
        "unexplained_changes": loss["character_changes"]["unexplained"],
        "files": len(report["delivery"]["files"]),
        "images": report["delivery"]["images"],
        "alt_placeholders": report["alt_text"]["placeholders"],
        "review_counts": report["review_counts"],
        "delivery_sha256": tree_sha(Path(report["root"])),
        "zip_sha256": report["delivery"]["zip_sha256"],
        "seconds": round(time.perf_counter() - started, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("format")
    ap.add_argument("--profile")
    ap.add_argument("books", nargs="*")
    args = ap.parse_args()
    profile = args.profile or DEFAULT_PROFILE[args.format]
    books = args.books or [*STEP20, *FRONTEND]
    out = ROOT / "experiments/out/formats"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        for book in books:
            first = run_one(args.format, profile, book, "run1", tmp)
            second = run_one(args.format, profile, book, "run2", tmp)
            first["byte_identical_rerun"] = (
                first["delivery_sha256"] == second["delivery_sha256"]
                and first["zip_sha256"] == second["zip_sha256"]
            )
            rows.append(first)
            keys = ("book", "verdict", "schema_errors", "rule_findings", "lossless_missing",
                    "lossless_extra", "byte_identical_rerun", "seconds")  # fmt: skip
            print(json.dumps({k: first[k] for k in keys}), flush=True)
            (out / f"{args.format}.json").write_text(json.dumps(rows, indent=1) + "\n", "utf-8")


if __name__ == "__main__":
    main()
