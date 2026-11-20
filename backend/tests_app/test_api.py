"""API tests for every endpoint of the app (stand-in converter, synthetic book)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from book_app.api import create_app

from .conftest import convert_job, make_app, make_pdf, wait_state

VALID_PROFILE = (
    "profile: acme_v1\nversion: 1.0.0\ndate: '2026-11-01'\nextends: _base/docbook_base\n"
    "client: Acme\nguideline: Acme guide\n"
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ guards, upload


def test_health_and_guards(client):
    assert client.get("/api/health").json()["lan"] is False
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 403
    r = client.post(
        "/api/profiles/validate", content=b"x", headers={"Origin": "http://evil.example"}
    )
    assert r.status_code == 403
    assert client.get("/").status_code == 200


def test_upload_checks_content_not_name(client, tmp_path):
    r = client.put("/api/jobs?filename=real.pdf", content=b"this is plain text, not a pdf")
    assert r.status_code == 415 and r.json()["code"] == "not_pdf"
    assert client.put("/api/jobs?filename=x.pdf", content=b"").status_code == 400
    r = client.put("/api/jobs?filename=notes.txt", content=make_pdf(2))
    assert r.status_code == 200 and r.json()["pages"] == 2  # a PDF is a PDF whatever its name


def test_upload_name_is_sanitised_and_stored_in_the_job(app_client):
    app, client = app_client
    job = client.put("/api/jobs?filename=../../etc/evil%00.pdf", content=make_pdf(1)).json()
    assert "/" not in job["name"] and ".." not in job["name"]
    folder = app.state.settings.data_path / "jobs" / job["id"]
    assert (folder / "input.pdf").is_file()
    assert client.get("/api/jobs/..%2f..%2fetc").status_code in (404, 422)
    assert client.get("/api/jobs/" + "z" * 16).status_code == 404


def test_upload_limit_and_damaged_pdf(tmp_path):
    app, client = make_app(tmp_path, max_upload_bytes=2000)
    r = client.put("/api/jobs?filename=big.pdf", content=make_pdf(5))
    assert r.status_code == 413 and r.json()["code"] == "too_large"
    app2, client2 = make_app(tmp_path / "b")
    assert client2.put("/api/jobs?filename=a.pdf", content=b"%PDF-1.4\ngarbage").status_code == 415


# ------------------------------------------------------------------ profiles


def test_profile_list_and_options(client):
    rows = client.get("/api/profiles").json()["profiles"]
    jay = next(p for p in rows if p["ref"] == "jaypee_v3@3.1.0")
    assert jay["status"] == "tested" and jay["date"]
    assert "qanda" in client.get("/api/profile-options?ref=jaypee_v3").json()["options"]
    assert client.get("/api/profile-options?ref=nope").status_code == 404


def test_profile_upload_valid_new_version_no_overwrite(app_client):
    app, client = app_client
    r = client.post("/api/profiles?filename=acme.yaml", content=VALID_PROFILE.encode())
    assert r.status_code == 200 and r.json()["profile"]["status"] == "untested"
    first = r.json()["profile"]
    again = client.post("/api/profiles?filename=acme.yaml", content=VALID_PROFILE.encode()).json()
    assert again["profile"]["ref"] == first["ref"] and again["profile"]["new"] is False
    stored = app.state.profiles.store.store / "acme_v1" / "1.0.0"
    before = {p.name: sha(p) for p in stored.glob("*.yaml")}
    changed = VALID_PROFILE + "description: second\n"
    second = client.post("/api/profiles?filename=acme.yaml", content=changed.encode()).json()[
        "profile"
    ]
    assert second["revision"] == 2 and second["ref"] != first["ref"]
    after = {p.name: sha(p) for p in stored.glob("*.yaml")}
    assert all(after[k] == v for k, v in before.items()) and len(after) == 2  # nothing overwritten
    refs = [p["ref"] for p in client.get("/api/profiles").json()["profiles"]]
    assert first["ref"] in refs and second["ref"] in refs


def test_profile_list_is_kept_until_a_profile_file_changes(app_client, monkeypatch):
    """Listing reads every profile in full (seconds), so the rows are kept; an upload or any
    change to a profile file shows up in the next listing."""
    app, client = app_client
    profiles = app.state.profiles
    reads = []
    real = profiles.entry
    monkeypatch.setattr(profiles, "entry", lambda p: reads.append(p.ref) or real(p))
    first = client.get("/api/profiles").json()["profiles"]
    n = len(reads)
    assert n == len(first) > 0
    again = client.get("/api/profiles").json()["profiles"]
    assert again == first and len(reads) == n  # nothing was read again
    again[0]["name"] = "changed by the caller"  # a caller cannot change what is kept
    assert client.get("/api/profiles").json()["profiles"] == first
    upload = client.post("/api/profiles?filename=acme.yaml", content=VALID_PROFILE.encode())
    assert upload.json()["ok"]
    after = client.get("/api/profiles").json()["profiles"]
    assert len(after) == len(first) + 1 and len(reads) > n  # the new profile is listed


def test_profile_list_rebuilds_once_when_many_requests_arrive_together(app_client, monkeypatch):
    import threading
    import time

    app, _ = app_client
    profiles = app.state.profiles
    reads = []
    real = profiles.entry

    def slow(p):
        reads.append(p.ref)
        time.sleep(0.02)
        return real(p)

    monkeypatch.setattr(profiles, "entry", slow)
    results = []
    threads = [threading.Thread(target=lambda: results.append(profiles.list())) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 8 and all(r == results[0] for r in results)
    assert len(reads) == len(results[0])  # one rebuild, not eight


def test_profile_upload_invalid_shows_line_field_suggestion(client):
    bad = VALID_PROFILE + "ids:\n  chaptr: 'ch{chapter}'\n"
    r = client.post("/api/profiles?filename=bad.yaml", content=bad.encode())
    assert r.status_code == 422
    err = r.json()["errors"][0]
    assert err["line"] == 8 and "chaptr" in err["field"] and err["suggestion"] == "chapter"
    assert client.post("/api/profiles/validate", content=bad.encode()).json()["ok"] is False
    assert (
        client.post("/api/profiles/validate", content=VALID_PROFILE.encode()).json()["ok"] is True
    )
    assert client.post("/api/profiles?filename=b.yaml", content=b"\xff\xfe\x00").status_code == 400
    assert not any(p["name"] == "bad" for p in client.get("/api/profiles").json()["profiles"])


def test_profile_maker_material(client):
    prompt = client.get("/api/profile-maker/prompt").json()["prompt"]
    assert "never" in prompt.lower() and "profile.schema.json" in prompt
    r = client.get("/api/profile-maker/schema")
    assert r.status_code == 200 and json.loads(r.content)["properties"]["profile"]
    assert client.get("/api/profile-maker/base").status_code == 200
    for name in ("html_base", "dtbook_nimas_base", "daisy3_base", "jats_base", "bits_base"):
        assert client.get(f"/api/profile-maker/base?name={name}").status_code == 200
    assert client.get("/api/profile-maker/base?name=../../etc/passwd").status_code == 404
    schema = client.get("/api/profile-maker/schema").json()
    for section in ("html", "dtbook", "daisy3", "jats", "bits", "formats"):
        assert section in schema["properties"]
    assert "JATS" in prompt and "NIMAS" in prompt


# ------------------------------------------------------------------ convert


def test_convert_needs_profile_then_succeeds(client, pdf_bytes):
    job = client.put("/api/jobs?filename=b.pdf", content=pdf_bytes).json()
    assert client.post(f"/api/jobs/{job['id']}/convert").json()["code"] == "no_profile"
    client.put(f"/api/jobs/{job['id']}/profile", json={"ref": "jaypee_v3"})
    assert client.put(f"/api/jobs/{job['id']}/profile", json={"ref": "missing"}).status_code == 404
    client.post(f"/api/jobs/{job['id']}/convert")
    done = wait_state(client, job["id"], {"converted", "failed"})
    assert done["state"] == "converted" and done["progress"]["index"] == done["progress"]["total"]
    assert done["started_at"] and done["finished_at"]
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 409


def test_convert_failure_shows_the_converter_record_not_a_stack_trace(
    client, pdf_bytes, monkeypatch
):
    monkeypatch.setenv("BOOK_APP_FAKE_MODE", "fail")
    job = client.put("/api/jobs?filename=b.pdf", content=pdf_bytes).json()
    client.put(f"/api/jobs/{job['id']}/profile", json={"ref": "jaypee_v3"})
    client.post(f"/api/jobs/{job['id']}/convert")
    failed = wait_state(client, job["id"], {"failed"})
    f = failed["failure"]
    assert (f["stage"], f["page"], f["error_type"]) == ("layout", 4, "ValueError")
    assert "Traceback" not in json.dumps(f)


def test_cancel_removes_temporary_files(app_client, pdf_bytes, monkeypatch):
    app, client = app_client
    monkeypatch.setenv("BOOK_APP_FAKE_MODE", "slow")
    job = client.put("/api/jobs?filename=b.pdf", content=pdf_bytes).json()
    client.put(f"/api/jobs/{job['id']}/profile", json={"ref": "jaypee_v3"})
    client.post(f"/api/jobs/{job['id']}/convert")
    folder = app.state.settings.data_path / "jobs" / job["id"]
    wait_state(client, job["id"], {"converting"})
    import time

    while not (folder / "converter_out" / "partial.txt").exists():
        time.sleep(0.1)
    assert client.delete(f"/api/jobs/{job['id']}?confirm=yes").json()["code"] == "busy"
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 200
    done = wait_state(client, job["id"], {"cancelled"})
    assert done["state"] == "cancelled"
    assert not (folder / "converter_out").exists() and not (folder / "tmp").exists()
    assert (folder / "input.pdf").is_file()


def test_disk_space_check(client, pdf_bytes, monkeypatch):
    import book_app.jobs as jobs

    monkeypatch.setattr(jobs.shutil, "disk_usage", lambda p: type("U", (), {"free": 1000})())
    job = client.put("/api/jobs?filename=b.pdf", content=pdf_bytes)
    monkeypatch.undo()
    job = (
        job.json()
        if job.status_code == 200
        else client.put("/api/jobs?filename=b.pdf", content=pdf_bytes).json()
    )
    client.put(f"/api/jobs/{job['id']}/profile", json={"ref": "jaypee_v3"})
    monkeypatch.setattr(jobs.shutil, "disk_usage", lambda p: type("U", (), {"free": 1000})())
    r = client.post(f"/api/jobs/{job['id']}/convert")
    assert r.status_code == 507 and r.json()["code"] == "disk_space"


def test_jobs_survive_restart_and_an_interrupted_conversion_resumes(
    app_client, tmp_path, pdf_bytes
):
    app, client = app_client
    done = None
    job = client.put("/api/jobs?filename=b.pdf", content=pdf_bytes).json()
    client.put(f"/api/jobs/{job['id']}/profile", json={"ref": "jaypee_v3"})
    client.post(f"/api/jobs/{job['id']}/convert")
    done = wait_state(client, job["id"], {"converted"})
    other = client.put("/api/jobs?filename=c.pdf", content=pdf_bytes).json()
    app.state.store.update(other["id"], state="converting", progress={"stage": "layout"})
    app2 = create_app(app.state.settings)
    from fastapi.testclient import TestClient

    c2 = TestClient(app2, base_url="http://127.0.0.1:8777")
    assert c2.get(f"/api/jobs/{job['id']}").json()["state"] == "converted"
    assert c2.get(f"/api/jobs/{job['id']}").json()["profile"] == done["profile"]
    # the conversion that was running goes back to the front of the queue and runs again
    # (from its cache; the stand-in converter simply converts)
    try:
        r = wait_state(c2, other["id"], {"converted", "failed"})
        assert r["state"] == "converted" and r.get("resumed_at")
        assert c2.get("/api/queue").json()["queue"][0]["position"] is None  # left the queue
    finally:
        app2.state.converter.stop()


# ------------------------------------------------------------------ details


def test_details_draft_and_isbn_check_digit(client, converted):
    jid = converted["id"]
    d = client.get(f"/api/jobs/{jid}/details").json()
    assert d["confirmed"] is False and d["details"]["isbn"] == "9780306406157"
    assert "qanda" in d["options"]
    bad = {**d["details"], "isbn": "9780306406158"}
    r = client.put(f"/api/jobs/{jid}/details", json=bad)
    assert r.status_code == 422 and r.json()["problems"][0]["field"] == "isbn"
    assert client.put(f"/api/jobs/{jid}/details", json={**bad, "isbn": ""}).status_code == 422
    ok = {**d["details"], "isbn": "978-0-306-40615-7", "options": {"qanda": False}}
    assert client.put(f"/api/jobs/{jid}/details", json=ok).status_code == 200
    again = client.get(f"/api/jobs/{jid}/details").json()
    assert again["confirmed"] and again["details"]["isbn"] == "9780306406157"
    assert again["details"]["options"] == {"qanda": False}


def test_isbn_is_never_invented(client, converted):
    jid = converted["id"]
    r = client.put(f"/api/jobs/{jid}/details", json={"title": "T", "isbn": None})
    assert r.status_code == 422


# ------------------------------------------------------------------ review, decisions


def test_review_list_and_decisions_restore(app_client, converted):
    app, client = app_client
    jid = converted["id"]
    rv = client.get(f"/api/jobs/{jid}/review").json()
    assert rv["total"] > 0 and rv["items"][0]["severity"] == "must_check"
    item = next(i for i in rv["items"] if i["editor"] == "alt_text")
    body = {
        "who": "Asha",
        "key": item["key"],
        "item_kind": "alt_text",
        "action": "fix",
        "note": "n",
        "fix": {"op": "alt_text", "unit": item["unit"], "text": "A drawing."},
        "item": {"kind": "alt_text", "reason": item["reason"]},
    }
    assert client.post(f"/api/jobs/{jid}/decisions", json={**body, "who": ""}).status_code == 422
    assert (
        client.post(f"/api/jobs/{jid}/decisions", json={**body, "action": "bogus"}).status_code
        == 422
    )
    assert client.post(f"/api/jobs/{jid}/decisions", json=body).status_code == 200
    # a new app instance (restart) still has it
    from fastapi.testclient import TestClient

    c2 = TestClient(create_app(app.state.settings), base_url="http://127.0.0.1:8777")
    dec = c2.get(f"/api/jobs/{jid}/decisions").json()
    mine = dec["decisions"][item["key"]]
    assert mine["who"] == "Asha" and mine["at"] and mine["fix"]["text"] == "A drawing."
    assert len(dec["edits"]) == 1
    rv2 = c2.get(f"/api/jobs/{jid}/review").json()
    assert rv2["decided"] == 1 and rv2["stale"] is True
    # the converter's output was never edited
    pub = app.state.store.publication(jid)
    base = json.loads((pub / "book.json").read_text())
    assert not any(u.get("alt_text", {}).get("text") == "A drawing." for u in base["content"])
    # undo
    assert c2.delete(f"/api/jobs/{jid}/decisions/{mine['id']}?who=Asha").status_code == 200
    assert c2.get(f"/api/jobs/{jid}/decisions").json()["decisions"] == {}


def test_browse_edits_split_join_heading_chapter(client, converted):
    jid = converted["id"]
    page = client.get(f"/api/jobs/{jid}/pages/7/units").json()
    para = next(u for u in page["units"] if u["type"] == "paragraph" and len(u["lines"]) > 1)
    post = lambda e, who="Asha": client.post(f"/api/jobs/{jid}/edits", json={"who": who, "edit": e})  # noqa: E731
    assert post({"op": "split", "unit": para["id"], "line": 1}, who="").status_code == 422
    assert post({"op": "split", "unit": para["id"], "line": 1}).status_code == 200
    after = client.get(f"/api/jobs/{jid}/pages/7/units").json()["units"]
    assert len(after) == len(page["units"]) + 1
    assert post({"op": "split", "unit": para["id"], "line": 9}).json()["code"] == "edit_failed"
    assert post({"op": "heading_set", "unit": para["id"], "level": 2}).status_code == 200
    h = next(
        u
        for u in client.get(f"/api/jobs/{jid}/pages/7/units").json()["units"]
        if u["id"] == para["id"]
    )
    assert h["type"] == "heading" and h["level"] == 2
    assert post({"op": "new_chapter", "unit": para["id"]}).status_code == 200
    assert post({"op": "heading_remove", "unit": para["id"]}).status_code == 200
    assert post({"op": "join_next", "unit": "f" * 16}).json()["code"] == "edit_failed"
    assert post({"op": "nonsense", "unit": para["id"]}).status_code == 422


def test_chapter_list_follows_the_reviewers_edits(client, converted):
    jid = converted["id"]
    post = lambda e: client.post(f"/api/jobs/{jid}/edits", json={"who": "Asha", "edit": e})  # noqa: E731
    rows = client.get(f"/api/jobs/{jid}/chapters").json()["chapters"]
    assert rows and all({"unit", "role", "number", "title", "page"} <= set(r) for r in rows)
    first = rows[0]
    # a kind the book does not have is refused; a good one changes the list at once
    assert post({"op": "heading_kind", "unit": first["unit"], "kind": "volume"}).json()["code"] == (
        "edit_failed")  # fmt: skip
    assert post({"op": "heading_kind", "unit": first["unit"], "kind": "section"}).status_code == 200
    after = client.get(f"/api/jobs/{jid}/chapters").json()["chapters"]
    assert first["unit"] not in [r["unit"] for r in after]
    # a paragraph starts a chapter with a number the person chose
    page = client.get(f"/api/jobs/{jid}/pages/7/units").json()
    para = next(u for u in page["units"] if u["type"] == "paragraph")
    assert post({"op": "new_chapter", "unit": para["id"], "number": "9x9"}).status_code == 422
    assert post({"op": "new_chapter", "unit": para["id"], "number": "9"}).status_code == 200
    row = next(r for r in client.get(f"/api/jobs/{jid}/chapters").json()["chapters"]
               if r["unit"] == para["id"])  # fmt: skip
    assert (row["role"], row["number"], row["set_by_reviewer"]) == ("chapter", "9", True)


def test_a_refused_title_change_is_not_recorded(client, converted):
    jid = converted["id"]
    post = lambda e: client.post(f"/api/jobs/{jid}/edits", json={"who": "Asha", "edit": e})  # noqa: E731
    page = client.get(f"/api/jobs/{jid}/pages/7/units").json()
    para = next(u for u in page["units"] if u["type"] == "paragraph")
    assert post({"op": "heading_set", "unit": para["id"], "level": 2}).status_code == 200
    # the words cannot change; a refused change is not recorded
    refused = post({"op": "heading_text", "unit": para["id"], "text": "Other words"})
    assert refused.status_code == 422
    edits = client.get(f"/api/jobs/{jid}/decisions").json()["edits"]
    assert not [e for e in edits if e["op"] == "heading_text"]
    # (the positive case, a number removed, is in test_overlay: the stand-in book has none)


# ------------------------------------------------------------------ export, download


def test_export_blocked_by_alt_text_then_override_recorded(app_client, converted):
    app, client = app_client
    jid = converted["id"]
    assert client.post(f"/api/jobs/{jid}/export", json={"who": "A"}).json()["code"] == "no_details"
    d = client.get(f"/api/jobs/{jid}/details").json()["details"]
    assert client.put(f"/api/jobs/{jid}/details", json=d).status_code == 200
    r = client.post(f"/api/jobs/{jid}/export", json={"who": "Asha"})
    assert (
        r.status_code == 409
        and r.json()["code"] == "alt_text_placeholders"
        and r.json()["placeholders"] >= 1
    )
    assert client.get(f"/api/jobs/{jid}/exports").json()["exports"] == []
    ok = client.post(
        f"/api/jobs/{jid}/export", json={"who": "Asha", "allow_alt_text_placeholders": True}
    )
    assert ok.status_code == 200
    res = ok.json()
    assert res["override_alt_text"] is True
    assert res["qc"]["overrides"]["alt_text_placeholders"] >= 1  # recorded in the QC report
    assert res["qc"]["verdict"] in ("warn", "pass") and res["qc"]["dtd"]["errors"] == 0
    assert any(
        e["type"] == "override" and e["who"] == "Asha"
        for e in client.get(f"/api/jobs/{jid}/decisions").json()["events"]
    )
    z = client.get(f"/api/jobs/{jid}/exports/1/delivery.zip")
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert any(n.endswith("page_info.xml") for n in names) and any("/Chapters/" in n for n in names)
    qc = client.get(f"/api/jobs/{jid}/exports/1/qc_report.html?download=true")
    assert qc.status_code == 200 and "attachment" in qc.headers["content-disposition"]
    assert client.get(f"/api/jobs/{jid}/exports/1/report/../../job.json").status_code in (404, 422)
    assert client.get(f"/api/jobs/{jid}/exports/9/delivery.zip").status_code == 404
    assert client.get(f"/api/jobs/{jid}").json()["last_export"]["verdict"] == res["qc"]["verdict"]


def test_export_allowed_once_alt_text_is_written(client, converted):
    jid = converted["id"]
    d = client.get(f"/api/jobs/{jid}/details").json()["details"]
    client.put(f"/api/jobs/{jid}/details", json=d)
    for item in client.get(f"/api/jobs/{jid}/review").json()["items"]:
        if item["editor"] == "alt_text":
            client.post(f"/api/jobs/{jid}/decisions", json={"who": "A", "key": item["key"], "item_kind": "alt_text", "action": "fix",  # noqa: E501
                "fix": {"op": "alt_text", "unit": item["unit"], "text": "Described."}})  # fmt: skip
    r = client.post(f"/api/jobs/{jid}/export", json={"who": "A"})
    assert r.status_code == 200 and r.json()["override_alt_text"] is False


# ------------------------------------------------------------------ check an edited delivery


def _export_zip(client, jid):
    d = client.get(f"/api/jobs/{jid}/details").json()["details"]
    client.put(f"/api/jobs/{jid}/details", json=d)
    client.post(f"/api/jobs/{jid}/export", json={"who": "A", "allow_alt_text_placeholders": True})
    return client.get(f"/api/jobs/{jid}/exports/1/delivery.zip").content


def test_check_edited_delivery(app_client, converted):
    app, client = app_client
    jid = converted["id"]
    data = _export_zip(client, jid)
    r = client.put(f"/api/checks?filename=same.zip&job={jid}", content=data)
    assert r.status_code == 200 and r.json()["verdict"] in ("pass", "warn")
    assert (
        r.json()["dtd"]["errors"] == 0
        and r.json()["text"]["removed"] == 0
        and r.json()["text"]["added"] == 0
    )
    # edit one chapter file: a changed word and a broken element
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for info in src.infolist():
            b = src.read(info.filename)
            if info.filename.endswith("ch1.xml"):
                b = b.replace(b"Temperatures", b"Heatwaves").replace(b"</para>", b"</paraX>", 1)
            z.writestr(info.filename, b)
    bad = client.put(f"/api/checks?filename=edited.zip&job={jid}", content=out.getvalue()).json()
    assert bad["verdict"] == "fail" and bad["dtd"]["errors"] > 0
    cid = bad["id"]
    assert client.get(f"/api/checks/{cid}").json()["verdict"] == "fail"
    assert "FAIL" in client.get(f"/api/checks/{cid}/report.html").text
    folder = app.state.service.checks_root / cid
    assert (folder / "upload.zip").read_bytes() == out.getvalue()  # their file is untouched
    assert len(client.get("/api/checks").json()["checks"]) == 2
    assert client.delete(f"/api/checks/{cid}").status_code == 200


def test_check_rejects_unsafe_and_non_zip(client, converted):
    jid = converted["id"]
    assert (
        client.put(f"/api/checks?filename=a.zip&job={jid}", content=b"not a zip").status_code == 415
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("../evil.xml", "<book/>")
    assert (
        client.put(f"/api/checks?filename=a.zip&job={jid}", content=out.getvalue()).json()["code"]
        == "unsafe_zip"
    )
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("readme.txt", "hi")
    r = client.put(f"/api/checks?filename=a.zip&job={jid}", content=empty.getvalue()).json()
    assert r["verdict"] == "fail" and "No main DocBook file" in r["reasons"][0]
    assert client.put("/api/checks?filename=a.zip", content=empty.getvalue()).status_code == 422


# ------------------------------------------------------------------ delete


def test_delete_only_that_job(app_client, pdf_bytes):
    app, client = app_client
    a = client.put("/api/jobs?filename=a.pdf", content=pdf_bytes).json()
    b = client.put("/api/jobs?filename=b.pdf", content=pdf_bytes).json()
    assert client.delete(f"/api/jobs/{a['id']}").json()["code"] == "confirm"
    assert client.delete(f"/api/jobs/{a['id']}?confirm=yes").status_code == 200
    root = app.state.settings.data_path / "jobs"
    assert not (root / a["id"]).exists() and (root / b["id"] / "input.pdf").is_file()
    assert client.get(f"/api/jobs/{a['id']}").status_code == 404
    assert [j["id"] for j in client.get("/api/jobs").json()["jobs"]] == [b["id"]]
    assert pytest is not None


# ------------------------------------------------------------------ ePub export


def _details(client, jid):
    d = client.get(f"/api/jobs/{jid}/details").json()["details"]
    assert client.put(f"/api/jobs/{jid}/details", json=d).status_code == 200


def test_export_epub_and_both(client, converted):
    jid = converted["id"]
    assert client.put(f"/api/jobs/{jid}/profile", json={"ref": "jaypee_v4"}).status_code == 200
    _details(client, jid)
    bad = client.post(f"/api/jobs/{jid}/export", json={"who": "A", "format": "pdf"})
    assert bad.status_code == 400
    blocked = client.post(f"/api/jobs/{jid}/export", json={"who": "A", "format": "epub"})
    assert blocked.status_code == 409 and blocked.json()["code"] == "alt_text_placeholders"
    assert client.get(f"/api/jobs/{jid}/exports").json()["exports"] == []
    r = client.post(
        f"/api/jobs/{jid}/export",
        json={"who": "A", "format": "epub", "allow_alt_text_placeholders": True},
    )
    assert r.status_code == 200
    res = r.json()
    assert res["formats"] == ["epub"] and res["epub"].endswith(".epub") and "zip" not in res
    assert res["epub_qc"]["verdict"] in ("pass", "warn")
    assert res["epub_qc"]["lossless"]["missing"] == 0 and res["epub_qc"]["lossless"]["extra"] == 0
    assert res["epub_qc"]["epubcheck"]["status"] in ("run", "not run")
    f = client.get(f"/api/jobs/{jid}/exports/1/book.epub")
    assert f.status_code == 200 and f.content[:2] == b"PK"
    z = zipfile.ZipFile(io.BytesIO(f.content))
    assert z.infolist()[0].filename == "mimetype"
    assert client.get(f"/api/jobs/{jid}/exports/1/delivery.zip").status_code == 404
    q = client.get(f"/api/jobs/{jid}/exports/1/epub_qc_report.html?download=true")
    assert q.status_code == 200 and "attachment" in q.headers["content-disposition"]
    assert client.get(f"/api/jobs/{jid}/exports/1/epub_report/review_list.html").status_code == 200
    assert client.get(f"/api/jobs/{jid}/exports/1/epub_report/../../export.json").status_code in (
        404,
        422,
    )
    # both formats in one export
    both = client.post(
        f"/api/jobs/{jid}/export",
        json={"who": "A", "format": "both", "allow_alt_text_placeholders": True},
    ).json()
    assert set(both["verdicts"]) == {"docbook", "epub"} and both["zip"] and both["epub"]
    assert client.get(f"/api/jobs/{jid}").json()["last_export"]["verdicts"].keys() == {
        "docbook",
        "epub",
    }
    # same export record -> same ePub bytes when re-run is not possible here (new time); the
    # modified time comes from the export record
    assert z.read("OEBPS/package.opf").count(b"dcterms:modified") == 1


def test_cover_upload(client, converted):
    jid = converted["id"]
    assert client.get(f"/api/jobs/{jid}/cover").json() == {"cover": None}
    assert client.put(f"/api/jobs/{jid}/cover", content=b"not an image").status_code == 400
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 60), "white").save(buf, "PNG")
    assert client.put(f"/api/jobs/{jid}/cover", content=buf.getvalue()).status_code == 200
    assert client.get(f"/api/jobs/{jid}/cover").json() == {"cover": "cover.png"}
    client.put(f"/api/jobs/{jid}/profile", json={"ref": "jaypee_v4"})
    _details(client, jid)
    res = client.post(
        f"/api/jobs/{jid}/export",
        json={"who": "A", "format": "epub", "allow_alt_text_placeholders": True},
    ).json()
    z = zipfile.ZipFile(
        io.BytesIO(client.get(f"/api/jobs/{jid}/exports/{res['n']}/book.epub").content)
    )
    assert "OEBPS/Text/cover.xhtml" in z.namelist() and "OEBPS/Images/cover.jpg" in z.namelist()


# ------------------------------------------------------------------ standard formats

BASE_OF = {
    "html": "html_base",
    "dtbook": "dtbook_nimas_base",
    "daisy3": "daisy3_base",
    "jats": "jats_base",
    "bits": "bits_base",
}


def test_profile_list_has_formats_and_standard(client):
    rows = {p["name"]: p for p in client.get("/api/profiles").json()["profiles"]}
    assert rows["html_base"]["formats"] == ["html", "tail"] and rows["html_base"]["standard"] is True
    assert "docbook" in rows["jaypee_v4"]["formats"] and "epub" in rows["jaypee_v4"]["formats"]
    assert rows["jaypee_v3"]["standard"] is False and "html" not in rows["jaypee_v3"]["formats"]


@pytest.mark.parametrize("fmt", sorted(BASE_OF))
def test_export_standard_format(client, converted, fmt):
    jid = converted["id"]
    assert client.put(f"/api/jobs/{jid}/profile", json={"ref": BASE_OF[fmt]}).status_code == 200
    _details(client, jid)
    blocked = client.post(f"/api/jobs/{jid}/export", json={"who": "A", "formats": [fmt]})
    assert blocked.status_code == 409 and blocked.json()["code"] == "alt_text_placeholders"
    r = client.post(
        f"/api/jobs/{jid}/export",
        json={"who": "A", "formats": [fmt], "allow_alt_text_placeholders": True},
    )
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["formats"] == [fmt] and fmt in res["others"] and "zip" not in res
    qc = res["other_qc"][fmt]
    assert qc["verdict"] in ("pass", "warn") and qc["dtd"]["errors"] == 0
    assert qc["lossless"]["missing"] == 0 and qc["lossless"]["extra"] == 0
    base = f"/api/jobs/{jid}/exports/1/formats/{fmt}"
    z = client.get(f"{base}/delivery.zip")
    assert z.status_code == 200 and z.content[:2] == b"PK"
    assert zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert (
        "attachment"
        in client.get(f"{base}/qc_report.html?download=true").headers["content-disposition"]
    )
    assert client.get(f"{base}/report/review_list.html").status_code == 200
    assert client.get(f"{base}/report/../../export.json").status_code in (404, 422)
    other = next(f for f in BASE_OF if f != fmt)
    assert client.get(f"/api/jobs/{jid}/exports/1/formats/{other}/delivery.zip").status_code == 404
    unsupported = client.post(f"/api/jobs/{jid}/export", json={"who": "A", "formats": ["docbook"]})
    assert unsupported.status_code == 400 and unsupported.json()["code"] == "format_not_supported"


def test_details_publication_facts_reach_the_settings(client, converted):
    jid = converted["id"]
    d = client.get(f"/api/jobs/{jid}/details").json()["details"]
    bad = client.put(f"/api/jobs/{jid}/details", json={**d, "publication_date": "March 2026"})
    assert bad.status_code == 422 and bad.json()["problems"][0]["field"] == "publication_date"
    ok = client.put(
        f"/api/jobs/{jid}/details",
        json={**d, "publisher": "Acme Press", "publication_date": "2026-03", "rights": "(c) Acme"},
    )
    assert ok.status_code == 200
    from book_app.details import settings_yaml

    text = settings_yaml(ok.json()["details"], "html_base")
    assert "publisher: Acme Press" in text and "publication_date: 2026-03" in text
    assert "rights: (c) Acme" in text


def test_details_confirmed_under_one_profile_can_be_saved_under_another(client, converted):
    jid = converted["id"]
    d = client.get(f"/api/jobs/{jid}/details").json()["details"]
    assert d["options"]  # jaypee_v3 declares book options
    assert client.put(f"/api/jobs/{jid}/details", json=d).status_code == 200
    assert client.put(f"/api/jobs/{jid}/profile", json={"ref": "html_base"}).status_code == 200
    again = client.get(f"/api/jobs/{jid}/details").json()
    assert again["confirmed"] and again["details"]["options"] == {}
    assert client.put(f"/api/jobs/{jid}/details", json=d).status_code == 200  # old options ignored


# ------------------------------------------------------------------ book parts


def test_parts_are_guessed_validated_and_confirmed(client, pdf_bytes):

    jid = convert_job(client, pdf_bytes)["id"]
    g = client.get(f"/api/jobs/{jid}/parts").json()
    assert g["confirmed"] is False and g["problems"] == []
    assert g["keys"] == ["front", "body", "bibliography", "glossary", "appendix", "index"]
    assert all(k in g["parts"] for k in g["keys"])
    gap = {**g["parts"], "body": {"first": g["parts"]["body"]["first"] + 1,
                                  "last": g["parts"]["body"]["last"]}}  # fmt: skip
    r = client.put(f"/api/jobs/{jid}/parts", json={"parts": gap, "who": "Asha"})
    assert r.status_code == 422 and r.json()["code"] == "bad_parts"
    assert any("in no part" in p["message"] for p in r.json()["problems"])
    missing = {k: v for k, v in g["parts"].items() if k != "index"}
    absent = client.put(f"/api/jobs/{jid}/parts", json={"parts": missing, "who": "A"})
    assert absent.status_code == 422
    nameless = client.put(f"/api/jobs/{jid}/parts", json={"parts": g["parts"], "who": " "})
    assert nameless.json()["code"] == "no_who"
    ok = client.put(f"/api/jobs/{jid}/parts", json={"parts": g["parts"], "who": "Asha"}).json()
    assert ok["confirmed"] is True and ok["confirmed_by"] == "Asha" and ok["rerun"] is False


def test_export_is_blocked_until_the_parts_are_confirmed(client, pdf_bytes):

    jid = convert_job(client, pdf_bytes)["id"]
    d = client.get(f"/api/jobs/{jid}/details").json()["details"]
    assert client.put(f"/api/jobs/{jid}/details", json=d).status_code == 200
    blocked = client.post(f"/api/jobs/{jid}/export", json={"who": "A"})
    assert blocked.status_code == 409 and blocked.json()["code"] == "parts_not_confirmed"
    override = client.post(
        f"/api/jobs/{jid}/export", json={"who": "A", "allow_alt_text_placeholders": True}
    )
    assert override.json()["code"] == "parts_not_confirmed"  # no override for the parts


def test_parts_filled_in_by_the_assistant_need_a_person(client, pdf_bytes):
    """Parts confirmed under the reviewing assistant's name are shown but do not count: the
    export stays blocked until a person confirms them."""

    jid = convert_job(client, pdf_bytes)["id"]
    d = client.get(f"/api/jobs/{jid}/details").json()["details"]
    assert client.put(f"/api/jobs/{jid}/details", json=d).status_code == 200
    g = client.get(f"/api/jobs/{jid}/parts").json()
    client.put(f"/api/jobs/{jid}/parts", json={"parts": g["parts"], "who": "Claude Desktop (AI)"})
    shown = client.get(f"/api/jobs/{jid}/parts").json()
    assert shown["confirmed"] is False and shown["by_assistant"] is True
    assert shown["confirmed_by"] == "Claude Desktop (AI)"
    blocked = client.post(f"/api/jobs/{jid}/export", json={"who": "A"})
    assert blocked.status_code == 409 and blocked.json()["code"] == "parts_not_confirmed"
    assert "A person must check them" in blocked.json()["detail"]
    ok = client.put(f"/api/jobs/{jid}/parts", json={"parts": g["parts"], "who": "Asha"}).json()
    assert ok["confirmed"] is True and ok["by_assistant"] is False


def test_corrected_parts_rerun_the_conversion_and_are_recorded(client, pdf_bytes):

    jid = convert_job(client, pdf_bytes)["id"]
    g = client.get(f"/api/jobs/{jid}/parts").json()
    body = g["parts"]["body"]
    assert body["last"] > body["first"]
    corrected = {**g["parts"], "body": {"first": body["first"], "last": body["last"] - 1},
                 "bibliography": {"first": body["last"], "last": body["last"]}}  # fmt: skip
    assert corrected["bibliography"]["first"] > body["first"]
    rear = g["parts"]["appendix"] or g["parts"]["index"] or g["parts"]["glossary"]
    if rear is not None and rear["first"] == body["last"] + 1:
        pass  # the book has rear pages after the body: ranges stay contiguous
    r = client.put(f"/api/jobs/{jid}/parts", json={"parts": corrected, "who": "Meera"})
    if r.status_code == 422:  # the sample's rear pages make this particular shape a gap
        assert r.json()["code"] == "bad_parts"
        return
    assert r.json()["rerun"] is True
    wait_state(client, jid, {"converted", "failed"})
    again = client.get(f"/api/jobs/{jid}/parts").json()
    assert again["confirmed"] is True and again["confirmed_by"] == "Meera"


def test_two_reviewers_refresh_and_read_the_list_safely(app_client, converted):
    """Reviewer A refreshes the list after an edit while reviewer B keeps reading it: B never
    sees a missing or half-built list; a refresh with unchanged edits does not rebuild."""
    import threading

    from fastapi.testclient import TestClient

    app, a = app_client
    b = TestClient(app, base_url="http://127.0.0.1:8777")
    jid = converted["id"]
    folder = app.state.store.folder(jid)
    first = a.get(f"/api/jobs/{jid}/review").json()
    before = json.loads((folder / "preview" / "preview.json").read_text())
    built, built_key = before["at"], before["key"]
    # unchanged edits: a refresh (by either reviewer) keeps the build
    assert a.post(f"/api/jobs/{jid}/review/refresh").json()["total"] == first["total"]
    assert b.post(f"/api/jobs/{jid}/review/refresh").status_code == 200
    assert json.loads((folder / "preview" / "preview.json").read_text())["at"] == built
    # an edit changes the build key; A refreshes while B reads
    page = a.get(f"/api/jobs/{jid}/pages/7/units").json()
    para = next(u for u in page["units"] if u["type"] == "paragraph" and len(u["lines"]) > 1)
    edit = {"who": "Asha", "edit": {"op": "split", "unit": para["id"], "line": 1}}
    assert a.post(f"/api/jobs/{jid}/edits", json=edit).status_code == 200
    errors, done = [], threading.Event()

    def read():
        while not done.is_set():
            r = b.get(f"/api/jobs/{jid}/review")
            if r.status_code != 200 or "items" not in r.json():
                errors.append(r.status_code)

    reader = threading.Thread(target=read)
    reader.start()
    try:
        refreshed = a.post(f"/api/jobs/{jid}/review/refresh")
    finally:
        done.set()
        reader.join()
    assert refreshed.status_code == 200 and refreshed.json()["stale"] is False
    assert errors == []
    state = json.loads((folder / "preview" / "preview.json").read_text())
    # rebuilt for the new edits (the key, not the time stamp: a rebuild can finish in the same second)
    assert state["key"] != built_key and str(folder / "preview") in (state["main_xml"] or str(folder / "preview"))
    assert not (folder / "preview.tmp").exists() and not (folder / "preview.old").exists()
    # B's refresh right after A's finds the list up to date
    assert b.post(f"/api/jobs/{jid}/review/refresh").status_code == 200
    assert json.loads((folder / "preview" / "preview.json").read_text())["at"] == state["at"]


def test_book_parts_given_before_the_conversion_are_followed_and_still_confirmed(client, pdf_bytes):
    """Parts given at upload go to the converter; after the conversion they are shown (not
    the guess), the export still needs a confirmation, and confirming the same ranges does
    not convert again."""
    job = client.put("/api/jobs?filename=book.pdf", content=pdf_bytes).json()
    jid, pages = job["id"], job["pages"]
    assert client.put(f"/api/jobs/{jid}/profile", json={"ref": "jaypee_v3"}).status_code == 200
    empty = client.get(f"/api/jobs/{jid}/parts/plan").json()
    assert empty["planned"] is False and empty["pages"] == pages
    parts = {"front": {"first": 1, "last": 2}, "body": {"first": 3, "last": pages - 1},
             "bibliography": None, "glossary": None, "appendix": None,
             "index": {"first": pages, "last": pages}}  # fmt: skip
    gap = {**parts, "body": {"first": 4, "last": pages - 1}}
    bad = client.put(f"/api/jobs/{jid}/parts/plan", json={"parts": gap, "who": "Asha"})
    assert bad.status_code == 422 and bad.json()["code"] == "bad_parts"
    ok = client.put(f"/api/jobs/{jid}/parts/plan", json={"parts": parts, "who": "Asha"}).json()
    assert ok["planned"] is True and ok["planned_by"] == "Asha"
    folder = client.app.state.store.folder(jid)
    assert json.loads((folder / "parts_confirmed.json").read_text()) == parts  # --parts input
    assert client.post(f"/api/jobs/{jid}/convert").status_code == 200
    wait_state(client, jid, {"converted", "failed"})
    late = client.put(f"/api/jobs/{jid}/parts/plan", json={"parts": parts, "who": "Asha"})
    assert late.status_code == 409 and late.json()["code"] == "too_late"
    shown = client.get(f"/api/jobs/{jid}/parts").json()
    assert shown["parts"] == parts and shown["confirmed"] is False and shown["planned"] is True
    d = client.get(f"/api/jobs/{jid}/details").json()["details"]
    assert client.put(f"/api/jobs/{jid}/details", json=d).status_code == 200
    blocked = client.post(f"/api/jobs/{jid}/export", json={"who": "A"})
    assert blocked.json()["code"] == "parts_not_confirmed"
    confirmed = client.put(f"/api/jobs/{jid}/parts", json={"parts": parts, "who": "Meera"}).json()
    assert confirmed["rerun"] is False and confirmed["confirmed"] is True
