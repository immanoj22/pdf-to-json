"""Browser test of "Turn this and the next N block(s) into → Paragraph" in Browse, on a real book
(job c98738ed66eff60d, page 30: a "list" that is one paragraph cut into items, with words cut at
line ends: "Analysemo|dell", "an|dere", "ausge|gangen", "Dis|sens"). Runs on a separate test app
instance (a free port; never the office app on 8777), signed in as a *reviewer*.

The job folder comes from $BOOK_P30_JOB or the main checkout's app_data (read-only copy);
skipped when Chrome or the job is not on this machine."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
import requests

from .test_e2e_editor import CHROME, ROOT, confirm, open_edit, playwright, server, units  # noqa: F401

JOB = Path(os.environ.get("BOOK_P30_JOB") or ROOT.parent / "pdf_book_converter" / "app_data" / "jobs" / "c98738ed66eff60d")
pytestmark = [
    pytest.mark.skipif(not Path(CHROME).exists(), reason="Chrome is not installed"),
    pytest.mark.skipif(not (JOB / "job.json").is_file(), reason="job c98738ed66eff60d is not on this machine"),
]
REVIEWER = ("try { localStorage.setItem('reviewer', 'Tester'); localStorage.setItem('role', 'reviewer'); localStorage.setItem('tourSeen:tester', '1'); } catch (e) {}")
CUT = ["Analysemodell", "andere", "ausgegangen", "Dissens"]


@pytest.fixture
def page(server):  # noqa: F811
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        ctx.add_init_script(REVIEWER)
        pg = ctx.new_page()
        pg.set_default_timeout(60000)
        problems = []
        pg.on("pageerror", lambda e: problems.append(str(e)))
        yield pg
        browser.close()
        assert not problems, problems


def seeded(server, pg):
    base = server["base"]
    jid = requests.put(base + "/api/jobs?filename=book.pdf", data=(JOB / "input.pdf").read_bytes()).json()["id"]
    folder = server["data"] / "jobs" / jid
    state = json.loads((JOB / "job.json").read_text())
    publication = state["publication"]
    shutil.copytree(JOB / "converter_out", folder / "converter_out", symlinks=True)
    mine = json.loads((folder / "job.json").read_text())
    mine.update(state="converted", publication=publication, profile=state["profile"])
    (folder / "job.json").write_text(json.dumps(mine))
    for name in ("parts.json", "parts_confirmed.json"):  # the job's confirmed parts, as the reviewer left them
        if (JOB / name).is_file():
            shutil.copy(JOB / name, folder / name)
    pg.goto(f"{base}/#/job/{jid}/review?mode=browse&page=30")
    details = requests.get(f"{base}/api/jobs/{jid}/details").json()["details"]
    assert requests.put(f"{base}/api/jobs/{jid}/details", json=details).ok  # the export needs them confirmed
    try:
        pg.get_by_test_id("who").wait_for(timeout=400000)
    except Exception:
        pg.screenshot(path="/tmp/claude-1000/who_missing.png")
        print("PAGE:", pg.url, pg.inner_text("body")[:600])
        raise
    pg.get_by_test_id("who").fill("Tester")
    pg.get_by_test_id("browse-list").locator("[data-testid=unit]").first.wait_for(timeout=180000)
    return jid


def first_list(base, jid):
    return next(r for r in units(base, jid, 30) if r["type"] == "list" and (r["clean"] or r["text"] or "").startswith("Die obige Darstellung"))


def turn_into_paragraph(pg, list_id, per_item=False, count=1):
    panel = open_edit(pg, list_id)
    kind = panel.get_by_test_id("turn-kind")
    assert kind.locator("option").nth(1).get_attribute("value") == "to_paragraph"  # "Paragraph" first, at the top
    assert kind.locator("option").nth(1).inner_text() == "Paragraph"
    assert not panel.get_by_test_id("turn-per-item").is_visible()
    kind.select_option("to_paragraph")
    assert panel.get_by_test_id("turn-per-item").is_visible()
    panel.get_by_test_id("turn-count").fill(str(count))
    if per_item:
        panel.get_by_test_id("turn-per-item").check()
    panel.get_by_test_id("turn-check").click()
    return confirm(pg, list_id)


def test_a_list_becomes_one_paragraph_then_undo(server, page):
    base = server["base"]
    jid = seeded(server, page)
    before = units(base, jid, 30)
    lst = first_list(base, jid)
    preview = turn_into_paragraph(page, lst["id"])
    assert preview
    rows = units(base, jid, 30)
    assert lst["id"] not in [r["id"] for r in rows]  # the list is gone
    para = next(r for r in rows if r["type"] == "paragraph" and (r["clean"] or r["text"] or "").startswith("Die obige Darstellung"))
    for word in CUT:
        assert word in para["clean"], (word, para["clean"])
    assert "Meta- und Objektebene" in para["clean"]  # a real hyphen stays
    assert len(rows) < len(before)
    page.wait_for_selector(f"[data-testid=unit][data-unit='{para['id']}']")
    # the audit log holds who did what
    edits = requests.get(f"{base}/api/jobs/{jid}/decisions").json()["edits"]
    assert [(e["who"], e["op"]) for e in edits if e["op"] == "to_paragraph"] == [("Tester", "to_paragraph")]
    # Undo brings the list back whole
    page.get_by_test_id("undo-last").click()
    page.wait_for_function("() => !document.querySelector('[data-testid=undo-last]') || document.querySelector('[data-testid=undo-last]').disabled")
    again = units(base, jid, 30)
    assert [(r["id"], r["type"]) for r in again] == [(r["id"], r["type"]) for r in before]


def test_one_paragraph_per_item(server, page):
    base = server["base"]
    jid = seeded(server, page)
    before = units(base, jid, 30)
    lst = first_list(base, jid)
    turn_into_paragraph(page, lst["id"], per_item=True)
    rows = units(base, jid, 30)
    got = [r for r in rows if r["type"] == "paragraph" and r["id"] in lst.get("item_ids", [])]
    assert len(got) == len(lst["item_ids"]) == 4
    assert "Analysemodell" in got[0]["clean"] and "Dissens" in got[3]["clean"]
    assert lst["id"] not in [r["id"] for r in rows]  # the list row is gone, its four items stand alone


def test_two_blocks_merge_into_one_paragraph(server, page):
    """A paragraph and the next one (any kind) become one paragraph."""
    base = server["base"]
    jid = seeded(server, page)
    rows = units(base, jid, 30)
    start = next(i for i, r in enumerate(rows) if r["type"] == "heading" and "Die Linguistik im Feld" in (r["clean"] or r["text"]))
    para = rows[start + 1]
    assert para["type"] == "paragraph"
    nxt = next(r for r in rows[start + 2 :] if r["depth"] == para["depth"] and r["type"] != "list_item")
    ids = [para["id"], nxt["id"]]
    panel = open_edit(page, para["id"])
    panel.get_by_test_id("turn-kind").select_option("to_paragraph")
    panel.get_by_test_id("turn-count").fill("2")
    panel.get_by_test_id("turn-check").click()
    confirm(page, para["id"])
    after = units(base, jid, 30)
    merged = next(r for r in after if r["id"] == para["id"])
    assert merged["type"] == "paragraph" and nxt["id"] not in [r["id"] for r in after]  # the next block is part of it
    assert "Verhältnis von fachlicher Disziplinarität sowie Trans-, Inter-, Multi- und XDisziplinarität" in merged["clean"]
