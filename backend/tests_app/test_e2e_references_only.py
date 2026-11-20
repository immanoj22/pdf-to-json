"""Browser test: the document type "References only" on the Profile step (it picks the tail
profile), and the reference-list options page that follows the conversion (no ISBN, title or
authors). Stand-in converter, own port."""

from __future__ import annotations

import time

import pytest
import requests

from tests_app.conftest import make_pdf
from tests_app.test_e2e_banner import CHROME, MANAGER, playwright, start, stop

pytestmark = pytest.mark.skipif(not __import__("pathlib").Path(CHROME).exists(), reason="Chrome is not installed")


@pytest.fixture
def server(tmp_path):
    base, proc = start(tmp_path, "ok")
    yield base
    stop(proc)


def test_references_only_is_chosen_on_the_profile_step_and_has_its_own_options_page(server):
    job = requests.put(f"{server}/api/jobs?filename=refs.pdf", data=make_pdf(3), headers=MANAGER).json()["id"]
    problems = []
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        ctx.add_init_script("localStorage.setItem('reviewer','Asha'); localStorage.setItem('role','manager'); localStorage.setItem('tourSeen:asha','1');")
        pg = ctx.new_page()
        pg.set_default_timeout(30000)
        pg.on("pageerror", lambda e: problems.append(str(e)))
        pg.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
        pg.goto(f"{server}/#/job/{job}/profile")
        pg.click("[data-testid=doctype-references_only]")
        assert pg.is_checked("[data-profile^='tail@'] input[type=radio]")  # the reference list is made with tail
        pg.click("[data-testid=profile-continue]")
        pg.wait_for_url(f"**/#/job/{job}/convert")
        got = requests.get(f"{server}/api/jobs/{job}", headers=MANAGER).json()
        assert got["document_type"] == "references_only" and got["profile"].startswith("tail@")
        assert requests.post(f"{server}/api/jobs/{job}/convert", headers=MANAGER).ok
        for _ in range(100):
            if requests.get(f"{server}/api/jobs/{job}", headers=MANAGER).json()["state"] == "converted":
                break
            time.sleep(0.2)
        pg.goto(f"{server}/#/job/{job}/details")
        pg.wait_for_selector("[data-testid=refs-only-info]")
        assert pg.query_selector("[data-testid=d-isbn]") is None
        pg.select_option("[data-testid=opt-accents]", "strip")
        pg.click("[data-testid=details-save]")
        pg.wait_for_url(f"**/#/job/{job}/review")
        # Browse: the Edit panel of the block holding reference [4] corrects its text
        pg.goto(f"{server}/#/job/{job}/review?mode=browse&page=3")
        pg.get_by_test_id("who").fill("Tester")
        row = pg.locator("[data-testid=unit]", has_text="Harlan").first
        row.wait_for()
        row.get_by_test_id("edit-block").click()
        row.get_by_test_id("edit-text-open").click()
        row.get_by_test_id("edit-text-input").fill("[4]\nHarlan JR. Crops and man. Agron J 1992; 5(1): 10-5.")
        row.get_by_test_id("edit-text-check").click()
        pg.get_by_test_id("preview-line").wait_for()
        pg.get_by_test_id("confirm-save").click()
        pg.locator("[data-testid=unit]", has_text="Agron J").first.wait_for()
        browser.close()
    page = requests.get(f"{server}/api/jobs/{job}/pages/3/units", headers=MANAGER).json()["units"]
    assert any("Agron J 1992" in (u.get("text") or "") for u in page)
    saved = requests.get(f"{server}/api/jobs/{job}/details", headers=MANAGER).json()
    assert saved["details"]["options"]["accents"] == "strip"
    assert problems == []
