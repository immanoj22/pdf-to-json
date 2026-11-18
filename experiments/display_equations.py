"""Display-equation candidates by page layout (read-only), counted per type.

Usage: python display_equations.py JOB_DIR [PAGE ...]
JOB_DIR holds input.pdf and cache/ of a Stage 1 run. Lists numbered and unnumbered candidates
(page, text, label) and the counts; the existing equation stage's display regions are counted
beside them."""
import gzip
import json
import os
import sys
from collections import Counter
from pathlib import Path

from book_core.cache_store import read_model
from book_core.equations.layout_display import display_candidates
from book_core.furniture import inputs as I
from book_core.layout.models import PageLayout
from book_core.model.spans import ExtractedPage

D = Path(sys.argv[1])
c = D / "cache"
digest = I.source_digest(D / "input.pdf")
tk = os.listdir(c / "text")[0]
newest = lambda sub: sorted(os.listdir(c / sub), key=lambda k: os.path.getmtime(c / sub / k))[-1]  # noqa: E731
lk, ek = newest("layout"), newest("equations")
pages = sorted(int(p.stem) for p in (c / "text" / tk).glob("*.json"))
if len(sys.argv) > 2:
    pages = [int(x) for x in sys.argv[2:]]
count, existing = Counter(), Counter()
for n in pages:
    page = read_model(c / "text" / tk / f"{n}.json", ExtractedPage, tk)
    layout = I._cached(c / "layout" / lk / f"{n}.json", PageLayout, lk, digest, n)
    raw = json.load(gzip.open(c / "equations" / ek / f"{n}.json"))["payload"]
    eq = json.loads(raw) if isinstance(raw, str) else raw
    math_lines = {lid for r in eq.get("regions", []) for lid in r.get("line_ids", [])}
    for r in eq.get("regions", []):
        existing[(r["presentation"], r["source"])] += 1
    kinds = {lid: r.type for r in layout.regions for lid in r.line_ids}
    lines = [x for x in layout.lines if x.inside_content]
    taken = [(r["bbox"]["x0"], r["bbox"]["y0"], r["bbox"]["x1"], r["bbox"]["y1"])
             for r in eq.get("regions", []) if r["presentation"] == "display"]
    for cand in display_candidates(page.store, lines, kinds, math_lines, taken):
        kind = "numbered" if cand.numbered else "unnumbered"
        count[kind] += 1
        print(f"p{n:3} {kind:10} {cand.label or '':8} {cand.text[:70]!r}")
print(dict(count), "| existing regions:", dict(existing))
