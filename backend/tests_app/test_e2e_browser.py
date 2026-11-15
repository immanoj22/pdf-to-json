"""End-to-end browser test (Playwright with the installed Chrome) of the whole user flow.

* ``test_art_therapy_nine_pages``: a real conversion of the nine-page art-therapy PDF through
  the real converter (several minutes), then profile, details, review, export, download.
* ``test_art_publication_review_export_check``: the cached ART publication (130 pages):
  details, flagged items, browse-mode fixes, export blocked / override, download, and the
  check of an edited delivery.

Screenshots of every screen go to docs/screenshots/. Skipped when Chrome, the layout models,
or the books are not on this machine."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest
import requests

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(ROOT / "experiments"))
from reference_paths import reference_path  # noqa: E402

playwright = pytest.importorskip("playwright.sync_api")
SHOTS = ROOT / "docs" / "screenshots"
CHROME = os.environ.get("BOOK_APP_CHROME", "/usr/bin/google-chrome")
MODELS = Path(os.environ.get("BOOK_APP_MODELS", ROOT / "frontend_temp/runtime/cache/huggingface"))
ART_JOB = ROOT / "frontend_temp/runtime/jobs/7d68b3309eb1cf6c4d6fe41b3c36168c"
if not ART_JOB.exists():  # a worktree has no runtime folder: read the main checkout's (read-only)
    MAIN = Path(os.environ.get("BOOK_MAIN_CHECKOUT", ROOT.parent / "pdf_book_converter"))
    ART_JOB = MAIN / "frontend_temp/runtime/jobs/7d68b3309eb1cf6c4d6fe41b3c36168c"
SIGNED_IN = ("try { if (!localStorage.getItem('role')) { localStorage.setItem('reviewer', 'Tester');"
             " localStorage.setItem('role', 'manager'); } } catch (e) {}")  # a manager is signed in
pytestmark = pytest.mark.skipif(not Path(CHROME).exists(), reason="Chrome is not installed")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    port = free_port()
    settings = tmp_path / "app_settings.yaml"
    settings.write_text(
        f"port: {port}\ndata_folder: {tmp_path / 'data'}\nmodels_folder: '{MODELS}'\n"
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(BACKEND / "src") + os.pathsep + str(BACKEND),
        "BOOK_APP_SETTINGS": str(settings),
    }
    proc = subprocess.Popen(
        [sys.executable, "-B", "-m", "book_app"],
        env=env,
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
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
def page(server, request):
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1366, "height": 768}, accept_downloads=True)
        ctx.add_init_script(SIGNED_IN)
        pg = ctx.new_page()
        pg.set_default_timeout(30000)
        problems = []
        pg.on("pageerror", lambda e: problems.append(str(e)))
        pg.on(
            "request",
            lambda r: (
                problems.append("EXTERNAL " + r.url)
                if not r.url.startswith(server["base"]) and not r.url.startswith("data:")
                else None
            ),
        )
        yield pg
        if getattr(request.node, "failed_call", False):
            pg.screenshot(path=str(SHOTS.parent.parent / ".cache" / "e2e_failure.png"))
            problems.append("(failure screenshot saved)")
        browser.close()
        assert not [
            x
            for x in problems
            if x.startswith(("EXTERNAL", "Error", "Type", "Syntax", "Reference"))
        ], problems


def confirm_parts_ui(pg):
    """The Book parts panel above the details: confirm the converter's guess as 'Tester'."""
    pg.get_by_test_id("parts-confirm").wait_for(timeout=60000)
    pg.get_by_test_id("parts-who").fill("Tester")
    pg.get_by_test_id("parts-confirm").click()
    pg.wait_for_load_state()
    pg.get_by_test_id("d-isbn").wait_for(timeout=60000)
    pg.get_by_text("Confirmed by Tester").wait_for(timeout=60000)


def shot(pg, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(SHOTS / f"{name}.png"))


def choose_profile(pg, base, job_id, ref="jaypee_v3@3.1.0"):
    pg.goto(f"{base}/#/job/{job_id}/profile")
    pg.locator(f"[data-profile='{ref}'] input[type=radio]").check()
    pg.get_by_test_id("profile-continue").click()


