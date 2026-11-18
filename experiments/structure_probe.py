"""Decide the structure of a book from its cached structure evidence (no conversion) and print
the part / chapter headings. Usage: structure_probe.py <cache_dir> [--roles part,unit,chapter]"""
import gzip, glob, json, sys
from book_core.structure.decide import DEFAULT_CONFIG, decide_book
cache = sys.argv[1]
f = sorted(glob.glob(f"{cache}/structure/evidence/*.json.gz"))[-1]
ev = json.loads(gzip.decompress(open(f, "rb").read()).decode().split("\n")[1])
book = sorted(glob.glob(f"{cache}/structure/book/*.json"), key=lambda p: -__import__("os").path.getmtime(p))[0]
cfg = json.loads(json.loads(gzip.decompress(open(book, "rb").read()))["payload"]).get("config", {})
text = {u["unit"]: u["text"] for p in ev["pages"] for u in p["units"]}
res = decide_book(ev, {**DEFAULT_CONFIG, **cfg, "heading_classifier": None})
roles = set((sys.argv[2] if len(sys.argv) > 2 else "part,unit,chapter").split(","))
for h in res["headings"]:
    if h.role in roles:
        print(h.page, h.role, h.level, repr(" ".join(text.get(u, "?") for u in h.unit_ids)[:60]))
if len(sys.argv) > 3:
    for h in res["headings"]:
        if h.page in {int(x) for x in sys.argv[3].split(",")}:
            print(h.page, h.role, h.level, h.level_method, h.style_group, repr(" ".join(text.get(u, "?") for u in h.unit_ids)[:40]), h.evidence.get("numbering_depth"), h.evidence.get("prominence"), h.reasons[-2:])
