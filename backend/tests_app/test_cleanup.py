"""The automatic cleanup: what it plans, what it proves, what it never touches."""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

from book_app import cleanup
from book_app.config import AppSettings, CleanupSettings, SettingsError

NOW = time.time()
H = 3600


def iso(ts):
    return cleanup.iso(ts)


def make_job(
    root,
    job_id="a" * 16,
    *,
    state="converted",
    exported_h=None,
    updated_h=100,
    final="f" * 64,
    extra_dirs=(),
    publication=True,
):
    folder = root / "jobs" / job_id
    pub = f"converter_out/book-{'b' * 64}"
    (folder / pub / "images").mkdir(parents=True)
    (folder / pub / "book.json").write_text("{}")
    (folder / pub / "manifest.json").write_text(json.dumps({"final_key": final}))
    (folder / "converter_out" / final).mkdir()
    (folder / "converter_out" / final / "page_000001.json.gz").write_bytes(b"x" * 100)
    for name in ("preview", "pagecache", "cache", "exports/001"):
        (folder / name).mkdir(parents=True, exist_ok=True)
        (folder / name / "f.bin").write_bytes(b"y" * 1000)
    (folder / "input.pdf").write_bytes(b"%PDF-")
    (folder / "decisions.json").write_text("{}")
    job = {
        "id": job_id,
        "name": "book.pdf",
        "state": state,
        "updated_at": iso(NOW - updated_h * H),
        "publication": pub if publication else None,
        "exports": 1 if exported_h else 0,
        "last_export": {"at": iso(NOW - exported_h * H)} if exported_h is not None else None,
    }
    (folder / "job.json").write_text(json.dumps(job))
    for name in extra_dirs:
        (folder / "converter_out" / name).mkdir()
        (folder / "converter_out" / name / "page_000001.json.gz").write_bytes(b"z" * 50)
    os.utime(folder / "decisions.json", (NOW - updated_h * H,) * 2)
    return folder


def plan(root, **kw):
    cfg = CleanupSettings(**kw)
    return cleanup.plan(root / "jobs", cfg, NOW, {}, 0.0)


def actions(report, job_id="a" * 16):
    job = next(j for j in report["jobs"] if j["id"] == job_id)
    return {i["path"].split("/")[-1][:12]: i["action"] for i in job["items"]}


def test_after_export_and_idle_rules_and_what_is_never_planned(tmp_path):
    make_job(tmp_path, "a" * 16, exported_h=3)
    make_job(tmp_path, "b" * 16, exported_h=1)
    make_job(tmp_path, "c" * 16, exported_h=None, updated_h=24 * 8)
    make_job(tmp_path, "d" * 16, exported_h=None, updated_h=24 * 3)
    report = plan(tmp_path)
    assert actions(report, "a" * 16)["preview"] == "delete"  # exported 3 h ago
    assert actions(report, "a" * 16)["pagecache"] == "delete"
    assert actions(report, "b" * 16)["preview"] == "keep"  # exported 1 h ago: 1 h left
    assert actions(report, "c" * 16)["preview"] == "delete"  # no activity for 8 days
    assert actions(report, "d" * 16)["preview"] == "keep"  # 3 days: not yet
    for job in report["jobs"]:
        paths = {i["path"] for i in job["items"] if i["action"] == "delete"}
        assert not {
            p for p in paths if p.split("/")[0] in {"exports", "input.pdf", "decisions.json"}
        }
        assert not any(p.startswith(f"converter_out/book-{'b' * 64}") for p in paths)  # current
        cache = next(i for i in job["items"] if i["path"] == "cache")
        assert cache["action"] == "report"  # reported, never deleted by default


def test_a_job_that_is_open_or_running_is_left_alone(tmp_path):
    make_job(tmp_path, "a" * 16, exported_h=3)
    make_job(tmp_path, "b" * 16, exported_h=3, state="converting")
    (tmp_path / "jobs" / ("b" * 16) / "preview.tmp").mkdir()
    cfg = CleanupSettings()
    report = cleanup.plan(tmp_path / "jobs", cfg, NOW, {"a" * 16: NOW - 5 * 60}, 0.0)
    assert actions(report, "a" * 16)["preview"] == "keep"  # used 5 minutes ago
    assert all(i["action"] == "keep" for i in report["jobs"][1]["items"])  # converting: nothing
    after_restart = cleanup.plan(tmp_path / "jobs", cfg, NOW, {}, NOW - 60)  # started a minute ago
    assert actions(after_restart, "a" * 16)["preview"] == "keep"  # restart grace period


def test_leftover_previews_always_go(tmp_path):
    folder = make_job(tmp_path, exported_h=None, updated_h=1)
    (folder / "preview.tmp").mkdir()
    (folder / "preview.tmp" / "x").write_text("x")
    items = {i["path"]: i["action"] for i in plan(tmp_path)["jobs"][0]["items"]}
    assert items["preview.tmp"] == "delete" and items["preview"] == "keep"


