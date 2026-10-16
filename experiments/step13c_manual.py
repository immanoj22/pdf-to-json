"""Step 13c seeded manual check: 40 equation records of the math book, render vs MathML.

Draws 40 records (seed 1340) from the final Statistics MathML records, renders each region
from the PDF (the stage renderer, own marks only) and writes sheets of five: the PDF crop on
the left, the chosen reading on the right (its LaTeX, which is serialized from the same tree
as the MathML; Cambria Math), with the path, review status and confidence. The judgement
of each row is recorded by hand in ``manual_check.json`` (``verdicts``).

Usage: python step13c_manual.py --out final
"""

# ruff: noqa: E402
import argparse
import io
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from PIL import Image, ImageDraw, ImageFont
from reference_paths import reference_path
from step13_books import BOOKS

from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.mathml.images import RegionImages, region_direction, region_marks
from book_core.mathml.symbols import TextSymbols
from book_core.model.spans import ExtractedPage
from book_core.run_context import source_session

OUT = ROOT / "experiments/out/step13c"
FONT = Path("C:/Windows/Fonts/cambria.ttc")
SEED, N = 1340, 40


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="final")
    args = parser.parse_args()
    run = json.loads((OUT / args.out / "performance/statistics.json").read_text("utf-8"))["run"]
    archive = Path(run["output"])
    records = []
    for number in range(1, run["pages"] + 1):
        payload = read_json(archive / f"page_{number:06d}.json.gz")
        for record in payload["mathml"]["equations"]:
            records.append((number, record))
    sample = random.Random(SEED).sample(records, N)
    sample.sort(key=lambda item: (item[0], item[1]["equation_id"]))
    target = OUT / "manual"
    target.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(FONT), 22)
    small = ImageFont.truetype(str(FONT), 16)
    rows, crops = [], []
    source = reference_path(BOOKS["statistics"][0])
    extractor = PyMuPDFExtractor("cpu")
    from step7_layouts import CACHE

    from book_core.equations.models import PageEquations
    from book_core.objects.analysis import verified_read
    from book_core.objects.models import NativeObjectPage

    keys = run["cache_keys"]
    with source_session(source):
        images = RegionImages(extractor, source, 300)
        for index, (number, record) in enumerate(sample, start=1):
            payload = read_json(archive / f"page_{number:06d}.json.gz")
            page = ExtractedPage.model_validate(payload["source"])
            region = next(
                r
                for r in PageEquations.model_validate(payload["equations"]).regions
                if r.id == record["equation_id"]
            )
            native = verified_read(
                CACHE / "native" / keys["native"] / f"{number}.json",
                NativeObjectPage,
                keys["native"],
            )
            objects = {o.id: o for o in native.objects}
            box = (region.bbox.x0, region.bbox.y0, region.bbox.x1, region.bbox.y1)
            text = TextSymbols(page, native)
            png = images.crop(
                number,
                box,
                region_marks(region, objects, text),
                8.25,
                region_direction(region, text),
            )
            crops.append(Image.open(io.BytesIO(png)).convert("RGB"))
            rows.append(
                {
                    "row": index,
                    "page": number,
                    "equation_id": record["equation_id"],
                    "source": record["source"],
                    "presentation": record["presentation"],
                    "path": record["path"],
                    "review_status": record["review_status"],
                    "confidence": record["confidence"],
                    "output": record["output"],
                    "latex": record["latex"],
                    "readings": {r["path"]: r["latex"] for r in record["readings"]},
                }
            )
    for sheet in range(0, N, 5):
        part = list(zip(rows[sheet : sheet + 5], crops[sheet : sheet + 5], strict=True))
        width = 1600
        heights = [max(120, min(crop.height, 400) + 70) for _, crop in part]
        canvas = Image.new("RGB", (width, sum(heights)), "white")
        draw = ImageDraw.Draw(canvas)
        y = 0
        for (row, crop), height in zip(part, heights, strict=True):
            scale = min(1.0, 700 / crop.width, 400 / crop.height)
            shown = crop.resize((max(1, int(crop.width * scale)), max(1, int(crop.height * scale))))
            canvas.paste(shown, (10, y + 30))
            draw.text((10, y + 4), f"#{row['row']} p{row['page']} {row['source']} "
                      f"{row['presentation']} path={row['path']} {row['review_status']} "
                      f"conf={row['confidence']}", fill="black", font=small)  # fmt: skip
            text = row["latex"] or "(no MathML)"
            lines = [text[i : i + 60] for i in range(0, len(text), 60)][:8]
            for k, line in enumerate(lines):
                draw.text((740, y + 30 + 26 * k), line, fill="navy", font=font)
            draw.line((0, y + height - 2, width, y + height - 2), fill="grey")
            y += height
        canvas.save(target / f"sheet_{sheet // 5 + 1}.png")
    (target / "sample.json").write_text(
        json.dumps({"seed": SEED, "n": N, "rows": rows}, indent=1, ensure_ascii=False) + "\n",
        "utf-8",
    )
    print("sheets", (N + 4) // 5, "in", target)


if __name__ == "__main__":
    main()
