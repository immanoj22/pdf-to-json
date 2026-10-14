"""Step 12 overlays from the published final archive only (figures, units, spans).

Drawing conventions: figure box blue with its file name; caption lines green; page-level
credit records orange dashed (proposals, never figure links); figure-internal text lines
purple; unlinked captions red. Pages are rendered through the Extractor.

Usage: python step12_overlays.py
"""

# ruff: noqa: E402
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import cv2
import numpy as np
from reference_paths import reference_path
from step7_layouts import BOOKS

from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.figures.imaging import decode_png

OUT = ROOT / "experiments/out/step12/overlays"
RUN = ROOT / "experiments/out/step12" / os.environ.get("STEP12_OUT", "run")
DPI = 110
# (book, physical page, what the page shows) - explicit review selections (CLI data).
PAGES = [
    ("spanish_us_history", 30, "composite figure (timeline of images and artwork)"),
    ("spanish_us_history", 125, "map with labels"),
    ("spanish_us_history", 123, "captioned photo"),
    ("spanish_us_history", 724, "rotated credit beside a figure (page 724)"),
    ("immigrant_children", 43, "book 2 figure"),
    ("medical_anatomy", 264, "book 4 anatomy diagram"),
]
COLOURS = {  # BGR
    "figure": (200, 90, 20),
    "caption": (40, 160, 40),
    "credit": (0, 140, 255),
    "internal": (160, 40, 160),
    "unlinked": (30, 30, 220),
}


def archive(book):
    run = json.loads((RUN / f"performance/{book}.json").read_text("utf-8"))["run"]
    return Path(run["output"])


def line_box(page, line_id):
    spans = page["source"]["store"]["spans"]
    boxes = [spans[s]["bbox"] for s in page["line_spans"][line_id]]
    return (
        min(b["x0"] for b in boxes),
        min(b["y0"] for b in boxes),
        max(b["x1"] for b in boxes),
        max(b["y1"] for b in boxes),
    )


def draw(image, scale, box, colour, width=2, dashed=False):
    x0, y0, x1, y1 = (int(round(v * scale)) for v in box)
    if not dashed:
        cv2.rectangle(image, (x0, y0), (x1, y1), colour, width)
        return
    for x in range(x0, x1, 8):
        cv2.line(image, (x, y0), (min(x + 4, x1), y0), colour, width)
        cv2.line(image, (x, y1), (min(x + 4, x1), y1), colour, width)
    for y in range(y0, y1, 8):
        cv2.line(image, (x0, y), (x0, min(y + 4, y1)), colour, width)
        cv2.line(image, (x1, y), (x1, min(y + 4, y1)), colour, width)


def overlay(book, number, title):
    page = read_json(archive(book) / f"page_{number:06d}.json.gz")
    extractor = PyMuPDFExtractor("cpu")
    raster = extractor.render_page(reference_path(BOOKS[book][0]), number, DPI)
    image = cv2.cvtColor(decode_png(raster.png), cv2.COLOR_RGB2BGR)
    scale = raster.width / raster.page_width
    row = {"book": book, "page": number, "shows": title, "figures": []}
    for figure in page["figures"]["figures"]:
        b = figure["bbox"]
        draw(image, scale, (b["x0"], b["y0"], b["x1"], b["y1"]), COLOURS["figure"], 3)
        label = f"{figure['name']} ({figure['kind']}, #{figure['anchor']['reading_index']})"
        cv2.putText(image, label, (int(b["x0"] * scale) + 4, int(b["y0"] * scale) + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOURS["figure"], 2)  # fmt: skip
        for role, links in (
            ("caption", figure["captions"]),
            ("credit", figure["credits"]),
            ("internal", figure["internal_text"]),
        ):
            for link in links:
                for line in link["line_ids"]:
                    draw(image, scale, line_box(page, line), COLOURS[role], 2,
                         dashed=link["review_required"])  # fmt: skip
        row["figures"].append(
            {
                "name": figure["name"],
                "kind": figure["kind"],
                "format": figure["image"]["format"] if figure["image"] else None,
                "captions": [c["rule"] for c in figure["captions"]],
                "credits": [c["rule"] for c in figure["credits"]],
                "internal_units": len(figure["internal_text"]),
                "review_flags": figure["review_flags"],
            }
        )
    for credit in page["figures"]["page_credits"]:
        for line in credit["line_ids"]:
            draw(image, scale, line_box(page, line), COLOURS["credit"], 2, dashed=True)
    row["page_credits"] = [c["rule"] for c in page["figures"]["page_credits"]]
    for caption in page["figures"]["unlinked_captions"]:
        for line in caption["line_ids"]:
            draw(image, scale, line_box(page, line), COLOURS["unlinked"], 2)
    row["unlinked_captions"] = len(page["figures"]["unlinked_captions"])
    OUT.mkdir(parents=True, exist_ok=True)
    name = f"figures_{book}_p{number}.png"
    cv2.imwrite(str(OUT / name), image)
    row["file"] = name
    return row


def main():
    rows = [overlay(*entry) for entry in PAGES]
    legend = {k: list(v[::-1]) for k, v in COLOURS.items()}
    (OUT / "overlays.json").write_text(
        json.dumps({"colours_rgb": legend, "pages": rows}, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(rows, indent=1, ensure_ascii=False)[:4000])


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
