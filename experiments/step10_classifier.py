"""Step 10: HeadingClassifier slot, trained on book 1 derived gold only, page-block CV.

Candidates are the rule candidates of the structure stage (every visually distinct title,
with its rule verdict and gold-free features; ``structure.classifier``). A candidate's label
is "heading" when at least half of its aligned tokens lie in reference heading units.

Cross-validation: pages are grouped into blocks of BLOCK consecutive pages and split with
GroupKFold, so no page (and no neighbouring page) is in both training and test. Out-of-fold
likelihoods are injected into the full decision (levels, roles, zones unchanged in method),
and the harness scores rules-only vs rules+classifier on the same book. The threshold is
chosen on the out-of-fold predictions: the highest F1 with recall at least MIN_RECALL.
The final model is then trained on all book 1 candidates and saved with a manifest.
Books 2 and 3 are never used here.

Usage: python step10_classifier.py
"""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from step10_run import GOLD, OUT, evidence_for  # noqa: E402

BOOK = "spanish_us_history"
BLOCK = 20
FOLDS = 5
MIN_RECALL = 0.85
MODEL = ROOT / "backend/heading_models/heading_classifier_book1.txt"


class FixedLikelihoods:
    """A classifier stand-in that returns precomputed out-of-fold likelihoods."""

    def __init__(self, by_id, order, threshold):
        self.by_id, self.order, self.threshold = by_id, order, threshold

    def likelihoods(self, rows):
        return [self.by_id[item_id] for item_id in self.order]

    def identity(self):
        return {"name": "out-of-fold", "threshold": self.threshold}


def main():
    import numpy as np
    from sklearn.model_selection import GroupKFold

    from book_core.evaluation.derived_harness import DerivedGold
    from book_core.evaluation.structure import heading_scores
    from book_core.structure.classifier import FEATURES, train
    from book_core.structure.decide import DEFAULT_CONFIG, decide_book

    evidence, _, _ = evidence_for(BOOK)
    gold = DerivedGold.load(GOLD / BOOK)
    reference = set()
    aligned = set()
    for unit in gold.units:
        for page, first, length in unit["pdf"]:
            for ordinal in range(first, first + length):
                aligned.add((page, ordinal))
                if unit["kind"] == "heading":
                    reference.add((page, ordinal))
    unit_tokens = {u["unit"]: [(p["page"], o) for o in u["token_ordinals"]]
                   for p in evidence["pages"] for u in p["units"]}  # fmt: skip
    rules = decide_book(evidence, DEFAULT_CONFIG)
    candidates = rules.pop("_candidates")
    rows, labels, groups, ids = [], [], [], []
    for item in candidates:
        tokens = [t for u in item["units"] for t in unit_tokens[u] if t in aligned]
        if item["run_in"] is not None:
            continue
        label = int(bool(tokens) and sum(t in reference for t in tokens) * 2 >= len(tokens))
        rows.append(item["features"])
        labels.append(label)
        groups.append(item["page"] // BLOCK)
        ids.append(item["id"])
    labels = np.array(labels)
    oof = np.zeros(len(rows))
    for train_index, test_index in GroupKFold(n_splits=FOLDS).split(rows, labels, groups):
        booster = train([rows[i] for i in train_index], labels[train_index])
        matrix = np.array([[float(rows[i][n]) for n in FEATURES] for i in test_index])
        oof[test_index] = booster.predict(matrix)
    rule_pred = np.array([row["rule_heading"] for row in rows])

    def prf(pred):
        tp = int(((pred == 1) & (labels == 1)).sum())
        p = tp / max(int(pred.sum()), 1)
        r = tp / max(int(labels.sum()), 1)
        return {"precision": round(p, 4), "recall": round(r, 4),
                "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}  # fmt: skip

    curve = {f"{t:.2f}": prf((oof >= t).astype(int)) for t in np.arange(0.1, 0.95, 0.05)}
    eligible = [(v["f1"], float(t)) for t, v in curve.items() if v["recall"] >= MIN_RECALL]
    threshold = max(eligible)[1] if eligible else 0.5
    by_id = dict(zip(ids, oof.tolist(), strict=True))
    for item in candidates:
        by_id.setdefault(item["id"], 1.0)  # run-in headings stay with the rules
    order = [item["id"] for item in candidates]
    learned = decide_book(evidence, DEFAULT_CONFIG, FixedLikelihoods(by_id, order, threshold))
    learned.pop("_candidates")

    def harness(decided):
        zone_of = {z.page: z.zone for z in decided["page_zones"]}
        scores = heading_scores(gold, decided["headings"], unit_tokens, zone_of)
        return {k: v for k, v in scores.items() if k not in {"misses", "role_confusion"}}

    final = train(rows, labels)
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    text = final.model_to_string()
    MODEL.write_bytes(text.encode("utf-8"))  # LF bytes on every platform
    importance = dict(zip(FEATURES, final.feature_importance("gain").round(1).tolist(),
                          strict=True))  # fmt: skip
    report = {
        "book": BOOK,
        "training_data": "book 1 derived gold only (human_approved: false)",
        "gold_manifest_sha256": hashlib.sha256(
            (GOLD / BOOK / "manifest.json").read_bytes()).hexdigest(),
        "candidates": len(rows),
        "positives": int(labels.sum()),
        "cross_validation": {"scheme": f"GroupKFold({FOLDS}) over {BLOCK}-page blocks"},
        "candidate_level": {"rules_only": prf(rule_pred),
                            "rules_plus_classifier": prf((oof >= threshold).astype(int))},
        "threshold": threshold,
        "threshold_rule": f"highest out-of-fold F1 with recall >= {MIN_RECALL}",
        "curve": curve,
        "harness_rules_only": harness(rules),
        "harness_rules_plus_classifier_out_of_fold": harness(learned),
        "model": {"path": str(MODEL.relative_to(ROOT)),
                  "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                  "features": list(FEATURES), "importance_gain": importance},
        "labels_by_rule_verdict": {str(k): v for k, v in Counter(
            (row["rule_heading"], lab) for row, lab in zip(rows, labels, strict=True)).items()},
    }  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "classifier_cv.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    (MODEL.parent / "heading_classifier_book1.json").write_text(json.dumps({
        k: report[k] for k in ("book", "training_data", "gold_manifest_sha256", "candidates",
                               "positives", "cross_validation", "candidate_level",
                               "threshold", "threshold_rule", "model")
    }, indent=1, ensure_ascii=False) + "\n", "utf-8")  # fmt: skip
    print(json.dumps({k: report[k] for k in ("candidate_level", "threshold")}, indent=1))
    for name in ("harness_rules_only", "harness_rules_plus_classifier_out_of_fold"):
        h = report[name]
        print(name, {k: h[k] for k in ("our_headings", "precision", "recall", "f1",
                                       "precision_without_convention_classes")},
              h["levels"]["all"])  # fmt: skip


if __name__ == "__main__":
    main()
