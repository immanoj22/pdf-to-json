"""Copy a job: same PDF/profile/details, no converter cache, rebuilt when converted."""

from tests_app.conftest import convert_job, wait_state


def test_copy_rebuilds_from_pdf(client, pdf_bytes):
    src = convert_job(client, pdf_bytes)
    r = client.post(f"/api/jobs/{src['id']}/copy", json={})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["id"] != src["id"] and c["state"] == "uploaded"
    assert c["name"].endswith("(copy)") and c["profile"] == src["profile"] and c["copy_of"] == src["id"]
    folder = client.app.state.store.folder(c["id"])
    assert (folder / "input.pdf").is_file() and not (folder / "cache").exists()
    assert not (folder / "converter_out").exists()
    done = client.post(f"/api/jobs/{c['id']}/convert").json()
    assert wait_state(client, done["id"], {"converted", "failed"})["state"] == "converted"


def test_copy_and_convert_and_reviewer_refused(client, pdf_bytes):
    src = convert_job(client, pdf_bytes)
    c = client.post(f"/api/jobs/{src['id']}/copy", json={"convert": True}).json()
    assert c["state"] == "queued"
    wait_state(client, c["id"], {"converted", "failed"})
    r = client.post(f"/api/jobs/{src['id']}/copy", json={}, headers={"X-Role": "reviewer", "X-User": "R"})
    assert r.status_code == 403
    assert all("isbn" in j for j in client.get("/api/jobs").json()["jobs"])
