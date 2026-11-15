"""Browser test of the Browse editor (one line per block, one Edit per block, preview -> Confirm,
Undo) on a real book (PULSE, 120 pages), run on a separate test app instance (a free port;
never the office app on 8777).

* ``test_pulse_box_this_block_and_what_follows`` / ``test_pulse_box_this_block_only``: page 19,
  "WHAT YOU WILL LEARN IN THIS CHAPTER?" and its list become a box, with each scope. The page
  is updated in place (no reload, same page, zoom and scroll), the preview shows the heading
  changes, the Chapters panel follows, Undo works, and the export is valid (DTD 0, EPUBCheck 0,
  lossless 0 missing / 0 extra).
* ``test_every_change_type_in_the_browser``: every element change applied from the Change
  element dialog on PULSE pages, then one export: DTD 0, EPUBCheck 0, lossless 0/0.

The PULSE publication (a converted book folder) comes from $BOOK_PULSE_PUBLICATION or
.cache/e2e/pulse/book-*; the PDF from $BOOK_PULSE_PDF or .cache/e2e/pulse/pulse.pdf. To set it up
copy a converted PULSE job's ``converter_out/*`` (the book-* folder and the folder named by its
manifest ``final_key``) and its ``input.pdf`` (as pulse.pdf) there. Skipped when Chrome or the
book is not on this machine."""

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
PORT = int(os.environ.get("BOOK_EDITOR_TEST_PORT", "0"))  # 0: any free port
CACHE = ROOT / ".cache" / "e2e" / "pulse"
PUB = Path(os.environ.get("BOOK_PULSE_PUBLICATION") or next(iter(sorted(CACHE.glob("book-*/"))), CACHE))
PDF = Path(os.environ.get("BOOK_PULSE_PDF", CACHE / "pulse.pdf"))
pytestmark = [
    pytest.mark.skipif(not Path(CHROME).exists(), reason="Chrome is not installed"),
    pytest.mark.skipif(not (PUB / "book.json").is_file() or not PDF.is_file(),
                       reason="the PULSE publication is not on this machine"),  # fmt: skip
]
assert PORT != 8777, "the editor test never runs on the office app's port"


def _port() -> int:
    """A port nothing listens on: the test must never talk to somebody else's running app."""
    import socket

    with socket.socket() as s:
        if PORT:
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                raise RuntimeError(f"port {PORT} is already in use by another app")
            return PORT
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
# EPUBCheck: $EPUBCHECK_JAR, else the jar the main checkout has downloaded (read-only), else not run.
EPUBCHECK = next(iter(sorted((ROOT.parent / "pdf_book_converter" / ".cache" / "tools" / "epubcheck").glob("*/epubcheck.jar"))), None)
JAR = Path(os.environ["EPUBCHECK_JAR"]) if os.environ.get("EPUBCHECK_JAR") else EPUBCHECK
SIGNED_IN = ("try { if (!localStorage.getItem('role')) { localStorage.setItem('reviewer', 'Tester');"
             " localStorage.setItem('role', 'manager'); } } catch (e) {}")  # a manager is signed in



@pytest.fixture
def server(tmp_path):
    port = _port()
    settings = tmp_path / "app_settings.yaml"
    settings.write_text(f"port: {port}\nbind_address: 127.0.0.1\ndata_folder: {tmp_path / 'data'}\n")
    env = {**os.environ, "PYTHONPATH": str(BACKEND / "src") + os.pathsep + str(BACKEND),
           "BOOK_APP_SETTINGS": str(settings),
           **({"EPUBCHECK_JAR": str(JAR)} if JAR and JAR.is_file() else {})}  # fmt: skip
    proc = subprocess.Popen([sys.executable, "-B", "-m", "book_app"], env=env, cwd=tmp_path,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)  # fmt: skip
    base = f"http://127.0.0.1:{port}"
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
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        ctx.add_init_script(SIGNED_IN)
        pg = ctx.new_page()
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
    pg.get_by_test_id("browse-page-no").fill(str(number))
    pg.get_by_test_id("browse-page-no").press("Enter")
    pg.wait_for_function(
        f"() => document.querySelector('[data-testid=browse-page-no]').value === '{number}'"
        " && document.querySelectorAll('[data-testid=unit]').length > 0"
    )
    time.sleep(0.5)


