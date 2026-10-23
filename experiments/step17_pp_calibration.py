"""Step 17 Part 1: PP-OCRv5's own word threshold, fitted like Tesseract's in Step 16.

The 52 Step 16 cases read by both readers (6 seeded pages per book, clean and 200 dpi) carry
per-word correctness labels for PP-OCRv5 (``scores.pp_ocrv5.observations``). The threshold
is fitted on the Step 16 seeded half of the (book, page) pairs (all degradations of a page
together) by error-detection F1 (``ocr.evaluation.fit_threshold``) and scored on the other
half; both folds and the threshold fitted on all pages are reported, with Tesseract's on the
same cases for comparison. No OCR is run.

Usage: python step17_pp_calibration.py
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.ocr.evaluation import calibration_counts, fit_threshold

import step16_report_data as data

OUT = ROOT / "experiments/out/step17/ocr"


def main():
    tess, _ = data.latest(data.load_cases(), with_secondary=False)
    pages = sorted({(b, p) for b, p, _ in tess})
    train = set(random.Random("1600:calibration").sample(pages, len(pages) // 2))
    both, _ = data.latest(data.load_cases(), with_secondary=True)
    result = {
        "cases": len(both),
        "split": "Step 16 seeded half of the (book, page) pairs",
    }
    for reader in ("pp_ocrv5", "tesseract"):
        halves = {"train": [], "test": []}
        for (book, page, _), record in sorted(both.items()):
            part = "train" if (book, page) in train else "test"
            halves[part].extend(
                (o["score"], o["wrong"])
                for o in record["scores"][reader]["observations"]
            )
        row = {"words": {k: len(v) for k, v in halves.items()}}
        for fit_on, score_on in (("train", "test"), ("test", "train")):
            fitted = fit_threshold(halves[fit_on])
            row[f"fit_on_{fit_on}"] = {
                "threshold": round(fitted["threshold"], 4),
                "held_out": calibration_counts(halves[score_on], fitted["threshold"]),
            }
        everything = halves["train"] + halves["test"]
        fitted = fit_threshold(everything)
        row["fitted_on_all"] = {
            "threshold": round(fitted["threshold"], 4),
            "in_sample": calibration_counts(everything, fitted["threshold"]),
            "sample_sha256": fitted["sample_sha256"],
        }
        row["at_0.84"] = calibration_counts(everything, 0.84)
        result[reader] = row
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pp_calibration.json").write_text(
        json.dumps(result, indent=1) + "\n", "utf-8", newline="\n"
    )
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
