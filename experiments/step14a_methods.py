"""Step 14a Task 4: method comparison for table detection and structure.

Detection, each source alone vs combined (``tables.page.analyze``): Heron, PP-DocLayoutV3
and Table Transformer table boxes, ruled grids, rule stacks and Step 4 table regions; a
source's region holds the tokens whose box centre lies inside it (one cell), scored for
detection only.

Structure, on the same regions (our detected tables that match a reference segment):
our geometry (``tables.grid``), Table Transformer structure, TableFormer (accurate),
pdfplumber (``find_tables``) and Camelot (lattice; stream where lattice finds nothing; the
pdfium image backend only, never Ghostscript). Each method's cells are mapped to tokens by
token-box centre; scored with structure-only TEDS, cell adjacency F1 and header accuracy.
Crops of rotated tables are turned upright for the image models; pdfplumber and Camelot
read page coordinates (rotated tables are reported as their result). Model readings are
cached per image (``tables.recognizers.ReadingCache``).

Usage: python step14a_methods.py --book NAME [--label final] [--skip camelot,...]
"""

# ruff: noqa: E402
import argparse
import sys
import time
import warnings
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14a_dev as dev

from book_core.evaluation import math_gold, table_scoring
from book_core.model.common import BBox
from book_core.tables import detect
from book_core.tables.page import analyze

MODELS = ROOT / ".cache/huggingface"
READINGS = ROOT / ".cache/models"
CROP_DPI = 150
PAD = 6.0  # points around a region for the image models


def centre_in(box, b):
    cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
    return box.x0 <= cx <= box.x1 and box.y0 <= cy <= box.y1


def token_boxes(book, number):
    boxes, _, _, _ = math_gold.token_geometry(common.text_page(book, number))
    return boxes


def region_grid(number, box, boxes):
    tokens = frozenset((number, i) for i, b in enumerate(boxes) if centre_in(box, b))
    return {"cells": [(0, 0, 1, 1, False, tokens)], "header_rows": 0}


def detection(book, bundle):
    """{source: score} for each evidence source alone and combined."""
    sources = defaultdict(dict)
    for number, page in sorted(bundle["pages"].items()):
        ev = page["evidence"]
        boxes = None
        regions = defaultdict(list)
        for model, found in ev.models.items():
            regions[model] += [b for b, score, _ in found if score >= detect.MODEL_SCORE]
        for net in detect.networks(detect.content_rules(ev), ev.font):
            if net.kind in {"grid", "stack"}:
                regions[f"rules_{net.kind}"].append(net.bbox)
        regions["layout_step4"] += [t["bbox"] for t in ev.layout_tables]
        tables, _ = analyze(ev)
        for index, draft in enumerate(tables):
            sources["combined"][(number, index)] = dev.our_grid(number, draft, page["tokens"])
        if regions:
            boxes = token_boxes(book, number)
        for source, found in regions.items():
            for index, box in enumerate(found):
                sources[source][(number, index)] = region_grid(number, box, boxes)
    gold = table_scoring.gold_segments(common.gold_tables(book))
    out = {}
    for source in ["combined", "heron", "pp", "tatr", "rules_grid", "rules_stack", "layout_step4"]:
        result = table_scoring.score(gold, sources.get(source, {}))
        out[source] = {k: result[k] for k in ("our_tables", "matched", "detection_precision",
                                               "detection_recall", "detection_f1")}  # fmt: skip
    return out


# --- structure methods ----------------------------------------------------------------------


def crop(book, number, box, rotation):
    """(PNG, pixel -> page point function) of an upright crop of a region."""
    import pymupdf

    with pymupdf.open(common.source(book)) as document:
        page = document[number - 1]
        clip = pymupdf.Rect(box.x0 - PAD, box.y0 - PAD, box.x1 + PAD, box.y1 + PAD) & page.rect
        zoom = CROP_DPI / 72
        best = None
        for degrees in (0, 90, 180, 270):
            matrix = pymupdf.Matrix(zoom, zoom).prerotate(degrees)
            # The text direction of the frame must point along +x in the image.
            import math

            theta = math.radians(rotation)
            d = pymupdf.Point(math.cos(theta), -math.sin(theta)) * pymupdf.Matrix(1, 1).prerotate(
                degrees
            )
            if best is None or d.x > best[0]:
                best = (d.x, matrix)
        matrix = best[1]
        pixmap = page.get_pixmap(matrix=matrix, clip=clip)
        rect = clip * matrix
        inverse = ~matrix

    def to_page(x, y):
        p = pymupdf.Point(x + rect.x0, y + rect.y0) * inverse
        return p.x, p.y

    return pixmap.tobytes("png"), to_page


def _box_from_pixels(to_page, b):
    corners = [to_page(b[0], b[1]), to_page(b[2], b[3]), to_page(b[0], b[3]), to_page(b[2], b[1])]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    return BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))


