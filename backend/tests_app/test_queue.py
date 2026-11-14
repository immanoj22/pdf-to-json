"""The conversion queue (order, pause, move, cancel, restart), reviewers' assignments, the two
roles and the audit log (stand-in converter)."""

import time

import pytest

from tests_app.conftest import make_app, make_pdf, wait_state

MANAGER = {"X-User": "Asha", "X-Role": "manager"}
REVIEWER = {"X-User": "Ravi", "X-Role": "reviewer"}


def upload(client, name, headers=MANAGER):
    r = client.put(f"/api/jobs?filename={name}&profile=jaypee_v3", content=make_pdf(3), headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def started_order(client, ids, timeout=60):
    """The jobs in the order they started converting."""
    seen, end = [], time.time() + timeout
    while len(seen) < len(ids) and time.time() < end:
        for job in client.get("/api/jobs").json()["jobs"]:
            if job["id"] in ids and job.get("started_at") and job["id"] not in seen:
                seen.append(job["id"])
        time.sleep(0.05)
    jobs = {j["id"]: j for j in client.get("/api/jobs").json()["jobs"]}
    return sorted(seen, key=lambda j: jobs[j]["started_at"])


def test_books_convert_in_queue_order_with_moves_and_pauses(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOK_APP_FAKE_DELAY", "0.6")
    app, client = make_app(tmp_path)
    try:
        jobs = [upload(client, f"b{i}.pdf") for i in range(4)]
        assert jobs[0]["uploaded_by"] == "Asha" and jobs[0]["profile"].startswith("jaypee_v3")
        ids = [j["id"] for j in jobs]
        for i in ids:
            assert client.post(f"/api/jobs/{i}/convert", headers=MANAGER).status_code == 200
        q = client.get("/api/queue").json()["queue"]
        assert [r["id"] for r in q if r["position"]][:4] == ids
        # b3 moves up ahead of b2; b1 is paused; b2 is cancelled while waiting
        client.post(f"/api/queue/{ids[3]}/move", json={"direction": "up"}, headers=MANAGER)
        client.post(f"/api/queue/{ids[1]}/pause", json={"paused": True}, headers=MANAGER)
        client.post(f"/api/jobs/{ids[2]}/cancel", headers=MANAGER)
        wait_state(client, ids[3], {"converted"})
        assert client.get(f"/api/jobs/{ids[1]}").json()["state"] == "queued"  # paused: waits
        client.post(f"/api/queue/{ids[1]}/pause", json={"paused": False}, headers=MANAGER)
        wait_state(client, ids[1], {"converted"})
        order = started_order(client, ids)
        assert order == [ids[0], ids[3], ids[1]]
        assert client.get(f"/api/jobs/{ids[2]}").json()["state"] == "cancelled"
        q = client.get("/api/queue").json()
        assert all(r["position"] is None for r in q["queue"])
        actions = [(e["who"], e["action"]) for e in client.get("/api/audit").json()["entries"]]
        assert ("Asha", "upload") in actions and ("Asha", "move") in actions
        assert ("Asha", "pause") in actions and ("Asha", "cancel") in actions
    finally:
        app.state.converter.stop()


def test_a_failed_book_does_not_block_the_queue(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    try:
        a, b = upload(client, "a.pdf"), upload(client, "b.pdf")
        (tmp_path / "data" / "jobs" / a["id"] / "FAIL").write_text("x")  # the stand-in fails it
        client.post(f"/api/jobs/{a['id']}/convert", headers=MANAGER)
        client.post(f"/api/jobs/{b['id']}/convert", headers=MANAGER)
        assert wait_state(client, a["id"], {"failed", "converted"})["state"] == "failed"
        assert wait_state(client, b["id"], {"converted", "failed"})["state"] == "converted"
        row = next(r for r in client.get("/api/queue").json()["queue"] if r["id"] == a["id"])
        assert row["state"] == "failed" and row["failure"]["message"]
    finally:
        app.state.converter.stop()


def test_the_queue_survives_a_restart(tmp_path):
    from book_app.api import create_app
    from fastapi.testclient import TestClient

    app, client = make_app(tmp_path)
    jobs = [upload(client, f"r{i}.pdf") for i in range(3)]
    ids = [j["id"] for j in jobs]
    # as if the app stopped with r0 converting and r1, r2 waiting (r2 first)
    app.state.converter.stop()
    app.state.store.update(ids[0], state="converting", started_at="2026-11-14T00:00:00+00:00")
    for i in ids[1:]:
        app.state.store.update(i, state="queued")
    app.state.converter.queue.save({"order": [ids[2], ids[1]], "paused": []})
    app2 = create_app(app.state.settings)
    c2 = TestClient(app2, base_url="http://127.0.0.1:8777")
    try:
        for i in ids:
            wait_state(c2, i, {"converted", "failed"})
        assert started_order(c2, ids) == [ids[0], ids[2], ids[1]]  # the running one first
        assert c2.get(f"/api/jobs/{ids[0]}").json().get("resumed_at")
    finally:
        app2.state.converter.stop()


def test_reviewers_are_assigned_and_see_their_books(tmp_path):
    app, client = make_app(tmp_path)
    try:
        job = upload(client, "book.pdf")
        client.post(f"/api/jobs/{job['id']}/convert", headers=MANAGER)
        wait_state(client, job["id"], {"converted"})
        rows = [{"name": "Ravi", "first": 1, "last": 2}, {"name": "Meera"}]
        bad = client.put(f"/api/jobs/{job['id']}/assignments", json={"reviewers": [{"name": "X", "first": 3, "last": 99}]}, headers=MANAGER)
        assert bad.status_code == 422
        ok = client.put(f"/api/jobs/{job['id']}/assignments", json={"reviewers": rows}, headers=MANAGER)
        assert ok.status_code == 200
        listed = next(j for j in client.get("/api/jobs").json()["jobs"] if j["id"] == job["id"])
        assert [a["name"] for a in listed["assigned_to"]] == ["Ravi", "Meera"]
        assert listed["assigned_to"][1]["first"] is None  # the whole book
        # a reviewer reviews; a reviewer cannot upload, assign, export or delete
        assert client.put("/api/jobs?filename=x.pdf", content=make_pdf(2), headers=REVIEWER).status_code == 403
        for method, url, body in [
            ("put", f"/api/jobs/{job['id']}/assignments", {"reviewers": rows}),
            ("post", f"/api/jobs/{job['id']}/export", {"who": "Ravi"}),
            ("delete", f"/api/jobs/{job['id']}?confirm=yes", None),
            ("post", f"/api/jobs/{job['id']}/convert", None),
        ]:
            r = getattr(client, method)(url, headers=REVIEWER, **({"json": body} if body is not None else {}))
            assert r.status_code == 403 and r.json()["code"] == "manager_only", url
        assert [e["action"] for e in client.get(f"/api/audit?job={job['id']}").json()["entries"]] == [
            "upload", "queue", "assign"]
    finally:
        app.state.converter.stop()


@pytest.mark.parametrize("role", ["", "reviewer"])
def test_unknown_or_missing_roles(tmp_path, role):
    app, client = make_app(tmp_path)
    try:
        headers = {"X-User": "Z", "X-Role": "boss"} if role else {}
        r = client.put("/api/jobs?filename=x.pdf", content=make_pdf(2), headers=headers)
        assert r.status_code == (403 if role else 200)  # an unknown role is a reviewer
    finally:
        app.state.converter.stop()
