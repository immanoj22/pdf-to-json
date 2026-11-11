"""Step 21 runs: the Step 20 runner (same production call, same actions and flags) with the
Step 21 development book added and results under ``experiments/out/step21/<tag>``,
caches under ``.cache/s21/<book>``.

Usage:
  python step21_run.py run --book neet_pg --tag before --ocr-config .cache/s20/ocr_config.json
  python step21_run.py proof --book neet_pg --tag before
"""

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

if __name__ == "__main__":
    raise SystemExit(step20_run.main())
