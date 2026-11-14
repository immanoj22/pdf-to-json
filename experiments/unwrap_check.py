"""Quick check: unwrap the big table of p46, make two tables (Change element -> Table), export
the ePub once on a copy of the job (never the office app's data), report lossless."""
import json, sys
from pathlib import Path
from fastapi.testclient import TestClient
from book_app.api import create_app
from book_app.config import AppSettings

root = Path(sys.argv[1]).resolve()
job = sys.argv[2]
app = create_app(AppSettings(data_folder=str(root / "data"), base=root, models_folder=""))
c = TestClient(app, base_url="http://127.0.0.1:8777")
H = {"X-User": "check", "X-Role": "manager"}
units = c.get(f"/api/jobs/{job}/pages/46/units").json()["units"]
tables = [u for u in units if u["type"] == "table"]
big = max(tables, key=lambda u: u.get("rows", 0))
print("table", big["id"], big.get("rows"), "rows")
def edit(e):
    r = c.post(f"/api/jobs/{job}/edits", json={"who": "check", "edit": e}, headers=H)
    print(e["op"], r.status_code, json.dumps(r.json())[:300]); assert r.status_code == 200; return r.json()
edit({"op": "unwrap", "unit": big["id"]})
after = c.get(f"/api/jobs/{job}/pages/46/units").json()["units"]
paras = [u for u in after if u["id"].startswith("") and u["type"] == "paragraph"][-1:]
mine = [u for u in after if u["type"] == "paragraph" and u["id"] not in {x["id"] for x in units}]
print("unwrapped into", len(mine), "paragraphs")
half = len(mine) // 2 // 4 * 4
edit({"op": "table_make", "units": [u["id"] for u in mine[:half]], "columns": 4})
edit({"op": "table_make", "units": [u["id"] for u in mine[half:]], "columns": 4})
r = c.post(f"/api/jobs/{job}/export", json={"who": "check", "format": "epub", "allow_alt_text_placeholders": True}, headers=H)
print("export", r.status_code, json.dumps(r.json())[:200])
n = r.json().get("n")
q = c.get(f"/api/jobs/{job}/exports/{n}").json()
print("LOSSLESS", json.dumps(q["epub_qc"]["lossless"]))
