"""Export a book on a copy (never the office app's data) and count a text in each output."""
import sys, json, re, zipfile, glob
from pathlib import Path
from fastapi.testclient import TestClient
from book_app.api import create_app
from book_app.config import AppSettings
root = Path(sys.argv[1]).resolve(); job = sys.argv[2]; needle = sys.argv[3]; formats = sys.argv[4].split(",")
import os
if len(sys.argv) > 5:
    jp = root / f"data/jobs/{job}/job.json"; jd = json.loads(jp.read_text()); jd["profile"] = sys.argv[5]; jp.write_text(json.dumps(jd))
dec = root / f"data/jobs/{job}/decisions.json"; full = json.loads(dec.read_text())
dec.write_text(json.dumps({**full, "events": [e for e in full["events"] if e.get("who") != "check"]}))
app = create_app(AppSettings(data_folder=str(root / "data"), base=root, models_folder=""))
c = TestClient(app, base_url="http://127.0.0.1:8777"); H = {"X-User": "check", "X-Role": "manager"}
r = c.post(f"/api/jobs/{job}/export", json={"who": "check", "formats": formats, "allow_alt_text_placeholders": True}, headers=H)
print("export", r.status_code, r.text[:200] if r.status_code != 200 else "")
n = r.json()["n"]; q = c.get(f"/api/jobs/{job}/exports/{n}").json()
folder = root / f"data/jobs/{job}/exports/{n:03d}"
print("verdicts", r.json().get("verdicts"))
count = lambda text: len(re.findall(re.escape(needle), text, re.I))
for f in folder.rglob("*"):
    if f.is_file() and f.suffix in (".xml", ".xhtml", ".html", ".dtbook"): 
        k = count(f.read_text("utf-8", "ignore"))
        if k: print("  ", f.relative_to(folder), k)
for name in ("qc", "epub_qc"):
    d = q.get(name)
    if d: print(name, "verdict", d.get("verdict"), "lossless", {k: (d.get("lossless") or {}).get(k) for k in ("missing", "extra", "tokens")}, "dtd", json.dumps(d.get("dtd"))[:120])
for fmt, d in (q.get("other_qc") or {}).items(): print(fmt, d.get("verdict"), {k: (d.get("lossless") or {}).get(k) for k in ("missing", "extra")})
