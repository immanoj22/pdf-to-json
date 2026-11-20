"""The edited book saved on disk, the worker pool, and the "preparing" answer (202).

A book that needs a replay is built in a worker process; the page that asked gets 202 at once and
asks again. The same work asked for by several people runs once, work on different books does not
wait for each other, and a restart loads the saved copy instead of replaying the edits."""

from __future__ import annotations

import threading
import time

import pytest

from book_app import effective
from tests_app.conftest import convert_job, confirm_parts, make_app, make_pdf


def until_ok(get, timeout=90):
    """Ask again while the answer is 202; returns the final response and how many 202s came."""
    end, waited = time.time() + timeout, 0
    while time.time() < end:
        r = get()
        if r.status_code != 202:
            return r, waited
        assert r.json()["code"] == "preparing" and r.json()["retry_after"] >= 1
        waited += 1
        time.sleep(0.3)
    raise AssertionError("still preparing")


@pytest.fixture
def pool_app(tmp_path):
    """The app with a real pool of one worker process, on a converted book with an edit."""
    app, client = make_app(tmp_path, build_workers=1)
    app.state.service.COLD_INLINE = 0  # a book this small is otherwise replayed in the request
    job = convert_job(client, make_pdf(9))
    jid = job["id"]
    confirm_parts(client, jid)
    para = next(u for u in client.get(f"/api/jobs/{jid}/pages/7/units").json()["units"]
                if u["type"] == "paragraph" and len(u["lines"]) > 1)  # fmt: skip
    r = client.post(
        f"/api/jobs/{jid}/edits",
        json={"who": "Asha", "edit": {"op": "split", "unit": para["id"], "line": 1}},
    )
    assert r.status_code == 200, r.text
    yield app, client, jid, tmp_path
    app.state.service.builds.stop()
    app.state.converter.stop()


def test_a_review_list_that_needs_work_answers_202_then_the_list(pool_app):
    app, client, jid, _ = pool_app
    first = client.get(f"/api/jobs/{jid}/review")
    assert first.status_code == 202 and first.json()["code"] == "preparing"
    assert first.json()["what"] in ("review list", "book")
    r, waited = until_ok(lambda: client.get(f"/api/jobs/{jid}/review"))
    assert r.status_code == 200 and waited >= 0 and "items" in r.json()
    t = time.time()
    again = client.get(f"/api/jobs/{jid}/review")
    assert again.status_code == 200 and time.time() - t < 1.5  # nothing to wait for now


def test_the_same_request_from_many_people_runs_the_work_once(pool_app, monkeypatch):
    from concurrent.futures import ProcessPoolExecutor

    app, client, jid, _ = pool_app
    submitted = []
    real = ProcessPoolExecutor.submit
    monkeypatch.setattr(
        ProcessPoolExecutor,
        "submit",
        lambda self, fn, *a, **k: submitted.append(fn.__name__) or real(self, fn, *a, **k),
    )
    answers = []
    threads = [threading.Thread(target=lambda: answers.append(client.get(f"/api/jobs/{jid}/review")))
               for _ in range(6)]  # fmt: skip
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert {r.status_code for r in answers} <= {202}
    until_ok(lambda: client.get(f"/api/jobs/{jid}/review"))
    assert submitted.count("preview_task") == 1  # six askers, one review-list run


def test_the_edited_book_is_saved_and_a_restart_loads_it(pool_app):
    app, client, jid, tmp_path = pool_app
    until_ok(lambda: client.get(f"/api/jobs/{jid}/review"))
    saved = list((tmp_path / "data" / "jobs" / jid / "effective").glob("*.json.gz"))
    assert saved and all(
        p.with_name(p.name.replace(".json.gz", ".meta.json")).exists() for p in saved
    )
    # a new app on the same data folder: the chapter list comes at once, no 202, no pool work
    from book_app.api import create_app

    app2 = create_app(app.state.settings)
    from fastapi.testclient import TestClient

    c2 = TestClient(app2, base_url="http://127.0.0.1:8777")
    try:
        t = time.time()
        r = c2.get(f"/api/jobs/{jid}/chapters")
        assert r.status_code == 200 and "chapters" in r.json()
        assert not app2.state.service.builds.futures  # loaded from disk, nothing was built
        assert time.time() - t < 5
    finally:
        app2.state.service.builds.stop()
        app2.state.converter.stop()


