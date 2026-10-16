"""Step 13c: UniMERNet readings of every equation region, through the side environment.

The main environment cannot hold UniMERNet 0.2.3 (Transformers 4.42.4 / NumPy 1.x pins; see
``experiments/out/step13c/dependencies``). This driver renders the same region images as the
stage (``mathml.images``), writes them to a git-ignored folder named by image digest, and
runs ``step13c_unimernet_worker.py`` with the side CPython 3.12 environment as a
subprocess. Readings are kept per image digest in
``experiments/out/step13c/unimernet/<book>.jsonl`` so evaluation can swap them in for the
image path. Comparison only: the stage itself does not call UniMERNet.

Usage: python step13c_unimernet.py --book statistics
"""

# ruff: noqa: E402
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step7_layouts import CACHE
from step13_books import BOOKS
from step13c_readings import book_size, keys_of

from book_core.cache_store import read_model
from book_core.equations.models import PageEquations
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.mathml.images import RegionImages, region_direction, region_marks
from book_core.mathml.settings import MathSettings
from book_core.mathml.symbols import TextSymbols
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import verified_read
from book_core.objects.models import NativeObjectPage
from book_core.run_context import source_session

SIDE = ROOT / ".cache/side_envs/unimernet/Scripts/python.exe"
WEIGHTS = (
    ROOT
    / ".cache/huggingface/models--wanderkid--unimernet_tiny/snapshots"
    / "3f09ac4b1cd583be47ea20a7d7daef839473028a"
)
CROPS = ROOT / ".cache/step13c/crops"
OUT = ROOT / "experiments/out/step13c/unimernet"


def crops(book):
    keys = keys_of(book)
    source = reference_path(BOOKS[book][0])
    target = CROPS / book
    target.mkdir(parents=True, exist_ok=True)
    size = book_size(book, keys)
    mapping = {}
    with source_session(source):
        images = RegionImages(PyMuPDFExtractor("cpu"), source, MathSettings().recognition_dpi)
        number = 1
        while (path := CACHE / "equations" / keys["equations"] / f"{number}.json").exists():
            record = read_model(path, PageEquations, keys["equations"])
            if record.regions:
                page = read_model(
                    CACHE / "text" / keys["native"] / f"{number}.json",
                    ExtractedPage,
                    keys["native"],
                )
                native = verified_read(
                    CACHE / "native" / keys["native"] / f"{number}.json",
                    NativeObjectPage,
                    keys["native"],
                )
                objects = {o.id: o for o in native.objects}
                text = TextSymbols(page, native)
                for region in record.regions:
                    box = (
                        region.bbox.x0,
                        region.bbox.y0,
                        region.bbox.x1,
                        region.bbox.y1,
                    )
                    png = images.crop(
                        number,
                        box,
                        region_marks(region, objects, text),
                        size,
                        region_direction(region, text),
                    )
                    digest = hashlib.sha256(png).hexdigest()
                    file = target / f"{digest}.png"
                    if not file.exists():
                        file.write_bytes(png)
                    mapping[region.id] = digest
            number += 1
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    mapping = crops(args.book)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.book}_regions.json").write_text(json.dumps(mapping, indent=0), "utf-8")
    listing = CROPS / f"{args.book}_list.json"
    files = sorted({str(CROPS / args.book / f"{d}.png") for d in mapping.values()})
    listing.write_text(json.dumps(files), "utf-8")
    raw = CROPS / f"{args.book}_readings.jsonl"
    rendered = time.perf_counter() - started
    subprocess.run(
        [str(SIDE), "-I", str(ROOT / "experiments/step13c_unimernet_worker.py"),
         "--weights", str(WEIGHTS), "--images", str(listing), "--out", str(raw)],
        check=True,
    )  # fmt: skip
    readings, header, seconds = {}, None, []
    for line in raw.read_text("utf-8").splitlines():
        row = json.loads(line)
        if row["path"] is None:
            header = row
            continue
        readings[Path(row["path"]).stem] = row["latex"]
        seconds.append(row["seconds"])
    (OUT / f"{args.book}.jsonl").write_text(
        "".join(
            json.dumps({"image_sha256": k, "latex": v}, ensure_ascii=False) + "\n"
            for k, v in sorted(readings.items())
        ),
        "utf-8",
    )
    summary = {
        "book": args.book,
        "regions": len(mapping),
        "images": len(files),
        "readings": len(readings),
        "render_seconds": round(rendered, 1),
        "model_seconds_total": round(sum(seconds), 1),
        "model_seconds_mean": round(sum(seconds) / max(1, len(seconds)), 3),
        "worker": header,
        "weights": "wanderkid/unimernet_tiny@3f09ac4b1cd583be47ea20a7d7daef839473028a",
    }
    (OUT / f"{args.book}_summary.json").write_text(json.dumps(summary, indent=1), "utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
