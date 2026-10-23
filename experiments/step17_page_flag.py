"""Step 17 Part 1: the OCR page-level flag (``must_check``) from the share of flagged words.

The Step 16 rule (page mean word confidence < 0.773) caught 2 of the 61 held-out bad pages
(page CER > 10%). Here every page's features are the share of its words below the word
threshold (0.84) and the share of its lines whose line confidence is below it. Each rule
is fitted on the same seeded training half of the (book, page) pairs as Step 16 (all
degradations of a page together; ``step16_report_data.calibration``), by error-detection
F1 (ties: fewer flags), and scored on the held-out half: recall and precision with counts,
beside the old rule on the same pages. No OCR is run; the Step 16 case records are read.

Usage: python step17_page_flag.py
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step16_report_data as data

OUT = ROOT / "experiments/out/step17/ocr"
WORD_THRESHOLD = 0.84  # Step 16 held-out word calibration (now the Tesseract default)
BAD_PAGE = 0.10  # page CER above which a page needs checking (Step 16 definition)
OLD_PAGE_THRESHOLD = 0.773


def features(record):
    reading = record["readings"]["tesseract"]
    words = reading["words"]
    if not words:
        return None
    lines = defaultdict(list)
    for word in words:
        lines[tuple(word["line_key"])].append(word["line_confidence"])
    return {
        "mean_confidence": sum(w["confidence"] for w in words) / len(words),
        "flagged_word_share": sum(w["confidence"] < WORD_THRESHOLD for w in words)
        / len(words),
        "low_line_share": sum(v[0] < WORD_THRESHOLD for v in lines.values())
        / len(lines),
        "words": len(words),
        "lines": len(lines),
    }


def fit(rows, name, above=True, beta=1.0):
    """Best threshold on training rows by F-beta of bad-page detection (ties: fewer flags);
    ``above``: a page is flagged when its feature is at least the threshold; ``beta`` 2
    weighs recall (a missed bad page) over a needless check."""
    best = None
    for threshold in sorted({r[name] for r in rows}):
        counts = score(rows, name, threshold, above)
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        b2 = beta * beta
        f1 = (1 + b2) * tp / ((1 + b2) * tp + b2 * fn + fp) if tp else 0.0
        key = (f1, -(tp + fp))
        if best is None or key > best[0]:
            best = (key, threshold)
    return best[1]


def score(rows, name, threshold, above=True):
    tp = fp = fn = tn = 0
    for row in rows:
        flagged = row[name] >= threshold if above else row[name] < threshold
        tp += flagged and row["bad"]
        fp += flagged and not row["bad"]
        fn += (not flagged) and row["bad"]
        tn += (not flagged) and not row["bad"]
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "flagged": tp + fp, "bad": tp + fn,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None}  # fmt: skip


def main():
    tess, _ = data.latest(data.load_cases(), with_secondary=False)
    pages = sorted({(b, p) for b, p, _ in tess})
    train = set(random.Random("1600:calibration").sample(pages, len(pages) // 2))
    rows = {"train": [], "test": []}
    for (book, page, degradation), record in sorted(tess.items()):
        found = features(record)
        cer = record["scores"]["tesseract"]["geometry_aligned"]["cer"]
        if found is None or cer is None:
            continue
        part = "train" if (book, page) in train else "test"
        rows[part].append({**found, "book": book, "page": page, "degradation": degradation,
                           "cer": cer, "bad": cer > BAD_PAGE})  # fmt: skip
    result = {"definition": f"bad page: CER > {BAD_PAGE}; word flag: confidence < "
                            f"{WORD_THRESHOLD}; low line: line confidence < {WORD_THRESHOLD}",
              "split": "Step 16 seeded half of the (book, page) pairs",
              "pages": {k: len(v) for k, v in rows.items()},
              "bad_pages": {k: sum(r["bad"] for r in v) for k, v in rows.items()},
              "rules": {}}  # fmt: skip
    result["rules"]["old_mean_confidence"] = {
        "threshold": OLD_PAGE_THRESHOLD,
        "flag": "mean word confidence < threshold",
        "train": score(
            rows["train"], "mean_confidence", OLD_PAGE_THRESHOLD, above=False
        ),
        "held_out": score(
            rows["test"], "mean_confidence", OLD_PAGE_THRESHOLD, above=False
        ),
    }
    for name in ("flagged_word_share", "low_line_share"):
        threshold = fit(rows["train"], name)
        result["rules"][name] = {
            "threshold": threshold, "flag": f"{name} >= threshold",
            "train": score(rows["train"], name, threshold),
            "held_out": score(rows["test"], name, threshold)}  # fmt: skip
    for row in (*rows["train"], *rows["test"]):
        w, ln = (
            result["rules"][n]["threshold"]
            for n in ("flagged_word_share", "low_line_share")
        )
        row["either"] = float(
            row["flagged_word_share"] >= w or row["low_line_share"] >= ln
        )
    result["rules"]["either"] = {
        "flag": "flagged_word_share or low_line_share at its threshold",
        "train": score(rows["train"], "either", 1.0),
        "held_out": score(rows["test"], "either", 1.0)}  # fmt: skip
    # Two-fold cross-fit: each half fits, the other half scores (the second fold fits on
    # the 61 held-out bad pages); counts pooled. F1 as in Step 16, and F2 (recall-weighted).
    result["cross_fit"] = {}
    for beta in (1.0, 2.0):
        for name in ("flagged_word_share", "low_line_share"):
            folds, pooled = [], {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
            for fit_on, score_on in (("train", "test"), ("test", "train")):
                threshold = fit(rows[fit_on], name, beta=beta)
                counts = score(rows[score_on], name, threshold)
                folds.append(
                    {"fit_on": fit_on, "threshold": threshold, "scored": counts}
                )
                for k in pooled:
                    pooled[k] += counts[k]
            tp, fp, fn = pooled["tp"], pooled["fp"], pooled["fn"]
            pooled["recall"] = round(tp / (tp + fn), 4)
            pooled["precision"] = round(tp / (tp + fp), 4) if tp + fp else None
            result["cross_fit"][f"{name}|F{beta:g}"] = {
                "folds": folds,
                "pooled": pooled,
            }
    old = [score(rows[k], "mean_confidence", OLD_PAGE_THRESHOLD, above=False)
           for k in ("train", "test")]  # fmt: skip
    result["cross_fit"]["old_mean_confidence"] = {
        "pooled": {k: old[0][k] + old[1][k] for k in ("tp", "fp", "fn", "tn")}
    }
    result["fitted_on_all_pages"] = {
        f"{name}|F{beta:g}": fit(rows["train"] + rows["test"], name, beta=beta)
        for beta in (1.0, 2.0)
        for name in ("flagged_word_share", "low_line_share")
    }
    missed = [
        r
        for r in rows["test"]
        if r["bad"]
        and r["flagged_word_share"] < result["rules"]["flagged_word_share"]["threshold"]
    ]
    result["held_out_missed_by_flagged_word_share"] = sorted(
        [[r["book"], r["page"], r["degradation"], round(r["cer"], 4),
          round(r["flagged_word_share"], 4)] for r in missed])  # fmt: skip
    false = [
        r
        for r in rows["test"]
        if not r["bad"]
        and r["flagged_word_share"]
        >= result["rules"]["flagged_word_share"]["threshold"]
    ]
    result["held_out_false_flags_by_flagged_word_share"] = sorted(
        [[r["book"], r["page"], r["degradation"], round(r["cer"], 4),
          round(r["flagged_word_share"], 4)] for r in false])  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "page_flag.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8",
                                        newline="\n")  # fmt: skip
    for name, rule in result["rules"].items():
        print(name, rule.get("threshold"), "held out", rule["held_out"])
    for name, rule in result["cross_fit"].items():
        print(name, [f.get("threshold") for f in rule.get("folds", [])], rule["pooled"])
    print(result["fitted_on_all_pages"])


if __name__ == "__main__":
    main()
