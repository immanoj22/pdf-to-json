"""Step 14b shared helpers: per-page development evidence and the Step 14b navigation.

``pages`` yields the per-page evidence of ``step14b_bundles`` one page at a time. ``load``
returns the Step 14a development bundle of a book (``step14a_dev.load``) with each
page's navigation kind replaced by the Step 14b structure decision (``step14b_navigation``
output, ``kinds_after``) when it exists, so table development sees the navigation fix
before the final runs. ``token_texts`` gives the retained tokens' texts of a page in
benchmark order (inspection only).
"""

# ruff: noqa: E402
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14a_dev as dev

OUT = ROOT / "experiments/out/step14b"
PAGES = ROOT / ".cache/step14b/pages"
FINAL = OUT / "final"
_keys = common.keys


def _final_keys(book, capture=None):
    """Cache keys: the Step 14b final capture once it exists (else as Step 14a)."""
    if capture is None and (FINAL / "performance" / f"{book}.json").exists():
        capture = FINAL
    return _keys(book, capture)


common.keys = _final_keys


@lru_cache
def navigation(book):
    """{page: navigation kind} after the Step 14b fix: the final run's structure stage when it
    exists, else the development decision (``step14b_navigation``), else Step 14a's."""
    if (FINAL / "performance" / f"{book}.json").exists():
        return common.navigation(book)
    path = OUT / "navigation" / f"{book}.json"
    if path.exists():
        row = common.read(path)
        if "kinds_after" in row:
            return {int(k): v for k, v in row["kinds_after"].items()}
    return common.navigation(book)


def page_numbers(book):
    """The pages of the latest build (its ``_index.json``)."""
    return sorted(common.read(PAGES / book / "_index.json")["pages"])


def page(book, number):
    """One page's development evidence (``step14b_bundles``): evidence, tokens, built."""
    import gzip
    import pickle

    with gzip.open(PAGES / book / f"{number}.pkl.gz", "rb") as stream:
        return pickle.load(stream)


def pages(book, only=None):
    """(number, page) for every development page of a book (one at a time)."""
    for number in page_numbers(book):
        if only is None or number in only:
            yield number, page(book, number)


def load(book, models=("heron", "pp", "tatr"), pages=None):
    """The book's bundle with Step 14b navigation; ``pages``: keep only these pages."""
    bundle = dev.load(book, models, sub=book == "spanish_us_history")
    kinds = navigation(book)
    if pages is not None:
        bundle["pages"] = {n: p for n, p in bundle["pages"].items() if n in pages}
    for number, page in bundle["pages"].items():
        page["evidence"].navigation = kinds.get(number)
    return bundle


def token_texts(book, number):
    """[NFKC token text] per retained token ordinal of a page (the bundle's token order)."""
    from book_core.ledger.tokenization import line_tokens

    page = common.text_page(book, number)
    out = []
    for line in page.store.lines:
        raw = page.store.raw_line_text(line)
        if not raw.strip() or not page.geometry.content_bbox.contains_center(line.bbox):
            continue
        out += [token.value for token in line_tokens(page.store, line)]
    return out
