"""Vertical-Chinese packs on the woodblock pages; emission-order CER and order-free char F1."""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.ocr.engines import TesseractEngine
from book_core.ocr.evaluation import error_counts
from step16_real_eval import truth

config = json.loads(
    (ROOT / "experiments/out/step16/benchmark/config_tess.json").read_text()
)
rows = []
for name in ("chi_samguk_15", "chi_samguk_16", "chi_samguk_17"):
    directory = ROOT / "experiments/test_data/step16_real_scans" / name
    reference, image = truth(directory), (directory / "page.jpg").read_bytes()
    ref_chars = Counter(c for c in reference if not c.isspace())
    for languages in (
        ["chi_tra_vert"],
        ["chi_sim_vert"],
        ["chi_tra_vert", "chi_sim_vert"],
        ["script/HanT_vert"],
        ["chi_tra"],
    ):
        for psm in (3, 5):
            engine = TesseractEngine(
                Path(config["tesseract_executable"]), Path(config["tessdata"]), psm=psm
            )
            reading = engine.read(image, languages=languages, deskew=True)
            text = " ".join(w.text for w in reading.words)
            got = Counter(c for c in text if not c.isspace())
            hit = sum((ref_chars & got).values())
            precision = hit / max(1, sum(got.values()))
            recall = hit / max(1, sum(ref_chars.values()))
            rows.append(
                {
                    "scan": name,
                    "languages": languages,
                    "psm": psm,
                    "cer_emission_order": error_counts(reference, text, cjk=True)[
                        "cer"
                    ],
                    "char_recall": recall,
                    "char_precision": precision,
                    "reference_chars": sum(ref_chars.values()),
                }
            )
            print(rows[-1], flush=True)
(ROOT / "experiments/out/step16/real_eval/vertical.json").write_text(
    json.dumps(rows, indent=1)
)
