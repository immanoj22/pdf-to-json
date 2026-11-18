"""For title candidates: where else does their text stand as a line of the book (a Contents entry)?
Usage: python title_contents.py JOB_DIR PAGE ... ; lists pages (outside +-0) holding a line with the same text."""
import sys, os
sys.argv_saved = sys.argv
exec(open(os.path.join(os.path.dirname(__file__), "title_signals.py")).read().split("def head")[0])
import fitz  # noqa
from book_core.furniture.classify import regex
n_pages = len(fitz.open(D / "input.pdf"))
def key(t): return " ".join(t.split()).casefold()
for p in map(int, sys.argv[2:]):
    row = [r for r in feats(p) if r.edge == "top" and r.inside_content and not r.blank][0:3]
    cands = [r for r in feats(p) if r.inside_content and not r.blank]
    hits = {}
    for r in cands:
        if r.edge != "top" or len(r.key) < 6: continue
        for q in range(1, n_pages + 1):
            if q == p: continue
            for o in feats(q):
                if o.key == r.key and o.line_id != r.line_id:
                    hits.setdefault(r.key, []).append(q)
    print(p, {k: v[:8] for k, v in hits.items()})
