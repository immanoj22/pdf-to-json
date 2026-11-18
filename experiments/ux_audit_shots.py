"""Screenshots of every screen and state of the Book Converter app, for docs/app_ux_audit.md.

Drives Chrome (Playwright) at 1440x900, scale 2. Run it only against a TEST copy of the app
(its own data folder), never the live app: some states (dialogs open, items selected) are
reached by clicking. Nothing is saved: no Save/Accept/Fix/Skip/Undo/Export is pressed.

Usage: python ux_audit_shots.py BASE_URL BIG_JOB SMALL_JOB OUT_DIR [PREFIX]"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

base, big, small, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
prefix = sys.argv[5] if len(sys.argv) > 5 else ""
out.mkdir(parents=True, exist_ok=True)
texts: dict[str, str] = {}


def api(path):
    with urllib.request.urlopen(base + path, timeout=300) as r:
        return json.load(r)


def shot(pg, name, full=False):
    pg.wait_for_timeout(600)
    pg.screenshot(path=str(out / f"{prefix}{name}.png"), full_page=full)
    try:
        texts[name] = pg.inner_text("main")[:6000]
    except Exception:
        texts[name] = ""
    print("shot", name, flush=True)


def safe(fn):
    try:
        fn()
    except Exception as e:  # one broken state must not stop the others
        print("FAILED", fn.__name__, e, flush=True)


with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    ctx = br.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    pg = ctx.new_page()
    pg.set_default_timeout(120000)

    def go(hash_, wait="main"):
        pg.goto(f"{base}/#{hash_}")
        pg.reload()  # a new hash on the same page would keep the old role/session state
        pg.wait_for_selector(wait)
        pg.wait_for_load_state("networkidle")

    def s_login():
        go("/login")
        shot(pg, "01_signin")
        pg.evaluate("localStorage.setItem('reviewer','Audit Manager');localStorage.setItem('role','manager')")

    def s_books():
        go("/")
        shot(pg, "02_books_manager", full=True)
        pg.get_by_test_id("assign").first.click()
        shot(pg, "03_assign_reviewers", full=True)
        pg.evaluate("localStorage.setItem('role','reviewer');localStorage.setItem('reviewer','Audit Reviewer')")
        go("/")
        shot(pg, "04_books_reviewer_my_books", full=True)
        pg.evaluate("localStorage.setItem('role','manager');localStorage.setItem('reviewer','Audit Manager')")

    def s_new():
        go("/new")
        shot(pg, "05_new_book")
        pdf = Path(__import__("os").environ.get("UX_TINY_DIR", ".")) / "ux_tiny_a.pdf"
        if pdf.exists():
            pg.get_by_test_id("file-input").set_input_files([str(pdf), str(pdf.with_name("ux_tiny_b.pdf"))])
            pg.get_by_test_id("batch-panel").wait_for(timeout=10000)
            shot(pg, "06_new_book_multiple", full=True)

    def s_profile():
        go(f"/job/{small}/profile")
        pg.get_by_test_id("profile-continue").wait_for()
        shot(pg, "07_profile_pick", full=True)
        pg.get_by_test_id("maker-panel").locator("summary").click()
        pg.get_by_test_id("maker-panel").scroll_into_view_if_needed()
        shot(pg, "08_profile_ai_prompt")

    def s_queue():
        go("/queue")
        shot(pg, "09_queue", full=True)

    def s_convert():
        go(f"/job/{small}/convert")
        shot(pg, "10_convert_done", full=True)
        for j in api("/api/jobs")["jobs"]:
            if j["state"] in ("queued", "converting", "running"):
                go(f"/job/{j['id']}/convert")
                shot(pg, "11_convert_in_progress", full=True)
                break
        for j in api("/api/jobs")["jobs"]:
            if j["state"] in ("failed", "cancelled"):
                go(f"/job/{j['id']}/convert")
                shot(pg, "12_convert_failed", full=True)
                break

    def s_details():
        go(f"/job/{big}/details")
        pg.get_by_test_id("details-save").wait_for()
        shot(pg, "13_book_details")
        shot(pg, "13b_book_details_full", full=True)
        pg.get_by_test_id("parts-confirm").scroll_into_view_if_needed()
        shot(pg, "14_book_parts")

    def s_review():
        go(f"/job/{big}/review")
        pg.get_by_test_id("right-pane").wait_for()
        pg.wait_for_timeout(1500)
        shot(pg, "15_review_open_items")
        pg.get_by_test_id("filter-status").select_option("all")
        shot(pg, "16_review_all_items")
        pg.get_by_test_id("filter-page").fill("77")
        pg.wait_for_timeout(800)
        shot(pg, "17_review_page77")
        shot(pg, "17b_review_page77_full", full=True)
        pg.get_by_test_id("filter-page").fill("")
        kinds = [o for o in pg.get_by_test_id("filter-kind").locator("option").evaluate_all("os => os.map(o => o.value)") if o]
        for k in kinds:
            pg.get_by_test_id("filter-kind").select_option(k)
            pg.wait_for_timeout(700)
            shot(pg, f"18_card_{k}")
        pg.get_by_test_id("filter-kind").select_option("")
        pg.get_by_test_id("history").locator("summary").click()
        pg.get_by_test_id("history").scroll_into_view_if_needed()
        shot(pg, "19_your_changes")

    def s_browse():
        go(f"/job/{big}/review?mode=browse&page=77")
        pg.get_by_test_id("unit-list").wait_for()
        pg.wait_for_timeout(1500)
        shot(pg, "20_browse_p77")
        shot(pg, "20b_browse_p77_full", full=True)
        pg.get_by_test_id("chapters-panel").scroll_into_view_if_needed()
        shot(pg, "21_chapters_parts_panel")
        pg.get_by_test_id("select").first.check()
        pg.get_by_test_id("change-element").click()
        pg.get_by_test_id("change-dialog").wait_for()
        pg.get_by_test_id("change-dialog").scroll_into_view_if_needed()
        shot(pg, "22_change_element_dialog")
        pg.get_by_test_id("change-cancel").click()
        go(f"/job/{big}/review?mode=browse&page=12")
        pg.get_by_test_id("unit-list").wait_for()
        shot(pg, "23_browse_list_page")

    def s_export():
        go(f"/job/{big}/export")
        pg.get_by_test_id("export-run").wait_for()
        shot(pg, "24_export")
        shot(pg, "24b_export_full", full=True)
        hist = pg.get_by_test_id("export-history")
        if hist.count():
            hist.scroll_into_view_if_needed()
            shot(pg, "25_export_history")
        qc = pg.get_by_test_id("qc")
        if qc.count():
            qc.first.scroll_into_view_if_needed()
            shot(pg, "26_qc_report")

    def s_check():
        go("/check")
        pg.get_by_test_id("check-run").wait_for()
        shot(pg, "27_check_delivery", full=True)

    def s_errors():
        go("/job/ffffffffffffffff/details")
        shot(pg, "28_error_missing_book")
        go("/nowhere")
        shot(pg, "29_unknown_page")

    for f in (s_login, s_books, s_new, s_profile, s_queue, s_convert, s_details, s_review, s_browse, s_export, s_check, s_errors):
        safe(f)
    (out / f"{prefix}texts.json").write_text(json.dumps(texts, indent=1, ensure_ascii=False))
    br.close()
