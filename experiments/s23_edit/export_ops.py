"""Every element change in one book (on different units), then the exports: DocBook (DTD,
lossless) and ePub (EPUBCheck, lossless). Usage: export_ops.py <publication folder> <out>"""
import json, subprocess, sys
from pathlib import Path
from book_app import overlay

pub, out = Path(sys.argv[1]), Path(sys.argv[2])
book = json.loads((pub / "book.json").read_text())
top = book["content"]

def runs(kind="paragraph", n=3, skip=0):
    found = 0
    for i in range(len(top) - n):
        w = top[i:i + n]
        if all(u["type"] == kind and u["id"] not in used for u in w) and len({u["pages"][0] for u in w}) == 1:
            found += 1
            if found > skip:
                for u in w: used.add(u["id"])
                return [u["id"] for u in w]
used = set()
def free_runs():
    while True:
        r = runs()
        if r is None: return
        yield r
pool = free_runs()
take = lambda: next(pool)
first = lambda t: next(u for u, _ in overlay.walk(top) if u["type"] == t)
fig, tbl = first("figure"), first("table")
edits = []
r = take(); edits.append({"op": "list_set", "units": r, "list_type": "bulleted"})
r = take(); edits.append({"op": "list_set", "units": r, "list_type": "numbered"})
r = take(); edits.append({"op": "box", "units": r, "kind": "box", "title": True, "scope": "follow"})
r = take(); edits.append({"op": "box", "units": r[:1], "kind": "quote"}); edits.append({"op": "box", "units": r[1:2], "kind": "pull_quote"})
r = take(); edits.append({"op": "caption", "unit": r[0], "figure": fig["id"]}); edits.append({"op": "footnote", "unit": r[1]}); edits.append({"op": "chapter_authors", "units": [r[2]]})
r = take(); edits.append({"op": "table_make", "units": r, "columns": 1})
r = take(); edits.append({"op": "table_text", "unit": r[0], "table": tbl["id"], "role": "note"})
r = take(); edits.append({"op": "bibliography", "units": r})
r = take(); edits.append({"op": "index_entries", "units": r})
r = take(); edits.append({"op": "not_content", "units": r[:1], "kind": "running_head"}); edits.append({"op": "merge", "units": r[1:]})
r = take(); edits.append({"op": "move", "unit": r[1], "direction": "up"})
r = take(); edits.append({"op": "swap_columns", "unit": r[1]})
li = next((u for u, _ in overlay.walk(top) if u["type"] == "list" and len(u["items"]) > 2), None)
if li: edits.append({"op": "list_level", "unit": li["items"][1]["id"], "direction": "in"})
edits = [{**e, "id": f"e{i}"} for i, e in enumerate(edits)]
data, applied, failed = overlay.apply_checked(book, edits)
print("applied", len(applied), "failed", failed)
target = out / "overlay"
overlay.write_overlay(pub, data, target)
for fmt, profile in (("docbook", "jaypee_v3"), ("epub", "jaypee_v4")):
    dest = out / fmt
    cmd = [sys.executable, "-B", "-m", "book_adapters", "run", str(target), "--out", str(dest), "--profile", profile,
           "--format", fmt, "--allow-alt-text-placeholders"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    print(fmt, "exit", p.returncode, p.stderr[-600:] if p.returncode else "")
