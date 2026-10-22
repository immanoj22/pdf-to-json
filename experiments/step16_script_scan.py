"""Does mean word confidence pick the right script model? (fallback when OSD is wrong/absent)"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.ocr.engines import TesseractEngine
from book_core.ocr.evaluation import error_counts
from step16_real_eval import truth

SCRIPTS = [
    "Latin",
    "Cyrillic",
    "Greek",
    "Arabic",
    "Hebrew",
    "Devanagari",
    "HanS",
    "HanT",
    "Hangul",
    "Japanese",
]
config = json.loads(
    (ROOT / "experiments/out/step16/benchmark/config_tess.json").read_text()
)
engine = TesseractEngine(Path(config["tesseract_executable"]), Path(config["tessdata"]))
rows = []
for name in sys.argv[1:]:
    directory = ROOT / "experiments/test_data/step16_real_scans" / name
    reference, image = truth(directory), (directory / "page.jpg").read_bytes()
    for script in SCRIPTS:
        reading = engine.read(image, languages=[f"script/{script}"], deskew=True)
        text = " ".join(w.text for w in reading.words)
        rows.append(
            {
                "scan": name,
                "script": script,
                "words": len(reading.words),
                "mean_confidence": reading.mean_confidence,
                "cer": error_counts(
                    reference,
                    text,
                    cjk=script.startswith(("Han", "Hangul", "Japanese")),
                )["cer"],
            }
        )
        print(rows[-1], flush=True)
Path(ROOT / "experiments/out/step16/real_eval/script_scan.json").write_text(
    json.dumps(rows, indent=1)
)
