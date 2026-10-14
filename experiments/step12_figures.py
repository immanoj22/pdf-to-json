"""Step 12: run the figures stage on one book's cached current stages and summarize it.

Development use: reads the cached layout, final list units/order, object analysis and Step 8
page labels (``step12_measure.load``), runs ``analyze_book_figures`` into ``.cache/step12``
and writes the book profile, timing and image-size totals.

Usage: python step12_figures.py --book spanish_us_history [--variant alone]
"""

# ruff: noqa: E402
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step12_measure import load

OUT = ROOT / "experiments/out/step12"
CACHE12 = ROOT / ".cache/step12"
IMAGE_BYTES_PER_FIGURE = 4 * 1024**2  # conservative 300 dpi estimate (PNG of a full page)


def run(book, variant):
    from step7_layouts import CACHE
    from step11_run import CACHE11

    from book_core.book_run import _NativeObjects
    from book_core.figures.cache import analyze_book_figures
    from book_core.figures.settings import FigureSettings
    from book_core.lists.cache import load_page as list_page
    from book_core.lists.keys import book_fingerprint
    from book_core.objects.analysis import fingerprints

    _, _, furniture, _ = load(book)
    context = load.context
    source, extractor, inputs, lists = (context[k] for k in ("source", "extractor", "inputs",
                                                             "lists"))  # fmt: skip
    _, analysis_key = fingerprints(inputs.digest, extractor, inputs.repetition)
    total = extractor.page_count(source)
    estimate = IMAGE_BYTES_PER_FIGURE * 600
    free = shutil.disk_usage(ROOT).free
    if free - estimate < 10_000_000_000:
        raise SystemExit("Insufficient free disk for figure images")
    started = time.perf_counter()
    key, result = analyze_book_figures(
        source,
        lambda: extractor.extract_pages(source),
        lambda page: inputs(page)[0],
        lambda number: list_page(lists, number, CACHE11),
        _NativeObjects(CACHE, analysis_key),
        {m.page: (m.label, m.source) for m in furniture.book.markers},
        book_fingerprint(lists.book.cache_key_inputs),
        CACHE12,
        total,
        extractor,
        FigureSettings(model_evidence="off"),
    )
    seconds = round(time.perf_counter() - started, 1)
    images = list((CACHE12 / "figures" / key / "images").glob("*"))
    row = {
        "book": book,
        "variant": variant,
        "figures_key": key,
        "seconds": seconds,
        "disk": {"free_before": free, "estimate": estimate},
        "image_files": len(images),
        "image_bytes": sum(p.stat().st_size for p in images),
        "profile": result.profile,
        "spreads": [s.model_dump(mode="json") for s in result.spreads],
    }
    target = OUT / "figures" / variant / f"{book}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(row, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(row, indent=1)[:3000])
    return key


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--variant", default="alone")
    args = parser.parse_args()
    run(args.book, args.variant)
