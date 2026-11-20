"""Browser test: the yellow bar on every page while a book converts, and Pause on the queue page.
Uses the stand-in converter (slow mode), so it needs only Chrome, on its own port."""

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
playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not Path(CHROME).exists(), reason="Chrome is not installed")
MANAGER = {"X-User": "Asha", "X-Role": "manager"}


def free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    port = free_port()
    fake = BACKEND / "tests_app" / "fake_converter.py"
    settings = tmp_path / "app_settings.yaml"
    settings.write_text(
        f"port: {port}\nbind_address: 127.0.0.1\ndata_folder: {tmp_path / 'data'}\n"
        f"converter_command: ['{sys.executable}', '-B', '{fake}']\ncleanup_mode: 'off'\n"
    )
    env = {**os.environ, "PYTHONPATH": str(BACKEND / "src") + os.pathsep + str(BACKEND),
           "BOOK_APP_SETTINGS": str(settings), "BOOK_APP_FAKE_MODE": "slow"}  # fmt: skip
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
    yield base
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_the_bar_shows_while_converting_and_pause_takes_it_away(server):
    r = requests.put(f"{server}/api/jobs?filename=Big book.pdf&profile=jaypee_v3",
                     data=make_pdf(3), headers=MANAGER)
    job = r.json()["id"]
    assert requests.post(f"{server}/api/jobs/{job}/convert", headers=MANAGER).ok
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_init_script("localStorage.setItem('reviewer','Asha'); localStorage.setItem('role','manager'); localStorage.setItem('tourSeen:asha','1');")
        pg = ctx.new_page()
        pg.set_default_timeout(30000)
        problems = []
        pg.on("pageerror", lambda e: problems.append(str(e)))
        pg.goto(f"{server}/#/new")
        bar = pg.get_by_test_id("convert-banner")
        bar.wait_for(state="visible")
        text = bar.inner_text()
        assert "A book is converting" in text and "Big book.pdf" in text and "%" in text
        pg.goto(f"{server}/#/queue")
        pg.get_by_test_id("converting-now").wait_for()
        pg.get_by_test_id("queue-pause-running").click()
        pg.get_by_test_id("queue-status").filter(has_text="paused").wait_for()
        pg.get_by_test_id("queue-pause").filter(has_text="Resume").wait_for()
        bar.wait_for(state="hidden", timeout=30000)  # the bar polls every 15 s
        pg.get_by_test_id("queue-pause").click()  # Resume
        bar.wait_for(state="visible", timeout=30000)
        browser.close()
        assert not problems, problems
