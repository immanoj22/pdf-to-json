"""Step 13a recall review for books without math gold: lines holding a math operator
(Unicode Sm) or a Greek letter in other-script text that no equation region touches, plus
the partial-boundary share of the regions. Writes the list for manual judgement.

Usage: python step13_missed.py --book immigrant_children --key KEY
"""

# ruff: noqa: E402
import argparse
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step13_equations import DEV, OUT, stage_inputs

from book_core.equations.cache import load_page


def candidate(text):
    letters = [c for c in text if c.isalpha()]
    greek = [c for c in letters if "GREEK" in unicodedata.name(c, "")]
    operator = any(unicodedata.category(c) == "Sm" for c in text)
    return operator or (greek and len(greek) < 0.5 * len(letters))


def main(book, key, run):
    inputs = stage_inputs(book, run)
    missed, covered = [], 0
    for page in inputs["pages"]():
        number = page.geometry.page
        record = load_page(DEV, key, number)
        spans = {ref.span_id for region in record.regions for ref in region.span_refs}
        lines = {lid for region in record.regions for lid in region.line_ids}
        for line in inputs["layout_of"](page).lines:
            text = "".join(page.store.spans[s].raw_text for s in line.span_ids)
            if not candidate(text):
                continue
            if line.id in lines or spans & set(line.span_ids):
                covered += 1
                continue
            missed.append({"page": number, "line": text.strip()})
    row = {
        "book": book,
        "key": key,
        "candidate_lines_covered": covered,
        "candidate_lines_missed": len(missed),
        "missed": missed,
    }
    target = OUT / "evaluation" / "recall_review"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{book}.json").write_text(
        json.dumps(row, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    print(book, covered, len(missed))
    for item in missed:
        print(item["page"], ascii(item["line"][:110]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--run", default="step12")
    args = parser.parse_args()
    main(args.book, args.key, args.run)
