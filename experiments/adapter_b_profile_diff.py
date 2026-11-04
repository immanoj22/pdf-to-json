"""Adapter B: fields that differ between two resolved profiles (defaults applied, parents
merged), e.g. the guideline-only jaypee_generated.yaml and the hand-written jaypee_v3.yaml.

Usage: python adapter_b_profile_diff.py A.yaml B.yaml [--out diff.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))

from book_adapters.engine.profile import load_profile  # noqa: E402

SKIP = {"profile", "version", "date", "description", "guideline", "confirm_with_client"}


def flat(value, prefix=""):
    if isinstance(value, dict) and value:
        for k, v in value.items():
            yield from flat(v, f"{prefix}.{k}" if prefix else k)
    else:
        yield prefix, value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a")
    parser.add_argument("b")
    parser.add_argument("--out")
    args = parser.parse_args()
    a, b = load_profile(args.a), load_profile(args.b)
    fa, fb = dict(flat(a.data)), dict(flat(b.data))
    rows = []
    for key in sorted(set(fa) | set(fb)):
        if key.split(".")[0] in SKIP:
            continue
        va, vb = fa.get(key, "(unset)"), fb.get(key, "(unset)")
        if isinstance(va, list) and isinstance(vb, list) and key == "rules":
            only_a, only_b = sorted(set(va) - set(vb)), sorted(set(vb) - set(va))
            if only_a or only_b:
                rows.append({"field": key, "only_a": only_a, "only_b": only_b})
            continue
        if va != vb:
            rows.append({"field": key, "a": va, "b": vb})
    result = {"a": args.a, "b": args.b, "differing_fields": len(rows), "fields": rows}
    text = json.dumps(result, indent=1, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", "utf-8")
    for r in rows:
        print(r["field"], "|", json.dumps({k: v for k, v in r.items() if k != "field"},
                                          ensure_ascii=False)[:200])  # fmt: skip
    print(len(rows), "differing fields")


if __name__ == "__main__":
    main()
