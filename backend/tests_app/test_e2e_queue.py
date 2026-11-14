"""Browser test of the upload queue and reviewer assignment, with the real converter on three
tiny PDFs (2-3 pages cut from PULSE), on a separate test app instance (port 8779).

A manager signs in, uploads the three PDFs at once (each with its profile) into the queue;
they convert in order; the manager assigns two reviewers (a page range, the whole book); a
reviewer signs in and sees "My books" first. One book's output is byte-identical to the same
PDF converted alone with the converter's command line."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

from tests_app.test_e2e_editor import CHROME, PDF, PORT

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
playwright = pytest.importorskip("playwright.sync_api")
MODELS = Path(os.environ.get("BOOK_APP_MODELS", ROOT.parent / "pdf_book_converter/.cache/huggingface"))
pytestmark = [
    pytest.mark.skipif(not Path(CHROME).exists(), reason="Chrome is not installed"),
    pytest.mark.skipif(not PDF.is_file() or not MODELS.is_dir(), reason="PULSE or the models are missing"),
]


@pytest.fixture
def server(tmp_path):
    """A test app instance on port 8779 (never the office app on 8777) with the real
    converter, one book at a time, one converter worker."""
    settings = tmp_path / "app_settings.yaml"
    settings.write_text(f"port: {PORT}\nbind_address: 127.0.0.1\ndata_folder: {tmp_path / 'data'}\n"
                        f"models_folder: '{MODELS}'\nmax_parallel_jobs: 1\nconverter_workers: 1\n")
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
    yield {"base": base, "data": tmp_path / "data", "settings": settings}
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def tiny(tmp_path):
    """Three tiny PDFs: pages of PULSE (2, 3 and 2 pages)."""
    import pymupdf

    src = pymupdf.open(PDF)
    out = []
    for name, first, last in (("tiny-a.pdf", 19, 20), ("tiny-b.pdf", 46, 48), ("tiny-c.pdf", 69, 70)):
        doc = pymupdf.open()
        doc.insert_pdf(src, from_page=first - 1, to_page=last - 1)
        doc.save(tmp_path / name, garbage=0, deflate=False)
        out.append(tmp_path / name)
    return out


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


def sign_in(pg, base, name, role):
    pg.goto(f"{base}/#/login")
    pg.get_by_test_id("login-name").fill(name)
    pg.get_by_test_id(f"login-{role}").check()
    pg.get_by_test_id("login-go").click()
    pg.get_by_test_id("me").filter(has_text=name).wait_for()


def files_digest(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}  # fmt: skip


def test_queue_three_tiny_books_assign_reviewers_my_books(server, page, tiny, tmp_path):
    base, pg = server["base"], page
    assert "8777" not in server["settings"].read_text()
    sign_in(pg, base, "Asha", "manager")
    pg.goto(f"{base}/#/new")
    pg.get_by_test_id("file-input").set_input_files([str(p) for p in tiny])
    rows = pg.get_by_test_id("batch-row")
    rows.first.wait_for()
    assert rows.count() == 3
    for i in range(3):
        rows.nth(i).get_by_test_id("batch-profile").select_option(index=0)
    pg.get_by_test_id("batch-queue").click()
    pg.wait_for_url("**/#/queue")
    pg.get_by_test_id("queue-row").first.wait_for()
    jobs = {j["name"]: j for j in requests.get(f"{base}/api/jobs").json()["jobs"]}
    ids = [jobs[p.name]["id"] for p in tiny]
    assert all(jobs[p.name]["uploaded_by"] == "Asha" for p in tiny)
    # they convert one after the other, in the order they were queued
    end = time.time() + 1800
    while time.time() < end:
        states = {j["id"]: j for j in requests.get(f"{base}/api/jobs").json()["jobs"]}
        if all(states[i]["state"] in ("converted", "failed") for i in ids):
            break
        running = [i for i in ids if states[i]["state"] == "converting"]
        assert len(running) <= 1
        time.sleep(1)
    assert all(states[i]["state"] == "converted" for i in ids), [states[i].get("failure") for i in ids]
    starts = [states[i]["started_at"] for i in ids]
    assert starts == sorted(starts)
    assert all(states[a]["finished_at"] <= states[b]["started_at"] for a, b in zip(ids, ids[1:]))
    # the manager assigns two reviewers to the first book
    pg.goto(f"{base}/#/")
    row = pg.locator(f"[data-job='{ids[0]}']")
    row.get_by_test_id("assign").click()
    panel = pg.get_by_test_id("assign-panel")
    panel.get_by_test_id("assign-name").first.fill("Ravi")
    panel.get_by_test_id("assign-first").first.fill("1")
    panel.get_by_test_id("assign-last").first.fill("1")
    panel.get_by_test_id("assign-add").click()
    panel.get_by_test_id("assign-name").nth(1).fill("Meera")
    panel.get_by_test_id("assign-save").click()
    pg.locator(f"[data-job='{ids[0]}'] [data-testid=assigned]").wait_for()
    assert "Ravi" in pg.locator(f"[data-job='{ids[0]}'] [data-testid=assigned]").inner_text()
    # a reviewer sees "My books" first, without the manager's buttons
    sign_in(pg, base, "Ravi", "reviewer")
    pg.goto(f"{base}/#/")
    my = pg.get_by_test_id("my-books")
    my.wait_for()
    assert my.locator(f"[data-job='{ids[0]}']").count() == 1
    assert "pages 1–1" in my.inner_text()
    assert pg.get_by_test_id("delete").count() == 0 and pg.get_by_test_id("assign").count() == 0
    audit = [(e["who"], e["action"]) for e in requests.get(f"{base}/api/audit").json()["entries"]]
    assert ("Asha", "upload") in audit and ("Asha", "queue") in audit and ("Asha", "assign") in audit
    # one book's output equals the same PDF converted alone (the converter's command line)
    alone = tmp_path / "alone"
    cache = alone / "cache"
    cache.mkdir(parents=True)
    (cache / "huggingface").symlink_to(MODELS, target_is_directory=True)
    workers = 1  # as the test instance's converter_workers
    env = {**os.environ, "PYTHONPATH": str(BACKEND / "src")}
    subprocess.run([sys.executable, "-B", "-m", "book_core", "run-book", str(tiny[0]), "--out",
                    str(alone / "out"), "--cache-dir", str(cache), "--workers", str(workers)],
                   check=True, env=env, capture_output=True)  # fmt: skip
    in_app = server["data"] / "jobs" / ids[0] / "converter_out"
    assert files_digest(in_app) == files_digest(alone / "out")
