"""Rebuild only assembly after an assembly fix, preserving every upstream stage/cache.

The final run record retains an assembly history and records the separately measured
refresh. No earlier baseline or output folder is replaced or deleted.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.assembly.cache import publish_book, read_native_evidence
from book_core.assembly.links import PyMuPDFLinkExtractor
from book_core.assembly.profile import load_profile
from book_core.caching import code_digest
from book_core.process_metrics import ProcessMonitor
from book_core.telemetry import measure

from reference_paths import reference_path
from step7_layouts import CACHE
from step13_books import BOOKS

FINAL = ROOT / "experiments/out/step17/final"


def main(book):
    path = FINAL / "performance" / f"{book}.json"
    record = json.loads(path.read_text("utf-8"))
    run = record["run"]
    previous = Path(run["book_json"])
    free_before = shutil.disk_usage(ROOT).free
    # A publication writes a new folder while preserving the old one. Allow growth
    # from added review records and JSON metadata, without consuming the owner's reserve.
    estimate = 2 * sum(p.stat().st_size for p in previous.rglob("*") if p.is_file()) + 1_000_000
    if free_before - estimate < 5_000_000_000:
        raise OSError(f"Publication needs {estimate} bytes with a 5 GB reserve; free {free_before}. "
                      "Stop for the owner's decision; no cleanup has been performed.")
    old = json.loads((previous / "book.json").read_text("utf-8"))
    key = run["cache_keys"]["native"]
    stages = {}

    def progress(stage, n, total):
        if n % 100 == 0 or n == total:
            print(book, stage, n, total, flush=True)

    with ProcessMonitor() as monitor, measure(stages, "assembly"):
        folder, stats = publish_book(
            Path(run["output"]), previous.parent,
            source=reference_path(BOOKS[book][0]), extractor=PyMuPDFLinkExtractor("cpu"),
            native_page=lambda n: read_native_evidence(CACHE, key, n),
            cache_root=CACHE, native_key=key,
            source_sha256=old["metadata"]["source"]["sha256"],
            final_key=Path(run["output"]).name, profile=load_profile(),
            settings_sha256=old["metadata"]["settings_sha256"],
            run_date=old["metadata"]["run"]["date"], progress=progress)
    record.setdefault("assembly_history", []).append(
        {"book_json": str(previous), "stats": run.get("assembly"),
         "measurement": run["stages"].get("assembly")})
    run["book_json"], run["assembly"] = str(folder), stats
    run["stages"]["assembly"] = stages["assembly"]
    run["cache_keys"]["assembly_evidence"] = stats["evidence_key"]
    record["assembly_refresh"] = {"peak_tree_rss_bytes": monitor.peak,
                                  "stages": stages,
                                  "disk": {"free_before": free_before, "estimated_write_bytes": estimate,
                                           "reserve_bytes": 5_000_000_000,
                                           "free_after": shutil.disk_usage(ROOT).free}}
    record.setdefault("producers", {})["assembly"] = code_digest("assembly")
    pending = path.with_suffix(".next")
    pending.write_text(json.dumps(record, indent=1) + "\n", "utf-8", newline="\n")
    pending.replace(path)
    print(book, folder, stats, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=BOOKS, required=True)
    main(parser.parse_args().book)
