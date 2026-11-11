"""Step 21 formula-reading speed: equations per hour at several batch sizes, and whether the
readings equal the one-image-at-a-time readings. Crops come from the equation regions of a
page sample's equations cache (``--cache``, ``--pdf``), rendered from the PDF; the readings
bypass every cache.

Usage: python step21_formula_batch.py --pdf SAMPLE.pdf --cache CACHE --count 24
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]


def crops(pdf, cache, count):
    import pymupdf

    from book_core.cache_store import read_json

    images = []
    with pymupdf.open(pdf) as document:
        for path in sorted(Path(cache, "equations").glob("*/*.json"),
                           key=lambda p: (p.parent.name, int(p.stem) if p.stem.isdigit() else 0)):
            if not path.stem.isdigit():
                continue
            payload = read_json(path)
            payload = payload.get("payload", payload)
            payload = json.loads(payload) if isinstance(payload, str) else payload
            for region in payload.get("regions", []):
                b = region["bbox"]
                clip = pymupdf.Rect(b["x0"] - 2, b["y0"] - 2, b["x1"] + 2, b["y1"] + 2)
                pixmap = document[int(path.stem) - 1].get_pixmap(dpi=200, clip=clip)
                images.append(pixmap.tobytes("png"))
                if len(images) >= count:
                    return images
    return images


def main():
    import torch

    from step21_batching import recognize_many
    from book_core.mathml.recognition import PPFormulaNet

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--out", required=True)
    parser.add_argument("--sizes", default="1,4,8,16")
    args = parser.parse_args()
    images = crops(args.pdf, args.cache, args.count)
    reader = PPFormulaNet(device="cpu", cache_dir=ROOT / ".cache/huggingface",
                          local_files_only=True)  # fmt: skip
    reader.recognize(images[0])  # load and warm up
    rows, reference = {}, None
    for size in map(int, args.sizes.split(",")):
        tick = time.perf_counter()
        if size == 1:
            outputs = [reader.recognize(png) for png in images]
        else:
            outputs = []
            for start in range(0, len(images), size):
                outputs += recognize_many(reader, images[start:start + size])
        seconds = time.perf_counter() - tick
        reference = reference or outputs
        rows[f"batch_{size}"] = {
            "images": len(images), "seconds": round(seconds, 1),
            "equations_per_hour": round(len(images) * 3600 / seconds),
            "identical_to_single": outputs == reference,
            "differing": sum(a != b for a, b in zip(outputs, reference, strict=True)),
        }
        print(size, rows[f"batch_{size}"], flush=True)
    rows["threads"] = torch.get_num_threads()
    rows["cpu_count"] = __import__("os").cpu_count()
    Path(args.out).write_text(json.dumps(rows, indent=1) + "\n", "utf-8")


if __name__ == "__main__":
    main()
