"""Step 20 adapter gate: the Jaypee profile on every development book's Step 20 publication
(DTD validity, house rules, lossless 0/0), and the ART book compared with Jaypee's delivery
(element counts and the biggest differences), as ``adapter_a_run.py`` does.

Deliveries go to .cache/s20/adapter/<book> (git-ignored); summaries to
experiments/out/step20/<tag>/adapter/.

Usage: python step20_adapter.py --tag final [book ...]
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

from adapter_a_run import summary, tree_sha
from book_adapters.compare import compare_deliveries
from book_adapters.engine.run import run_book
from reference_paths import reference_path

BOOKS = ("spanish_us_history", "immigrant_children", "art_therapy_index", "medical_anatomy",
         "statistics", "art_lab", "iap_mec", "trichology")  # fmt: skip
SETTINGS = {"art_lab": ROOT / "books/9789372025262.yaml"}
REFERENCE = {"art_lab": "jaypee_art_delivery"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("books", nargs="*")
    args = parser.parse_args()
    out = ROOT / "experiments/out/step20" / args.tag / "adapter"
    out.mkdir(parents=True, exist_ok=True)
    results = json.loads((out / "runs.json").read_text("utf-8")) if (out / "runs.json").exists() else {}
    for book in args.books or BOOKS:
        record = json.loads((ROOT / "experiments/out/step20" / args.tag / "performance"
                             / f"{book}.json").read_text("utf-8"))  # fmt: skip
        settings = SETTINGS.get(book)
        started = time.perf_counter()
        report = run_book(Path(record["run"]["book_json"]), ROOT / ".cache/s20/adapter" / book,
                          settings, None if settings else "jaypee_v3",
                          allow_alt_text_placeholders=True)  # fmt: skip
        row = summary(report)
        row["delivery_sha256"] = tree_sha(Path(report["root"]))
        if book in REFERENCE:
            cmp = compare_deliveries(Path(report["root"]), reference_path(REFERENCE[book]))
            (out / f"compare_{book}.json").write_text(
                json.dumps(cmp, indent=1, ensure_ascii=False) + "\n", "utf-8")  # fmt: skip
            row["compare"] = {"biggest": cmp["biggest_differences"][:12],
                              "page_info_equal": cmp["page_info"]["equal"],
                              "files": {k: v for k, v in cmp["files"].items() if k != "common"}}  # fmt: skip
        row["wall_seconds"] = round(time.perf_counter() - started, 1)
        results[book] = row
        print(book, json.dumps({k: row[k] for k in ("dtd_errors", "house_violations")}),
              row["lossless"]["missing"], row["lossless"]["extra"], flush=True)  # fmt: skip
        (out / "runs.json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n",
                                       "utf-8")  # fmt: skip


if __name__ == "__main__":
    main()