def test_a_new_edit_after_a_restart_is_applied_in_the_request_not_replayed(pool_app):
    app, client, jid, _ = pool_app
    until_ok(lambda: client.get(f"/api/jobs/{jid}/chapters"))
    from book_app.api import create_app
    from fastapi.testclient import TestClient

    app2 = create_app(app.state.settings)
    c2 = TestClient(app2, base_url="http://127.0.0.1:8777")
    try:
        assert c2.get(f"/api/jobs/{jid}/chapters").status_code == 200  # loads the saved copy
        para = next(u for u in c2.get(f"/api/jobs/{jid}/pages/7/units").json()["units"]
                    if u["type"] == "paragraph")  # fmt: skip
        r = c2.post(
            f"/api/jobs/{jid}/edits",
            json={"who": "Ravi", "edit": {"op": "heading_set", "unit": para["id"], "level": 2}},
        )
        assert r.status_code == 200, r.text
        assert not app2.state.service.builds.futures  # no worker was needed for one edit
    finally:
        app2.state.service.builds.stop()
        app2.state.converter.stop()


def test_a_book_in_the_pool_does_not_block_another_book(tmp_path):
    app, client = make_app(tmp_path, build_workers=2)
    app.state.service.COLD_INLINE = 0
    try:
        a = convert_job(client, make_pdf(9))["id"]
        b = convert_job(client, make_pdf(5))["id"]
        for jid in (a, b):
            confirm_parts(client, jid)
        started = time.time()
        ra = client.get(f"/api/jobs/{a}/review")  # starts the work of book a
        rb = client.get(f"/api/jobs/{b}/review")  # book b is asked at once, not after a
        assert ra.status_code == 202 and rb.status_code == 202 and time.time() - started < 5
        assert client.get("/api/profiles").status_code == 200  # quick requests are never held
        for jid in (a, b):
            r, _ = until_ok(lambda jid=jid: client.get(f"/api/jobs/{jid}/review"))
            assert r.status_code == 200
    finally:
        app.state.service.builds.stop()
        app.state.converter.stop()


def test_saved_states_are_found_by_prefix_and_dropped_when_the_edit_code_changes(
    tmp_path, monkeypatch
):
    folder = tmp_path / "job"
    keys = ["k1", "k2", "k3"]
    for n in (1, 2, 3):
        effective.save(
            folder,
            f"s{n}",
            effective.meta_of("pub", keys[:n], {"m": 1}, False),
            {"pre": {"n": n}, "applied": [], "failed": []},
        )
    found = effective.find_resume(folder, "pub", {"m": 1}, keys + ["k4"])
    assert found["pre"] == {"n": 3} and found["keys"] == keys  # the longest prefix
    assert effective.find_resume(folder, "pub", {"m": 1}, ["k1", "x"])["pre"] == {"n": 1}
    assert effective.find_resume(folder, "pub", {"m": 2}, keys) is None  # other list marks
    assert effective.find_resume(folder, "other", {"m": 1}, keys) is None  # other publication
    assert effective.state_key("pub", keys, {}, False) != effective.state_key("pub", keys, {}, True)
    before = effective.state_key("pub", keys, {}, False)
    monkeypatch.setattr(effective, "code_version", lambda: "changed")
    assert effective.state_key("pub", keys, {}, False) != before  # new edit code: not reused
    assert effective.find_resume(folder, "pub", {"m": 1}, keys) is None
    for n in (4, 5):  # only the newest few are kept
        effective.save(
            folder,
            f"s{n}",
            effective.meta_of("pub", keys, {}, False),
            {"pre": {}, "applied": [], "failed": []},
        )
    assert len(list((folder / "effective").glob("*.meta.json"))) == effective.KEEP


# ------------------------------------------------------------------ the review list in pages


