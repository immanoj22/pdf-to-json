"""Step 15 manual check: the joins to verify by hand, listed and rendered.

From the Step 15 final archives, every break of every chain (kept Step 9 joins, lists-stage
entry links, new continuity joins, table continuations) gets a stable id
(``<book>:<kind>:<from page>:<n>``) and the evidence a reader needs: the last two lines of
the first part, the first two lines of the second, the items skipped between them, the
reasons (``joins/<book>.txt``, UTF-8). The check set (owner instruction):

- every join of book 4 (all kinds);
- every table continuation of Statistics, and the six continuation marks of Step 14b that
  were wrong (four now withdrawn, with their review flags; two kept);
- book 1 p260 (a wrong join of development, refused now): its candidate record;
- at least 25 seeded random joins (seed 1500) each in books 1 and 2, over all their joins;
- every new join (``source`` continuity) of every book.

Book 4 joins are rendered (``check/``: first part red, second blue, both pages side by
side, JPEG) and table continuations on contact sheets of four (``sheets/``); other joins are
judged from their text, a render made when the text leaves doubt. Verdicts are recorded by
hand in ``verdicts.json`` ({id: [verdict, method, note]}), and ``step15_precision.py`` turns
them into precision per book and kind.

Usage: python step15_manual.py [--out final] [--render]
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

from book_core.cache_store import read_json

OUT = ROOT / "experiments/out/step15"
SEED = 1500
RANDOM = 25
STEP14B_WRONG = [(82, 83), (253, 254), (288, 289), (603, 604), (658, 659), (835, 836)]


class Pages:
    def __init__(self, root):
        self.root, self.cache = root, {}

    def __call__(self, number):
        if number not in self.cache:
            if len(self.cache) > 4:
                self.cache = {}
            self.cache[number] = read_json(self.root / f"page_{number:06d}.json.gz")
        return self.cache[number]


def text(payload, lid):
    spans = payload["source"]["store"]["spans"]
    return "".join(spans[s]["raw_text"] for s in payload["line_spans"].get(lid, [])).strip()


def member(payload, mid):
    view = payload["table_view"]
    removed = set(view["removed"])
    for unit in [*[u for u in payload["units"]["units"] if u["id"] not in removed],
                 *view["added"]]:  # fmt: skip
        if unit["id"] == mid:
            return unit
    for table in payload["tables"]["tables"]:
        if table["id"] == mid:
            return {"id": mid, "kind": "table", "line_ids": table["line_ids"],
                    "bbox": table["bbox"], "title": table["title"]}  # fmt: skip
    return None


def kind_of(chain, brk):
    if chain["kind"] == "table":
        return "table"
    if brk["kind"] == "column":
        return "column"
    return "list" if chain["kind"] == "list_item" else chain["kind"]


def joins(book, root):
    archive = read_json(root / "book.json.gz")
    pages = Pages(root)
    out, seen = [], {}
    for chain in archive["continuity"]["chains"]:
        for brk in chain["breaks"]:
            kind = kind_of(chain, brk)
            key = (kind, brk["from_page"])
            seen[key] = seen.get(key, 0) + 1
            a_page, b_page = pages(brk["from_page"]), pages(brk["to_page"])
            a, b = member(a_page, brk["from_id"]), member(b_page, brk["to_id"])
            unit = kind != "table"
            out.append({
                "id": f"{book}:{kind}:{brk['from_page']}:{seen[key]}", "book": book,
                "kind": kind, "source": brk["source"], "from_page": brk["from_page"],
                "to_page": brk["to_page"], "from_id": brk["from_id"], "to_id": brk["to_id"],
                "tail": [text(a_page, lid) for lid in a["line_ids"][-2:]] if unit else [],
                "head": [text(b_page, lid) for lid in b["line_ids"][:2]] if unit else [],
                "titles": [] if unit else [
                    text(a_page, a["title"]["line_ids"][0]) if a["title"] else None,
                    text(b_page, b["title"]["line_ids"][0]) if b["title"] else None],
                "skipped": len(brk["skipped_ids"]), "pages_skipped": brk["skipped_pages"],
                "repeated_header_rows": brk["repeated_header_rows"],
                "marks": [m["position"] for m in brk["marks"]], "reasons": brk["reasons"],
            })  # fmt: skip
    return out


def withdrawn(root):
    """Table continuations the title checks withdrew (review flag on both tables)."""
    archive = read_json(root / "book.json.gz")
    pages = Pages(root)
    out = []
    for number in sorted(int(n) for n in archive["tables"]["by_page"]):
        for table in pages(number)["tables"]["tables"]:
            flags = [f for f in table["review_flags"]
                     if f.startswith("continuation across the page withdrawn")]  # fmt: skip
            if flags:
                out.append({"page": number, "table": table["id"][:12], "flag": flags[0],
                            "status": table.get("review_status"),
                            "continues_to": table["continues_to"],
                            "continues_from": table["continues_from"]})  # fmt: skip
    return out


def boxes_of(payload, mid):
    unit = member(payload, mid)
    if unit is None:
        return None
    if "bbox" in unit:
        b = unit["bbox"]
        return [b["x0"], b["y0"], b["x1"], b["y1"]]
    spans = payload["source"]["store"]["spans"]
    found = [spans[s]["bbox"] for lid in unit["line_ids"]
             for s in payload["line_spans"].get(lid, [])]  # fmt: skip
    return [min(b["x0"] for b in found), min(b["y0"] for b in found),
            max(b["x1"] for b in found), max(b["y1"] for b in found)]  # fmt: skip


def render(row, root, path):
    import cv2
    import numpy as np

    images = []
    for page, mid, colour in ((row["from_page"], row["from_id"], (220, 0, 0)),
                              (row["to_page"], row["to_id"], (0, 0, 220))):  # fmt: skip
        payload = read_json(root / f"page_{page:06d}.json.gz")
        box = boxes_of(payload, mid)
        target = OUT / "manual" / "_part.png"
        common.render(row["book"], page, [(box, colour, 3, "A" if colour[0] else "B")], target,
                      dpi=60)  # fmt: skip
        images.append(cv2.imread(str(target)))
        if row["from_page"] == row["to_page"]:
            break
    height = max(i.shape[0] for i in images)
    padded = [np.pad(i, ((0, height - i.shape[0]), (0, 0), (0, 0)), constant_values=255)
              for i in images]  # fmt: skip
    cv2.imwrite(str(path), np.concatenate(padded, axis=1), [cv2.IMWRITE_JPEG_QUALITY, 80])


def contact_sheets(images, target):
    """Four renders per sheet (2 x 2, scaled 0.7, named), JPEG."""
    import cv2
    import numpy as np

    target.mkdir(parents=True, exist_ok=True)
    for k in range(0, len(images), 4):
        parts = []
        for name, image in images[k : k + 4]:
            image = cv2.resize(image, (int(image.shape[1] * 0.7), int(image.shape[0] * 0.7)))
            cv2.putText(image, name, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 128, 0), 1)
            parts.append(image)
        h = max(i.shape[0] for i in parts)
        w = max(i.shape[1] for i in parts)
        parts = [np.pad(i, ((0, h - i.shape[0]), (0, w - i.shape[1]), (0, 0)),
                        constant_values=255) for i in parts]  # fmt: skip
        while len(parts) < 4:
            parts.append(np.full((h, w, 3), 255, np.uint8))
        sheet = np.concatenate([np.concatenate(parts[:2], 1), np.concatenate(parts[2:], 1)], 0)
        cv2.imwrite(str(target / f"sheet_{k // 4:02d}.jpg"), sheet,
                    [cv2.IMWRITE_JPEG_QUALITY, 80])  # fmt: skip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="final")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    rows, roots, check = [], {}, {}
    for book in common.BOOK_ORDER:
        perf = OUT / args.out / "performance" / f"{book}.json"
        roots[book] = Path(common.read(perf)["run"]["output"])
        found = joins(book, roots[book])
        rows += found
        lines = []
        for r in found:
            lines.append(f"[{r['id']}] {r['source']} p{r['from_page']}->p{r['to_page']} "
                         f"skipped {r['skipped']} pages {r['pages_skipped']} "
                         f"rep {r['repeated_header_rows']} marks {r['marks']}")  # fmt: skip
            lines += [f"    A| {t}" for t in r["tail"]] + [f"    B| {t}" for t in r["head"]]
            lines += [f"    T| {t}" for t in r["titles"]]
            lines.append(f"    why: {'; '.join(r['reasons'][:2])}")
        target = OUT / "manual" / "joins" / f"{book}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines) + "\n", "utf-8", newline="\n")
    by_id = {r["id"]: r for r in rows}
    rng = random.Random(SEED)
    for r in rows:
        if r["book"] == "medical_anatomy":
            check.setdefault(r["id"], []).append("book 4: every join")
        if r["book"] == common.MATH_BOOK and r["kind"] == "table":
            check.setdefault(r["id"], []).append("Statistics: every table continuation")
        if r["source"] == "continuity":
            check.setdefault(r["id"], []).append("every new join")
        if r["book"] == common.MATH_BOOK and r["kind"] == "table" and (
                r["from_page"], r["to_page"]) in STEP14B_WRONG:  # fmt: skip
            check[r["id"]].append("Step 14b wrong mark, kept")
    for book in ("spanish_us_history", "immigrant_children"):
        pool = sorted(r["id"] for r in rows if r["book"] == book)
        for rid in rng.sample(pool, min(RANDOM, len(pool))):
            check.setdefault(rid, []).append(f"random {RANDOM} (seed {SEED})")
    stats_withdrawn = withdrawn(roots[common.MATH_BOOK])
    archive1 = read_json(roots["spanish_us_history"] / "book.json.gz")["continuity"]
    p260 = [c for c in archive1["candidates"] if c["from_page"] == 260 and c["to_page"] == 261]
    p260_joined = [r["id"] for r in rows if r["book"] == "spanish_us_history"
                   and r["from_page"] == 260 and r["kind"] != "column"]  # fmt: skip
    common.write(OUT / "manual" / "check_set.json", {
        "seed": SEED, "joins": {rid: {**by_id[rid], "why_checked": why}
                                for rid, why in sorted(check.items())},
        "statistics_withdrawn": stats_withdrawn,
        "statistics_step14b_wrong": STEP14B_WRONG,
        "book1_p260": {"joins_from_p260": p260_joined, "candidates": p260},
    })  # fmt: skip
    print("joins", len(rows), "to check", len(check), "withdrawn", len(stats_withdrawn),
          "p260 joins", p260_joined, flush=True)  # fmt: skip
    if args.render:
        import cv2

        (OUT / "manual" / "check").mkdir(parents=True, exist_ok=True)
        tables = []
        for rid in sorted(check):
            r = by_id[rid]
            name = rid.replace(":", "_") + ".jpg"
            if r["kind"] == "table":
                path = OUT / "manual" / "_table.jpg"
                render(r, roots[r["book"]], path)
                tables.append((rid.replace(":", "_"), cv2.imread(str(path))))
            elif r["book"] == "medical_anatomy":
                render(r, roots[r["book"]], OUT / "manual" / "check" / name)
        contact_sheets(tables, OUT / "manual" / "sheets")
        for name in ("_part.png", "_table.jpg"):
            (OUT / "manual" / name).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