def test_converter_output_is_deleted_only_with_proof_it_is_unreferenced(tmp_path):
    other = "c" * 64
    linked = "d" * 64
    named = "e" * 64
    stale = "book-" + "9" * 64
    folder = make_job(tmp_path, extra_dirs=(other, linked, named, stale))
    # a hard link from the current publication into one folder, a name written in details.json
    os.link(
        folder / "converter_out" / linked / "page_000001.json.gz",
        folder / "converter_out" / f"book-{'b' * 64}" / "images" / "shared.gz",
    )
    (folder / "details.json").write_text(json.dumps({"note": named}))
    job = plan(tmp_path)["jobs"][0]
    items = {
        i["path"].split("/")[-1][:9]: i for i in job["items"] if i["category"] == "converter output"
    }
    assert items["f" * 9]["action"] == "keep" and "final_key" in items["f" * 9]["reason"]
    assert items["book-" + "b" * 4]["action"] == "keep"
    assert items["d" * 9]["action"] == "keep" and "link into it" in items["d" * 9]["reason"]
    assert items["e" * 9]["action"] == "keep" and "details.json" in items["e" * 9]["reason"]
    gone = [items["c" * 9], items["book-" + "9" * 4]]
    assert all(i["action"] == "delete" and i["rule"] == "unreferenced" for i in gone)
    assert all(len(i["proof"]) >= 4 for i in gone)  # the proof lists every check made


def test_no_publication_means_nothing_is_proved(tmp_path):
    make_job(tmp_path, publication=False, exported_h=3)
    items = [i for i in plan(tmp_path)["jobs"][0]["items"] if i["category"] == "converter output"]
    assert items and all(i["action"] == "keep" for i in items)


def test_the_converter_cache_goes_only_when_switched_on(tmp_path):
    make_job(tmp_path, exported_h=3)
    on = plan(tmp_path, delete_converter_cache=True)
    assert next(i for i in on["jobs"][0]["items"] if i["path"] == "cache")["action"] == "delete"


def run(tmp_path, mode, locks=lambda job_id: [], **kw):
    cfg = CleanupSettings(mode=mode, **kw)
    (tmp_path / "jobs").mkdir(exist_ok=True)
    return cleanup.run_once(tmp_path / "jobs", tmp_path, cfg, {}, 0.0, locks)


def test_dry_run_deletes_nothing_and_delete_mode_logs_every_removal(tmp_path):
    folder = make_job(tmp_path, exported_h=3, extra_dirs=("c" * 64,))
    (folder / "preview.tmp").mkdir()
    report = run(tmp_path, "dry_run")
    assert report["totals"]["delete"]["bytes"] > 0 and "removed" not in report
    assert (folder / "preview").exists() and (folder / "preview.tmp").exists()
    assert (
        json.loads((tmp_path / "cleanup_report.json").read_text())["settings"]["mode"] == "dry_run"
    )
    report = run(tmp_path, "delete")
    removed = {r["path"]: r for r in report["removed"]}
    assert {"preview", "pagecache", "preview.tmp", f"converter_out/{'c' * 64}"} <= set(removed)
    assert removed["preview"]["bytes"] == 1000 and removed["preview"]["job"] == "a" * 16
    assert not (folder / "preview").exists() and not (folder / "pagecache").exists()
    for kept in (
        "input.pdf",
        "decisions.json",
        "job.json",
        "exports/001/f.bin",
        "cache/f.bin",
        f"converter_out/book-{'b' * 64}/book.json",
        f"converter_out/{'f' * 64}",
    ):
        assert (folder / kept).exists(), kept
    lines = [json.loads(x) for x in (tmp_path / "cleanup_log.jsonl").read_text().splitlines()]
    assert len(lines) == len(removed) and all(
        {"job", "path", "files", "bytes"} <= set(x) for x in lines
    )


def test_a_busy_job_is_skipped_and_hard_linked_files_are_not_counted_as_freed(tmp_path):
    folder = make_job(tmp_path, exported_h=3)
    lock = threading.Lock()
    with lock:
        report = run(tmp_path, "delete", locks=lambda job_id: [lock])
    assert not report["removed"] and (folder / "preview").exists()  # a build holds the lock
    os.link(folder / "pagecache" / "f.bin", tmp_path / "copy.bin")  # another job shares the file
    files, total, freed = cleanup.measure(folder / "pagecache")
    assert (files, total, freed) == (1, 1000, 0)


@pytest.mark.parametrize(
    "rel",
    [
        "input.pdf",
        "exports",
        "../x",
        "converter_out/a/b",
        "preview/out",
        "decisions.json",
        "cache/x",
    ],
)
def test_the_guard_refuses_anything_but_the_known_folders(tmp_path, rel):
    folder = make_job(tmp_path)
    with pytest.raises(ValueError):
        cleanup.guard(folder, rel)


def test_a_symbolic_link_is_never_followed_or_removed(tmp_path):
    folder = make_job(tmp_path)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (folder / "preview.old").symlink_to(target)
    with pytest.raises(ValueError):
        cleanup.guard(folder, "preview.old")


def test_settings_are_validated():
    for bad in (
        {"cleanup_mode": "now"},
        {"cleanup_idle_days": 0},
        {"cleanup_interval_minutes": -1},
    ):
        with pytest.raises(SettingsError):
            AppSettings(**bad).validate()
    ok = AppSettings()
    ok.validate()
    assert ok.cleanup.mode == "dry_run" and ok.cleanup.interval_minutes == 15
    assert ok.cleanup.after_export_hours == 2 and ok.cleanup.delete_converter_cache is False


def test_the_app_starts_the_task_and_serves_the_report(app_client):
    app, client = app_client
    assert app.state.cleaner.cfg.mode == "dry_run"
    report = client.get("/api/cleanup").json()
    assert report["settings"]["mode"] == "dry_run" and "jobs" in report
    assert client.get("/api/cleanup", headers={"X-Role": "reviewer"}).status_code == 403
    time.sleep(0)
