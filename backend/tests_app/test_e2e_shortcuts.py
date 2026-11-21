"""Browser test: the shortcut strip (hide, remembered), the ? panel, the first-time tips (three
visits), the keys in the tooltips, the tour step, and "click a word + S" splits a block.
Uses the stand-in converter, so it needs only Chrome, on its own port."""

from __future__ import annotations

import time

import pytest
import requests

from tests_app.conftest import make_pdf

from .test_e2e_banner import CHROME, MANAGER, ok_server, playwright  # noqa: F401

pytestmark = pytest.mark.skipif(not __import__("pathlib").Path(CHROME).exists(), reason="Chrome is not installed")
SIGNED = "try { localStorage.setItem('reviewer','Asha'); localStorage.setItem('role','manager'); localStorage.setItem('tourSeen:asha','1'); } catch (e) {}"


def converted_job(server):
    job = requests.put(f"{server}/api/jobs?filename=Keys.pdf&profile=jaypee_v3", data=make_pdf(9), headers=MANAGER).json()["id"]
    assert requests.post(f"{server}/api/jobs/{job}/convert", headers=MANAGER).ok
    end = time.time() + 60
    while time.time() < end and requests.get(f"{server}/api/jobs/{job}").json()["state"] != "converted":
        time.sleep(0.3)
    return job


def find_para(server, job):
    """(page, row) of a paragraph of three words or more in the stand-in book."""
    for n in range(1, 10):
        rows = requests.get(f"{server}/api/jobs/{job}/pages/{n}/units").json()["units"]
        for r in rows:
            if r["type"] == "paragraph" and len((r.get("clean") or "").split()) >= 3:
                return n, r
    pytest.skip("the stand-in book has no paragraph of three words")


def test_shortcuts_are_visible_and_taught(ok_server):  # noqa: F811
    server = ok_server
    job = converted_job(server)
    number, _ = find_para(server, job)
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_init_script(SIGNED)
        pg = ctx.new_page()
        pg.set_default_timeout(60000)
        problems = []
        pg.on("pageerror", lambda e: problems.append(str(e)))

        # Review (flagged items): the strip names its keys; Browse: its own
        pg.goto(f"{server}/#/job/{job}/review")
        pg.get_by_test_id("progress").filter(has_text="confirmed").wait_for()
        bar = pg.get_by_test_id("shortcut-bar")
        assert "answer" in bar.inner_text() and "skip" in bar.inner_text() and "all shortcuts" in bar.inner_text()
        pg.goto(f"{server}/#/job/{job}/review?mode=browse&page={number}")
        pg.reload()
        pg.get_by_test_id("unit").first.wait_for()
        bar = pg.get_by_test_id("shortcut-bar")
        text = bar.inner_text()
        for part in ("Click a word + S", "split", "J", "join with previous", "Shift/Ctrl+click + M", "merge", "undo"):
            assert part in text, text
        assert pg.get_by_test_id("first-tips").locator("li").count() == 3

        # tooltips show the key
        assert "U or Ctrl+Z" in pg.get_by_test_id("undo-last").get_attribute("title")
        assert "(S)" in pg.get_by_test_id("split-block").first.get_attribute("title")
        assert "(J)" in pg.get_by_test_id("join-prev").first.get_attribute("title")

        # ? opens every shortcut, grouped, each with when to use it; Esc closes
        pg.mouse.click(5, 5)
        pg.keyboard.press("?")
        panel = pg.get_by_test_id("shortcuts-panel")
        panel.wait_for()
        assert [g.get_attribute("data-group") for g in panel.locator("section").all()] == ["Browse", "Review: flagged items", "Navigation"]
        assert "a paragraph cut by a page break" in panel.inner_text().lower()
        assert panel.get_by_test_id("shortcut-row").count() >= 18
        pg.keyboard.press("Escape")
        panel.wait_for(state="detached")
        pg.get_by_test_id("shortcuts-open").click()
        panel.wait_for()
        pg.get_by_test_id("shortcuts-close").click()

        # Hide: remembered after a reload; the tab brings it back
        pg.get_by_test_id("shortcut-hide").click()
        bar.wait_for(state="hidden")
        pg.reload()
        pg.get_by_test_id("progress").filter(has_text="confirmed").wait_for()
        assert pg.get_by_test_id("shortcut-bar").is_hidden() and pg.get_by_test_id("shortcut-tab").is_visible()
        pg.get_by_test_id("shortcut-tab").click()
        pg.get_by_test_id("shortcut-bar").wait_for(state="visible")

        # First-time tips: the first three visits of Browse show the card, the fourth does not
        pg.evaluate("() => localStorage.removeItem('tipVisits:asha:browse')")
        for n in (1, 2, 3):
            pg.reload()
            pg.get_by_test_id("unit").first.wait_for()
            assert pg.get_by_test_id("first-tips").count() == 1, n
        pg.get_by_test_id("tips-ok").click()  # dismissed for now
        assert pg.get_by_test_id("first-tips").count() == 0
        pg.reload()
        pg.get_by_test_id("unit").first.wait_for()
        assert pg.get_by_test_id("first-tips").count() == 0  # the fourth visit: no card
        browser.close()
        assert not problems, problems