def open_edit(pg, uid):
    """The Edit panel of one block (the list row for a list item)."""
    row = pg.locator(f"[data-testid=unit][data-unit='{uid}']").first
    row.scroll_into_view_if_needed()
    if row.get_by_test_id("edit-panel").count() == 0:
        row.get_by_test_id("edit-block").click()
    return row.get_by_test_id("edit-panel")


def confirm(pg, uid=None):
    """The one-line preview is shown, then Confirm saves; returns the preview text."""
    pg.get_by_test_id("preview-line").wait_for()
    preview = pg.get_by_test_id("preview-line").inner_text()
    pg.evaluate("() => { window.__topBefore = document.querySelector('[data-testid=unit]').getBoundingClientRect().top; }")  # the first block on the page
    pg.get_by_test_id("confirm-save").click()
    pg.get_by_test_id("edit-panel").wait_for(state="detached")  # the panel closes once it is saved
    time.sleep(0.5)
    return preview


def change(pg, kind, ids, scope="block", target=False, columns=None, item=None, direction=None):
    """Open the Edit panel of ids[0], choose the change (for the next len(ids) blocks), preview
    it, confirm it."""
    panel = open_edit(pg, ids[0])
    if kind == "merge":
        panel.get_by_test_id("merge").click()
    elif kind in ("move_up", "move_down"):
        panel.get_by_test_id(kind.replace("_", "-")).click()
    elif kind == "swap_columns":
        panel.get_by_test_id("swap-columns").click()
    elif kind in ("list_in", "list_out"):
        panel.get_by_test_id("item").select_option(item)
        panel.get_by_test_id("dir").select_option(kind[5:])
        panel.get_by_test_id("list-level").click()
    else:
        panel.get_by_test_id("turn-kind").select_option(kind)
        if target:
            pg.wait_for_function("() => document.querySelector('[data-testid=turn-target]').options.length > 0"
                                 " && document.querySelector('[data-testid=turn-target]').value !== ''")  # fmt: skip
        if columns:
            panel.get_by_test_id("turn-columns").fill(str(columns))
        if not target and kind not in ("footnote",):
            panel.get_by_test_id("turn-count").fill(str(len(ids)))
        panel.get_by_test_id("turn-scope").select_option(scope)
        panel.get_by_test_id("turn-check").click()
    return confirm(pg, ids[0])


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
    pg.get_by_test_id("export-all").click()  # "Export all formats"
    blocked = pg.get_by_test_id("blocked")
    done = ("document.querySelector('[data-testid=verdict]')"
            " && document.querySelector('[data-testid=export-progress]').textContent === ''")  # every format finished
    pg.wait_for_function(f"() => document.querySelector('[data-testid=blocked]') || ({done})",
                         timeout=900000)  # fmt: skip
    if blocked.count():
        pg.get_by_test_id("override").check()
        pg.get_by_test_id("export-all").click()
        pg.wait_for_function(f"() => {done}", timeout=900000)
    n = requests.get(f"{base}/api/jobs/{jid}/exports").json()["exports"][-1]["n"]
    r = requests.get(f"{base}/api/jobs/{jid}/exports/{n}").json()
    dtd = r["qc"]["dtd"].get("errors")
    lossless = r["qc"]["lossless"]
    epub = r["epub_qc"]["epubcheck"]
    epub_errors = epub.get("errors", epub.get("fatal", 0)) if isinstance(epub, dict) else epub
    assert dtd == 0, r["qc"]["dtd"]
    assert epub_errors == 0, epub
    if JAR and JAR.is_file():
        assert epub.get("status") == "run", epub  # EPUBCheck really ran
    cov = lossless.get("coverage", lossless)
    assert cov.get("missing", 0) == 0 and cov.get("extra", 0) == 0, lossless
    return r


