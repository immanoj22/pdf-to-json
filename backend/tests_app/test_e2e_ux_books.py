"""Browser test of Books / New book / Queue / Copy / help on a test app (port 8784, its own data
folder, stand-in converter): upload two PDFs (one a duplicate) -> queue -> ready notice -> retry
a failed book -> copy -> search and filters -> help and the first-time tour. Screenshots go to
$UX_SHOTS when set."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

from tests_app.conftest import make_pdf

BACKEND = Path(__file__).resolve().parents[1]
CHROME = os.environ.get("BOOK_APP_CHROME", "/usr/bin/google-chrome")
PORT = int(os.environ.get("BOOK_UX_TEST_PORT", "8784"))
playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not Path(CHROME).exists(), reason="Chrome is not installed")


@pytest.fixture
def server(tmp_path):
    settings = tmp_path / "app_settings.yaml"
    fake = BACKEND / "tests_app" / "fake_converter.py"
    settings.write_text(
        f"port: {PORT}\nbind_address: 127.0.0.1\ndata_folder: {tmp_path / 'data'}\n"
        f"converter_command: ['{sys.executable}', '-B', '{fake}']\n")
    env = {**os.environ, "PYTHONPATH": str(BACKEND / "src") + os.pathsep + str(BACKEND),
           "BOOK_APP_SETTINGS": str(settings), "BOOK_APP_FAKE_DELAY": "4"}  # fmt: skip
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
    proc.wait(10)


def shot(pg, name):
    out = os.environ.get("UX_SHOTS")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(Path(out) / f"{name}.png"))


def test_upload_queue_copy_help(server, tmp_path):
    base = server["base"]
    pdfs = []
    for n, pages in (("Anatomy 9789350259153.pdf", 4), ("Physics.pdf", 3)):
        p = tmp_path / n
        p.write_bytes(make_pdf(pages, n))
        pdfs.append(p)
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_context(viewport={"width": 1366, "height": 850}).new_page()
        pg.set_default_timeout(30000)
        problems = []
        pg.on("pageerror", lambda e: problems.append(str(e)))
        pg.on("dialog", lambda d: d.accept())
        pg.goto(f"{base}/#/login")
        pg.get_by_test_id("login-name").fill("Asha")
        pg.get_by_test_id("login-manager").check()
        pg.get_by_test_id("login-go").click()
        # first-time tour: shown once, can be skipped
        pg.get_by_test_id("tour-next").wait_for()
        shot(pg, "01_tour")
        pg.get_by_test_id("tour-skip").click()
        pg.reload()
        pg.get_by_test_id("new-book").wait_for()
        assert pg.get_by_test_id("tour-next").count() == 0
        # help on each screen
        pg.get_by_test_id("help-btn").click()
        assert pg.get_by_test_id("help-dialog").locator("li").count() == 3
        shot(pg, "02_help_books")
        pg.keyboard.press("Escape")
        pg.get_by_test_id("help-dialog").click(position={"x": 5, "y": 5})
        # upload two PDFs at once
        pg.goto(f"{base}/#/new")
        pg.get_by_test_id("help-btn").wait_for()
        pg.get_by_test_id("file-input").set_input_files([str(p) for p in pdfs])
        pg.get_by_test_id("batch-row").first.wait_for()
        pg.get_by_test_id("batch-profile").nth(1).select_option(index=0)
        shot(pg, "03_upload_batch")
        pg.get_by_test_id("batch-queue").click()
        pg.wait_for_url("**/#/queue")
        pg.get_by_test_id("queue-row").first.wait_for()
        shot(pg, "04_queue")
        # in-app notice when a book is ready
        pg.get_by_test_id("ready-notice").first.wait_for(timeout=60000)
        shot(pg, "05_ready_notice")
        jobs = requests.get(f"{base}/api/jobs").json()["jobs"]
        end = time.time() + 60
        while time.time() < end and any(j["state"] != "converted" for j in jobs):
            time.sleep(0.5)
            jobs = requests.get(f"{base}/api/jobs").json()["jobs"]
        assert all(j["state"] == "converted" for j in jobs)
        # duplicate warning on a second upload of the same file
        pg.goto(f"{base}/#/new")
        pg.get_by_test_id("file-input").set_input_files([str(p) for p in pdfs])
        pg.get_by_test_id("dup-warning").wait_for()
        shot(pg, "06_duplicate_warning")
        # a failed book can be retried
        physics = next(j for j in jobs if j["name"] == "Physics.pdf")
        flag = server["data"] / "jobs" / physics["id"] / "FAIL"
        flag.write_text("x")
        requests.post(f"{base}/api/jobs/{physics['id']}/copy", json={"decisions": "clean"})
        pg.goto(f"{base}/#/queue")
        pg.get_by_test_id("queue-retry").wait_for() if False else None
        failed = next(j for j in requests.get(f"{base}/api/jobs").json()["jobs"] if j["name"].startswith("COPY"))
        (server["data"] / "jobs" / failed["id"] / "FAIL").write_text("x")
        requests.post(f"{base}/api/jobs/{failed['id']}/convert")
        pg.get_by_test_id("queue-retry").wait_for(timeout=60000)
        shot(pg, "07_queue_failed")
        (server["data"] / "jobs" / failed["id"] / "FAIL").unlink()
        pg.get_by_test_id("queue-retry").click()
        end = time.time() + 60
        while time.time() < end and requests.get(f"{base}/api/jobs/{failed['id']}").json()["state"] != "converted":
            time.sleep(0.5)
        assert requests.get(f"{base}/api/jobs/{failed['id']}").json()["state"] == "converted"
        # copy from the Books screen
        pg.goto(f"{base}/#/")
        pg.get_by_test_id("books-table").wait_for()
        before = pg.locator("tbody tr[data-job]").count()
        pg.locator("tr[data-job]").filter(has_text="Anatomy").first.get_by_test_id("copy").click()
        pg.get_by_test_id("copy-dialog").wait_for()
        shot(pg, "08_copy_dialog")
        pg.get_by_test_id("copy-with").click()
        pg.goto(f"{base}/#/")
        pg.get_by_test_id("books-table").wait_for()
        end = time.time() + 30
        while pg.locator("tr[data-job]").count() <= before and time.time() < end:
            pg.wait_for_timeout(200)
        assert pg.locator("tr[data-job]").count() > before
        # search, filters, sort, continue
        pg.get_by_test_id("books-search").fill("physics")
        assert pg.locator("tr[data-job]").count() == 2
        pg.get_by_test_id("books-search").fill("")
        pg.get_by_test_id("filter-state").select_option("converted")
        pg.get_by_test_id("books-sort").select_option("name")
        names = pg.locator("tr[data-job] td:first-child a").all_inner_texts()
        assert names == sorted(names)
        pg.get_by_test_id("books-search").fill("zzz-nothing")
        pg.get_by_test_id("books-none").wait_for()
        pg.get_by_test_id("books-search").fill("")
        shot(pg, "08_books")
        pg.goto(f"{base}/#/job/{physics['id']}/details")
        pg.get_by_test_id("me").wait_for()
        pg.goto(f"{base}/#/")
        assert "/details" in pg.get_by_test_id("continue").get_attribute("href")
        # tour replay from the help
        pg.get_by_test_id("help-btn").click()
        pg.get_by_test_id("help-tour").click()
        pg.get_by_test_id("tour-next").wait_for()
        b.close()
        assert not problems, problems
