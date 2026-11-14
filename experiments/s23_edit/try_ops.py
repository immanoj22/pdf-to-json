"""Apply each element change to a real book.json and check: applied, schema-valid, text kept."""
import json, sys, collections
from pathlib import Path
from book_app import overlay
from book_app.edit_ops import number_mark

book = json.loads(Path(sys.argv[1]).read_text())

def texts(data):
    out = collections.Counter()
    def add(c):
        if c and c.get("text"): out.update(c["text"].split())
    for u, _ in overlay.walk(data["content"]):
        add(u.get("content"))
        if u.get("marker"): add({"text": u["marker"]["text"]})
        for k in ("captions", "text", "credits", "notes"):
            for t in u.get(k) or []: add(t.get("content"))
        if u.get("title") and isinstance(u["title"], dict): add(u["title"].get("content"))
        for cell in u.get("cells") or []:
            for it in cell.get("content") or []:
                if it.get("type") == "text": add(it["content"])
    for f in data.get("furniture") or []: add(f.get("content"))
    return out

def paras(page, n=3, kind="paragraph"):
    out, run = [], []
    for u, sib in overlay.walk(book["content"]):
        pass
    for i, u in enumerate(book["content"]):
        if u["type"] == kind and page in u["pages"]:
            run.append(u["id"])
            if len(run) == n: return run
        elif u["type"] != "page_marker":
            run = []
    return None

def find(pred):
    for u, _ in overlay.walk(book["content"]):
        if pred(u): return u
first = lambda t: find(lambda u: u["type"] == t)
body = [u for u in book["content"] if u["type"] == "paragraph"]
runs = []
for i in range(len(book["content"]) - 3):
    w = book["content"][i:i + 3]
    if all(u["type"] == "paragraph" for u in w): runs.append([u["id"] for u in w])
r = runs[10]; r2 = runs[20]
fig, tbl = first("figure"), first("table")
li = find(lambda u: u["type"] == "list" and len(u["items"]) > 2)
cases = {
 "list_set bulleted": {"op": "list_set", "units": r, "list_type": "bulleted"},
 "list_set numbered": {"op": "list_set", "units": r, "list_type": "numbered"},
 "list_set retype": {"op": "list_set", "units": [i["id"] for i in li["items"]], "list_type": "numbered" if li["list_type"] != "numbered" else "bulleted"},
 "list_level in": {"op": "list_level", "unit": li["items"][1]["id"], "direction": "in"},
 "box": {"op": "box", "units": r, "kind": "box", "title": True},
 "quote": {"op": "box", "units": r[:1], "kind": "quote"},
 "pull_quote": {"op": "box", "units": r[:1], "kind": "pull_quote"},
 "caption": {"op": "caption", "unit": r[0], "figure": fig["id"]},
 "table_make": {"op": "table_make", "units": r, "columns": 1},
 "table title": {"op": "table_text", "unit": r[0], "table": tbl["id"], "role": "title" if not tbl.get("title") else "note"},
 "table note": {"op": "table_text", "unit": r[0], "table": tbl["id"], "role": "note"},
 "footnote": {"op": "footnote", "unit": r[0]},
 "chapter_authors": {"op": "chapter_authors", "units": r[:1]},
 "bibliography": {"op": "bibliography", "units": r},
 "index_entries": {"op": "index_entries", "units": r},
 "not_content": {"op": "not_content", "units": r[:1], "kind": "running_head"},
 "merge": {"op": "merge", "units": r},
 "move up": {"op": "move", "unit": r[1], "direction": "up"},
 "move down": {"op": "move", "unit": r[1], "direction": "down"},
 "swap_columns": {"op": "swap_columns", "unit": r[1]},
}
before = texts(book)
for name, e in cases.items():
    e = {**e, "id": "x"}
    out, ok, bad = overlay.apply_checked(book, [e])
    after = texts(out)
    lost = before - after; gained = after - before
    print(f"{name:18} {'ok' if ok else 'FAILED ' + bad[0]['reason'][:90]}  lost={sum(lost.values())} gained={sum(gained.values())}")
