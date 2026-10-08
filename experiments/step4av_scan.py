"""Step 4a-v candidate scan: per-page geometry and text statistics only (no layout pipeline).

Reads configured references read-only; writes experiments/out/step4av/page_stats.jsonl.
"""

import json
import re
import sys
from pathlib import Path

import pymupdf
from reference_paths import reference_path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step4av"
OUT.mkdir(parents=True, exist_ok=True)
SOURCES = {
    "spanish_pdf": reference_path("spanish_pdf"),
    "science_pdf": reference_path("science_pdf"),
    "small_pdf": reference_path("small_pdf"),
    "canadian_index_pdf": reference_path("downloads") / "9780802027962.pdf",
    "art_index_pdf": reference_path("downloads")
    / "docbook xml index sample/docbook index input.pdf",
}
ES = set(
    (
        "el la los las de del que y en un una por con para es se al lo como más su sus pero"
        " este esta"
    ).split()
)
EN = set("the of and to in is that for it as with was on are by this be from or which an".split())
WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
LOCATOR = re.compile(r"\d+(?:\s*[-–,]\s*\d+)*[.,;]?\s*$")


def gutters(intervals, x0, x1, step=2.0):
    """Empty x-strips (>= 1.2% of width) between occupied text lanes."""
    width = x1 - x0
    bins = max(1, int(width / step))
    occ = [0] * bins
    for a, b in intervals:
        for i in range(max(0, int((a - x0) / step)), min(bins, int((b - x0) / step) + 1)):
            occ[i] += 1
    lanes, cur = [], None
    for i, v in enumerate(occ):
        if v and cur is None:
            cur = i
        if not v and cur is not None:
            lanes.append((cur, i))
            cur = None
    if cur is not None:
        lanes.append((cur, bins))
    lanes = [(x0 + a * step, x0 + b * step) for a, b in lanes if (b - a) * step > width * 0.08]
    merged = []
    for lane in lanes:
        if merged and lane[0] - merged[-1][1] < width * 0.012:
            merged[-1] = (merged[-1][0], lane[1])
        else:
            merged.append(lane)
    return merged


def page_stats(key, doc, index):
    page = doc[index]
    rect = page.rect
    area = rect.width * rect.height
    data = page.get_text("dict")
    lines, words, chars, bold = [], [], 0, 0
    for block in data["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = "".join(s["text"] for s in line["spans"])
            if not text.strip():
                continue
            chars += len(text.strip())
            lines.append((line["bbox"], text, line["spans"][0]["size"]))
            bold += any(s["flags"] & 16 for s in line["spans"])
            words += [w.lower() for w in WORD.findall(text)]
    image_cover = 0.0
    full_image = 0
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"]) & rect
        image_cover += r.get_area() / area
        full_image = max(
            full_image, int(r.width > rect.width * 0.75 and r.height > rect.height * 0.2)
        )
    drawings = page.get_drawings()
    hrule = vrule = filled_side = 0
    wide_art = 0
    for d in drawings:
        r = d["rect"]
        if r.height < 2 and r.width > rect.width * 0.08:
            hrule += 1
        if r.width < 2 and r.height > rect.height * 0.03:
            vrule += 1
        fill = d.get("fill")
        if (
            fill
            and min(fill) < 0.97
            and r.width < rect.width * 0.4
            and r.height > rect.height * 0.25
        ):
            filled_side += 1
        if (
            r.width > rect.width * 0.7
            and r.height > rect.height * 0.2
            and fill
            and min(fill) < 0.97
        ):
            wide_art += 1
    # column lanes from non-spanning lines in the vertical middle of the page
    body = [b for b, _, _ in lines if rect.height * 0.1 < b[1] < rect.height * 0.9]
    narrow = [(b[0], b[2]) for b in body if b[2] - b[0] < rect.width * 0.55]
    lanes = gutters(narrow, rect.x0, rect.x1) if len(narrow) >= 6 else []
    widths = [b - a for a, b in lanes]
    ratio = min(widths) / max(widths) if len(widths) >= 2 else None
    # rows with >= 3 separated segments on one baseline (table evidence)
    rows = {}
    for b, _, _ in lines:
        rows.setdefault(round(b[3] / 3), []).append(b[0])
    gridrows = sum(1 for xs in rows.values() if len(xs) >= 3)
    loc = sum(1 for _, t, _ in lines if LOCATOR.search(t))
    es = sum(w in ES for w in words)
    en = sum(w in EN for w in words)
    return {
        "source": key,
        "page": index + 1,
        "w": round(rect.width),
        "h": round(rect.height),
        "chars": chars,
        "lines": len(lines),
        "bold_lines": bold,
        "image_cover": round(image_cover, 3),
        "full_image": full_image,
        "drawings": len(drawings),
        "hrules": hrule,
        "vrules": vrule,
        "filled_side": filled_side,
        "wide_art": wide_art,
        "lanes": [[round(a), round(b)] for a, b in lanes],
        "lane_ratio": round(ratio, 3) if ratio else None,
        "grid_rows": gridrows,
        "locator_lines": loc,
        "es": es,
        "en": en,
        "words": len(words),
    }


def main():
    keys = sys.argv[1:] or list(SOURCES)
    with (OUT / "page_stats.jsonl").open("a", encoding="utf-8") as out:
        for key in keys:
            path = SOURCES[key]
            if not path.exists():
                print("MISSING", key, path)
                continue
            with pymupdf.open(path) as doc:
                print(key, path, len(doc), flush=True)
                for i in range(len(doc)):
                    out.write(json.dumps(page_stats(key, doc, i)) + "\n")


if __name__ == "__main__":
    main()
