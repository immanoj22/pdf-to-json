"""Step 12: classes of pages where we find more figures than the reference (and fewer).

Per page with a count disagreement, from the final archive figure records and the reference
view (``step12_evaluate.reference_view``):

- no reference figure on the page: small artwork (<2% of the content area: icons, bullets,
  logos), front-matter pages (before the first page with a reference figure), or other;
- more than the reference: separate figures of one multi-panel reference figure (our boxes
  touch or nearly touch: gap < 2% of the page's shorter side), or small extra artwork beside
  a reference figure, or other;
- fewer than the reference: we merged panels the reference keeps apart, or missed a figure.

Usage: python step12_overdetect.py --book medical_anatomy
"""

# ruff: noqa: E402
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step12_evaluate import reference_view

from book_core.cache_store import read_json

RUN = ROOT / "experiments/out/step12" / os.environ.get("STEP12_OUT", "run")
SMALL = 0.02
TOUCH = 0.02


def gap(a, b):
    dx = max(0.0, max(a["x0"], b["x0"]) - min(a["x1"], b["x1"]))
    dy = max(0.0, max(a["y0"], b["y0"]) - min(a["y1"], b["y1"]))
    return max(dx, dy)


def main(book):
    run = json.loads((RUN / f"performance/{book}.json").read_text("utf-8"))["run"]
    output = Path(run["output"])
    _, ref_pages, _ = reference_view(book)
    first_ref = min((p for p in ref_pages if p), default=0)
    classes = defaultdict(list)
    for number in range(1, run["pages"] + 1):
        page = read_json(output / f"page_{number:06d}.json.gz")
        figures = page["figures"]["figures"]
        content = page["source"]["geometry"]["content_bbox"]
        area = (content["x1"] - content["x0"]) * (content["y1"] - content["y0"])
        short = min(content["x1"] - content["x0"], content["y1"] - content["y0"])
        ours, ref = len(figures), ref_pages.get(number, 0)
        if ours == ref:
            continue
        shares = [
            (f["bbox"]["x1"] - f["bbox"]["x0"]) * (f["bbox"]["y1"] - f["bbox"]["y0"]) / area
            for f in figures
        ]
        row = {"page": number, "ours": ours, "reference": ref,
               "names": [f["name"] for f in figures],
               "area_shares": [round(s, 3) for s in shares]}  # fmt: skip
        if ours > ref and ref == 0:
            if all(s < SMALL for s in shares):
                cls = "no reference figure: only small artwork (<2% of content area)"
            elif number < first_ref:
                cls = "no reference figure: front matter before the first reference figure"
            else:
                cls = "no reference figure: other"
        elif ours > ref:
            touching = any(
                gap(a["bbox"], b["bbox"]) < TOUCH * short
                for i, a in enumerate(figures)
                for b in figures[i + 1 :]
            )
            small = sum(s < SMALL for s in shares)
            if touching:
                cls = "more than reference: panels of one figure kept apart (boxes nearly touch)"
            elif ours - small <= ref:
                cls = "more than reference: extra small artwork beside reference figures"
            else:
                cls = "more than reference: other"
        elif ours == 0:
            cls = "fewer than reference: no figure found"
        else:
            cls = "fewer than reference: fewer figures than reference images"
        classes[cls].append(row)
    result = {
        cls: {"pages": len(rows), "figures_over_or_under": sum(r["ours"] - r["reference"]
              for r in rows), "examples": rows[:3]}
        for cls, rows in sorted(classes.items(), key=lambda kv: -len(kv[1]))
    }  # fmt: skip
    target = ROOT / f"experiments/out/step12/overdetection_{book}.json"
    target.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    for cls, row in result.items():
        print(row["pages"], row["figures_over_or_under"], cls, [e["page"] for e in row["examples"]])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    main(parser.parse_args().book)