def nesting(server, jid, deep=False):
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
    found = chapter.iter("section") if deep else chapter.findall("section")  # deep: at any depth
    return [" ".join(" ".join(s.find("title").itertext()).split()).upper()
            for s in found if s.find("title") is not None]  # fmt: skip


def headings(base, jid, first=19, last=120):
    """Every heading of the book from page `first`, in reading order: (id, text, level, role)."""
    out = []
    for number in range(first, last + 1):
        out += [(r["id"], " ".join((r["text"] or "").split()), r["level"], r["role"])
                for r in units(base, jid, number) if r["type"] == "heading"]  # fmt: skip
    return out


def box_learn(server, pg, jid, scope):
    base = server["base"]
    pg.get_by_test_id("browse-zoom-in").click()
    pg.evaluate("() => { window.__noReload = 1; }")
    ids = learn_box_ids(base, jid)
    # What the old Change dialog showed for this exact change: the server's preview of the edit.
    edit = {"op": "box", "units": ids, "kind": "box", "title": True, "scope": scope}
    want = requests.post(f"{base}/api/jobs/{jid}/edits/preview", json={"edit": edit}).json()["headings"]
    before = headings(base, jid)
    preview = change(pg, "box", ids, scope)
    after = headings(base, jid)
    box_learn.relevelled = want
    gone = {h[0] for h in before} - {h[0] for h in after}  # the boxed heading is now the box title
    assert gone <= {ids[0]}, gone
    # order is kept; each heading the preview named has exactly the level and role it showed
    assert [h[0] for h in before if h[0] not in gone] == [h[0] for h in after]
    now = {h[0]: h for h in after}
    named = {}
    for w in want:
        hit = [h for h in before if h[1].startswith(" ".join(w["text"].split())[:30])]
        assert hit, w
        named[hit[0][0]] = w
    for hid, w in named.items():
        if w["after"] is None:
            assert hid not in now, w
        else:
            assert (now[hid][2], now[hid][3]) == (w["after"]["level"], w["after"]["role"]), (w, now[hid])
    # every other heading kept its level; with "and what follows" no level is skipped
    unchanged = {h[0]: h for h in before if h[0] not in named and h[0] in now}
    assert all((now[k][2], now[k][3]) == (v[2], v[3]) for k, v in unchanged.items())
    if scope == "follow":
        assert want, "the follow scope re-levels the headings after the box"
        def skips(hs):  # pairs of neighbouring headings where the level jumps by more than one
            hs = [h for h in hs if h[3] != "feature_title"]
            return {(a[0], b[0]) for a, b in zip(hs, hs[1:]) if b[2] > a[2] + 1}
        assert skips(after) <= skips(before), skips(after) - skips(before)  # (the book has its own skips)
    # the page was updated in place: no reload, same page, same zoom, the block stays where it was on screen
    assert pg.evaluate("() => window.__noReload") == 1
    assert pg.get_by_test_id("browse-page-no").input_value() == "19"
    top = pg.evaluate("() => document.querySelector('[data-testid=unit]').getBoundingClientRect().top")
    assert abs(top - pg.evaluate("() => window.__topBefore")) < 5  # a block above the change did not move on screen
    pg.locator("[data-testid=unit][data-type=box]").first.wait_for()
    assert pg.locator(f"[data-testid=unit][data-unit='{ids[0]}']").first.get_attribute("data-type") == "heading"
    pg.get_by_test_id("chapters-panel").wait_for()
    # the screen saved exactly the change the old Change dialog saved: one "box" with a title
    saved = requests.get(f"{base}/api/jobs/{jid}/decisions").json()["edits"][-1]
    assert {k: saved.get(k) for k in ("op", "units", "kind", "title", "scope")} == {
        "op": "box", "units": ids, "kind": "box", "title": True, "scope": scope}, saved  # fmt: skip
    return preview


