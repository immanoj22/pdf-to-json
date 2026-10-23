"""Replay PP geometry and capture missing Tesseract geometry for Chinese policy checks."""

import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
from book_core.ocr.cache import pp_first
from book_core.extraction.fingerprints import source_digest
from book_core.ocr.engines import OcrWord, TesseractEngine, text_properties


def main():
    directory = ROOT / "experiments/out/step17/real_eval"
    settings = SimpleNamespace(accuracy_mode="best_measured", pp_primary=("chi_sim", "chi_tra"))
    rows = []
    groups = {}
    readings = list(map(json.loads, (directory / "rows.jsonl").read_text("utf-8").splitlines()))
    primary = {row["scan"]: row for row in readings if row["reader"] == "tesseract"}
    capture_path = directory / "primary_geometry.json"
    captured = json.loads(capture_path.read_text("utf-8")) if capture_path.exists() else {}
    config = json.loads((ROOT / "experiments/out/step16/benchmark/config_main.json").read_text())
    engine = TesseractEngine(Path(config["tesseract_executable"]), Path(config["tessdata"]))
    for row in readings:
        if row["reader"] != "pp_ocrv5":
            continue
        words = []
        for index, (text, box, score) in enumerate(row["boxes"]):
            script, direction = text_properties(text)
            words.append(OcrWord(text, tuple(box), score, (index,), script=script,
                                 text_direction=direction, granularity="line"))
        second = SimpleNamespace(words=words)
        promoted = pp_first(settings, (row["language"],), second, second)
        first_words = []
        if row["language"] in settings.pp_primary:
            image = ROOT / "experiments/test_data" / row["set"] / row["scan"] / "page.jpg"
            digest = source_digest(image)
            if row["scan"] not in captured or captured[row["scan"]]["image_sha256"] != digest:
                first = engine.read(image.read_bytes(), languages=[row["language"]], deskew=True)
                hypothesis = " ".join(word.text for word in first.words)
                captured[row["scan"]] = {
                    "image_sha256": digest, "engine": engine.identity,
                    "matches_frozen_hypothesis": hypothesis == primary[row["scan"]]["hypothesis"],
                    "word_geometry": [[w.text, list(w.pixel_bbox), w.confidence, list(w.line_key)]
                                      for w in first.words]}
                capture_path.write_text(json.dumps(captured, indent=1, ensure_ascii=False) + "\n",
                                        "utf-8", newline="\n")
                print(row["scan"], "geometry captured", flush=True)
            geometry = captured[row["scan"]]["word_geometry"]
        else:
            geometry = []
        for text, box, score, line in geometry:
            script, direction = text_properties(text)
            first_words.append(OcrWord(text, tuple(box), score, tuple(line), script=script,
                                       text_direction=direction))
        confirmed = pp_first(settings, (row["language"],), second,
                             SimpleNamespace(words=first_words))
        group = f"{row['language']} | {row['script']}"
        groups.setdefault(group, Counter())["pp_primary" if confirmed else "tesseract_primary"] += 1
        groups[group]["pp_geometry_only"] += bool(promoted)
        groups[group]["both_readers_horizontal"] += bool(confirmed)
        rows.append({"scan": row["scan"], "group": group, "pp_primary": confirmed,
                     "pp_geometry_only": promoted,
                     "both_readers_horizontal": confirmed})
    result = {"method": "Frozen PP line boxes; Chinese Tesseract geometry re-read separately "
                         "because the earlier rows overwrote word geometry with word counts",
              "groups": {key: dict(value) for key, value in groups.items()}, "pages": rows}
    (directory / "primary_policy.json").write_text(json.dumps(result, indent=1) + "\n",
                                                   "utf-8", newline="\n")
    print(json.dumps(result["groups"], indent=1))


if __name__ == "__main__":
    main()
