"""Read-only Step 17b sampling of frozen publications; writes new audit evidence only.

No extractor, stage cache, source PDF, reference, ledger or publication is modified.
"""

import gzip
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step13_books import BOOKS

OUT = ROOT / "experiments/out/step17b"
SEED = 17023
CELLS = {
    "statistics": ("bold", "underline", "subscript"),
    "immigrant_children": ("bold",),
    "medical_anatomy": ("bold", "italic", "underline"),
    "spanish_us_history": ("underline",),
}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")


def walk(node, context=(), pages=(), table_header=False):
    """Keep overlapping contexts (heading in an index is counted in both)."""
    pages = node.get("pages", pages)
    tags = set(context)
    kind = node.get("type")
    if kind == "heading":
        tags.add("heading")
    if kind == "caption":
        tags.add("caption")
    if node.get("list_type") == "index":
        tags.add("index")
    if table_header:
        tags.add("table_header")
    yield node, sorted(tags), pages
    for key in ("items", "children"):
        for child in node.get(key) or ():
            yield from walk(child, tags, pages)
    for cell in node.get("cells") or ():
        for child in cell["content"]:
            yield from walk(child, tags, pages, cell.get("role") in {"column_header", "row_header"})
    if kind == "figure":
        for key in ("captions", "credits", "text"):
            for child in node.get(key) or ():
                yield from walk(child, tags | ({"caption"} if key == "captions" else set()), pages)
    if kind == "table":
        for key in ("title", "notes"):
            value = node.get(key)
            for child in [value] if isinstance(value, dict) else value or []:
                yield from walk(child, tags | ({"caption"} if key == "title" else set()), pages)


def populations(book, document):
    with gzip.open(ROOT / f"experiments/out/step17/styling/{book}_spans.json.gz", "rt", encoding="utf-8") as f:
        frozen = json.load(f)
    lookup = defaultdict(list)
    for row in frozen:
        lookup[(row["page"], row["kind"], row["text"])].append(row["box"])
    found = defaultdict(list)
    all_nodes = [row for top in document["content"] for row in walk(top)]
    for node, context, pages in all_nodes:
        content = node.get("content")
        if not isinstance(content, dict) or not pages:
            continue
        for span in content["spans"]:
            kinds = ("bold", "italic") if span["kind"] == "bold_italic" else (span["kind"],)
            text = content["text"][span["start"]:span["end"]]
            boxes = lookup.get((pages[0], span["kind"], text), [])
            # If identical text repeats on the page, choose the frozen source box
            # nearest the current owner's geometry. Record ambiguity explicitly.
            owner = node.get("boxes", [])
            def distance(b, owner=owner):
                return min((abs(b[0]-r["x0"]) + abs(b[1]-r["y0"]) for r in owner), default=0)
            box = min(boxes, key=distance) if boxes else None
            row = {"book": book, "page": pages[0], "unit": node.get("id"),
                   "node_type": node.get("type"), "role": node.get("role"),
                   "context": context, "kind": span["kind"], "start": span["start"],
                   "end": span["end"], "text": text, "box": box,
                   "box_matches": len(boxes), "owner_boxes": owner,
                   "refs": node.get("refs"), "unit_text": content["text"]}
            for kind in kinds:
                found[kind].append(row)
    return found, all_nodes


