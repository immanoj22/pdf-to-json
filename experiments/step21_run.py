"""Step 21 runs: the Step 20 runner (same production call, same actions and flags) with the
Step 21 development book added and results under ``experiments/out/step21/<tag>``,
caches under ``.cache/s21/<book>``.

Usage:
  python step21_run.py run --book neet_pg --tag before --ocr-config .cache/s20/ocr_config.json
  python step21_run.py proof --book neet_pg --tag before
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

import step20_run

step20_run.BOOKS["neet_pg"] = "neet_pg_pdf"
# A page sample of the NEET book for fast iteration (BOOK_CONVERTER_NEET_SAMPLE_PDF).
step20_run.BOOKS["neet_sample"] = "neet_sample_pdf"
step20_run.BOOKS["hypertension"] = "hypertension_pdf"
step20_run.BOOKS["dermatology"] = "dermatology_pdf"
step20_run.BOOKS["derm_sample"] = "derm_sample_pdf"
step20_run.OUT = ROOT / "experiments/out/step21"
step20_run.CACHE = ROOT / ".cache/s21"

# Confirmed book parts (page ranges, as the app saves them) for a run: STEP21_PARTS=FILE.json.
if os.environ.get("STEP21_PARTS"):
    import functools

    import book_core.book_run as book_run

    _parts = json.loads(Path(os.environ["STEP21_PARTS"]).read_text("utf-8"))
    book_run.run_book = functools.partial(book_run.run_book, book_parts=_parts)

if __name__ == "__main__":
    raise SystemExit(step20_run.main())
