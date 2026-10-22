"""Step 15 overlays: six seeded page breaks drawn from the Step 15 final archives.

Constrained (seed 1501, one per class, drawn from all books): a join through a break
hyphen, a join with floats skipped between the halves, a column link, an entry link, a
table chain with a repeated header row, and a refused candidate (no join). Each overlay
stacks the two pages (one page for a column link): first part red, second blue, skipped
items grey, table parts red/blue, the printed label of the page that begins in the title.

Usage: python step15_overlays.py [--out final]
"""

# ruff: noqa: E402
import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common  # noqa: F401
from step15_manual import boxes_of

from book_core.cache_store import read_json

OUT = ROOT / "experiments/out/step15/overlays"
SEED = 1501


def classes(book, root):
    archive = read_json(root / "book.json.gz")["continuity"]
    found = {}
    for chain in archive["chains"]:
        for brk in chain["breaks"]:
            row = {"book": book, "root": str(root), **brk, "chain_kind": chain["kind"]}
            if chain["kind"] == "table" and brk["repeated_header_rows"]:
                found.setdefault("table_repeated_header", []).append(row)
            elif brk["join"] and brk["join"]["hyphen"]:
                found.setdefault("hyphen", []).append(row)  # any source (Step 9 joins kept)
            elif brk["source"] != "continuity":
                continue
            elif brk["kind"] == "column":
                found.setdefault("column", []).append(row)
            elif chain["kind"] == "entry":
                found.setdefault("entry", []).append(row)
            elif brk["skipped_ids"]:
                found.setdefault("floats_skipped", []).append(row)
    for cand in archive["candidates"]:
        if cand["from_id"] and cand["to_id"] and cand["to_page"] == cand["from_page"] + 1:
            found.setdefault("refused", []).append(
                {"book": book, "root": str(root), "from_page": cand["from_page"],
                 "to_page": cand["to_page"], "from_id": cand["from_id"], "to_id": cand["to_id"],
                 "skipped_ids": [], "page_label": None, "reasons": cand["reasons"],
                 "chain_kind": cand["kind"]})  # fmt: skip
    return found


def draw(row, path):
    import cv2
    import numpy as np

    root = Path(row["root"])
    parts = []
    pages = (
        [row["from_page"]]
        if row["from_page"] == row["to_page"]
        else [row["from_page"], row["to_page"]]
    )
    for number in pages:
        payload = read_json(root / f"page_{number:06d}.json.gz")
        boxes = []
        for mid, colour, tag in ((row["from_id"], (220, 0, 0), "A"),
                                 (row["to_id"], (0, 0, 220), "B")):  # fmt: skip
            box = boxes_of(payload, mid)
            if box:
                boxes.append((box, colour, 3, tag))
        for sid in row.get("skipped_ids", []):
            box = boxes_of(payload, sid)
            if box:
                boxes.append((box, (150, 150, 150), 2, "skip"))
        target = OUT / "_part.png"
        common.render(row["book"], number, boxes, target, dpi=70)
        parts.append(cv2.imread(str(target)))
    width = max(p.shape[1] for p in parts)
    image = np.concatenate([np.pad(p, ((0, 0), (0, width - p.shape[1]), (0, 0)),
                                   constant_values=255) for p in parts], axis=1
                           if len(parts) > 1 else 0)  # fmt: skip
    cv2.imwrite(str(path), image)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="final")
    args = parser.parse_args()
    pool = {}
    for book in common.BOOK_ORDER:
        perf = ROOT / "experiments/out/step15" / args.out / "performance" / f"{book}.json"
        if perf.exists():
            for name, rows in classes(book, Path(common.read(perf)["run"]["output"])).items():
                pool.setdefault(name, []).extend(rows)
    rng = random.Random(SEED)
    index = []
    for k, name in enumerate(("hyphen", "floats_skipped", "column", "entry",
                              "table_repeated_header", "refused"), 1):  # fmt: skip
        if not pool.get(name):
            index.append({"class": name, "found": 0})
            continue
        row = rng.choice(pool[name])
        file = f"{k}_{name}_{row['book']}_p{row['from_page']}.png"
        draw(row, OUT / file)
        index.append({"class": name, "found": len(pool[name]), "file": file,
                      "book": row["book"], "pages": [row["from_page"], row["to_page"]],
                      "page_label": row.get("page_label"),
                      "reasons": row.get("reasons", [])[:2]})  # fmt: skip
    (OUT / "_part.png").unlink(missing_ok=True)
    common.write(OUT / "overlays.json", index)
    print(index, flush=True)


if __name__ == "__main__":
    main()
