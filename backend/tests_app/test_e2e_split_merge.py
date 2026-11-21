"""Browser test of "Split here", multi-select merge and "join with previous" in Browse, on a real
book (Ophthalmology Clinics-2, 464 pages), on a separate test app instance (a free port; never the
office app on 8777), signed in as a *reviewer*.

* split a paragraph at a word (click "Split", click the word, preview, Confirm) and Undo (Ctrl+Z);
  Alt+click on a word splits at once and Undo (U) takes it back;
* three blocks across a page break are picked (Ctrl+click on one page, the pick stays when the
  page turns), M merges them into one paragraph;
* J joins the first block of another page with the last one of the page before;
* one export with those changes: lossless 0 missing / 0 extra; then Undo each change.

Pages are found at run time (a paragraph cut by a page break: the last block of a page is a
paragraph that does not end a sentence, the first block of the next one starts in lower case).
The job folder comes from $BOOK_SPLIT_JOB or the main checkout's app_data (read-only: the converter
output is linked, not copied); skipped when Chrome or the job is not on this machine."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

import pytest
import requests

from .test_e2e_editor import CHROME, ROOT, go_page, playwright, server  # noqa: F401

JOB = Path(os.environ.get("BOOK_SPLIT_JOB") or ROOT.parent / "pdf_book_converter" / "app_data" / "jobs" / "c517e2e5c7534523")
pytestmark = [
    pytest.mark.skipif(not Path(CHROME).exists(), reason="Chrome is not installed"),
    pytest.mark.skipif(not (JOB / "job.json").is_file(), reason="the Ophthalmology job is not on this machine"),
]
REVIEWER = ("try { localStorage.setItem('reviewer', 'Tester'); localStorage.setItem('role', 'reviewer'); localStorage.setItem('tourSeen:tester', '1'); } catch (e) {}")


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


def api(base, path, **kw):
    """GET that waits while the app says "preparing" (202)."""
    for _ in range(600):
        r = requests.get(base + path, **kw)
        if r.status_code != 202:
            r.raise_for_status()
            return r.json()
        time.sleep(1)
    raise TimeoutError(path)


def rows(base, jid, number):
    return [r for r in api(base, f"/api/jobs/{jid}/pages/{number}/units")["units"] if r["type"] != "page_marker"]


def seed(server):
    base = server["base"]
    jid = requests.put(base + "/api/jobs?filename=book.pdf", data=(JOB / "input.pdf").read_bytes()).json()["id"]
    folder = server["data"] / "jobs" / jid
    state = json.loads((JOB / "job.json").read_text())
    shutil.rmtree(folder / "converter_out", ignore_errors=True)
    (folder / "converter_out").symlink_to(JOB / "converter_out")  # read-only use: nothing is written there
    mine = json.loads((folder / "job.json").read_text())
    mine.update(state="converted", publication=state["publication"], profile=state["profile"])
    (folder / "job.json").write_text(json.dumps(mine))
    for name in ("parts.json", "parts_confirmed.json"):
        if (JOB / name).is_file():
            shutil.copy(JOB / name, folder / name)
    details = api(base, f"/api/jobs/{jid}/details")["details"]
    assert requests.put(f"{base}/api/jobs/{jid}/details", json=details).ok
    return jid, state["pages"]


def clean(r):
    return " ".join((r.get("clean") or r.get("text") or "").split())


def find_cuts(base, jid, pages, want):
    """Paragraphs cut by a page break: (page, [the two or three paragraphs]) for ``want`` of them,
    a page apart from each other; and one paragraph of 12+ words for the split."""
    cuts, splitter = [], None
    for n in range(2, pages):
        a, b = rows(base, jid, n - 1), rows(base, jid, n)
        if splitter is None and len(a) > 2:
            for r in a:
                if r["type"] == "paragraph" and len(clean(r).split()) >= 12 and r["id"] not in {x["id"] for x in b}:
                    splitter = (n - 1, r)
                    break
        if not a or not b or any(cuts and n - 1 <= c[0] + 1 for c in cuts):
            continue
        last, first = a[-1], b[0]
        if (last["type"] == first["type"] == "paragraph" and last["depth"] == first["depth"] and last["id"] != first["id"]
                and not re.search(r"[.!?:]\s*$", clean(last)) and clean(first)[:1].islower()
                and len(clean(first).split()) > 3 and len(clean(last).split()) > 3):
            cuts.append((n - 1, a, b))
        if len(cuts) >= want and splitter:
            break
    return cuts, splitter


def settle(check, timeout=60):
    """Wait until ``check()`` is true (the app saves in the background; a busy machine is slower)."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if check():
                return True
        except StopIteration:
            pass
        time.sleep(0.5)
    return False


