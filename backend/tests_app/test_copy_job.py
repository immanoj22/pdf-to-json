"""Copy a book: marked COPY, ready at once by sharing the cache (hard links), with or without
the review decisions, never queued by itself."""

import hashlib
import os
from pathlib import Path

from tests_app.conftest import convert_job, wait_state


def _digest(folder: Path) -> dict:
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file() and not p.is_symlink()}  # fmt: skip


def _decide(client, jid):
    review = client.get(f"/api/jobs/{jid}/review").json()["items"]
    if review:
        it = review[0]
        client.post(f"/api/jobs/{jid}/decisions", json={"who": "Asha", "key": it["key"], "item_kind": it["kind"],
                                                        "action": "accept", "item": {}})  # fmt: skip
    return client.get(f"/api/jobs/{jid}/decisions").json()


def test_copy_of_a_converted_book_is_ready_at_once_and_marked(client, pdf_bytes):
    src = convert_job(client, pdf_bytes)
    store = client.app.state.store
    r = client.post(f"/api/jobs/{src['id']}/copy", json={"decisions": "clean"})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["id"] != src["id"] and c["state"] == "converted"  # no conversion, never queued
    assert c["name"].startswith("COPY - ") and c["is_copy"] and c["copy_of"] == src["id"]
    assert c["profile"] == src["profile"] and c["publication"] == store.get(src["id"])["publication"]
    a, b = store.folder(src["id"]), store.folder(c["id"])
    pub = Path(c["publication"]) / "book.json"
    assert os.stat(a / pub).st_ino == os.stat(b / pub).st_ino  # one file on disk, two names
    assert os.stat(a / "input.pdf").st_ino == os.stat(b / "input.pdf").st_ino
    assert not (b / "decisions.json").exists() and not (b / "exports").exists()
    assert client.get(f"/api/jobs/{c['id']}/review").status_code == 200  # reviewable now


def test_copy_with_decisions_keeps_them_apart(client, pdf_bytes):
    src = convert_job(client, pdf_bytes)
    before = _decide(client, src["id"])
    c = client.post(f"/api/jobs/{src['id']}/copy", json={"decisions": "with"}).json()
    kept = client.get(f"/api/jobs/{c['id']}/decisions").json()
    assert [e["id"] for e in kept["events"]] == [e["id"] for e in before["events"]]
    if before["events"]:  # a decision on the copy never reaches the original
        client.post(f"/api/jobs/{c['id']}/decisions", json={"who": "Ravi", "key": "zz", "item_kind": "figure",
                                                            "action": "skip", "item": {}})  # fmt: skip
        assert len(client.get(f"/api/jobs/{src['id']}/decisions").json()["events"]) == len(before["events"])
    clean = client.post(f"/api/jobs/{src['id']}/copy", json={"decisions": "clean"}).json()
    assert client.get(f"/api/jobs/{clean['id']}/decisions").json()["events"] == []


def test_converting_or_deleting_a_copy_leaves_the_original_untouched(client, pdf_bytes):
    src = convert_job(client, pdf_bytes)
    store = client.app.state.store
    original = _digest(store.folder(src["id"]) / "cache"), _digest(store.folder(src["id"]) / "converter_out")
    c = client.post(f"/api/jobs/{src['id']}/copy", json={}).json()
    assert client.post(f"/api/jobs/{c['id']}/convert").status_code == 200  # a manual Start
    assert wait_state(client, c["id"], {"converted", "failed"})["state"] == "converted"
    assert client.delete(f"/api/jobs/{c['id']}?confirm=yes").status_code == 200
    assert (_digest(store.folder(src["id"]) / "cache"), _digest(store.folder(src["id"]) / "converter_out")) == original
    assert client.get(f"/api/jobs/{src['id']}/review").status_code == 200


def test_copy_of_an_unconverted_book_waits_for_a_manual_start(client, pdf_bytes):
    up = client.put("/api/jobs?filename=A.pdf", content=pdf_bytes).json()
    job = up.get("job") or up
    c = client.post(f"/api/jobs/{job['id']}/copy", json={"decisions": "with"}).json()
    assert c["state"] == "uploaded" and c["name"] == "COPY - A.pdf" and not c.get("shared_cache")
    assert client.post(f"/api/jobs/{job['id']}/copy", json={"decisions": "maybe"}).status_code == 422


def test_reviewer_cannot_copy(client, pdf_bytes):
    src = convert_job(client, pdf_bytes)
    r = client.post(f"/api/jobs/{src['id']}/copy", json={}, headers={"X-Role": "reviewer", "X-User": "R"})
    assert r.status_code == 403
    assert all("isbn" in j for j in client.get("/api/jobs").json()["jobs"])
