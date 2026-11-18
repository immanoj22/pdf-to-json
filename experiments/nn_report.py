"""Which cached books have decimal "N.N" headings, and are their headings unchanged between the
old run (cmp_old.json) and the new run (cmpn_*.json)? Usage: nn_report.py <dir with the json files>"""
import glob, gzip, json, re, sys
d = sys.argv[1]
old = json.load(open(f"{d}/cmp_old.json")); new = {}
for f in glob.glob(f"{d}/cmpn_*.json"):
    new.update(json.load(open(f)))
NN = re.compile(r"^\s*\d{1,2}\.\d{1,2}(?!\.?\d)\.?\s*\S")
seen = {}
for f, a in sorted(old.items()):
    if isinstance(a, str) or f in seen.values():
        continue
    ev = json.loads(gzip.decompress(open(f, "rb").read()).decode().split("\n")[1])
    text = {u["unit"]: u["text"] for p in ev["pages"] for u in p["units"]}
    nn = [h for h in a if NN.match(" ".join(text.get(u, "") for u in h[3]))]
    key = (len(a), len(nn), json.dumps(a)[:200])
    if key in seen:
        continue
    seen[key] = f
    b = new.get(f)
    same = a == b
    name = "/".join(f.split("/")[-5:-3])
    print(f"{'SAME' if same else 'DIFF':5s} headings={len(a):5d} N.N-headings={len(nn):4d}  {name}")
