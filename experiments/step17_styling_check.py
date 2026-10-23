"""Step 17 Part 2: hand check of 40 seeded inline spans (contact sheets for review).

Spans written by ``step17_styling_eval.py`` (all books) are drawn with a fixed seed
(``1702``), spread over the span kinds found (as evenly as the counts allow). Each is rendered
from its PDF page (the span's box outlined in red, one line of context around it) and labelled
with its number, book, page, kind and text. Verdicts are entered by hand in
``styling/hand_check.json`` (``correct`` / ``wrong`` / ``unclear`` with a note) and summarised.

Usage: python step17_styling_check.py sheets | summary
"""

import gzip
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step13_books import BOOKS

OUT = ROOT / "experiments/out/step17/styling"
ORDER = ("spanish_us_history", "immigrant_children", "art_therapy_index", "medical_anatomy",
         "statistics")  # fmt: skip


def sample(n=40, seed=1702):
    by_kind = defaultdict(list)
    for book in ORDER:
        path = OUT / f"{book}_spans.json.gz"
        if not path.exists():
            continue
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for span in json.load(stream):
                by_kind[span["kind"]].append({**span, "book": book})
    rng = random.Random(seed)
    kinds = sorted(by_kind)
    picked, k = [], 0
    pools = {kind: rng.sample(by_kind[kind], len(by_kind[kind])) for kind in kinds}
    while len(picked) < n and any(pools.values()):
        kind = kinds[k % len(kinds)]
        if pools[kind]:
            picked.append(pools[kind].pop())
        k += 1
    return picked


def sheets():
    import pymupdf
    from PIL import Image, ImageDraw

    picked = sample()
    tiles = []
    for number, span in enumerate(picked, start=1):
        with pymupdf.open(reference_path(BOOKS[span["book"]][0])) as document:
            page = document[span["page"] - 1]
            x0, y0, x1, y1 = span["box"]
            clip = pymupdf.Rect(x0 - 60, y0 - 14, x1 + 60, y1 + 14) & page.rect
            pixmap = page.get_pixmap(dpi=144, clip=clip)
            image = Image.frombytes(
                "RGB", (pixmap.width, pixmap.height), pixmap.samples
            )
            scale = 144 / 72
            draw = ImageDraw.Draw(image)
            draw.rectangle([(x0 - clip.x0) * scale - 2, (y0 - clip.y0) * scale - 2,
                            (x1 - clip.x0) * scale + 2, (y1 - clip.y0) * scale + 2],
                           outline=(220, 0, 0), width=2)  # fmt: skip
        label = f"#{number} {span['book'][:10]} p{span['page']} {span['kind']}: {span['text'][:60]!r}"
        if span.get("href"):
            label += f" -> {span['href'][:40]}"
        if span.get("language"):
            label += f" [{span['language']}]"
        tiles.append((label, image))
    width = 1100
    for sheet in range(0, len(tiles), 8):
        group = tiles[sheet : sheet + 8]
        rows = []
        for label, image in group:
            image.thumbnail((width, 220))
            canvas = Image.new("RGB", (width, image.height + 22), "white")
            ImageDraw.Draw(canvas).text((4, 2), label, fill=(0, 0, 160))
            canvas.paste(image, (0, 22))
            rows.append(canvas)
        out = Image.new("RGB", (width, sum(r.height for r in rows)), "white")
        y = 0
        for row in rows:
            out.paste(row, (0, y))
            y += row.height
        out.save(OUT / f"hand_check_sheet_{sheet // 8 + 1}.png")
    (OUT / "hand_check_sample.json").write_text(json.dumps(
        [{"n": i + 1, **{k: s[k] for k in ("book", "page", "kind", "text", "box", "href",
                                           "language")}} for i, s in enumerate(picked)],
        indent=1, ensure_ascii=False) + "\n", "utf-8", newline="\n")  # fmt: skip
    print(len(picked), "spans", Counter(s["kind"] for s in picked))


def summary():
    sample_rows = json.loads((OUT / "hand_check_sample.json").read_text("utf-8"))
    verdicts = json.loads((OUT / "hand_check.json").read_text("utf-8"))
    by_kind = defaultdict(Counter)
    for row in sample_rows:
        verdict = verdicts[str(row["n"])][0]
        by_kind[row["kind"]][verdict] += 1
    total = Counter()
    for counts in by_kind.values():
        total.update(counts)
    result = {
        "by_kind": {k: dict(v) for k, v in sorted(by_kind.items())},
        "total": dict(total),
    }
    (OUT / "hand_check_summary.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8",
                                                 newline="\n")  # fmt: skip
    print(json.dumps(result))


if __name__ == "__main__":
    {"sheets": sheets, "summary": summary}[sys.argv[1]]()