def test_the_tour_names_the_new_keys(ok_server):  # noqa: F811
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_init_script("try { localStorage.setItem('reviewer','Asha'); localStorage.setItem('role','manager'); } catch (e) {}")
        pg = ctx.new_page()
        pg.goto(f"{ok_server}/#/")
        pg.get_by_test_id("tour-next").wait_for()
        seen = ""
        for _ in range(8):
            seen += pg.get_by_test_id("help-dialog").inner_text()
            if pg.get_by_test_id("tour-next").inner_text() == "Done":
                break
            pg.get_by_test_id("tour-next").click()
        assert "press S to split" in seen and "J joins" in seen and "M merges" in seen and "B opens it in Browse" in seen, seen
        browser.close()


def test_click_a_word_and_press_s_splits_the_block(ok_server):  # noqa: F811
    server = ok_server
    job = converted_job(server)
    number, para = find_para(server, job)
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_init_script(SIGNED)
        pg = ctx.new_page()
        pg.set_default_timeout(60000)
        problems = []
        pg.on("pageerror", lambda e: problems.append(str(e)))
        pg.goto(f"{server}/#/job/{job}/review?mode=browse&page={number}")
        pg.get_by_test_id("who").wait_for()
        pg.get_by_test_id("who").fill("Asha")
        pg.get_by_test_id("unit").first.wait_for()
        words = para["clean"].split()
        unit = pg.locator(f"[data-testid=unit][data-unit='{para['id']}']")
        pg.keyboard.press("s")  # nothing picked yet: says what to do, saves nothing
        assert not requests.get(f"{server}/api/jobs/{job}/decisions").json()["edits"]
        x, y = pg.evaluate("""(uid) => {
            const el = document.querySelector(`[data-testid=unit][data-unit='${uid}'] [data-testid=btext]`);
            const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let n, last; while ((n = w.nextNode())) last = n;
            const m = [...last.textContent.matchAll(/\\S+/g)][1];
            const r = document.createRange(); r.setStart(last, m.index + 1); r.setEnd(last, m.index + 2);
            const b = r.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2];
        }""", para["id"])
        pg.mouse.click(x, y)  # a plain click picks the word
        pg.keyboard.press("s")
        pg.get_by_test_id("status-undo").wait_for()
        after = [r["clean"] for r in requests.get(f"{server}/api/jobs/{job}/pages/{number}/units").json()["units"] if r["type"] == "paragraph"]
        assert words[0] in after and " ".join(words[1:]) in after, after
        pg.keyboard.press("u")  # U undoes the whole action
        time.sleep(1.5)
        assert para["clean"] in [r["clean"] for r in requests.get(f"{server}/api/jobs/{job}/pages/{number}/units").json()["units"]]
        _ = unit
        browser.close()
        assert not problems, problems