def render_crop(document, row, dest, context=28):
    import pymupdf
    from PIL import Image, ImageDraw
    page = document[row["page"] - 1]
    box = pymupdf.Rect(row["box"])
    clip = pymupdf.Rect(box.x0 - 65, box.y0 - context, box.x1 + 65, box.y1 + context) & page.rect
    pix = page.get_pixmap(dpi=160, clip=clip, alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    ImageDraw.Draw(image).rectangle([(box.x0-clip.x0)*160/72, (box.y0-clip.y0)*160/72,
                                   (box.x1-clip.x0)*160/72, (box.y1-clip.y0)*160/72],
                                  outline="red", width=2)
    image.save(dest)
    return image


def sheets(rows, document, prefix, per_sheet=5):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 17)
    tiles = []
    for i, row in enumerate(rows, 1):
        row["sample_id"] = f"{prefix}-{i:02d}"
        path = OUT / "crops" / f"{row['sample_id']}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image = render_crop(document, row, path)
        image.thumbnail((1250, 340))
        tile = Image.new("RGB", (1280, image.height + 50), "white")
        d = ImageDraw.Draw(tile)
        d.text((5, 2), f"{row['sample_id']} p{row['page']} {','.join(row['context']) or 'other'}", fill="blue", font=font)
        d.text((5, 24), repr(row["text"])[:135], fill="blue", font=font)
        tile.paste(image, (0, 50))
        tiles.append(tile)
        row["crop"] = path.relative_to(ROOT).as_posix()
    for start in range(0, len(tiles), per_sheet):
        group = tiles[start:start+per_sheet]
        canvas = Image.new("RGB", (1280, sum(t.height for t in group)), "white")
        y = 0
        for t in group:
            canvas.paste(t, (0, y)); y += t.height
        path = OUT / "sheets" / f"{prefix}-{start//per_sheet+1}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(path)


def main():
    import pymupdf
    all_samples, census, index = [], {}, {}
    inputs = {}
    for book in BOOKS:
        record_path = ROOT / f"experiments/out/step17/final/performance/{book}.json"
        run = json.loads(record_path.read_text())["run"]
        path = Path(run["book_json"]) / "book.json"
        document = json.loads(path.read_text("utf-8"))
        inputs[book] = {"json": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "archive": run["output"], "pdf_key": BOOKS[book][0]}
        pools, nodes = populations(book, document)
        with pymupdf.open(reference_path(BOOKS[book][0])) as pdf:
            for kind in CELLS.get(book, ()):
                population = pools[kind]
                counts = Counter(tag for row in population for tag in row["context"])
                counts["other"] = sum(not row["context"] for row in population)
                key = f"{book}-{kind}"
                census[key] = {"detected_spans": len(population), "contexts_overlap": dict(counts),
                               "pages": len({r['page'] for r in population}),
                               "missing_source_boxes": sum(r['box'] is None for r in population)}
                picked = random.Random(f"{SEED}:{key}").sample(population, 20)
                assert all(row["box"] for row in picked), key
                sheets(picked, pdf, key)
                all_samples.extend(picked)
            pages = sorted({p for n, _, _ in nodes if n.get('list_type') == 'index' for p in n['pages']})
            selected = [pages[0], pages[len(pages)//2], pages[-1]] if len(pages) >= 3 else pages + [pages[-1]+1]
            dividers = [{"id": n["id"], "pages": ps, "text": n['content']['text']}
                        for n, _, ps in nodes if n.get('type') == 'index_divider']
            index[book] = {"index_pages": pages, "selected": selected, "all_json_dividers": dividers}
            for p in selected:
                dest = OUT / "index" / f"{book}-p{p}.png"
                dest.parent.mkdir(parents=True, exist_ok=True)
                pdf[p-1].get_pixmap(dpi=125, alpha=False).save(dest)
            if book == "statistics":
                flagged = [n for n, _, _ in nodes if n.get('type') == 'paragraph' and n.get('role') == 'figure_text']
                picked = random.Random(f"{SEED}:figure_text").sample(flagged, 30)
                rows = [{"book": book, "page": n['pages'][0], "unit": n['id'], "kind": "figure_text",
                         "text": n['content']['text'], "context": [], "flags": n['flags'],
                         "refs": n['refs'], "box": [n['boxes'][0][k] for k in ('x0','y0','x1','y1')]}
                        for n in picked]
                sheets(rows, pdf, 'statistics-figure_text', per_sheet=3)
                write(OUT / "figure_sample.json", {"population": len(flagged), "seed": SEED, "rows": rows})
        print(book, "done", flush=True)
    write(OUT / "inputs.json", inputs)
    write(OUT / "style_census.json", {"seed": SEED, "bold_italic_counts_in_both": True, "cells": census})
    write(OUT / "style_sample.json", all_samples)
    write(OUT / "index_sample.json", index)


if __name__ == "__main__":
    main()
