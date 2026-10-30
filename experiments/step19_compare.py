"""Step 19 output comparison of two runs of one book: which archive page fields differ, which
region identities changed (and whether each was ambiguous before: empty evidence or a
repeated identity on its page; otherwise whether its lines and objects changed), and whether
the publications differ beyond run metadata.

Cache keys and producer digests differ whenever code changes; they are not compared.

Usage: python step19_compare.py --book medical_anatomy --before before --after after1
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
OUT = ROOT / "experiments/out/step19"
IGNORED = {"cache_key_inputs", "page_keys", "keys"}


def strip(value):
    """The value without cache-key fields at any depth."""
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in IGNORED}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def record(tag, book):
    return json.loads((OUT / tag / "performance" / f"{book}.json").read_text("utf-8"))


def regions(record_, number):
    from book_core.cache_store import read_json

    key = record_["run"]["cache_keys"]["layout"]
    data = read_json(Path(record_["cache"]) / "layout" / key / f"{number}.json")
    data = json.loads(data["payload"]) if "payload" in data else data
    return data.get("regions", [])  # defaults are left out of the cache


def evidence(region):
    """The lines and objects a region holds (its identity evidence)."""
    return frozenset(region.get("line_ids", [])), frozenset(region.get("object_ids", []))


def main():
    from book_core.cache_store import read_json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    args = parser.parse_args()
    a, b = record(args.before, args.book), record(args.after, args.book)
    fields, pages = Counter(), {}
    region_changes = Counter()
    for number in range(1, a["run"]["pages"] + 1):
        name = f"page_{number:06d}.json.gz"
        left = strip(read_json(Path(a["run"]["output"]) / name))
        right = strip(read_json(Path(b["run"]["output"]) / name))
        changed = sorted(
            k for k in set(left) | set(right) if k not in IGNORED and left.get(k) != right.get(k)
        )
        if changed:
            pages[number] = changed
            fields.update(changed)
        old, new = regions(a, number), regions(b, number)
        old_ids, new_ids = Counter(r["id"] for r in old), {r["id"] for r in new}
        new_evidence = {evidence(r) for r in new}
        for region in old:
            if region["id"] in new_ids:
                continue
            empty = not region.get("line_ids") and not region.get("object_ids")
            repeated = old_ids[region["id"]] > 1
            moved = evidence(region) not in new_evidence
            kind = ("empty_evidence" if empty else "repeated" if repeated
                    else "evidence_changed" if moved else "same_evidence")  # fmt: skip
            region_changes[kind] += 1
    book_a = json.loads((Path(a["run"]["book_json"]) / "book.json").read_text("utf-8"))
    book_b = json.loads((Path(b["run"]["book_json"]) / "book.json").read_text("utf-8"))
    publication = sorted(
        k for k in set(book_a) | set(book_b) if k != "metadata" and book_a.get(k) != book_b.get(k)
    )
    result = {
        "book": args.book,
        "before": args.before,
        "after": args.after,
        "pages": a["run"]["pages"],
        "pages_changed": len(pages),
        "changed_fields": dict(fields.most_common()),
        "changed_pages": pages,
        "region_ids_changed": dict(region_changes),
        "publication_sections_changed": publication,
    }
    path = OUT / args.after / "compare" / f"{args.book}_vs_{args.before}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "changed_pages"}))


if __name__ == "__main__":
    main()
