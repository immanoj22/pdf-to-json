"""Step 17: book 2 (immigrant children) with its cover page OCR'd (owner decision).

``run``: the eligibility screen with the visual text check (Step 16) qualifies the cover;
``prepare_book`` reads it (Tesseract first for English, PP-OCRv5 second, per the measured
defaults and the default client profile); then ``run_book`` with the OCR input, the
development caches of the earlier runs and the Step 13 figure settings. The run record is
written as the other books' (``out/step17/<out>/performance``).

``proof``: I1-I7 and exact line ownership on every page from the run's own cache keys (the
OCR view has its own native key, so the Step 11 identity capture does not apply).

Usage: python step17_ocr_cover.py run --out final | proof --out final
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step13_run
import step16_downstream as downstream
from reference_paths import reference_path
from step13_books import BOOKS
from step16_benchmark import make_engines

BOOK = "immigrant_children"
OUT = ROOT / "experiments/out/step17"
CONFIG = ROOT / "experiments/out/step16/benchmark/config_main.json"


def ocr_settings(config):
    from book_core.assembly.profile import load_profile
    from book_core.assembly.profile import ocr_settings as from_profile
    from book_core.ocr.settings import OcrJobSettings, OcrSettings

    settings = OcrSettings(
        executable=Path(config["tesseract_executable"]),
        tessdata=Path(config["tessdata"]),
        asset_manifest=ROOT / "experiments/out/step16/dependencies/tessdata_manifest.json",
        second_reader="on",
        detector_path=Path(config["pp_detector"]),
        recognizer_paths={r["name"]: Path(r["path"]) for r in config["pp_recognizers"]},
        model_revisions={"detector": config["pp_detector_revision"],
                         **{r["name"]: r["revision"] for r in config["pp_recognizers"]}},
    )  # fmt: skip
    return OcrJobSettings(device="cpu", ocr_languages=["eng"],
                          ocr=from_profile(load_profile(), settings))  # fmt: skip


def run(out):
    from book_core.book_run import run_book
    from book_core.caching import SCOPES, code_digest
    from book_core.ocr.prepare import prepare_book

    config = json.loads(CONFIG.read_text("utf-8"))
    primary, secondary = make_engines(config)
    source = reference_path(BOOKS[BOOK][0])
    cache = ROOT / ".cache"
    settings = ocr_settings(config)
    ocr_input = prepare_book(
        source,
        cache / "s17ocr",
        settings,
        primary,
        secondary,
        visual_checks=downstream.visual_checks(source, cache / "s17ocr"),
    )
    print(
        "OCR pages",
        ocr_input.page_keys,
        "compare",
        ocr_input.comparison_keys,
        flush=True,
    )

    def progress(stage, completed, total):
        if completed % 25 == 0 or completed == total:
            print(BOOK, stage, completed, total, flush=True)

    from step8_run import step6_artifact, vocabulary_for

    free = shutil.disk_usage(ROOT).free
    base = json.loads((OUT / "before" / f"{BOOK}.json").read_text("utf-8"))
    artifact, _ = step6_artifact(base["source_sha256"])
    # The Step 16 driver's arguments (document evidence, vocabulary, caches, figure settings).
    result = run_book(
        source, ROOT / ".cache/step11d2/final_books" / "step13", cache, workers=1, device="cpu",
        settings=settings, evidence=artifact, vocabulary=vocabulary_for(BOOK),
        cache_dirs=step13_run.CACHE_DIRS | {"detections": cache / "models"},
        progress=progress, figure_settings=step13_run.figure_settings(),
        model_cache_dir=cache / "huggingface", ocr_input=ocr_input,
    )  # fmt: skip
    record = {"disk_before": {"free_bytes": free},
              "producers": {scope: code_digest(scope) for scope in SCOPES},
              "ocr": {"page_keys": ocr_input.page_keys,
                      "comparison_keys": ocr_input.comparison_keys},
              "run": result}  # fmt: skip
    target = OUT / out / "performance" / f"{BOOK}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(record, indent=1, default=str) + "\n", "utf-8", newline="\n"
    )
    print(BOOK, "run complete", result["output"], result.get("book_json"), flush=True)


def proof(out):
    step13_run.OUT = OUT
    step13_run.MATH_BOOK = BOOK
    step13_run.proof_math_book(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run", "proof"])
    parser.add_argument("--out", default="final")
    args = parser.parse_args()
    {"run": run, "proof": proof}[args.action](args.out)
