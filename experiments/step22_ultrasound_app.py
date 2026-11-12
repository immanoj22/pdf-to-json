"""Step 22: the Ultrasound-guided Regional Blocks book fixed with the app's Browse edit
operations only (the same calls the Browse buttons make), then exported as DocBook and ePub.

A copy of the book's job (converter output, parts, details) goes into a throw-away app; the
live app's data is not touched. Edits are chosen by page and title start (page numbers are
allowed in a scenario like this one). Prints the chapter list the Browse panel shows and the
export QC.

Usage: python step22_ultrasound_app.py JOB_DIR WORK_DIR
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT)]

from book_app.api import create_app
from book_app.config import AppSettings
from fastapi.testclient import TestClient

KIND = {"op": "heading_kind"}
SCENARIO = [  # (page, title starts with, edit)
    (9, "Contents", {**KIND, "kind": "front_matter"}),
    (11, "\t 1.", {"op": "heading_remove"}),
    (13, "1\n", {**KIND, "kind": "chapter"}),
    (13, "PART I:", {**KIND, "kind": "section"}),
    (14, "PART II:", {**KIND, "kind": "section"}),
    (14, "ULTRASOUND PROBE", {**KIND, "kind": "section"}),
    (14, "Modes", {**KIND, "kind": "section"}),
    (16, "PART III:", {**KIND, "kind": "section"}),
    (19, "Upper Limb", {**KIND, "kind": "part"}),
    (37, "Truncal", {**KIND, "kind": "part"}),
    (59, "Lower Limb", {**KIND, "kind": "part"}),
    (67, "Recent Advances", {**KIND, "kind": "part"}),
]


def without_number(text, number):
    """What a person does in the title box: delete the stray number (a line of its own, or at
    the start or end of the title) and nothing else."""
    lines = [ln for ln in text.split("\n") if ln.strip(" .:-\t") != str(number)]
    out = "\n".join(lines).strip()
    for lead in (f"{number}. ", f"{number} ", f"{number}.\t"):
        if out.startswith(lead):
            out = out[len(lead):].strip()
    if out.endswith(" " + str(number)):
        out = out[: -len(str(number))].strip()
    return out


def main():
    job_dir, work = Path(sys.argv[1]), Path(sys.argv[2])
    data = work / "data"
    shutil.rmtree(work, ignore_errors=True)
    job = data / "jobs" / job_dir.name
    shutil.copytree(job_dir, job, ignore=shutil.ignore_patterns("exports", "pagecache", "preview"))
    (job / "decisions.json").unlink(missing_ok=True)
    app = create_app(AppSettings(data_folder=str(data), base=work))
    client = TestClient(app, base_url="http://127.0.0.1:8777")
    jid = job_dir.name
    who = "Asha"

    def post(edit):
        r = client.post(f"/api/jobs/{jid}/edits", json={"who": who, "edit": edit})
        if r.status_code != 200:
            print("  refused:", edit.get("op"), r.json().get("error") or r.json())
        return r

    def unit_on(page, start):
        units = client.get(f"/api/jobs/{jid}/pages/{page}/units").json()["units"]
        return next((u for u in units if u["type"] == "heading"
                     and u["text"].startswith(start)), None)  # fmt: skip

    # the contents page entries: the Browse list shows them as headings, "Not a heading" each
    units9 = client.get(f"/api/jobs/{jid}/pages/9/units").json()["units"]
    for u in units9:
        if u["type"] == "heading" and not u["text"].startswith("Contents"):
            post({"op": "heading_remove", "unit": u["id"]})
    for page, start, edit in SCENARIO:
        unit = unit_on(page, start)
        if unit is None:
            print(f"page {page}: no heading starts with {start!r}")
            continue
        post({**edit, "unit": unit["id"]})
    # the title editor: each chapter and part title loses its stray number
    for row in client.get(f"/api/jobs/{jid}/chapters").json()["chapters"]:
        if row["number"] and row["title"] != row["text"]:
            units = client.get(f"/api/jobs/{jid}/pages/{row['page']}/units").json()["units"]
            raw = next(u["text"] for u in units if u["id"] == row["unit"])
            post({"op": "heading_text", "unit": row["unit"], "text": without_number(raw, row["number"])})
    rows = client.get(f"/api/jobs/{jid}/chapters").json()["chapters"]
    print("chapter list:", sum(r["role"] == "part" for r in rows), "parts,",
          sum(r["role"] == "chapter" for r in rows), "chapters")
    for r in rows:
        print(f"  {r['role']:8s} {r['number']!s:>4s}  p{r['page']:<3d} {r['title'][:70]}")
    details = client.get(f"/api/jobs/{jid}/details").json()["details"]
    client.put(f"/api/jobs/{jid}/details", json=details)
    ex = client.post(f"/api/jobs/{jid}/export", json={
        "who": who, "formats": ["docbook", "epub"], "allow_alt_text_placeholders": True})
    body = ex.json()
    print("export status", ex.status_code, "epubcheck:", body.get("epubcheck"))
    print("verdicts:", body.get("verdicts"), "failed edits:", body.get("failed_edits"))
    folder = data / "jobs" / jid / "exports" / f"{body['n']:03d}"
    for report in sorted(folder.rglob("qc_report.json")):
        qc = json.loads(report.read_text("utf-8"))
        loss = qc.get("lossless") or {}
        print(report.relative_to(folder), "| verdict", qc.get("verdict"), "| dtd errors",
              (qc.get("dtd") or {}).get("errors"), "| lossless missing/extra",
              loss.get("missing"), loss.get("extra"), "| house-rule findings",
              (qc.get("house_rules") or {}).get("violations"))
    qc = body.get("epub_qc") or {}
    own = (qc.get("lossless") or {})
    print("epub lossless missing/extra:", own.get("missing"), own.get("extra"),
          "| epubcheck:", json.dumps(qc.get("epubcheck"))[:300])
    app.state.converter.stop()


if __name__ == "__main__":
    main()
