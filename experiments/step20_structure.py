"""Step 20 structure-only check: decide the book structure again with the current code from a
run's cached structure evidence (no other stage runs) and compare it with the run's cached
structure: heading census (headings by role and level, display titles, labels), zones, and,
for books with derived gold, the Step 10 heading scores (as ``step20_eval.py`` computes them).

Usage: python step20_structure.py --book art_lab --tag before
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
OUT = ROOT / "experiments/out/step20"
GOLD = ROOT / "backend/tests/gold_derived"


def census(structure):
    zones = Counter(z.zone for z in structure.page_zones)
    return {
        "headings": len(structure.headings),
        "by_role_level": dict(sorted(Counter(f"{h.role} {h.level}" for h in structure.headings).items())),
        "styled": dict(Counter(s.role for s in structure.styled)),
        "zones": dict(zones),
    }  # fmt: skip


def scores(book, structure, evidence):
    if not (GOLD / book).exists():
        return None
    from book_core.evaluation.derived_harness import DerivedGold
    from book_core.evaluation.structure import heading_scores

    unit_tokens = {u["unit"]: [(p["page"], o) for o in u["token_ordinals"]]
                   for p in evidence["pages"] for u in p["units"]}  # fmt: skip
    zone_of = {z.page: z.zone for z in structure.page_zones}
    result = heading_scores(DerivedGold.load(GOLD / book), structure.headings, unit_tokens,
                            zone_of)  # fmt: skip
    keep = ("reference_headings", "our_headings", "precision", "recall", "f1")
    out = {k: result.get(k) for k in keep}
    nesting = (result.get("levels") or {}).get("nesting") or {}
    out["levels_exact"] = nesting.get("exact")
    out["levels_within_one"] = nesting.get("within_one")
    return out


def check(book, tag):
    from book_core.objects.analysis import verified_read
    from book_core.structure.cache import DEFAULT_CONFIG, STRUCTURE_VERSION
    from book_core.structure.decide import decide_book
    from book_core.structure.evidence import _read
    from book_core.structure.models import BookStructure

    record = json.loads((OUT / tag / "performance" / f"{book}.json").read_text("utf-8"))
    root, keys = Path(record["cache"]), record["run"]["cache_keys"]
    evidence = _read(root / "structure/evidence" / f"{keys['structure_evidence']}.json.gz",
                     keys["structure_evidence"])  # fmt: skip
    old = verified_read(root / "structure/book" / f"{keys['structure']}.json", BookStructure,
                        keys["structure"])  # fmt: skip
    config = {**DEFAULT_CONFIG, "heading_classifier": None}
    decided = decide_book(evidence, config)
    decided.pop("_candidates", None)
    new = BookStructure.model_construct(
        source_sha256=evidence["source_sha256"], structure_version=STRUCTURE_VERSION,
        pages=len(evidence["pages"]), config=config, **decided,
    )  # fmt: skip
    result = {
        "book": book,
        "tag": tag,
        "old": {**census(old), "scores": scores(book, old, evidence)},
        "new": {**census(new), "scores": scores(book, new, evidence)},
    }
    target = OUT / "dev" / "structure" / f"{book}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", "utf-8")
    for side in ("old", "new"):
        row = result[side]
        print(book, side, "headings", row["headings"], "styled", row["styled"],
              "zones", row["zones"], "scores", row["scores"])  # fmt: skip
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    check(args.book, args.tag)


if __name__ == "__main__":
    main()
