"""Offline test of the guard "the same text is already printed as a line near the page": for every
line the title rules moved out of the furniture, is there a line with the same text within two
pages that is not itself a running head or folio? Usage: python title_guard_check.py JOB_DIR"""
import gzip
import json
import os
import sys
from pathlib import Path

from book_core.cache_store import read_model
from book_core.furniture import inputs as I
from book_core.furniture.features import page_features
from book_core.model.spans import ExtractedPage

D = Path(sys.argv[1]); c = D / "cache"
digest = I.source_digest(D / "input.pdf"); tk = os.listdir(c / "text")[0]
newest = lambda sub: sorted(os.listdir(c / sub), key=lambda k: os.path.getmtime(c / sub / k))[-1]  # noqa: E731
lk, ok = newest("layout"), newest("reading_order")
F = sorted((c / "furniture" / "book").glob("*.json"), key=os.path.getmtime)[-1]
dec = json.loads(json.load(gzip.open(F))["payload"])
roles = {(int(p), r["line_id"]): r for p, rs in dec["roles"].items() for r in rs}
flagged = sorted((p, l) for (p, l), r in roles.items() if r["reasons"][0].startswith(("running-head slot text printed", "first page of a run")))
cache = {}


def feats(n):
    if n >= 1 and n not in cache:
        try:
            _ = read_model(c / "text" / tk / f"{n}.json", ExtractedPage, tk)
        except Exception:  # beyond the last page
            return []
        page = read_model(c / "text" / tk / f"{n}.json", ExtractedPage, tk)
        layout = I._cached(c / "layout" / lk / f"{n}.json", I.PageLayout, lk, digest, n)
        order = I._cached(c / "reading_order" / ok / f"{n}.json", I.PageReadingOrder, ok, digest, n)
        cache[n] = page_features(page, layout, order)
    return cache.get(n, [])


def same(a, b):
    """The same text, or the shorter is inside the longer (a heading set over several lines)."""
    short, long_ = sorted((a, b), key=len)
    return a == b or (len(short) >= 12 and short in long_)


blocked = 0
for page, lid in flagged:
    row = next(r for r in feats(page) if r.line_id == lid)
    near = [(q, r) for q in range(page - 2, page + 3) for r in feats(q)
            if r is not row and same(row.key, r.key) and r.font_size >= 1.3 * row.font_size and roles.get((q, r.line_id), {}).get("role") not in ("running_head", "folio", "running_foot")]
    blocked += bool(near)
    print(f"p{page:3} {row.text[:34]!r:38} same text elsewhere near: {[(q, round(r.font_size, 1), roles.get((q, r.line_id), {}).get('role')) for q, r in near][:2]}")
print(f"{len(flagged)} flagged, {blocked} would be blocked by the guard")
