"""Export a copy with all of its edits (docbook + epub), print the lossless and DTD numbers."""
import sys, json
from pathlib import Path
from fastapi.testclient import TestClient
from book_app.api import create_app
from book_app.config import AppSettings
root = Path(sys.argv[1]).resolve(); job = sys.argv[2]
dec = root / f"data/jobs/{job}/decisions.json"; full = json.loads(dec.read_text())
dec.write_text(json.dumps({**full, "events": [e for e in full["events"] if e.get("who") != "check"]}))
app = create_app(AppSettings(data_folder=str(root / "data"), base=root, models_folder=""))
c = TestClient(app, base_url="http://127.0.0.1:8777"); H = {"X-User": "check", "X-Role": "manager"}
r = c.post(f"/api/jobs/{job}/export", json={"who": "check", "formats": ["docbook", "epub"], "allow_alt_text_placeholders": True}, headers=H)
q = c.get(f"/api/jobs/{job}/exports/{r.json()['n']}").json()
l, d = q["epub_qc"]["lossless"], q["qc"]["dtd"]
print("RESULT epub", l["missing"], l["extra"], "docbook", q["qc"]["lossless"]["missing"], q["qc"]["lossless"]["extra"],
      "dtd errors", sum(v["errors"] for v in d["by_file"].values()), "verdicts", r.json().get("verdicts"), flush=True)
