"""Replay the review edits of a job on a COPY: export after the first k edits, binary-search
the first edit after which the ePub lossless check has missing/extra tokens."""
import sys, json
from pathlib import Path
from fastapi.testclient import TestClient
from book_app.api import create_app
from book_app.config import AppSettings
root = Path(sys.argv[1]).resolve(); job = sys.argv[2]
dec = root / f"data/jobs/{job}/decisions.json"; full = json.loads(dec.read_text())
events = [e for e in full["events"] if e.get("who") != "check"]
app = create_app(AppSettings(data_folder=str(root / "data"), base=root, models_folder=""))
c = TestClient(app, base_url="http://127.0.0.1:8777"); H = {"X-User": "check", "X-Role": "manager"}
cache = {}
def bad(k):
    """Gap after the first k events (an event is an edit, override or its undo, in log order)."""
    if k in cache: return cache[k]
    dec.write_text(json.dumps({**full, "events": events[:k]}))
    r = c.post(f"/api/jobs/{job}/export", json={"who": "check", "formats": ["docbook", "epub"], "allow_alt_text_placeholders": True}, headers=H)
    q = c.get(f"/api/jobs/{job}/exports/{r.json()['n']}").json()
    l = q["epub_qc"]["lossless"]; d = q["qc"]["dtd"]
    errs = sum(v["errors"] for v in d["by_file"].values()) if d else None
    cache[k] = (l["missing"], l["extra"], errs, (q["qc"].get("lossless") or {}).get("missing"))
    print("k", k, "epub missing/extra", cache[k][:2], "dtd errors", errs, "docbook missing", cache[k][3], flush=True)
    return cache[k]
try:
    n = len(events)
    base = bad(0)
    print("with all", n, bad(n), flush=True)
    lo, hi = 0, n          # lo: fine, hi: broken
    while hi - lo > 1:
        mid = (lo + hi) // 2
        m = bad(mid)
        if m[0] or m[1]: hi = mid
        else: lo = mid
    e = events[hi - 1]
    print("FIRST BAD EVENT index", hi - 1, json.dumps(e)[:600])
finally:
    dec.write_text(json.dumps(full))