def grid_from_cells(number, cells, boxes, header_rows=0):
    """Scoring grid from [(row, col, row_span, col_span, header, page bbox)]."""
    out = []
    taken = set()
    for row, col, rs, cs, header, box in cells:
        tokens = frozenset(
            (number, i) for i, b in enumerate(boxes) if i not in taken and centre_in(box, b)
        )
        taken |= {i for _, i in tokens}
        out.append((row, col, rs, cs, header, tokens))
    return {"cells": out, "header_rows": header_rows}


def tatr_cells(reading, to_page):
    objects = reading["objects"]
    rows = sorted((o for o in objects if o["label"] == "table row"), key=lambda o: o["box"][1])
    cols = sorted((o for o in objects if o["label"] == "table column"), key=lambda o: o["box"][0])
    if not rows or not cols:
        return [], 0
    spans = [o for o in objects if o["label"] == "table spanning cell"]
    headers = [o for o in objects if o["label"] == "table column header"]
    grid = {}
    for r, row in enumerate(rows):
        for c, col in enumerate(cols):
            b = [col["box"][0], row["box"][1], col["box"][2], row["box"][3]]
            grid[(r, c)] = b

    def overlap(a, b):
        w = min(a[2], b[2]) - max(a[0], b[0])
        h = min(a[3], b[3]) - max(a[1], b[1])
        area = (a[2] - a[0]) * (a[3] - a[1])
        return w * h / area if w > 0 and h > 0 and area > 0 else 0

    owner = {}
    for k, sp in enumerate(spans):
        members = [key for key, b in grid.items() if overlap(b, sp["box"]) >= 0.5]
        if len(members) > 1:
            for key in members:
                owner.setdefault(key, k)
    header_rows = sum(
        1 for row in rows if any(overlap(row["box"], h["box"]) >= 0.5 for h in headers)
    )
    cells, done = [], set()
    for r, c in sorted(grid):
        if (r, c) in done:
            continue
        k = owner.get((r, c))
        members = [key for key, v in owner.items() if v == k] if k is not None else [(r, c)]
        members = [m for m in members if m not in done] or [(r, c)]
        r0, r1 = min(m[0] for m in members), max(m[0] for m in members)
        c0, c1 = min(m[1] for m in members), max(m[1] for m in members)
        block = {(a, d) for a in range(r0, r1 + 1) for d in range(c0, c1 + 1)} - done
        done |= block
        px = [grid[r0, c0][0], grid[r0, c0][1], grid[r1, c1][2], grid[r1, c1][3]]
        cells.append((r0, c0, r1 - r0 + 1, c1 - c0 + 1, r0 < header_rows,
                      _box_from_pixels(to_page, px)))  # fmt: skip
    return cells, header_rows


def tableformer_cells(reading, to_page):
    cells = []
    for cell in reading["cells"]:
        cells.append((cell["row"], cell["column"], cell["row_span"], cell["column_span"],
                      cell["column_header"], _box_from_pixels(to_page, cell["box"])))  # fmt: skip
    rows_with_header = {c[0] for c in cells if c[4]}
    header_rows = 0
    while header_rows in rows_with_header:
        header_rows += 1
    return cells, header_rows


def plumber_cells(pdf_page, box):
    found = pdf_page.crop((box.x0 - 2, box.y0 - 2, box.x1 + 2, box.y1 + 2)).find_tables()
    if not found:
        found = pdf_page.crop((box.x0 - 2, box.y0 - 2, box.x1 + 2, box.y1 + 2)).find_tables(
            {"vertical_strategy": "text", "horizontal_strategy": "text"}
        )
    if not found:
        return []
    table = max(found, key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]))
    xs = sorted({round(v, 1) for c in table.cells for v in (c[0], c[2])})
    ys = sorted({round(v, 1) for c in table.cells for v in (c[1], c[3])})

    def index(values, v):
        return min(range(len(values)), key=lambda i: abs(values[i] - v))

    cells = []
    for x0, y0, x1, y1 in table.cells:
        r0, r1 = index(ys, y0), index(ys, y1)
        c0, c1 = index(xs, x0), index(xs, x1)
        if r1 <= r0 or c1 <= c0:
            continue
        cells.append((r0, c0, r1 - r0, c1 - c0, False, BBox(x0=x0, y0=y0, x1=x1, y1=y1)))
    return cells