def test_pulse_box_this_block_and_what_follows(server, page):
    pg = page
    jid = seeded_job(server, pg)
    preview = box_learn(server, pg, jid, "follow")
    assert "WHAT YOU WILL LEARN" in preview.upper() and "Box" in preview, preview
    # Apply to all similar: the same heading of every chapter, listed with its page
    pg.get_by_test_id("similar-open").click()
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
    assert sections[0].startswith("INTRODUCTION"), sections
    everything = nesting(server, jid, deep=True)  # how deep each heading sits depends on the book's own levels
    assert any(s.startswith("CONCLUSION") for s in everything), everything  # no section was lost
    assert not any(s.startswith("WHAT YOU WILL LEARN") for s in everything)
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
    assert "level" in preview and "no longer" not in preview
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
        change(pg, kind, ids[:n], **kw)
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
            change(pg, "caption", [para["id"]], target=True)
            done.append("caption")
            break
    for number in range(20, 120):
        rows = units(base, jid, number)
        tbl = next((r for r in rows if r["type"] == "table"), None)
        paras = [r for r in rows if r["type"] == "paragraph" and r["depth"] == 0]
        if tbl and len(paras) >= 2:
            go_page(pg, number)
            change(pg, "table_note", [paras[0]["id"]], target=True)
            done.append("table_note")
            break
    # swap columns: the second block of a page is read first
    number, ids = next(runs)
    go_page(pg, number)
    rows = [r for r in units(base, jid, number) if r["depth"] == 0]
    change(pg, "swap_columns", [rows[1]["id"]])
    done.append("swap_columns")
    # a list item one level in, then out again
    for number in range(20, 120):
        rows = units(base, jid, number)
        items = [r for r in rows if r["type"] == "list_item" and r["depth"] == 1]
        items = next(([a, b] for a, b in zip(items, items[1:]) if a["parent"] == b["parent"]), [])
        if len(items) >= 2:
            go_page(pg, number)
            change(pg, "list_in", [items[1]["parent"]], item=items[1]["id"])  # on the list's Edit panel
            done.append("list_in")
            change(pg, "list_out", [items[1]["parent"]], item=items[1]["id"])
            done.append("list_out")
            break
    # MCQ: a question line and its lettered list (page 25); glossary: "Term: text" lines (46)
    rows = units(base, jid, 25)
    k = next(i for i, r in enumerate(rows) if (r["text"] or "").upper().startswith("WHAT YOU WILL LEARN"))
    stem, options = rows[k], next(r for r in rows[k + 1 :] if r["type"] == "list")
    go_page(pg, 25)
    change(pg, "question", [stem["id"], options["id"]])
    done.append("question")
    assert any(r["type"] == "question_set" for r in units(base, jid, 25))
    rows = [r for r in units(base, jid, 46) if r["depth"] == 0]
    terms = [r for r in rows if r["type"] == "paragraph" and re.match(r"^[A-Z][\w ]{2,30}:\s", r["text"] or "")]
    go_page(pg, 46)
    pair = next(([a, b] for a, b in zip(rows, rows[1:]) if a in terms and b in terms), terms[:1])  # next to each other
    change(pg, "glossary", [t["id"] for t in pair])
    done.append("glossary")
    # a run without lettered options is refused, plainly
    number, ids = next(runs)
    go_page(pg, number)
    panel = open_edit(pg, ids[0])
    panel.get_by_test_id("turn-kind").select_option("question")
    panel.get_by_test_id("turn-count").fill(str(len(ids)))
    panel.get_by_test_id("turn-check").click()
    panel.get_by_test_id("error").wait_for()
    assert "option" in panel.get_by_test_id("error").inner_text()
    assert pg.get_by_test_id("confirm-save").count() == 0  # nothing to confirm: it was refused
    pg.keyboard.press("Escape")
    edits = requests.get(f"{base}/api/jobs/{jid}/decisions").json()["edits"]
    assert len(edits) == len(done), (len(edits), done)
    assert {e["who"] for e in edits} == {"Tester"}  # every change is in the audit log
    export_checked(server, pg, jid)
