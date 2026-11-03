"""Step 20 formula-reading speed: equations per hour of the formula reader on Statistics
equation regions, with one torch thread (what the OCR engine's process-wide setting left
before Step 20) and with the process default after the fix. Crops come from the regions in a
Step 19 run's equations cache, rendered from the PDF; readings bypass every cache.

Usage: python step20_formula_speed.py --count 24
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
OUT = ROOT / "experiments/out/step20/formula_speed.json"


def crops(count):
    import pymupdf
    from book_core.equations.models import PageEquations
    from book_core.objects.analysis import verified_read
    from reference_paths import reference_path

    record = json.loads((ROOT / "experiments/out/step19/final2/performance/statistics.json")
                        .read_text("utf-8"))  # fmt: skip
    root, key = Path(record["cache"]), record["run"]["cache_keys"]["equations"]
    images = []
    with pymupdf.open(reference_path("statistics_pdf")) as document:
        for number in range(1, record["run"]["pages"] + 1):
            path = root / "equations" / key / f"{number}.json"
            if not path.exists():
                continue
            page = verified_read(path, PageEquations, key)
            for region in page.regions:
                if region.source == "text":
                    continue
                b = region.bbox
                clip = pymupdf.Rect(b.x0 - 2, b.y0 - 2, b.x1 + 2, b.y1 + 2)
                pixmap = document[number - 1].get_pixmap(dpi=200, clip=clip)
                images.append(pixmap.tobytes("png"))
                if len(images) >= count:
                    return images
    return images


def main():
    import torch
    from book_core.mathml.recognition import PPFormulaNet

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=24)
    args = parser.parse_args()
    images = crops(args.count)
    reader = PPFormulaNet(device="cpu", cache_dir=ROOT / ".cache/huggingface",
                          local_files_only=True)  # fmt: skip
    reader.recognize(images[0])  # load and warm up
    default = torch.get_num_threads()
    rows, outputs = {}, {}
    for label, threads in (("one_thread_before", 1), ("default_after", default)):
        torch.set_num_threads(threads)
        tick = time.perf_counter()
        outputs[label] = [reader.recognize(png)[0] for png in images]
        seconds = time.perf_counter() - tick
        rows[label] = {"threads": threads, "images": len(images), "seconds": round(seconds, 1),
                       "equations_per_hour": round(len(images) * 3600 / seconds)}  # fmt: skip
    rows["identical_readings"] = outputs["one_thread_before"] == outputs["default_after"]
    rows["cpu_count"] = __import__("os").cpu_count()
    OUT.write_text(json.dumps(rows, indent=1) + "\n", "utf-8")
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
