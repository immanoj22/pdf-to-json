"""Browser check of "Restore as…" in Browse, on a COPY of a converted book (never the live app).

Opens Browse on a page, restores the title line as a chapter title (Check -> Confirm), shows the
saved status, undoes it, and reads the audit log. Screenshots go to OUT.

Usage: python restore_browser_check.py BASE_URL JOB PAGE OUT_DIR"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

base, job, page, out = sys.argv[1].rstrip("/"), sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
assert base.rsplit(":", 1)[-1] != "8777", "never run this against the live app"
out.mkdir(parents=True, exist_ok=True)


def api(path):
    with urllib.request.urlopen(base + path, timeout=900) as r:
        return json.load(r)


def shot(pg, name):
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(out / f"{name}.png"))
    print("shot", name, flush=True)


with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = br.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2).new_page()
    pg.set_default_timeout(90000)
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "/#/login")
    pg.evaluate("localStorage.setItem('reviewer','Restore Tester');localStorage.setItem('role','reviewer');localStorage.setItem('tourSeen:restore tester','1')")
    pg.goto(f"{base}/#/job/{job}/review?mode=browse&page={page}")
    pg.reload()
    panel = pg.get_by_test_id("restore-panel")
    print("page loaded", flush=True); panel.wait_for(state="visible")
    line = panel.get_by_test_id("restore-line").first
    text = line.locator(".rtext").inner_text()
    print("line:", text, "| head:", pg.get_by_test_id("restore-head").inner_text().split("\n")[0])
    print("counting rows", flush=True); before_rows = pg.get_by_test_id("unit").count(); print("rows", before_rows, flush=True)
    shot(pg, "1_panel")
    line.get_by_test_id("restore-open").click()
    pg.get_by_test_id("restore-as-chapter").check()
    shot(pg, "2_choose")
    pg.get_by_test_id("restore-check").click()
    pv = pg.get_by_test_id("restore-preview-line")
    pv.wait_for()
    print("preview:", pv.inner_text())
    assert pg.get_by_test_id("unit").count() == before_rows, "the preview must not change the page"
    assert not [e for e in api(f"/api/jobs/{job}/decisions")["edits"] if e["op"] == "restore_line"], "nothing saved before Confirm"
    shot(pg, "3_preview")
    pg.get_by_test_id("restore-confirm").click()
    pg.get_by_test_id("status").wait_for(state="visible")
    pg.wait_for_function("n => document.querySelectorAll('[data-testid=unit]').length === n + 1", arg=before_rows)
    print("status:", pg.get_by_test_id("status").inner_text())
    first = pg.get_by_test_id("unit").first
    print("first block now:", first.get_attribute("data-type"), "|", first.inner_text().split("\n")[0][:70])
    saved = [e for e in api(f"/api/jobs/{job}/decisions")["edits"] if e["op"] == "restore_line"]
    assert len(saved) == 1 and saved[0]["who"] == "Restore Tester" and saved[0]["as"] == "chapter", saved
    assert pg.get_by_test_id("restore-line").count() == 0 or text not in pg.get_by_test_id("restore-panel").inner_text().split("Left out")[0]
    shot(pg, "4_saved")
    pg.get_by_test_id("status-undo").click()
    pg.wait_for_function("n => document.querySelectorAll('[data-testid=unit]').length === n", arg=before_rows)
    pg.get_by_test_id("restore-line").first.wait_for()
    assert not [e for e in api(f"/api/jobs/{job}/decisions")["edits"] if e["op"] == "restore_line"], "Undo takes the change out of the book"
    shot(pg, "5_undone")
    audit = [json.loads(x) for x in Path(sys.argv[5]).read_text().splitlines()] if len(sys.argv) > 5 else []
    print("audit entries for restore_line:", [a for a in audit if a.get("op") == "restore_line"][-2:])
    assert not errors, errors
    br.close()
print("OK")