def test_the_review_list_comes_in_pages_with_the_totals_of_the_whole_list(client, converted):
    jid = converted["id"]
    full = client.get(f"/api/jobs/{jid}/review").json()
    n = full["total"]
    assert n == len(full["items"]) and n >= 3 and full["has_more"] is False
    seen = []
    for offset in range(0, n, 2):
        page = client.get(f"/api/jobs/{jid}/review?offset={offset}&limit=2").json()
        assert page["total"] == n and page["decided"] == full["decided"] and len(page["items"]) <= 2
        assert page["has_more"] == (offset + 2 < n) and page["offset"] == offset
        seen += page["items"]
    assert client.get(f"/api/jobs/{jid}/review?offset={n}&limit=2").json()["items"] == []
    assert seen == full["items"]  # the pages are the list, in order, nothing twice
    # a decision shows in the page that holds the item and in the totals
    item = full["items"][-1]
    r = client.post(f"/api/jobs/{jid}/decisions",
                    json={"who": "Asha", "key": item["key"], "action": "accept", "item": item})
    assert r.status_code == 200, r.text
    last = client.get(f"/api/jobs/{jid}/review?offset={n - 1}&limit=5").json()
    assert last["items"][0]["decision"]["action"] == "accept" and last["decided"] == full["decided"] + 1
    assert client.get(f"/api/jobs/{jid}/review?limit=0").status_code == 422


def test_the_static_part_of_the_list_is_built_once_per_edit_list(client, converted, monkeypatch):
    from book_app.service import Service

    jid = converted["id"]
    calls = []
    real = Service._review_static
    monkeypatch.setattr(Service, "_review_static",
                        lambda self, *a: calls.append(1) or real(self, *a))
    for _ in range(4):
        assert client.get(f"/api/jobs/{jid}/review?offset=0&limit=3").status_code == 200
    assert len(calls) == 1  # four requests, one build


# ------------------------------------------------------------------ exports in the pool


def confirm(client, jid):
    d, _ = until_ok(lambda: client.get(f"/api/jobs/{jid}/details"))
    assert client.put(f"/api/jobs/{jid}/details", json=d.json()["details"]).status_code == 200


def test_an_export_is_made_in_a_worker_and_two_books_export_at_once(tmp_path, monkeypatch):
    from concurrent.futures import ProcessPoolExecutor

    app, client = make_app(tmp_path, build_workers=2)
    app.state.service.COLD_INLINE = 0
    sent = []
    real = ProcessPoolExecutor.submit
    monkeypatch.setattr(ProcessPoolExecutor, "submit",
                        lambda self, fn, *a, **k: sent.append(fn.__name__) or real(self, fn, *a, **k))
    try:
        ids = []
        for pages in (9, 6):
            jid = convert_job(client, make_pdf(pages))["id"]
            confirm_parts(client, jid)
            confirm(client, jid)
            ids.append(jid)
        answers = {}

        def go(jid):
            answers[jid] = client.post(f"/api/jobs/{jid}/export",
                                       json={"who": "Asha", "allow_alt_text_placeholders": True})

        threads = [threading.Thread(target=go, args=(j,)) for j in ids]
        t0 = time.time()
        [t.start() for t in threads]
        probe = time.time()
        assert client.get("/api/profiles").status_code == 200
        assert time.time() - probe < 3  # the pages stay answerable while the exports run
        [t.join() for t in threads]
        assert all(a.status_code == 200 for a in answers.values()), {k: a.text[:200] for k, a in answers.items()}
        assert sent.count("export_task") == 2  # one format each, in a worker
        for jid in ids:
            assert len(client.get(f"/api/jobs/{jid}/exports").json()["exports"]) == 1
        assert time.time() - t0 < 120
    finally:
        app.state.service.builds.stop()
        app.state.converter.stop()


def test_a_worker_ends_when_the_app_is_killed(tmp_path):
    """The pool's workers must not outlive the app (a killed app left them holding memory)."""
    import os
    import signal
    import subprocess
    import sys

    code = (
        "import time\nfrom book_app.builds import Builds, _noop\n"
        "b = Builds(1); b.warm(); time.sleep(1.5)\n"
        "f = b._pool().submit(__import__('os').getpid); print(f.result(), flush=True)\n"
        "time.sleep(60)\n"
    )
    env = {**os.environ, "PYTHONPATH": str(__import__("pathlib").Path(effective.__file__).parents[1])}
    proc = subprocess.Popen([sys.executable, "-B", "-c", code], stdout=subprocess.PIPE, env=env)
    worker = int(proc.stdout.readline())
    os.kill(proc.pid, signal.SIGKILL)  # no chance to shut the pool down
    proc.wait()
    end = time.time() + 20
    while time.time() < end:
        try:
            os.kill(worker, 0)
        except ProcessLookupError:
            return
        time.sleep(0.5)
    os.kill(worker, signal.SIGKILL)
    raise AssertionError("the worker outlived the app")
