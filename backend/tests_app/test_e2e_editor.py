"""Browser test of the Review/Browse editor on a real book (PULSE, 120 pages), run on a
separate test app instance (port 8779, never the office app on 8777).

* ``test_pulse_box_this_block_and_what_follows`` / ``test_pulse_box_this_block_only``: page 19,
  "WHAT YOU WILL LEARN IN THIS CHAPTER?" and its list become a box, with each scope. The page
  is updated in place (no reload, same page, zoom and scroll), the preview shows the heading
  changes, the Chapters panel follows, Undo works, and the export is valid (DTD 0, EPUBCheck 0,
  lossless 0 missing / 0 extra).
* ``test_every_change_type_in_the_browser``: every element change applied from the Change
  element dialog on PULSE pages, then one export: DTD 0, EPUBCheck 0, lossless 0/0.

The PULSE publication (a converted book folder) comes from $BOOK_PULSE_PUBLICATION or
.cache/e2e/pulse/book-*; the PDF from $BOOK_PULSE_PDF or the publication's job folder. Skipped
when Chrome or the book is not on this machine."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
playwright = pytest.importorskip("playwright.sync_api")
CHROME = os.environ.get("BOOK_APP_CHROME", "/usr/bin/google-chrome")
PORT = int(os.environ.get("BOOK_EDITOR_TEST_PORT", "8779"))
CACHE = ROOT / ".cache" / "e2e" / "pulse"
PUB = Path(os.environ.get("BOOK_PULSE_PUBLICATION") or next(iter(sorted(CACHE.glob("book-*/"))), CACHE))
PDF = Path(os.environ.get("BOOK_PULSE_PDF", CACHE / "pulse.pdf"))
pytestmark = [
    pytest.mark.skipif(not Path(CHROME).exists(), reason="Chrome is not installed"),
    pytest.mark.skipif(not (PUB / "book.json").is_file() or not PDF.is_file(),
                       reason="the PULSE publication is not on this machine"),  # fmt: skip
]
assert PORT != 8777, "the editor test never runs on the office app's port"


@pytest.fixture
def server(tmp_path):
    settings = tmp_path / "app_settings.yaml"
    settings.write_text(f"port: {PORT}\nbind_address: 127.0.0.1\ndata_folder: {tmp_path / 'data'}\n")
    env = {**os.environ, "PYTHONPATH": str(BACKEND / "src") + os.pathsep + str(BACKEND),
           "BOOK_APP_SETTINGS": str(settings)}  # fmt: skip
    proc = subprocess.Popen([sys.executable, "-B", "-m", "book_app"], env=env, cwd=tmp_path,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)  # fmt: skip
    base = f"http://127.0.0.1:{PORT}"
    for _ in range(150):
        try:
            if requests.get(base + "/api/health", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError(proc.stdout.read().decode())
    yield {"base": base, "data": tmp_path / "data"}
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def page(server):
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = browser.new_context(viewport={"width": 1366, "height": 900}).new_page()
        pg.set_default_timeout(60000)
        problems = []
        pg.on("pageerror", lambda e: problems.append(str(e)))
        yield pg
        browser.close()
        assert not problems, problems


def seeded_job(server, pg):
    """The PULSE publication as a converted job; profile jaypee_v4 (DocBook and ePub), parts
    and details confirmed; the browser on the review screen as reviewer 'Tester'."""
    base = server["base"]
    jid = requests.put(base + "/api/jobs?filename=PULSE.pdf", data=PDF.read_bytes()).json()["id"]
    folder = server["data"] / "jobs" / jid
    shutil.copytree(PUB, folder / "converter_out" / PUB.name, symlinks=True)
    final = json.loads((PUB / "manifest.json").read_text())["final_key"]  # the page records
    shutil.copytree(PUB.parent / final, folder / "converter_out" / final, symlinks=True)
    state = json.loads((folder / "job.json").read_text())
    state.update(state="converted", publication=f"converter_out/{PUB.name}")
    (folder / "job.json").write_text(json.dumps(state))
    assert requests.put(f"{base}/api/jobs/{jid}/profile", json={"ref": "jaypee_v4"}).ok
    guess = requests.get(f"{base}/api/jobs/{jid}/parts").json()["parts"]
    assert requests.put(f"{base}/api/jobs/{jid}/parts", json={"parts": guess, "who": "Tester"}).ok
    details = requests.get(f"{base}/api/jobs/{jid}/details").json()["details"]
    assert requests.put(f"{base}/api/jobs/{jid}/details", json=details).ok
    pg.goto(f"{base}/#/job/{jid}/review?mode=browse&page=19")
    pg.get_by_test_id("who").fill("Tester")
    pg.get_by_test_id("browse-list").locator("[data-testid=unit]").first.wait_for(timeout=180000)
    return jid


def units(base, jid, number):
    return requests.get(f"{base}/api/jobs/{jid}/pages/{number}/units").json()["units"]


def go_page(pg, number):
    pg.get_by_test_id("page-no").fill(str(number))
    pg.get_by_test_id("page-no").press("Enter")
    pg.wait_for_function(
        f"() => document.querySelector('[data-testid=page-no]').value === '{number}'"
        " && document.querySelectorAll('[data-testid=unit]').length > 0"
    )
    time.sleep(0.5)


def select(pg, ids):
    for uid in ids:
        pg.locator(f"[data-testid=unit][data-unit='{uid}'] [data-testid=select]").first.check()


def change(pg, kind, scope="block", target=None, columns=None, level=None):
    """Open the dialog for the selected units, choose the change, preview it, save it."""
    pg.get_by_test_id("change-element").click()
    pg.get_by_test_id("change-kind").select_option(kind)
    if target:
        pg.get_by_test_id("change-target").locator("option").first.wait_for(state="attached")
        pg.wait_for_function("() => document.querySelector('[data-testid=change-target]').options.length > 0"
                             " && document.querySelector('[data-testid=change-target]').value !== ''")  # fmt: skip
    if columns:
        pg.get_by_test_id("change-columns").fill(str(columns))
    if level:
        pg.get_by_test_id("change-level").select_option(str(level))
    pg.get_by_test_id(f"scope-{scope}").check()
    pg.get_by_test_id("change-preview-btn").click()
    pg.get_by_test_id("change-preview").locator("[data-testid=preview-page]").first.wait_for()
    preview = pg.get_by_test_id("change-preview").inner_text()
    pg.get_by_test_id("change-save").scroll_into_view_if_needed()
    pg.evaluate("() => { window.__yBeforeSave = window.scrollY; }")
    pg.get_by_test_id("change-save").click()
    pg.get_by_test_id("change-dialog").wait_for(state="detached")
    return preview


def learn_box_ids(base, jid):
    rows = units(base, jid, 19)
    start = next(i for i, r in enumerate(rows) if (r["text"] or "").upper().startswith("WHAT YOU WILL LEARN"))
    ids = [rows[start]["id"]]
    for r in rows[start + 1 :]:
        if r["type"] == "heading" or r["depth"] != rows[start]["depth"]:
            if r["type"] == "heading":
                break
            continue  # the items inside the list follow their list
        ids.append(r["id"])
    return ids


def export_checked(server, pg, jid):
    """Export DocBook and ePub from the Export screen; DTD, EPUBCheck and lossless from the
    export record."""
    base = server["base"]
    pg.goto(f"{base}/#/job/{jid}/export")
    pg.get_by_test_id("export-format").select_option("all")
    pg.get_by_test_id("export-run").click()
    blocked = pg.get_by_test_id("blocked")
    done = "document.querySelector('[data-testid=qc]') && document.querySelector('[data-testid=epub-result]')"
    pg.wait_for_function(f"() => document.querySelector('[data-testid=blocked]') || ({done})",
                         timeout=900000)  # fmt: skip
    if blocked.count():
        pg.get_by_test_id("override").check()
        pg.get_by_test_id("export-run").click()
        pg.wait_for_function(f"() => {done}", timeout=900000)
    n = requests.get(f"{base}/api/jobs/{jid}/exports").json()["exports"][-1]["n"]
    r = requests.get(f"{base}/api/jobs/{jid}/exports/{n}").json()
    dtd = r["qc"]["dtd"].get("errors")
    lossless = r["qc"]["lossless"]
    epub = r["epub_qc"]["epubcheck"]
    epub_errors = epub.get("errors", epub.get("fatal", 0)) if isinstance(epub, dict) else epub
    assert dtd == 0, r["qc"]["dtd"]
    assert epub_errors == 0, epub
    cov = lossless.get("coverage", lossless)
    assert cov.get("missing", 0) == 0 and cov.get("extra", 0) == 0, lossless
    return r


def nesting(server, jid):
    """The section titles directly inside the chapter that holds page 19, from the export."""
    from lxml import etree

    base = server["base"]
    n = requests.get(f"{base}/api/jobs/{jid}/exports").json()["exports"][-1]["n"]
    folder = server["data"] / "jobs" / jid / "exports" / f"{n:03d}"
    parser = etree.XMLParser(load_dtd=False, resolve_entities=False, no_network=True)
    chapter = next(
        c
        for path in sorted((folder / "out").rglob("*.xml")) if "report" not in path.parts
        for c in etree.parse(str(path), parser).iter("chapter")
        if c.find("title") is not None and "Knobology" in " ".join(c.find("title").itertext())
    )
    return [" ".join(" ".join(s.find("title").itertext()).split()).upper()
            for s in chapter.findall("section")]  # fmt: skip


def box_learn(server, pg, jid, scope):
    base = server["base"]
    pg.get_by_test_id("zoom-in").click()
    pg.evaluate("() => { window.__noReload = 1; }")
    ids = learn_box_ids(base, jid)
    select(pg, ids)
    preview = change(pg, "box", scope)
    # the page was updated in place: no reload, same page, same zoom, same scroll position
    assert pg.evaluate("() => window.__noReload") == 1
    assert pg.get_by_test_id("page-no").input_value() == "19"
    assert abs(pg.evaluate("() => window.scrollY - window.__yBeforeSave")) < 5
    pg.locator("[data-testid=unit][data-type=box]").first.wait_for()
    assert pg.locator(f"[data-testid=unit][data-unit='{ids[0]}']").first.get_attribute("data-type") == "heading"
    pg.get_by_test_id("chapters-panel").wait_for()
    return preview


def test_pulse_box_this_block_and_what_follows(server, page):
    pg = page
    jid = seeded_job(server, pg)
    preview = box_learn(server, pg, jid, "follow")
    assert "WHAT YOU WILL LEARN" in preview and "sidebar_title" in preview
    # Apply to all similar: the same heading of every chapter, listed with its page
    pg.get_by_test_id("similar-find").click()
    pg.get_by_test_id("similar-apply").wait_for()
    picks = pg.get_by_test_id("similar-pick")
    pages = [int(picks.nth(i).get_attribute("data-page")) for i in range(picks.count())]
    assert len(pages) >= 5 and 25 in pages, pages
    picks.nth(len(pages) - 1).uncheck()  # the reviewer leaves one as it is
    pg.get_by_test_id("similar-apply").click()
    pg.get_by_test_id("similar-panel").wait_for(state="detached")
    base = server["base"]
    edits = requests.get(f"{base}/api/jobs/{jid}/decisions").json()["edits"]
    group = [e for e in edits if e.get("group")]
    assert len(group) == len(pages) - 1 and all(e["scope"] == "follow" and e["op"] == "box" for e in group)
    boxed = {p for p in pages[:-1] if any(r["type"] == "box" for r in units(base, jid, p))}
    assert boxed == set(pages[:-1]) and not any(r["type"] == "box" for r in units(base, jid, pages[-1]))
    export_checked(server, pg, jid)
    sections = nesting(server, jid)
    assert sections[0].startswith("INTRODUCTION") and any(s.startswith("CONCLUSION") for s in sections), sections
    assert not any(s.startswith("WHAT YOU WILL LEARN") for s in sections)
    # One Undo takes back the whole group (the first change and the repeated ones)
    pg.goto(f"{server['base']}/#/job/{jid}/review?mode=browse&page=19")
    pg.locator("[data-testid=unit][data-type=box]").first.wait_for()
    pg.locator("[data-testid=history] summary").click()
    pg.get_by_test_id("undo-group").first.click()
    pg.locator("[data-testid=unit][data-type=box]").first.wait_for(state="detached")
    assert requests.get(f"{base}/api/jobs/{jid}/decisions").json()["edits"] == []
    assert not any(r["type"] == "box" for p in pages for r in units(base, jid, p))


def test_pulse_box_this_block_only(server, page):
    pg = page
    jid = seeded_job(server, pg)
    base = server["base"]
    before = {r["id"]: (r["level"], r["role"]) for p in range(19, 31) for r in units(base, jid, p)
              if r["type"] == "heading"}  # fmt: skip
    preview = box_learn(server, pg, jid, "block")
    after = {r["id"]: (r["level"], r["role"]) for p in range(19, 31) for r in units(base, jid, p)
             if r["type"] == "heading"}  # fmt: skip
    changed = {k for k in before if before[k] != after.get(k)}
    assert len(changed) == 1  # only the boxed heading (now the box title) changed
    assert preview.count("level") >= 1 and "no longer a heading" not in preview
    export_checked(server, pg, jid)
    sections = nesting(server, jid)
    assert sections and not any(s.startswith("WHAT YOU WILL LEARN") for s in sections), sections


def paragraph_runs(base, jid, pages, n):
    """Runs of n consecutive top-level paragraphs on one page (each used once, at most two
    per page)."""
    for number in pages:
        rows = [r for r in units(base, jid, number) if r["depth"] == 0]
        i = found = 0
        while i <= len(rows) - n and found < 2:
            w = rows[i : i + n]
            if all(r["type"] == "paragraph" and len(r["text"] or "") > 20 for r in w):
                yield number, [r["id"] for r in w]
                found += 1
                i += n + 1
            else:
                i += 1


def test_every_change_type_in_the_browser(server, page):
    pg = page
    jid = seeded_job(server, pg)
    base = server["base"]
    runs = paragraph_runs(base, jid, range(20, 120), 2)
    done = []

    def on(kind, n=2, **kw):
        number, ids = next(runs)
        go_page(pg, number)
        select(pg, ids[:n])
        change(pg, kind, **kw)
        done.append(kind)
        return number, ids

    on("list_bulleted")
    on("list_numbered")
    on("box")
    on("box_plain")
    on("quote", 1)
    on("pull_quote", 1)
    on("footnote", 1)
    on("chapter_authors", 1)
    on("table_make", 2, columns=2)
    on("bibliography")
    on("index_entries")
    on("not_running_head", 1)
    on("not_folio", 1)
    on("not_production_mark", 1)
    on("merge", 2)
    on("move_down", 1)
    # a caption of a figure and a note of a table on a page that has one
    for number in range(20, 120):
        rows = units(base, jid, number)
        fig = next((r for r in rows if r["type"] == "figure"), None)
        para = next((r for r in rows if r["type"] == "paragraph" and r["depth"] == 0), None)
        if fig and para:
            go_page(pg, number)
            select(pg, [para["id"]])
            change(pg, "caption", target=True)
            done.append("caption")
            break
    for number in range(20, 120):
        rows = units(base, jid, number)
        tbl = next((r for r in rows if r["type"] == "table"), None)
        paras = [r for r in rows if r["type"] == "paragraph" and r["depth"] == 0]
        if tbl and len(paras) >= 2:
            go_page(pg, number)
            select(pg, [paras[0]["id"]])
            change(pg, "table_note", target=True)
            done.append("table_note")
            break
    # swap columns: the second block of a page is read first
    number, ids = next(runs)
    go_page(pg, number)
    rows = [r for r in units(base, jid, number) if r["depth"] == 0]
    select(pg, [rows[1]["id"]])
    change(pg, "swap_columns")
    done.append("swap_columns")
    # a list item one level in, then out again
    for number in range(20, 120):
        rows = units(base, jid, number)
        items = [r for r in rows if r["type"] == "list_item" and r["depth"] == 1]
        items = next(([a, b] for a, b in zip(items, items[1:]) if a["parent"] == b["parent"]), [])
        if len(items) >= 2:
            go_page(pg, number)
            select(pg, [items[1]["id"]])
            change(pg, "list_in")
            done.append("list_in")
            select(pg, [items[1]["id"]])
            change(pg, "list_out")
            done.append("list_out")
            break
    # MCQ: a question line and its lettered list (page 25); glossary: "Term: text" lines (46)
    rows = units(base, jid, 25)
    k = next(i for i, r in enumerate(rows) if (r["text"] or "").upper().startswith("WHAT YOU WILL LEARN"))
    stem, options = rows[k], next(r for r in rows[k + 1 :] if r["type"] == "list")
    go_page(pg, 25)
    select(pg, [stem["id"], options["id"]])
    change(pg, "question")
    done.append("question")
    assert any(r["type"] == "question_set" for r in units(base, jid, 25))
    rows = [r for r in units(base, jid, 46) if r["depth"] == 0]
    terms = [r for r in rows if r["type"] == "paragraph" and re.match(r"^[A-Z][\w ]{2,30}:\s", r["text"] or "")]
    go_page(pg, 46)
    select(pg, [t["id"] for t in terms[:2]])
    change(pg, "glossary")
    done.append("glossary")
    # a run without lettered options is refused, plainly
    number, ids = next(runs)
    go_page(pg, number)
    select(pg, ids)
    pg.get_by_test_id("change-element").click()
    pg.get_by_test_id("change-kind").select_option("question")
    pg.get_by_test_id("change-preview-btn").click()
    pg.get_by_test_id("change-dialog").get_by_test_id("error").wait_for()
    assert "option" in pg.get_by_test_id("change-dialog").get_by_test_id("error").inner_text()
    pg.get_by_test_id("change-cancel").click()
    edits = requests.get(f"{base}/api/jobs/{jid}/decisions").json()["edits"]
    assert len(edits) == len(done), (len(edits), done)
    assert {e["who"] for e in edits} == {"Tester"}  # every change is in the audit log
    export_checked(server, pg, jid)
