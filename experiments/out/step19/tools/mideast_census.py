"""Step 19: Mideast heading census and review-safety counts on a confirmation run.

Reuses Step 18's saved source observations of 20 pages
(experiments/out/step18/measurement_evidence/source_census_mideast_*.json), recorded before
any output was examined, and matches them mechanically against one run's publication: each
observed standalone heading is found by normalized text among the page's units; each observed
running head is looked for among the page's furniture and its heading units. Descriptive only:
Mideast has no reference, so no rate is claimed.

usage: python mideast_census.py TAG     (run from the repository root)
"""

import glob
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]


def norm(text):
    return re.sub(r"\W", "", unicodedata.normalize("NFKC", text).casefold())


def main():
    import step17_json_eval as json_eval
    from step19_run import OUT

    tag = sys.argv[1]
    performance = json.loads((OUT / tag / "performance" / "mideast.json").read_text("utf-8"))
    book_json = Path(performance["run"]["book_json"]) / "book.json"
    book = json.loads(book_json.read_text("utf-8"))
    _, _, units = json_eval.json_view(book)
    by_page = {}
    for uid, unit in units.items():
        by_page.setdefault(unit["page"], []).append((uid, unit))
    furniture = {}
    for item in book["furniture"]:
        for page in [item.get("page")] if item.get("page") else item.get("pages", []):
            furniture.setdefault(page, []).append(item)
    observations = [row for path in sorted(glob.glob(str(
        ROOT / "experiments/out/step18/measurement_evidence/source_census_mideast_0*.json")))
        for row in json.loads(Path(path).read_text("utf-8"))]  # fmt: skip
    counts, rows = Counter(), []
    for row in observations:
        page, units_here = row["page"], by_page.get(row["page"], [])
        out = {"page": page, "headings": [], "running_headers": []}
        for heading in row["headings"]:
            key = norm(heading["text"])
            hits = [(uid, u) for uid, u in units_here
                    if key and key in norm(json_eval_text(u["node"]))]  # fmt: skip
            counts["source_headings"] += 1
            if not hits:
                verdict = "not_found_as_unit"
            else:
                node = hits[0][1]["node"]
                flagged = any(f.startswith("heading:") for f in node.get("flags", []))
                if hits[0][1]["type"] == "heading":
                    verdict = "heading"
                elif flagged:
                    verdict = f"{hits[0][1]['type']}_flagged_heading_like"
                else:
                    verdict = f"{hits[0][1]['type']}_unflagged"
            counts[f"heading:{verdict}"] += 1
            out["headings"].append({"text": heading["text"], "verdict": verdict})
        for header in row["running_headers"]:
            key = norm(header["text"])
            as_heading = [uid for uid, u in units_here if u["type"] == "heading"
                          and norm(json_eval_text(u["node"])) == key]  # fmt: skip
            as_furniture = [f for f in furniture.get(page, [])
                            if norm((f.get("content") or {}).get("text", "")) == key]  # fmt: skip
            verdict = ("heading" if as_heading else "furniture" if as_furniture
                       else "other")  # fmt: skip
            counts["running_headers"] += 1
            counts[f"running_header:{verdict}"] += 1
            out["running_headers"].append({"text": header["text"], "verdict": verdict})
        rows.append(out)
    review = book["review"] if isinstance(book["review"], list) else book["review"].get("items", [])
    severity = Counter(key.split(":")[0] for key, n in book["review"]["counts"].items() for _ in range(n))
    pages = len(book["pages"])
    result = {
        "book": "mideast", "tag": tag, "census_pages": len(observations),
        "counts": dict(counts), "pages": rows,
        "review": {"items": len(review), "per_page": round(len(review) / pages, 3),
                   "by_severity": dict(severity)},
        "note": "Descriptive only: Step 18 source observations matched mechanically; no rate.",
    }  # fmt: skip
    target = OUT / tag / "mideast_census.json"
    with target.open("x", encoding="utf8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in result.items() if k != "pages"}, ensure_ascii=False))


def json_eval_text(node):
    content = node.get("content")
    return content.get("text", "") if isinstance(content, dict) else ""


if __name__ == "__main__":
    main()