def camelot_cells(path, number, box, height):
    import camelot

    area = f"{box.x0 - 2},{height - box.y0 + 2},{box.x1 + 2},{height - box.y1 - 2}"
    for flavor in ("lattice", "stream"):
        options = {"table_areas": [area]}
        if flavor == "lattice":
            options.update(backend="pdfium", use_fallback=False)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tables = camelot.read_pdf(str(path), pages=str(number), flavor=flavor,
                                          suppress_stdout=True, **options)  # fmt: skip
        except Exception:  # noqa: BLE001 - a failed comparison method scores as no table
            tables = []
        if tables and tables.n:
            table = tables[0]
            break
    else:
        return []
    cells, done = [], set()
    rows = table.cells
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if (r, c) in done:
                continue
            c1 = c
            while (
                c1 + 1 < len(row)
                and not cell.right
                and not row[c1 + 1].left
                and flavor == "lattice"
            ):
                if row[c1].right:
                    break
                c1 += 1
                if row[c1].right or c1 + 1 >= len(row):
                    break
            r1 = r
            while (r1 + 1 < len(rows) and flavor == "lattice" and not rows[r1][c].bottom
                   and not rows[r1 + 1][c].top):  # fmt: skip
                r1 += 1
            for a in range(r, r1 + 1):
                for d in range(c, c1 + 1):
                    done.add((a, d))
            x0, x1 = row[c].x1, rows[r1][c1].x2
            top, bottom = height - row[c].y2, height - rows[r1][c1].y1
            cells.append((r, c, r1 - r + 1, c1 - c + 1, False,
                          BBox(x0=min(x0, x1), y0=min(top, bottom), x1=max(x0, x1),
                               y1=max(top, bottom))))  # fmt: skip
    return cells


def structure(book, bundle, skip):
    import pdfplumber

    from book_core.tables.recognizers import (
        ReadingCache,
        TableFormerStructure,
        TATRStructure,
    )

    readers = {}
    if "tatr" not in skip:
        readers["tatr"] = ReadingCache(TATRStructure(device="cpu", cache_dir=MODELS), READINGS)
    if "tableformer" not in skip:
        readers["tableformer"] = ReadingCache(
            TableFormerStructure(device="cpu", cache_dir=MODELS), READINGS
        )
    gold = table_scoring.gold_segments(common.gold_tables(book))
    methods = defaultdict(dict)
    seconds = defaultdict(float)
    path = common.source(book)
    pdf = pdfplumber.open(str(path))
    for number, page in sorted(bundle["pages"].items()):
        tables, _ = analyze(page["evidence"])
        if not tables:
            continue
        ours = {(number, i): dev.our_grid(number, t, page["tokens"]) for i, t in enumerate(tables)}
        matched = table_scoring.match(gold, ours)
        if not matched:
            continue
        boxes = token_boxes(book, number)
        height = pdf.pages[number - 1].height
        for _, okey, _ in matched:
            draft = tables[okey[1]]
            methods["geometry"][okey] = ours[okey]
            png = to_page = None
            for name, reader in readers.items():
                begun = time.perf_counter()
                if png is None:
                    png, to_page = crop(book, number, draft.bbox, draft.rotation)
                reading = reader.read(png)
                cells, header_rows = (tatr_cells if name == "tatr" else tableformer_cells)(
                    reading, to_page
                )
                methods[name][okey] = grid_from_cells(number, cells, boxes, header_rows)
                seconds[name] += time.perf_counter() - begun
            if "pdfplumber" not in skip:
                begun = time.perf_counter()
                cells = plumber_cells(pdf.pages[number - 1], draft.bbox)
                methods["pdfplumber"][okey] = grid_from_cells(number, cells, boxes)
                seconds["pdfplumber"] += time.perf_counter() - begun
            if "camelot" not in skip:
                begun = time.perf_counter()
                cells = camelot_cells(path, number, draft.bbox, height)
                methods["camelot"][okey] = grid_from_cells(number, cells, boxes)
                seconds["camelot"] += time.perf_counter() - begun
        if number % 50 == 0:
            print(book, "structure", number, {k: round(v) for k, v in seconds.items()}, flush=True)
    pdf.close()
    out = {}
    for name, grids in methods.items():
        # Score on the matched regions only (detection is the same for every method).
        result = table_scoring.score(
            {k: v for k, v in gold.items()},
            {k: (v if v["cells"] else {"cells": [(0, 0, 1, 1, False, frozenset())],
                                         "header_rows": 0}) for k, v in grids.items()},
        )  # fmt: skip
        out[name] = {
            k: result[k]
            for k in (
                "structure_scored",
                "teds_structure_mean",
                "teds_exact_share",
                "adjacency_precision",
                "adjacency_recall",
                "adjacency_f1",
                "header_rows_exact",
                "header_token_accuracy",
            )  # fmt: skip
        }
        out[name]["seconds"] = round(seconds.get(name, 0.0), 1)
        out[name]["no_structure"] = sum(1 for v in grids.values() if not v["cells"])
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=common.BOOK_ORDER)
    parser.add_argument("--label", default="final")
    parser.add_argument("--skip", default="")
    args = parser.parse_args()
    skip = set(filter(None, args.skip.split(",")))
    bundle = dev.load(args.book, sub=args.book == "spanish_us_history")
    started = time.perf_counter()
    result = {"detection": detection(args.book, bundle)}
    print(args.book, result["detection"], flush=True)
    result["structure"] = structure(args.book, bundle, skip)
    result["seconds"] = round(time.perf_counter() - started, 1)
    common.write(common.OUT / "methods" / args.label / f"{args.book}.json", result)
    for name, row in result["structure"].items():
        print(args.book, name, row, flush=True)


if __name__ == "__main__":
    main()
