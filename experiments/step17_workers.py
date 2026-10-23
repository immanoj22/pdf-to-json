"""Step 17: 1 vs 2 workers and development vs production on a real book (book 3).

Book 3 runs twice in production mode (each run its own temporary cache: every stage
recomputed), with one and with two workers; the published book folders (book.json, images,
review crops, manifest) must be byte-identical to each other and, apart from the folder
key, to the development final run's.

Usage: python step17_workers.py
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.book_run import run_book
from book_core.caching import code_digest

import step13_run
from reference_paths import reference_path
from step8_run import step6_artifact, vocabulary_for
from step13_books import BOOKS

BOOK = "art_therapy_index"
OUT = ROOT / "experiments/out/step17/final"
WORK = ROOT / ".cache/s17w"


def files(folder):
    folder = Path(folder)
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}  # fmt: skip


def main():
    base = json.loads(
        (ROOT / "experiments/out/step17/before" / f"{BOOK}.json").read_text()
    )
    artifact, _ = step6_artifact(base["source_sha256"])
    results = {}
    for workers in (1, 2):
        result = run_book(reference_path(BOOKS[BOOK][0]), WORK / f"w{workers}", WORK / "cache",
                          mode="production", workers=workers, device="cpu", evidence=artifact,
                          vocabulary=vocabulary_for(BOOK),
                          figure_settings=step13_run.figure_settings(),
                          model_cache_dir=ROOT / ".cache/huggingface")  # fmt: skip
        results[workers] = files(result["book_json"])
    development = json.loads((OUT / "performance" / f"{BOOK}.json").read_text("utf-8"))[
        "run"
    ]
    dev = files(development["book_json"])
    row = {
        "files": len(results[1]),
        "assembly_producer": code_digest("assembly"),
        "final_producer": code_digest("final"),
        "one_vs_two_workers_identical": results[1] == results[2],
        "production_vs_development_identical": results[1] == dev,
        "one_worker_files": results[1],
        "two_worker_files": results[2],
        "development_files": dev,
        "differing_vs_development": sorted(k for k in set(dev) | set(results[1])
                                           if dev.get(k) != results[1].get(k)),
    }  # fmt: skip
    (OUT / "workers_book3.json").write_text(json.dumps(row, indent=1) + "\n", "utf-8",
                                            newline="\n")  # fmt: skip
    print(row)


if __name__ == "__main__":
    main()
