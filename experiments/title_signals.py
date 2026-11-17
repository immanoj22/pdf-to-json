"""For pages the title rules flagged: does the page look like where a section starts?
Usage: python title_signals.py JOB_DIR_WITH_CACHE PAGE [PAGE ...]
Rebuilds the line features of each page and the next three from the run's caches and applies the
classifier's own test (a display-size line right under the head, or far more white space under it
than on the pages after)."""
import os
import sys
from pathlib import Path

from book_core.cache_store import read_model
from book_core.furniture import inputs as I
from book_core.furniture.classify import Classifier, FurnitureConfig
from book_core.furniture.features import page_features
from book_core.model.spans import ExtractedPage

D = Path(sys.argv[1])
c = D / "cache"
digest = I.source_digest(D / "input.pdf")
tk = os.listdir(c / "text")[0]
newest = lambda sub: sorted(os.listdir(c / sub), key=lambda k: os.path.getmtime(c / sub / k))[-1]  # noqa: E731
lk, ok = newest("layout"), newest("reading_order")
cache = {}


def feats(n):
    if n not in cache:
        page = read_model(c / "text" / tk / f"{n}.json", ExtractedPage, tk)
        layout = I._cached(c / "layout" / lk / f"{n}.json", I.PageLayout, lk, digest, n)
        order = I._cached(c / "reading_order" / ok / f"{n}.json", I.PageReadingOrder, ok, digest, n)
        cache[n] = page_features(page, layout, order)
    return cache[n]


def head(n):
    rows = [r for r in feats(n) if r.edge == "top" and r.inside_content and not r.blank and r.stream != "furniture-x"]
    return min(rows, key=lambda r: r.bbox[1]) if rows else None


for p in map(int, sys.argv[2:]):
    pages = {q: feats(q) for q in range(p, p + 4)}
    cl = Classifier.__new__(Classifier)
    cl.config, cl.features = FurnitureConfig(), pages
    row = head(p)
    later = [h for h in (head(q) for q in range(p + 1, p + 4)) if h]
    a = any(o is not row and o.inside_content and not o.blank and o.visible and o.font_size >= 0.9 * row.font_size
            and -row.font_size <= o.bbox[1] - row.bbox[3] <= 1.5 * row.font_size for o in feats(p))
    gaps = sorted(h.inward_gap for h in later if h.inward_gap is not None)
    print(f"p{p:3} head={row.text[:26]!r:30} A(display line)={a!s:5} gap={row.inward_gap and round(row.inward_gap, 1)} later gaps={[round(g, 1) for g in gaps]} -> opens={cl._opens_a_section(row, later)}")
