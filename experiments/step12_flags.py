"""Step 12: review flags per book by type and severity, from the final archives.

Severity:
- must-check: a possibly wrong or fake figure, or a link at risk of being wrong;
- quick-confirm: a single proposal or an inferred value a reviewer confirms at a glance;
- info-only: an encoding or presentation choice.
Alt-text slots are counted separately (normal team work, not a flag).

Usage: STEP12_OUT=final python step12_flags.py
"""

# ruff: noqa: E402
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.cache_store import read_json
from book_core.figures.cache import PAGE_SCALE
from book_core.figures.evidence import MODEL_DISAGREES
from book_core.figures.imaging import UNCERTAIN
from book_core.figures.names import COLLISION, INFERRED, NO_LABEL

RUN = ROOT / "experiments/out/step12" / os.environ.get("STEP12_OUT", "run")
BOOKS = ("spanish_us_history", "immigrant_children", "art_therapy_index", "medical_anatomy")
SEVERITY = {
    "model disagrees": "must-check",
    "page-scale figure region": "must-check",
    "unit mixes figure roles or figures": "must-check",
    "page credit proposing several figures": "must-check",
    "page credit with one proposed figure": "quick-confirm",
    "inferred page label": "quick-confirm",
    "no page label (named by PDF page)": "quick-confirm",
    "file name collision suffix": "quick-confirm",
    "unlinked caption": "quick-confirm",
    "format: mixed evidence, PNG": "info-only",
    "spread halves disagree on photo/drawing": "info-only",
    "small artwork (client setting)": "info-only",
}


def flag_type(text):
    return {
        MODEL_DISAGREES: "model disagrees",
        PAGE_SCALE: "page-scale figure region",
        INFERRED: "inferred page label",
        NO_LABEL: "no page label (named by PDF page)",
        COLLISION: "file name collision suffix",
        UNCERTAIN: "format: mixed evidence, PNG",
    }.get(text) or (
        "unit mixes figure roles or figures"
        if "mixes figure roles" in text
        else "spread halves disagree on photo/drawing"
        if "spread halves disagree" in text
        else f"other: {text[:60]}"
    )


def book_flags(book):
    run = json.loads((RUN / f"performance/{book}.json").read_text("utf-8"))["run"]
    output, pages = Path(run["output"]), run["pages"]
    counts, alt = Counter(), Counter()
    for number in range(1, pages + 1):
        figures = read_json(output / f"page_{number:06d}.json.gz")["figures"]
        for figure in figures["figures"]:
            for text in figure["review_flags"]:
                counts[flag_type(text)] += 1
            counts["small artwork (client setting)"] += figure.get("small_artwork", False)
            alt[f"{figure['alt_text']['status']} / {figure['alt_text']['source']}"] += 1
        counts["unlinked caption"] += len(figures["unlinked_captions"])
        for credit in figures.get("page_credits", []):
            one = len(credit["proposed_figure_ids"]) == 1
            counts[
                "page credit with one proposed figure"
                if one
                else "page credit proposing several figures"
            ] += 1
    rows = {
        name: {"count": n, "severity": SEVERITY.get(name, "must-check")}
        for name, n in counts.most_common()
        if n
    }
    by_severity = Counter()
    for row in rows.values():
        by_severity[row["severity"]] += row["count"]
    return {
        "pages": pages,
        "flags": rows,
        "by_severity": dict(by_severity),
        "must_check_per_100_pages": round(100 * by_severity["must-check"] / pages, 2),
        "alt_text_slots": dict(alt),
    }


def main():
    result = {book: book_flags(book) for book in BOOKS}
    (RUN / "review_flags.json").write_text(
        json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    for book, row in result.items():
        print(book, row["by_severity"], row["must_check_per_100_pages"], row["alt_text_slots"])


if __name__ == "__main__":
    main()