def full(base, jid, uid):
    """The whole text of a block as the book reads it (a row carries only its first 600 characters)."""
    return " ".join(w["t"] for w in api(base, f"/api/jobs/{jid}/units/{uid}/words")["words"])


def word_xy(pg, uid, k):
    """Where the k-th word of a block's text is on the screen."""
    return pg.evaluate("""([uid, k]) => {
        const el = document.querySelector(`[data-testid=unit][data-unit='${uid}'] [data-testid=btext]`);
        el.scrollIntoView({ block: "center" });
        const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const nodes = []; let n;
        while ((n = w.nextNode())) nodes.push(n);
        const node = nodes[nodes.length - 1], text = node.textContent;
        const hit = [...text.matchAll(/\\S+/g)][k];
        const r = document.createRange(); r.setStart(node, hit.index + 1); r.setEnd(node, hit.index + 2);
        const b = r.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2];
    }""", [uid, k])


def test_split_merge_join_and_undo(server, page):
    base, pg = server["base"], page
    jid, pages = seed(server)
    cuts, splitter = find_cuts(base, jid, pages, 2)
    if len(cuts) < 2 or not splitter:
        pytest.skip("no paragraph cut by a page break found in this book")
    (pa, a_rows, b_rows), (pj, j_rows, k_rows) = cuts
    pg.goto(f"{base}/#/job/{jid}/review?mode=browse&page={splitter[0]}")
    pg.get_by_test_id("who").wait_for(timeout=600000)
    pg.get_by_test_id("who").fill("Tester")
    pg.get_by_test_id("browse-list").locator("[data-testid=unit]").first.wait_for(timeout=300000)
    unit = lambda uid: pg.locator(f"[data-testid=unit][data-unit='{uid}']").first  # noqa: E731

    # ---- 1. Split here: the Split button, the word, the preview, Confirm; Undo with Ctrl+Z
    sp_page, sp = splitter
    go_page(pg, sp_page)
    words = clean(sp).split()
    unit(sp["id"]).get_by_test_id("split-block").click()
    pg.get_by_test_id("split-word").nth(5).wait_for()
    assert pg.get_by_test_id("split-word").count() == len(words)  # one clickable word each
    pg.get_by_test_id("split-word").nth(5).click()
    pg.get_by_test_id("preview-line").wait_for()
    pg.get_by_test_id("confirm-save").click()
    pg.get_by_test_id("split-panel").wait_for(state="detached")
    assert settle(lambda: {" ".join(words[:5]), " ".join(words[5:])} <= {clean(r) for r in rows(base, jid, sp_page)})
    pg.keyboard.press("Control+z")
    assert settle(lambda: " ".join(words) in [clean(r) for r in rows(base, jid, sp_page)])
    assert " ".join(words[5:]) not in [clean(r) for r in rows(base, jid, sp_page)]

    # ---- 1b. Alt+click on a word splits at once; U takes it back
    x, y = word_xy(pg, sp["id"], 7)
    pg.keyboard.down("Alt")
    pg.mouse.click(x, y)
    pg.keyboard.up("Alt")
    assert settle(lambda: {" ".join(words[:7]), " ".join(words[7:])} <= {clean(r) for r in rows(base, jid, sp_page)})
    pg.mouse.click(5, 5)
    pg.keyboard.press("u")
    assert settle(lambda: " ".join(words) in [clean(r) for r in rows(base, jid, sp_page)])

    # ---- 2. Pick three blocks across a page break (Ctrl+click, Shift+click), M merges them
    a_prev = [r for r in a_rows if r["type"] == "paragraph" and r["depth"] == a_rows[-1]["depth"]]
    if len(a_prev) < 2 or a_prev[-2]["id"] == a_rows[-1]["id"] or a_rows.index(a_prev[-2]) != len(a_rows) - 2:
        a_prev = None
    last_a, first_b = a_rows[-1], b_rows[0]
    picked = [last_a, first_b] if not a_prev else [a_prev[-2], last_a, first_b]
    first_pick_before = full(base, jid, picked[0]["id"])
    before_text = " ".join(full(base, jid, r["id"]) for r in picked)
    go_page(pg, pa)
    unit(picked[0]["id"]).click(modifiers=["Control"], position={"x": 60, "y": 8})
    if len(picked) == 3:
        unit(last_a["id"]).click(modifiers=["Shift"], position={"x": 60, "y": 8})  # a range: both blocks
    assert pg.get_by_test_id("sel-count").inner_text().startswith(f"{len(picked) - 1} selected")
    go_page(pg, pa + 1)  # the pick stays when the page turns
    unit(first_b["id"]).click(modifiers=["Control"], position={"x": 60, "y": 8})
    assert pg.get_by_test_id("sel-count").inner_text().startswith(f"{len(picked)} selected")
    pg.mouse.click(5, 5)
    pg.keyboard.press("m")
    pg.get_by_test_id("sel-count").wait_for(state="hidden")
    flat = lambda t: re.sub(r"[\s\-­]", "", t)  # noqa: E731  a break hyphen goes, spaces differ
    assert settle(lambda: flat(full(base, jid, picked[0]["id"])) == flat(before_text))
    assert first_b["id"] not in {r["id"] for r in rows(base, jid, pa + 1)}

    # ---- 3. J: the first block of the next page joins the last block before it (no preview)
    last_j, first_k = j_rows[-1], k_rows[0]
    joined_before_last = full(base, jid, last_j["id"])
    joined = flat(full(base, jid, last_j["id"]) + full(base, jid, first_k["id"]))
    go_page(pg, pj + 1)
    unit(first_k["id"]).click(position={"x": 60, "y": 8})
    pg.keyboard.press("j")
    assert settle(lambda: flat(full(base, jid, last_j["id"])) == joined)
    assert first_k["id"] not in {r["id"] for r in rows(base, jid, pj + 1)}

    # ---- the audit log names who did what; the book stays whole (lossless 0 missing / 0 extra)
    edits = api(base, f"/api/jobs/{jid}/decisions")["edits"]
    assert [e["op"] for e in edits if e["op"] in ("split_word", "merge")].count("merge") == 2
    assert {e["who"] for e in edits} == {"Tester"}
    run = requests.post(f"{base}/api/jobs/{jid}/export/start", json={"formats": ["docbook"], "who": "Tester", "allow_alt_text_placeholders": True})
    assert run.ok, run.text
    for _ in range(1800):
        st = requests.get(f"{base}/api/jobs/{jid}/export/progress").json()
        if st["state"] != "running":
            break
        time.sleep(1)
    assert st["state"] == "done", st
    rec = requests.get(f"{base}/api/jobs/{jid}/exports/{st['n']}").json()
    cov = rec["qc"]["lossless"].get("coverage", rec["qc"]["lossless"])
    assert cov.get("missing", 0) == 0 and cov.get("extra", 0) == 0, rec["qc"]["lossless"]

    # ---- Undo each: J, then the merge
    pg.goto(f"{base}/#/job/{jid}/review?mode=browse&page={pj + 1}")
    pg.get_by_test_id("browse-list").locator("[data-testid=unit]").first.wait_for(timeout=300000)
    for _ in range(2):
        edits = api(base, f"/api/jobs/{jid}/decisions")["edits"]
        eid = [e for e in edits if e["op"] == "merge"][-1]["id"]
        requests.delete(f"{base}/api/jobs/{jid}/decisions/{eid}?who=Tester").raise_for_status()
    assert flat(full(base, jid, last_j["id"])) == flat(joined_before_last)
    assert flat(full(base, jid, picked[0]["id"])) == flat(first_pick_before)
    assert first_k["id"] in {r["id"] for r in rows(base, jid, pj + 1)} and first_b["id"] in {r["id"] for r in rows(base, jid, pa + 1)}
