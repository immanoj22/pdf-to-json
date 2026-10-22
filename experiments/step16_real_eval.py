"""Score OCR readers on the frozen real public-domain scans (Part 4.2).

Truth is derived from the frozen ``transcription.html`` (CSS and Wikisource status
boilerplate removed); the frozen files themselves are never modified. Every scan is read
with: the specific language, the script model chosen by OSD, and (for non-English) the
language plus English. PP-OCRv5 is run where it covers the language (``--pp``).
Reading order is the engine's emission order; no semantic order is claimed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

SCANS = ROOT / "experiments/test_data/step16_real_scans"
OUT = ROOT / "experiments/out/step16/real_eval"
BOILERPLATE = ("本页已校对",)
CODES = {
    "eng": "eng",
    "spa": "spa",
    "hin": "hin",
    "ara": "ara",
    "chi": "chi_tra",
    "rus": "rus",
    "ell": "ell",
}


def line_ordered(words, *, rtl=False):
    """Evaluation only, single-column scans: group words into lines by vertical overlap
    (at least half the smaller height), lines top to bottom, words by x within a line
    (right to left for RTL scripts). This is not the pipeline's reading-order stage."""
    lines = []
    for word in sorted(words, key=lambda w: (w.pixel_bbox[1] + w.pixel_bbox[3]) / 2):
        y0, y1 = word.pixel_bbox[1], word.pixel_bbox[3]
        for line in lines:
            overlap = min(y1, line["y1"]) - max(y0, line["y0"])
            if overlap >= 0.5 * min(y1 - y0, line["y1"] - line["y0"]):
                line["words"].append(word)
                line["y0"], line["y1"] = min(y0, line["y0"]), max(y1, line["y1"])
                break
        else:
            lines.append({"y0": y0, "y1": y1, "words": [word]})
    lines.sort(key=lambda line: line["y0"])
    return "\n".join(
        " ".join(
            w.text
            for w in sorted(line["words"], key=lambda w: w.pixel_bbox[0], reverse=rtl)
        )
        for line in lines
    )


def order_free(reference, hypothesis):
    """Character multiset recall/precision/F1: recognition without any order."""
    from collections import Counter

    ref = Counter(c for c in reference if not c.isspace())
    hyp = Counter(c for c in hypothesis if not c.isspace())
    hit = sum((ref & hyp).values())
    recall, precision = hit / max(1, sum(ref.values())), hit / max(1, sum(hyp.values()))
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
    return {"recall": recall, "precision": precision, "f1": f1}


def truth(directory):
    from lxml import html

    tree = html.fromstring((directory / "transcription.html").read_text("utf-8"))
    for node in tree.xpath("//style|//script"):
        node.drop_tree()
    bodies = tree.xpath(
        "//*[contains(concat(' ',normalize-space(@class),' '),' pagetext ')]"
    )
    text = " ".join((bodies[0] if bodies else tree).text_content().split())
    for item in BOILERPLATE:
        text = text.replace(item, "")
    return text.replace("﻿", "").strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--pp", action="store_true")
    parser.add_argument("--only", action="append")
    parser.add_argument("--mode", action="append", help="restrict to these modes")
    parser.add_argument("--tag", default="")
    args = parser.parse_args()

    from book_core.ocr.evaluation import error_counts
    from step16_benchmark import make_engines

    config = json.loads(args.config.read_text("utf-8"))
    primary, secondary = make_engines(config)
    from book_core.ocr.language_choice import lingua_detector, read_with_language_choice

    detector = lingua_detector()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for directory in sorted(SCANS.iterdir()):
        code = directory.name.split("_")[0]
        if args.only and directory.name not in args.only:
            continue
        image = (directory / "page.jpg").read_bytes()
        reference = truth(directory)
        cjk = code == "chi"
        language = CODES[code]
        modes = {"specific": [language], "script_osd": []}
        if language != "eng":
            modes["with_eng"] = [language, "eng"]
        modes["script_lingua"] = None
        for mode, languages in modes.items():
            if args.mode and mode not in args.mode:
                continue
            started = time.perf_counter()
            try:
                if mode == "script_lingua":
                    reading, choice = read_with_language_choice(
                        primary,
                        image,
                        detector=detector,
                        deskew=True,
                    )
                else:
                    reading, choice = (
                        primary.read(image, languages=languages, deskew=True),
                        None,
                    )
            except Exception as error:  # noqa: BLE001 - report, never hide
                rows.append(
                    {
                        "scan": directory.name,
                        "reader": "tesseract",
                        "mode": mode,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
                continue
            text = " ".join(word.text for word in reading.words)
            rows.append(
                {
                    "scan": directory.name,
                    "language": code,
                    "reader": "tesseract",
                    "mode": mode,
                    "packs": list(reading.languages),
                    "choice": choice.__dict__ if choice else None,
                    "osd_script": reading.orientation.script,
                    "rotation": reading.orientation.rotation_clockwise,
                    "mean_confidence": reading.mean_confidence,
                    "hypothesis": text,
                    "order_free": order_free(reference, text),
                    "seconds": time.perf_counter() - started,
                    **error_counts(reference, text, cjk=cjk),
                }
            )
            print(rows[-1]["scan"], mode, rows[-1]["cer"], flush=True)
        if args.pp and secondary and secondary.supports([language]):
            started = time.perf_counter()
            reading = secondary.read(image, languages=[language])
            text = " ".join(word.text for word in reading.words)
            ordered = line_ordered(reading.words, rtl=code == "ara")
            rows.append(
                {
                    "scan": directory.name,
                    "language": code,
                    "reader": "pp_ocrv5",
                    "mode": "specific",
                    "seconds": time.perf_counter() - started,
                    "hypothesis": text,
                    "reference": reference,
                    "line_ordered_hypothesis": ordered,
                    "line_ordered": error_counts(reference, ordered, cjk=cjk),
                    "order_free": order_free(reference, text),
                    "boxes": [[w.text, list(w.pixel_bbox)] for w in reading.words],
                    **error_counts(reference, text, cjk=cjk),
                }
            )
            print(rows[-1]["scan"], "pp", rows[-1]["cer"], flush=True)
        (OUT / f"{directory.name}.txt").write_text(reference + "\n", "utf-8")
    name = f"real_pp{args.tag}.json" if args.pp else f"real_tesseract{args.tag}.json"
    (OUT / name).write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
