"""Headings (page, role, level, units) decided from every cached structure evidence file, as JSON
on stdout: run with the old and the new code and diff. Usage: structure_compare.py <cache_dir>..."""
import glob, gzip, json, os, sys
from book_core.structure.decide import DEFAULT_CONFIG, decide_book
out = {}
for cache in sys.argv[1:]:
    for f in sorted(glob.glob(f"{cache}/structure/evidence/*.json.gz")):
        ev = json.loads(gzip.decompress(open(f, "rb").read()).decode().split("\n")[1])
        books = sorted(glob.glob(f"{cache}/structure/book/*.json"), key=os.path.getmtime)
        cfg = {}
        for b in reversed(books):
            try:
                p = json.loads(json.loads(gzip.decompress(open(b, "rb").read()))["payload"])
                if p.get("source_sha256") == ev["source_sha256"]:
                    cfg = p.get("config", {}); break
            except Exception:
                continue
        try:
            res = decide_book(ev, {**DEFAULT_CONFIG, **cfg, "heading_classifier": None})
        except Exception as e:
            out[f] = f"error {type(e).__name__}: {e}"; continue
        out[f] = [[h.page, h.role, h.level, list(h.unit_ids)] for h in res["headings"]]
json.dump(out, sys.stdout)
