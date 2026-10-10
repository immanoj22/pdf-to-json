"""Step 10b Part B: rules-only heading analysis on the development books (1 and 2).

Reads the cached pass-1 structure evidence (the key recorded in each book's Step 10 summary),
decides with the current rules in memory (no cache write) and scores against derived gold:
precision/recall/F1, levels, roles, false-heading classes (book 1) and missed-heading classes
(book 2), with examples. Book 2 is a development book for headings from Step 10b on (owner
decision, docs/decisions.md); its Step 7-10 hold-out results stay recorded.

Usage: python step10b_headings.py [--label before|after] [--out experiments/out/step10b]
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))

BOOKS = ("spanish_us_history", "immigrant_children")
GOLD = ROOT / "backend/tests/gold_derived"
CACHE10 = ROOT / ".cache/step10"


def load_evidence(book):
    from book_core.structure.evidence import _read

    summary = json.loads((ROOT / f"experiments/out/step10/{book}/summary.json").read_text("utf-8"))
    key = summary["cache_key_inputs"]["evidence_key"]
    return _read(CACHE10 / "structure" / "evidence" / f"{key}.json.gz", key), key


def token_maps(gold):
    owner = {}
    for unit in gold.units:
        for page, first, length in unit["pdf"]:
            for ordinal in range(first, first + length):
                owner[(page, ordinal)] = unit["unit"]
    return owner, {u["unit"]: u for u in gold.units}


def false_heading_class(heading, unit, reference):
    """Coarse class of a false heading from its own decision evidence and reference kind."""
    kind = reference["kind"]
    path = reference["path"]
    if kind == "list_item":
        return "list item"
    if kind in {"image_description", "caption"}:
        return "figure/caption text"
    if kind == "table_cell":
        return "table cell"
    if heading.role in {"sidebar_title", "feature_title"}:
        return f"attached ({heading.role}) set as {kind}"
    if heading.evidence.get("numbering"):
        return f"numbered, set as {kind}"
    return f"{heading.role} set as {kind}" if "sidebar" not in path else f"box text set as {kind}"


def analyze(book, evidence, key):
    from book_core.evaluation.derived_harness import DerivedGold
    from book_core.evaluation.structure import heading_scores
    from book_core.structure.decide import DEFAULT_CONFIG, decide_book

    decided = decide_book(evidence, dict(DEFAULT_CONFIG))
    gold = DerivedGold.load(GOLD / book)
    units = {u["unit"]: u for p in evidence["pages"] for u in p["units"]}
    unit_tokens = {uid: [(u["page"], o) for o in u["token_ordinals"]] for uid, u in units.items()}
    zone_of = {z.page: z.zone for z in decided["page_zones"]}
    scores = heading_scores(gold, decided["headings"], unit_tokens, zone_of)
    owner, gold_units = token_maps(gold)
    reference_heading = {t for u in gold.units if u["kind"] == "heading"
                         for p, f, n in u["pdf"]
                         for t in ((p, o) for o in range(f, f + n))}  # fmt: skip
    false_classes, examples = Counter(), defaultdict(list)
    for heading in decided["headings"]:
        tokens = [t for uid in heading.unit_ids for t in unit_tokens.get(uid, ()) if t in owner]
        if heading.run_in:
            tokens = sorted(tokens)[: max(1, heading.evidence.get("run_in_tokens", 1))]
        if not tokens or sum(t in reference_heading for t in tokens) * 2 >= len(tokens):
            continue
        reference = gold_units[Counter(owner[t] for t in tokens).most_common(1)[0][0]]
        cls = false_heading_class(heading, units[heading.unit_ids[0]], reference)
        false_classes[cls] += 1
        if len(examples[cls]) < 3:
            text = " | ".join(units[u]["text"][:60] for u in heading.unit_ids)
            examples[cls].append({"page": heading.page, "text": text, "role": heading.role,
                                  "group": heading.style_group, "reasons": heading.reasons[:4],
                                  "reference_path": reference["path"]})  # fmt: skip
    # Misses: what the decision did with each missed reference heading's tokens.
    candidates = {u: item for item in decided["_candidates"] for u in item["units"]}
    styled_of = {u: s for s in decided["styled"] for u in s.unit_ids}
    scored = {r.unit_id: r for r in decided["rejected"]}
    token_unit = {(u["page"], o): uid for uid, u in units.items() for o in u["token_ordinals"]}
    miss_classes, miss_examples = Counter(), defaultdict(list)
    for miss in scores["misses"]:
        reference = gold_units[miss["unit"]]
        mine = Counter(token_unit.get((p, o)) for p, f, n in reference["pdf"]
                       for o in range(f, f + n))  # fmt: skip
        uid = mine.most_common(1)[0][0] if mine else None
        unit = units.get(uid)
        if unit is None:
            cls = "tokens in no text unit (figure/table/furniture)"
        elif uid in styled_of:
            cls = f"decided {styled_of[uid].role}: {styled_of[uid].reasons[0]}"
        elif uid in candidates:
            cls = "candidate merged elsewhere"
        elif uid in scored:
            cls = "scored below the threshold"
        elif unit["lines"] > 3 or unit["tokens"] > 20:
            cls = f"unit too long ({unit['kind']}, {unit['lines']} lines): merged with text"
        else:
            cls = "scored far below the threshold"
        miss_classes[cls] += 1
        if len(miss_examples[cls]) < 3:
            row = {"page": miss["page"], "level": miss["level"],
                   "reference_text_unit": reference["path"]}  # fmt: skip
            if unit is not None:
                row.update({"text": unit["text"][:90], "kind": unit["kind"],
                            "stream": unit["stream"], "lines": unit["lines"],
                            "size": unit["size"], "bold": unit["bold"],
                            "caps": unit["caps"]})  # fmt: skip
            if uid in scored:
                row["score"], row["reasons"] = scored[uid].score, scored[uid].reasons[:6]
            miss_examples[cls].append(row)
    return {
        "book": book,
        "evidence_key": key,
        "headings": {k: v for k, v in scores.items() if k != "misses"},
        "levels_count": dict(sorted(Counter(h.level for h in decided["headings"]).items())),
        "roles_count": dict(Counter(h.role for h in decided["headings"])),
        "styled": dict(Counter(s.role for s in decided["styled"])),
        "contents_outline": decided["profile"]["styled"],
        "false_heading_classes": dict(false_classes.most_common()),
        "false_heading_examples": examples,
        "missed_heading_classes": dict(miss_classes.most_common()),
        "missed_heading_examples": miss_examples,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="current")
    parser.add_argument("--out", type=Path, default=ROOT / "experiments/out/step10b")
    parser.add_argument("--book", choices=BOOKS, action="append")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for book in args.book or BOOKS:
        evidence, key = load_evidence(book)
        result = analyze(book, evidence, key)
        (args.out / f"headings_{args.label}_{book}.json").write_text(
            json.dumps(result, indent=1, ensure_ascii=False, default=str) + "\n", "utf-8"
        )
        h = result["headings"]
        print(book, {k: h[k] for k in ("reference_headings", "our_headings", "precision",
                                       "recall", "f1")}, h["levels"].get("all"))  # fmt: skip
        print("  false:", result["false_heading_classes"])
        print("  missed:", result["missed_heading_classes"])


if __name__ == "__main__":
    main()
