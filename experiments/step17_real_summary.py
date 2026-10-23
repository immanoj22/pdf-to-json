"""Step 17 Part 1: the two readers on the real scans, per group (language and script).

Reads ``real_eval/rows.jsonl`` (``step17_real_eval.py``). Scores, as Step 16:

- Tesseract: CER/WER in its emitted order (it orders lines and columns itself);
  ``tesseract_vert`` (vertical model) for vertical print, reported beside it;
- PP-OCRv5: CER/WER after ordering its line boxes by position (evaluation only): vertical
  pages (most boxes taller than wide) read columns right to left, top to bottom; other pages
  are split into columns where a vertical gap no line crosses lies in the middle of the
  page (full-width lines are bands read in place), columns left to right (right to left for
  Arabic), lines top to bottom inside a column (``step16_real_eval.line_ordered``);
- the order-free character F1 for both.

A reader is better for a group when its character errors are fewer by at least 20% of the
other's (relative) and it wins on at least two thirds of the group's pages; the counts behind
each decision are written.

Usage: python step17_real_summary.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.ocr.evaluation import error_counts

import step16_real_eval as s16

OUT = ROOT / "experiments/out/step17/real_eval"
MARGIN = 0.2
WINS = 2 / 3


def group_of(row):
    script = row.get("script") or row["language"]
    return f"{row['language']} | {script}"


def ordered(boxes, rtl):
    words = [
        SimpleNamespace(text=t, pixel_bbox=tuple(b)) for t, b, *_ in boxes if t.strip()
    ]
    if not words:
        return ""
    tall = sum((w.pixel_bbox[3] - w.pixel_bbox[1]) > 1.5 * (w.pixel_bbox[2] - w.pixel_bbox[0])
               for w in words)  # fmt: skip
    if tall * 2 > len(words):
        columns = sorted(words, key=lambda w: (-(w.pixel_bbox[0] + w.pixel_bbox[2]) / 2,
                                               w.pixel_bbox[1]))  # fmt: skip
        return "\n".join(w.text for w in columns)
    x0 = min(w.pixel_bbox[0] for w in words)
    x1 = max(w.pixel_bbox[2] for w in words)
    width = x1 - x0
    # A column gap: a vertical line in the middle of the page crossed by at most 5% of the
    # boxes (headers and full-width lines become bands read in place).
    split, full = None, []
    allowed = max(1, int(0.05 * len(words)))
    for k in range(30, 71):
        x = x0 + width * k / 100
        crossing = [w for w in words if w.pixel_bbox[0] < x < w.pixel_bbox[2]]
        left = [w for w in words if w.pixel_bbox[2] <= x]
        right = [w for w in words if w.pixel_bbox[0] >= x]
        if len(crossing) <= allowed and len(left) >= 3 and len(right) >= 3:
            split, full = x, crossing
            break
    rest = [w for w in words if w not in full]
    if split is None:
        return s16.line_ordered(words, rtl=rtl)
    # Bands: full-width lines cut the page; columns are read inside each band.
    cuts = sorted((w.pixel_bbox[1] + w.pixel_bbox[3]) / 2 for w in full)
    bands = defaultdict(list)
    for w in rest:
        centre = (w.pixel_bbox[1] + w.pixel_bbox[3]) / 2
        bands[sum(c < centre for c in cuts)].append(w)
    parts = []
    for index in range(len(cuts) + 1):
        if index > 0:
            parts.append(full[sorted(range(len(full)), key=lambda i: (full[i].pixel_bbox[1]
                                                                       + full[i].pixel_bbox[3]))[
                index - 1]].text)  # fmt: skip
        group = bands.get(index, [])
        left = [w for w in group if w.pixel_bbox[2] <= split]
        right = [w for w in group if w.pixel_bbox[0] >= split]
        cols = [right, left] if rtl else [left, right]
        parts.extend(s16.line_ordered(c, rtl=rtl) for c in cols if c)
    return "\n".join(p for p in parts if p)


def main():
    rows = [
        json.loads(line)
        for line in (OUT / "rows.jsonl").read_text("utf-8").splitlines()
    ]
    pages = defaultdict(dict)
    for row in rows:
        pages[row["scan"]][row["reader"]] = row
    groups = defaultdict(lambda: defaultdict(lambda: {"characters": 0, "character_errors": 0,
                                                       "words": 0, "word_errors": 0}))  # fmt: skip
    per_page = []
    for scan, readers in sorted(pages.items()):
        any_row = next(iter(readers.values()))
        reference = any_row.get("reference") or s16.truth(
            ROOT / "experiments/test_data" / any_row["set"] / scan
        )
        cjk = any_row["language"] in {"chi_sim", "chi_tra"}
        rtl = any_row["language"] == "ara"
        group = group_of(any_row) + (" (Step 16 pages)" if any_row["set"] == "step16_real_scans"
                                     else "")  # fmt: skip
        page_row = {"scan": scan, "group": group}
        for reader, row in readers.items():
            if reader == "pp_ocrv5":
                text = ordered(row["boxes"], rtl)
            else:
                text = row["hypothesis"]
            counts = error_counts(reference, text, cjk=cjk)
            for key in ("characters", "character_errors", "words", "word_errors"):
                groups[group][reader][key] += counts[key]
            page_row[reader] = (
                round(counts["cer"], 4) if counts["cer"] is not None else None
            )
            page_row[f"{reader}_order_free_f1"] = round(
                s16.order_free(reference, text)["f1"], 4
            )
        per_page.append(page_row)
    summary = {}
    for group, readers in sorted(groups.items()):
        row = {}
        for reader, c in readers.items():
            row[reader] = {
                **c,
                "cer": round(c["character_errors"] / c["characters"], 4),
                "wer": round(c["word_errors"] / c["words"], 4) if c["words"] else None,
            }
        mine = [
            p
            for p in per_page
            if p["group"] == group and "pp_ocrv5" in p and "tesseract" in p
        ]
        wins = sum(p["pp_ocrv5"] < p["tesseract"] for p in mine)
        if "pp_ocrv5" in row and "tesseract" in row:
            t, p = (
                row["tesseract"]["character_errors"],
                row["pp_ocrv5"]["character_errors"],
            )
            row["pp_wins_pages"] = f"{wins} of {len(mine)}"
            row["pp_better"] = p <= (1 - MARGIN) * t and wins >= WINS * len(mine)
            row["tesseract_better"] = t <= (1 - MARGIN) * p and (
                len(mine) - wins
            ) >= WINS * len(mine)
        summary[group] = row
    result = {
        "rule": f"better: at least {MARGIN:.0%} fewer character errors and wins on at "
        f"least two thirds of the pages",
        "groups": summary,
        "pages": per_page,
    }
    (OUT / "summary.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n",
                                      "utf-8", newline="\n")  # fmt: skip
    for group, row in summary.items():
        print(
            group,
            {
                r: (v["cer"], v["character_errors"], v["characters"])
                for r, v in row.items()
                if isinstance(v, dict)
            },
            row.get("pp_wins_pages"),
            "PP better"
            if row.get("pp_better")
            else "Tess better"
            if row.get("tesseract_better")
            else "",
        )


if __name__ == "__main__":
    main()
