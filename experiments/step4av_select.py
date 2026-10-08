"""Step 4a-v candidate list: contact sheet and selection table from page_stats.jsonl.

Selection was made from geometry/text statistics (step4av_scan.py) plus a visual check.
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from step4av_scan import SOURCES

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step4av"
CANDIDATES = [
    (
        "u01_art_index_3col",
        "art_index_pdf",
        3,
        "3-column page",
        "3 equal lanes, 97/161 lines end in locators",
    ),
    (
        "u02_science_index",
        "science_pdf",
        709,
        "index page",
        "banner title then 3 lanes; 64 locator lines; 42 aligned rows",
    ),
    (
        "u03_spanish_index_4col",
        "spanish_pdf",
        700,
        "index page (4 columns)",
        "4 narrow lanes (scan saw 3: lane split below 8% width); Spanish locators",
    ),
    (
        "u04_canadian_scanned",
        "canadian_index_pdf",
        200,
        "scanned page",
        "page image covers 0.93; all 336 text spans render mode 3 (invisible OCR layer)",
    ),
    (
        "u05_immigrant_image_only",
        "small_pdf",
        1,
        "image-only page",
        "image covers 1.0; 0 native characters (cover)",
    ),
    (
        "u06_science_ruled_table",
        "science_pdf",
        656,
        "table-heavy (ruled)",
        "78 h-rules, 92 v-rules, 33 aligned rows",
    ),
    (
        "u07_immigrant_rotated_table",
        "small_pdf",
        71,
        "table-heavy (rotated)",
        "20 aligned rows; 16 vertical strokes = rotated table rules; text rotated 90 degrees",
    ),
    (
        "u08_immigrant_unruled_table",
        "small_pdf",
        206,
        "table-heavy (whitespace) + prose",
        "16 aligned rows, 5 h-rules, table above full-width prose",
    ),
    (
        "u09_science_unframed_cards",
        "science_pdf",
        11,
        "unframed cards",
        "name/affiliation blocks in a grid separated only by whitespace under a colored banner",
    ),
    (
        "u10_science_fullwidth_figure",
        "science_pdf",
        113,
        "full-width figure",
        "image cover 0.14 as one strip spanning the text width, between prose and a vocabulary box",
    ),
    (
        "u11_spanish_fullpage_map",
        "spanish_pdf",
        654,
        "full-width figure (map)",
        "3 filled drawings > 70% width; 769 short label lines",
    ),
    (
        "u12_spanish_bilingual_glossary",
        "spanish_pdf",
        675,
        "bilingual page",
        "Spanish/English stopwords 86/67; one language per column, ruled two-column table",
    ),
    (
        "u13_science_bilingual_glossary",
        "science_pdf",
        696,
        "bilingual page (parallel columns)",
        "English book; Spanish/English stopwords 135/86; English column left, Spanish column right",
    ),
    (
        "u14_spanish_sidebar",
        "spanish_pdf",
        145,
        "sidebar page",
        "framed narrow reading-strategy box beside a wide column; lane ratio 0.37; 25 h-rules",
    ),
    (
        "u15_science_narrow_wide",
        "science_pdf",
        299,
        "narrow column next to wide",
        "lanes [80-462] and [520-612]; ratio 0.24; unframed",
    ),
]


def stats():
    rows = [json.loads(line) for line in (OUT / "page_stats.jsonl").open(encoding="utf-8")]
    return {(r["source"], r["page"]): r for r in rows}


def tile(key, page_number, label, height=520, width=380):
    with pymupdf.open(SOURCES[key]) as doc:
        page = doc[page_number - 1]
        zoom = height / page.rect.height
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)[:, :, ::-1]
    image = image[:, :width]
    out = np.full((height + 50, width, 3), 255, np.uint8)
    out[50 : 50 + image.shape[0], : image.shape[1]] = image
    for i, text in enumerate(label):
        cv2.putText(out, text, (4, 18 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 170), 1)
    return out


def main():
    table = stats()
    tiles, lines = (
        [],
        [
            "| ID | Source key | Physical page | Covers | Statistics behind the pick |",
            "|---|---|---:|---|---|",
        ],
    )
    for cid, key, page, covers, why in CANDIDATES:
        assert (key, page) in table, (key, page)
        tiles.append(tile(key, page, [f"{cid}", f"{key}  physical p{page}"]))
        lines.append(f"| {cid} | {key} | {page} | {covers} | {why} |")
    cols = 5
    rows = (len(tiles) + cols - 1) // cols
    h, w = tiles[0].shape[:2]
    sheet = np.full((rows * h, cols * w, 3), 160, np.uint8)
    for i, t in enumerate(tiles):
        sheet[(i // cols) * h : (i // cols) * h + h, (i % cols) * w : (i % cols) * w + w] = t
    cv2.imwrite(str(OUT / "contact_sheet.png"), sheet)
    (OUT / "candidates.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    json.dump(
        [
            dict(zip(("id", "source_key", "physical_page", "covers", "why"), c, strict=True))
            for c in CANDIDATES
        ],
        (OUT / "candidates.json").open("w", encoding="utf-8"),
        indent=2,
    )


if __name__ == "__main__":
    main()