def profile_panel_checks(pg, tmp_path):
    """Upload an invalid and a valid profile; look at the profile-maker panel."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "profile: acme_v1\nversion: 1.0.0\ndate: '2026-11-01'\nextends: _base/docbook_base\nids:\n  chaptr: 'x{chapter}'\n"  # noqa: E501
    )
    pg.get_by_test_id("profile-file").set_input_files(str(bad))
    pg.get_by_test_id("profile-errors").wait_for()
    text = pg.get_by_test_id("profile-errors").inner_text()
    assert "chaptr" in text and "chapter" in text and "5" not in text.split("Line")[0]
    shot(pg, "02_profile_invalid_upload")
    good = tmp_path / "acme.yaml"
    good.write_text(
        "profile: acme_v1\nversion: 1.0.0\ndate: '2026-11-01'\nextends: _base/docbook_base\nclient: Acme\nguideline: Acme guide\n"  # noqa: E501
    )
    pg.get_by_test_id("profile-file").set_input_files(str(good))
    pg.get_by_test_id("profile-saved").wait_for()
    assert "untested" in pg.locator("[data-profile^='acme_v1']").inner_text()
    pg.locator("[data-testid=maker-panel] summary").click()
    prompt = pg.get_by_test_id("maker-prompt").inner_text()
    assert "profile.schema.json" in prompt
    assert "never book content" in pg.get_by_test_id("maker-panel").inner_text()
    pg.context.grant_permissions(["clipboard-read", "clipboard-write"])
    pg.get_by_test_id("maker-copy").click()
    assert pg.evaluate("navigator.clipboard.readText()").startswith(prompt[:40])
    with pg.expect_download() as d:
        pg.get_by_test_id("maker-schema").click()
    assert d.value.suggested_filename == "profile.schema.json"
    shot(pg, "03_profile_choose_and_maker")


def fill_details_and_review_basics(pg, base, jid):
    pg.goto(f"{base}/#/job/{jid}/details")
    pg.get_by_test_id("d-isbn").wait_for()
    pg.get_by_test_id("d-isbn").fill("9789372025263")  # wrong check digit
    assert "not valid" in pg.locator("[data-err=isbn]").inner_text()
    assert pg.get_by_test_id("details-save").is_disabled()
    return


@pytest.mark.skipif(not MODELS.is_dir(), reason="layout models not available")
def test_art_therapy_nine_pages(server, page, tmp_path):
    base, pg = server["base"], page
    pdf = reference_path("art_index_pdf")
    pg.goto(base)
    pg.get_by_test_id("nav-new").click()
    pg.get_by_test_id("file-input").set_input_files(str(pdf))
    pg.wait_for_url(re.compile(r"#/job/[0-9a-f]{16}/profile"))
    jid = pg.url.split("/job/")[1].split("/")[0]
    shot(pg, "01_upload")
    # a non-PDF is refused by content
    fake = tmp_path / "fake.pdf"
    fake.write_text("hello")
    pg.goto(base + "/#/new")
    pg.get_by_test_id("file-input").set_input_files(str(fake))
    assert "not a PDF" in pg.get_by_test_id("error").inner_text()
    pg.goto(f"{base}/#/job/{jid}/profile")
    profile_panel_checks(pg, tmp_path)
    pg.locator("[data-profile='jaypee_v3@3.1.0'] input[type=radio]").check()
    pg.get_by_test_id("profile-continue").click()
    pg.get_by_test_id("start-convert").click()
    pg.get_by_test_id("progress-text").wait_for()
    shot(pg, "04_convert_progress")
    pg.get_by_test_id("converted").wait_for(timeout=1500000)
    shot(pg, "05_convert_done")
    pg.get_by_test_id("to-details").click()
    pg.get_by_test_id("d-isbn").wait_for(timeout=120000)
    confirm_parts_ui(pg)
    pg.get_by_test_id("d-isbn").fill("9780306406158")
    assert "not valid" in pg.locator("[data-err=isbn]").inner_text()
    pg.get_by_test_id("d-isbn").fill("9780306406157")
    pg.get_by_test_id("d-title").fill("Art therapy index excerpt")
    shot(pg, "06_details")
    pg.get_by_test_id("details-save").click()
    pg.get_by_test_id("who").wait_for(timeout=120000)
    pg.get_by_test_id("who").fill("Test Reviewer")
    pg.get_by_test_id("queue").wait_for()
    shot(pg, "07_review_queue")
    pg.get_by_test_id("accept").or_(pg.get_by_test_id("skip")).first.click()
    pg.get_by_test_id("to-export").click()
    pg.get_by_test_id("export-run").click()
    pg.get_by_test_id("verdict").wait_for(timeout=300000)
    shot(pg, "08_export_result")
    with pg.expect_download() as d:
        pg.get_by_test_id("download-zip").click()
    z = tmp_path / "out.zip"
    d.value.save_as(z)
    assert any(n.endswith("page_info.xml") for n in zipfile.ZipFile(z).namelist())
    with pg.expect_download() as d:
        pg.get_by_test_id("download-qc").click()
    assert d.value.suggested_filename == "qc_report.html"
    # Books page
    pg.get_by_test_id("nav-books-link").click()
    assert (
        "Art therapy" in pg.get_by_test_id("books-table").inner_text()
        or "docbook" in pg.get_by_test_id("books-table").inner_text()
    )
    shot(pg, "09_books")


@pytest.mark.skipif(
    not (ART_JOB / "output").is_dir(), reason="cached ART publication not available"
)
def test_art_publication_review_export_check(server, page, tmp_path):
    base, pg = server["base"], page
    pdf = ART_JOB / "input.pdf"
    job = requests.put(base + "/api/jobs?filename=ART.pdf", data=pdf.read_bytes()).json()
    jid = job["id"]
    folder = server["data"] / "jobs" / jid
    pub = next((ART_JOB / "output").glob("book-*/"))
    shutil.copytree(pub, folder / "converter_out" / pub.name, symlinks=True)
    state = json.loads((folder / "job.json").read_text())
    state.update(state="converted", publication=f"converter_out/{pub.name}")
    (folder / "job.json").write_text(json.dumps(state))
    choose_profile(pg, base, jid)
    pg.wait_for_url(re.compile(r"/details"))
    pg.goto(f"{base}/#/job/{jid}/details")
    pg.get_by_test_id("d-isbn").wait_for(timeout=180000)
    confirm_parts_ui(pg)
    assert pg.get_by_test_id("d-isbn").input_value() == "9789372025262"
    assert pg.get_by_test_id("a-0-surname").input_value() == "Salunke"
    shot(pg, "10_art_details")
    pg.get_by_test_id("details-save").click()
    pg.get_by_test_id("who").wait_for(timeout=120000)
    pg.get_by_test_id("who").fill("Test Reviewer")
    # --- flagged items: must check first, page picture with highlight
    first = pg.get_by_test_id("item-card")
    first.wait_for()
    first_row = pg.get_by_test_id("queue-item").first.inner_text()
    assert "must check" in first_row or "Part, chapter or section" in first_row  # structure first, then must check
    assert pg.get_by_test_id("highlight").is_visible()
    pg.wait_for_function(
        "() => document.querySelector('[data-testid=page-image]').naturalWidth > 100",
        timeout=60000,
    )
    before = pg.get_by_test_id("page-no").input_value()
    pg.get_by_test_id("next-page").click()
    assert pg.get_by_test_id("page-no").input_value() == str(int(before) + 1)
    pg.get_by_test_id("zoom-in").click()
    # alt text: write a description for the first alt item
    pg.get_by_test_id("filter-kind").select_option("alt_text")
    pg.get_by_test_id("alt-text").fill("A drawing of a laboratory dish.")
    pg.get_by_test_id("confirm-fix").click()  # nothing is saved before Confirm
    playwright.expect(pg.get_by_test_id("progress")).to_contain_text("1 of")
    shot(pg, "11_review_queue")
    # heading item: not a heading
    pg.get_by_test_id("progress").filter(has_text="1 of").wait_for()
    pg.get_by_test_id("filter-kind").select_option("heading")
    pg.get_by_test_id("fix-heading").click()
    pg.get_by_test_id("heading-level").select_option("none")
    pg.get_by_test_id("confirm-fix").click()
    pg.get_by_test_id("filter-kind").select_option("table")
    pg.get_by_test_id("details").first.locator("xpath=preceding-sibling::details[1]/summary").click()  # Add a note
    pg.get_by_test_id("note").fill("Header row missing")
    pg.get_by_test_id("answer-2").click()  # Needs fixing
    pg.get_by_test_id("filter-kind").select_option("")
    pg.get_by_test_id("skip").click()
    # --- browse mode: any page
    pg.get_by_test_id("mode-browse").click()
    pg.get_by_test_id("page-no").fill("19")
    pg.get_by_test_id("page-no").press("Enter")
    pg.get_by_test_id("browse-list").locator("[data-testid=unit]").first.wait_for()
    shot(pg, "12_review_browse")
    para = (
        pg.locator("[data-testid=unit][data-type=paragraph]")
        .filter(has=pg.get_by_test_id("split-open"))
        .first
    )
    para.get_by_test_id("split-open").click()
    para.get_by_test_id("split-line").first.click()
    pg.locator("[data-testid=unit]").first.wait_for()
    para2 = pg.locator("[data-testid=unit][data-type=paragraph]").first
    para2.get_by_test_id("make-heading").click()
    pg.get_by_test_id("browse-list").locator("[data-type=heading]").first.wait_for()
    pg.locator("[data-testid=unit][data-type=heading]").first.get_by_test_id("new-chapter").click()
    # the chapter list panel shows what the export will have; a heading's kind is set in place
    pg.get_by_test_id("chapters-panel").wait_for()
    assert "chapters" in pg.get_by_test_id("chapters-panel").locator("summary").inner_text()
    head = pg.locator("[data-testid=unit][data-type=heading]").first
    head.get_by_test_id("heading-kind").select_option("section")
    head.get_by_test_id("set-kind").click()
    pg.get_by_test_id("browse-list").locator("[data-type=heading]").first.wait_for()
    assert pg.get_by_test_id("chapters-panel").count() == 1
    assert (
        pg.get_by_test_id("edit-row").count() >= 4
        or pg.locator("[data-testid=history]").count() == 1
    )
    pg.locator("[data-testid=history] summary").click()
    shot(pg, "13_review_changes")
    # --- export: blocked by alt-text placeholders
    pg.get_by_test_id("to-export").click()
    pg.get_by_test_id("export-run").click()
    pg.get_by_test_id("blocked").wait_for(timeout=300000)
    assert "blocked" in pg.get_by_test_id("blocked").inner_text().lower()
    shot(pg, "14_export_blocked")
    pg.get_by_test_id("override").check()
    pg.get_by_test_id("export-run").click()
    pg.get_by_test_id("verdict").wait_for(timeout=300000)
    assert pg.get_by_test_id("override").count() >= 1
    assert "Exported with" in pg.get_by_test_id("qc").inner_text()
    assert pg.get_by_test_id("dtd").inner_text().startswith("0 error")
    shot(pg, "15_export_result")
    with pg.expect_download() as d:
        pg.get_by_test_id("download-zip").click()
    z = tmp_path / "edited.zip"
    d.value.save_as(z)
    # --- ePub: format choice, profile with an ePub part, both formats
    sel = pg.get_by_test_id("export-profile")
    v4 = sel.locator("option").evaluate_all(
        "o => o.map(x => x.value).find(v => v.startsWith('jaypee_v4'))"
    )
    sel.select_option(value=v4)
    pg.get_by_test_id("export-format").select_option("all")  # DocBook and ePub
    pg.get_by_test_id("export-run").click()
    pg.get_by_test_id("epub-result").wait_for(timeout=600000)
    shot(pg, "18_export_epub_result")
    assert "EPUBCheck" in pg.get_by_test_id("epub-qc").inner_text()
    assert pg.get_by_test_id("epub-lossless").inner_text().startswith("0 word(s) missing, 0 extra")
    assert pg.get_by_test_id("download-zip").count() == 1
    with pg.expect_download() as de:
        pg.get_by_test_id("download-epub").click()
    epub = tmp_path / "art.epub"
    de.value.save_as(epub)
    ez = zipfile.ZipFile(epub)
    assert (
        ez.infolist()[0].filename == "mimetype" and ez.read("mimetype") == b"application/epub+zip"
    )
    assert "OEBPS/nav.xhtml" in ez.namelist()
    with pg.expect_download() as dq:
        pg.get_by_test_id("download-epub-qc").click()
    assert dq.value.suggested_filename.endswith(".html")
    playwright.expect(pg.get_by_test_id("export-history")).to_contain_text("ePub", timeout=30000)
    # --- check an edited delivery: change one word, upload
    src = zipfile.ZipFile(z)
    out = tmp_path / "edited_delivery.zip"
    with zipfile.ZipFile(out, "w") as zf:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith("ch2.xml"):
                data = data.replace(b"Quality", b"Qualities", 1)
            zf.writestr(info.filename, data)
    pg.get_by_test_id("nav-check").click()
    pg.get_by_test_id("check-book").select_option(jid)
    pg.get_by_test_id("check-file").set_input_files(str(out))
    pg.get_by_test_id("check-run").click()
    pg.get_by_test_id("check-qc").wait_for(timeout=300000)
    assert "added" in pg.get_by_test_id("check-qc").inner_text()
    shot(pg, "16_check_edited_delivery")
    # --- books page: reopen, re-export link, delete asks to confirm
    pg.get_by_test_id("nav-books-link").click()
    assert "ART" in pg.get_by_test_id("books-table").inner_text()
    shot(pg, "17_books")
    pg.once("dialog", lambda dlg: dlg.dismiss())
    pg.get_by_test_id("delete").click()
    assert (server["data"] / "jobs" / jid).exists()
    pg.once("dialog", lambda dlg: dlg.accept())
    pg.get_by_test_id("delete").click()
    playwright.expect(pg.get_by_test_id("delete")).to_have_count(0)
    assert not (server["data"] / "jobs" / jid).exists()


FORMAT_BASES = {
    "html": "html_base",
    "dtbook": "dtbook_nimas_base",
    "daisy3": "daisy3_base",
    "jats": "jats_base",
    "bits": "bits_base",
}


def test_art_export_in_every_standard_format(server, page, tmp_path):
    """ART exported in HTML, NIMAS/DTBook, DAISY 3, JATS and BITS from the Export screen:
    only the formats of the chosen profile are offered, base profiles are labelled standard,
    each result has its QC verdict, report and download."""
    base, pg = server["base"], page
    job = requests.put(
        base + "/api/jobs?filename=ART.pdf", data=(ART_JOB / "input.pdf").read_bytes()
    ).json()
    jid = job["id"]
    folder = server["data"] / "jobs" / jid
    pub = next((ART_JOB / "output").glob("book-*/"))
    shutil.copytree(pub, folder / "converter_out" / pub.name, symlinks=True)
    state = json.loads((folder / "job.json").read_text())
    state.update(state="converted", publication=f"converter_out/{pub.name}")
    (folder / "job.json").write_text(json.dumps(state))
    choose_profile(pg, base, jid)
    pg.wait_for_url(re.compile(r"/details"))
    pg.get_by_test_id("d-isbn").wait_for(timeout=180000)
    confirm_parts_ui(pg)
    pg.get_by_test_id("details-save").click()
    pg.get_by_test_id("who").wait_for(timeout=120000)
    pg.get_by_test_id("who").fill("Test Reviewer")
    for fmt, ref in FORMAT_BASES.items():
        pg.goto(f"{base}/#/job/{jid}/export")
        pg.reload()  # a fresh Export screen for each format (the override box is unticked)
        sel = pg.get_by_test_id("export-profile")
        sel.wait_for()
        value = sel.locator("option").evaluate_all(
            f"o => o.map(x => x.value).find(v => v.startsWith('{ref}@'))"
        )
        sel.select_option(value=value)
        pg.locator(".banner.info", has_text=f"Profile changed to {value}").wait_for()
        assert "standard" in sel.locator(f"option[value='{value}']").inner_text()
        offered = (
            pg.get_by_test_id("export-format")
            .locator("option")
            .evaluate_all("o => o.map(x => x.value)")
        )
        assert offered == [fmt], offered  # only what the profile supports
        pg.get_by_test_id("export-run").click()
        pg.get_by_test_id("blocked").wait_for(timeout=300000)
        pg.get_by_test_id("override").check()
        pg.get_by_test_id("export-run").click()
        pg.get_by_test_id(f"result-{fmt}").wait_for(timeout=600000)
        qc = pg.get_by_test_id(f"qc-{fmt}").inner_text()
        assert "0 error" in qc or "0 word" in qc or "Lossless" in qc
        shot(pg, f"19_export_{fmt}")
        with pg.expect_download() as d:
            pg.get_by_test_id(f"download-{fmt}").click()
        out = tmp_path / f"{fmt}.zip"
        d.value.save_as(out)
        assert zipfile.ZipFile(out).namelist()
        with pg.expect_download() as d:
            pg.get_by_test_id(f"download-{fmt}-qc").click()
        assert d.value.suggested_filename.endswith("qc_report.html")
    rows = requests.get(f"{base}/api/jobs/{jid}/exports").json()["exports"]
    assert [next(iter(r["others"])) for r in rows] == list(FORMAT_BASES)
    assert all(r["verdicts"][next(iter(r["others"]))] in ("pass", "warn") for r in rows)
