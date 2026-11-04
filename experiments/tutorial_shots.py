"""Screens for the tutorial (docs/tutorial/): drives the real app in Chrome (Playwright) on a
copy of the app that already holds a converted book, and saves one screenshot per step.

Usage: python tutorial_shots.py BASE_URL JOB_ID"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs/tutorial/shots"
base, jid = sys.argv[1], sys.argv[2]
OUT.mkdir(parents=True, exist_ok=True)


def shot(pg, name):
    pg.screenshot(path=str(OUT / f"{name}.png"))


with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = br.new_page(viewport={"width": 1280, "height": 800})
    pg.set_default_timeout(120000)
    pg.goto(base + "/#/")
    pg.wait_for_selector("main")
    pg.wait_for_timeout(800)
    shot(pg, "01_books")
    pg.goto(base + "/#/new")
    pg.wait_for_timeout(500)
    shot(pg, "02_upload")
    pg.goto(f"{base}/#/job/{jid}/profile")
    pg.get_by_test_id("profile-continue").wait_for()
    pg.wait_for_timeout(500)
    shot(pg, "03_profile_list")
    pg.locator("[data-profile^='jats_base'] input[type=radio]").check()
    pg.wait_for_timeout(300)
    shot(pg, "04_profile_standard_chosen")
    pg.goto(f"{base}/#/job/{jid}/convert")
    pg.wait_for_timeout(1500)
    shot(pg, "04b_convert")
    pg.goto(f"{base}/#/job/{jid}/profile")
    pg.locator("[data-profile^='jats_base'] input[type=radio]").check()
    pg.get_by_test_id("profile-continue").click()
    pg.wait_for_url(re.compile(r"/details"))
    pg.get_by_test_id("d-isbn").wait_for(timeout=300000)
    pg.get_by_test_id("d-publisher").fill("Example Publisher Ltd")
    pg.get_by_test_id("d-publication_date").fill("2026-03")
    pg.wait_for_timeout(300)
    shot(pg, "05_book_details")
    pg.get_by_test_id("details-save").click()
    try:
        pg.get_by_test_id("who").wait_for(timeout=60000)
    except Exception:
        pg.screenshot(path="/tmp/x/tutorial_fail.png")
        print(pg.url, pg.inner_text("main")[:500])
        raise
    pg.get_by_test_id("who").fill("Tutorial Reader")
    pg.wait_for_timeout(1500)
    shot(pg, "06_review")
    pg.get_by_test_id("to-export").click()
    pg.get_by_test_id("export-run").wait_for()
    pg.wait_for_timeout(500)
    shot(pg, "07_export_choose_format")
    pg.get_by_test_id("export-run").click()
    pg.get_by_test_id("blocked").wait_for(timeout=300000)
    shot(pg, "08_export_blocked")
    pg.get_by_test_id("override").check()
    pg.get_by_test_id("export-run").click()
    pg.get_by_test_id("result-jats").wait_for(timeout=600000)
    pg.wait_for_timeout(500)
    pg.evaluate("window.scrollTo(0, 0)")
    shot(pg, "09_export_result")
    pg.get_by_test_id("qc-jats").scroll_into_view_if_needed()
    pg.wait_for_timeout(300)
    shot(pg, "10_export_qc")
    pg.goto(base + "/#/check")
    pg.wait_for_timeout(800)
    shot(pg, "11_check_delivery")
    pg.goto(f"{base}/#/job/{jid}/profile")
    pg.get_by_test_id("profile-continue").wait_for()
    pg.locator("[data-testid=maker-panel] summary").click()
    pg.wait_for_timeout(500)
    pg.evaluate("document.querySelector('[data-testid=maker-panel]').scrollIntoView()")
    shot(pg, "12_profile_maker")
    pg.goto(base + "/#/")
    pg.wait_for_timeout(800)
    shot(pg, "13_books_after")
    expect(pg.locator("body")).to_contain_text("Book Converter")
    br.close()
print("shots in", OUT)
