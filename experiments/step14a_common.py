"""Step 14a shared helpers: the five books, their current cache keys and cached page reads.

Keys come from the latest final capture of each book (Step 13c, or a Step 14a run once it
exists). Every read is a verified cache read; no stage is recomputed here.
"""

# ruff: noqa: E402
import json
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step7_layouts import CACHE
from step11_run import CACHE11
from step13_books import BOOKS, MATH_BOOK

from book_core.cache_store import read_model
from book_core.extraction.fingerprints import stable_id
from book_core.layout.models import PageLayout
from book_core.lists.keys import book_fingerprint
from book_core.lists.models import PageLists
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import verified_read
from book_core.objects.models import NativeObjectPage

OUT = ROOT / "experiments/out/step14a"
BOOK_ORDER = ["spanish_us_history", "immigrant_children", "art_therapy_index", "medical_anatomy",
              MATH_BOOK]  # fmt: skip
SHORT = {
    "spanish_us_history": "1 Spanish US history",
    "immigrant_children": "2 Immigrant children",
    "art_therapy_index": "3 Art-therapy index",
    "medical_anatomy": "4 Medical anatomy",
    MATH_BOOK: "Statistics",
}


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=1, ensure_ascii=False, default=str) + "\n", "utf-8", newline="\n"
    )


def read(path):
    return json.loads(Path(path).read_text("utf-8"))


@lru_cache
def keys(book, capture=None):
    """Cache keys of the book's latest run: {stage: key}; lists as its book fingerprint."""
    candidates = [capture] if capture else []
    candidates += [OUT / "final", ROOT / "experiments/out/step13c/final"]
    for root in candidates:
        path = Path(root) / f"performance/{book}.json"
        if path.exists():
            run = read(path)["run"]
            found = dict(run["cache_keys"])
            found["_pages"] = run["pages"]
            found["_capture"] = str(root)
            lists = found["lists"]
            found["lists_fp"] = book_fingerprint(lists) if isinstance(lists, dict) else lists
            return found
    raise FileNotFoundError(f"No run record for {book}")


def source(book):
    from reference_paths import reference_path

    return reference_path(BOOKS[book][0])


def text_page(book, number):
    key = keys(book)["native"]
    return read_model(CACHE / "text" / key / f"{number}.json", ExtractedPage, key)


def native_page(book, number):
    key = keys(book)["native"]
    return verified_read(CACHE / "native" / key / f"{number}.json", NativeObjectPage, key)


def layout_page(book, number):
    key = keys(book)["layout"]
    return verified_read(CACHE / "layout" / key / f"{number}.json", PageLayout, key)


def list_page(book, number):
    key = keys(book)["lists_fp"]
    return verified_read(
        CACHE11 / "lists/page" / key / f"{number}.json", PageLists, stable_id(key, "page", number)
    )


def pages(book):
    return keys(book)["_pages"]


def figure_page(book, number):
    from book_core.figures.cache import load_page

    return load_page(CACHE, keys(book)["figures"], number)


def equation_page(book, number):
    from book_core.equations.cache import load_page

    return load_page(CACHE, keys(book)["equations"], number)


GOLD_TABLES = ROOT / "backend/tests/gold_derived_tables"


@lru_cache
def gold_tables(book):
    import gzip

    path = GOLD_TABLES / book / "tables.jsonl.gz"
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


@lru_cache
def derived_gold(book):
    from book_core.evaluation.derived_harness import DerivedGold

    return DerivedGold.load(ROOT / "backend/tests/gold_derived" / book)


def token_owners(book, number):
    """[line id or None] per retained token ordinal of the page (benchmark order)."""
    from book_core.evaluation.furniture import token_lines

    return token_lines(text_page(book, number), layout_page(book, number))


def render(book, number, boxes, path, dpi=100, crop=None):
    """Save a page render with outlined boxes [(bbox, (r, g, b), width, label)] (page points)."""
    import cv2
    import numpy as np
    import pymupdf

    with pymupdf.open(source(book)) as document:
        page = document[number - 1]
        clip = pymupdf.Rect(*crop) if crop else None
        pixmap = page.get_pixmap(dpi=dpi, clip=clip)
        image = (
            np.frombuffer(pixmap.samples, dtype=np.uint8)
            .reshape(pixmap.height, pixmap.width, pixmap.n)[:, :, :3][:, :, ::-1]
            .copy()
        )
        origin = (crop[0], crop[1]) if crop else (page.rect.x0, page.rect.y0)
    scale = dpi / 72
    for bbox, colour, width, label in boxes:
        x0, y0, x1, y1 = (
            int((bbox[0] - origin[0]) * scale),
            int((bbox[1] - origin[1]) * scale),
            int((bbox[2] - origin[0]) * scale),
            int((bbox[3] - origin[1]) * scale),
        )
        cv2.rectangle(image, (x0, y0), (x1, y1), colour[::-1], width)
        if label:
            cv2.putText(image, str(label), (x0 + 2, max(10, y0 + 12)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.4, colour[::-1], 1, cv2.LINE_AA)  # fmt: skip
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)
    return path


@lru_cache
def navigation(book):
    """{page: printed navigation kind} from the structure stage's book record."""
    from step10_run import CACHE10

    from book_core.structure.models import BookStructure

    key = keys(book)["structure"]
    structure = verified_read(CACHE10 / "structure/book" / f"{key}.json", BookStructure, key)
    return {n.page: n.kind for n in structure.navigation_pages}
