"""App test fixtures: a client on a throw-away data folder with a stand-in converter."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from book_app.api import create_app
from book_app.config import AppSettings

HERE = Path(__file__).parent


def make_pdf(pages: int = 9, text: str = "Test page") -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 100), f"{text} {i + 1}")
    return doc.tobytes()


def make_app(tmp_path: Path, **overrides):
    settings = AppSettings(
        data_folder=str(tmp_path / "data"),
        converter_command=[sys.executable, "-B", str(HERE / "fake_converter.py")],
        base=tmp_path,
        **overrides,
    )
    app = create_app(settings)
    return app, TestClient(app, base_url="http://127.0.0.1:8777")


@pytest.fixture
def app_client(tmp_path):
    app, client = make_app(tmp_path)
    yield app, client
    app.state.converter.stop()


@pytest.fixture
def client(app_client):
    return app_client[1]


@pytest.fixture
def pdf_bytes():
    return make_pdf()


def wait_state(client, job_id: str, states, timeout: float = 60):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in states:
            return job
        time.sleep(0.15)
    raise AssertionError(f"job stayed {job['state']}")


@pytest.fixture
def converted(client, pdf_bytes):
    """A converted job (stand-in converter, built sample book) with profile jaypee_v3."""
    job = client.put("/api/jobs?filename=book.pdf", content=pdf_bytes).json()
    assert (
        client.put(f"/api/jobs/{job['id']}/profile", json={"ref": "jaypee_v3"}).status_code == 200
    )
    assert client.post(f"/api/jobs/{job['id']}/convert").status_code == 200
    return wait_state(client, job["id"], {"converted", "failed"})


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.when == "call":
        item.failed_call = report.failed
    return report
