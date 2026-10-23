"""Step 17 Part 1: both readers on the added real scans (and the Step 16 Arabic pages again).

Every page of ``test_data/step17_real_scans`` (and, with ``--step16``, the Step 16 Arabic
pages, to check the right-to-left fix end to end) is read by Tesseract with the page's
language (``chi_sim``, ``chi_tra``, ``ell``, ``ara``) and by PP-OCRv5 with the same language
(its recognizer covering it). Truth is the frozen proofread transcription (Step 16 rule,
``step16_real_eval.truth``). Scores, as in Step 16: CER/WER in the reader's emitted order;
PP-OCRv5 lines grouped by position (``line_ordered``, evaluation only, single-column
pages); and the order-free character F1. PP-OCRv5 lines are already in logical order
(``ocr.bidi``); no reversal is applied here. One JSON row per (page, reader) is appended to
``real_eval/rows.jsonl`` as soon as it is read (resumable: done pages are skipped).

Readings are stored with their boxes; scores are computed by ``step17_real_summary.py``.
Vertical print groups are also read by Tesseract's vertical model (``chi_tra_vert``).

Usage: python step17_real_eval.py [--step16] [--only ID ...] [--no-pp]
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step16_real_eval as s16

SCANS = ROOT / "experiments/test_data/step17_real_scans"
SCANS16 = ROOT / "experiments/test_data/step16_real_scans"
OUT = ROOT / "experiments/out/step17/real_eval"
CONFIG = ROOT / "experiments/out/step16/benchmark/config_main.json"
CODES = {
    "zhs": "chi_sim",
    "zht": "chi_tra",
    "ell": "ell",
    "ara": "ara",
    "chi": "chi_tra",
}
CJK = {"chi_sim", "chi_tra"}
SCRIPTS = {
    row["id"]: row["script"]
    for row in json.loads(
        (ROOT / "experiments/out/step17/real_data/candidates.json").read_text("utf-8")
    )
}


def done():
    path = OUT / "rows.jsonl"
    if not path.exists():
        return set()
    return {
        (r["scan"], r["reader"])
        for r in map(json.loads, path.read_text("utf-8").splitlines())
    }


def append(row):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "rows.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--step16", action="store_true", help="also the Step 16 Arabic pages"
    )
    parser.add_argument("--only", action="append")
    parser.add_argument("--no-pp", action="store_true")
    args = parser.parse_args()
    from book_core.ocr.evaluation import error_counts

    from step16_benchmark import make_engines

    primary, secondary = make_engines(json.loads(CONFIG.read_text("utf-8")))
    directories = sorted(SCANS.iterdir())
    if args.step16:
        directories += sorted(d for d in SCANS16.iterdir() if d.name.startswith("ara_"))
    seen = done()
    for directory in directories:
        if args.only and directory.name not in args.only:
            continue
        if (
            not (directory / "page.jpg").exists()
            or not (directory / "transcription.html").exists()
        ):
            print(directory.name, "incomplete download; skipped", flush=True)
            continue
        source = json.loads((directory / "source.json").read_text("utf-8"))
        script = SCRIPTS.get(directory.name, source.get("script"))
        language = CODES[directory.name.split("_")[0]]
        image = (directory / "page.jpg").read_bytes()
        reference = s16.truth(directory)
        cjk = language in CJK
        base = {"scan": directory.name, "set": directory.parent.name, "language": language,
                "script": script, "licence": source.get("license_short_name"),
                "proofreading_level": source.get("human_proofreading_level"),
                "revision_id": source.get("revision_id")}  # fmt: skip
        variants = [("tesseract", [language])]
        if "vertical" in (script or ""):
            variants.append(("tesseract_vert", [f"{language}_vert"]))
        for reader, packs in variants:
            if (directory.name, reader) in seen:
                continue
            started = time.perf_counter()
            reading = primary.read(image, languages=packs, deskew=True)
            text = " ".join(word.text for word in reading.words)
            append({**base, "reader": reader, "packs": packs,
                    "seconds": round(time.perf_counter() - started, 1),
                    "mean_confidence": reading.mean_confidence, "hypothesis": text,
                    "reference": reference, "order_free": s16.order_free(reference, text),
                    "words": [[w.text, list(w.pixel_bbox), w.confidence, list(w.line_key)]
                              for w in reading.words],
                    **error_counts(reference, text, cjk=cjk)})  # fmt: skip
            print(directory.name, reader, "done", flush=True)
        if not args.no_pp and (directory.name, "pp_ocrv5") not in seen:
            started = time.perf_counter()
            reading = secondary.read(image, languages=[language])
            text = " ".join(word.text for word in reading.words)
            ordered = s16.line_ordered(reading.words, rtl=language == "ara")
            append({**base, "reader": "pp_ocrv5", "seconds": round(time.perf_counter() - started, 1),
                    "hypothesis": text, "reference": reference,
                    "line_ordered_hypothesis": ordered,
                    "line_ordered": error_counts(reference, ordered, cjk=cjk),
                    "order_free": s16.order_free(reference, text),
                    "boxes": [[w.text, list(w.pixel_bbox), w.confidence] for w in reading.words],
                    **error_counts(reference, text, cjk=cjk)})  # fmt: skip
            print(directory.name, "pp done", flush=True)
        (OUT / "truth").mkdir(parents=True, exist_ok=True)
        (OUT / "truth" / f"{directory.name}.txt").write_text(reference + "\n", "utf-8",
                                                             newline="\n")  # fmt: skip


if __name__ == "__main__":
    main()
