"""Local routing/measurement only; calls the frozen converter without rule changes."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
BASE = ROOT / ".cache/step18_part2"
LEDGER = ROOT / "experiments/holdout_runs.jsonl"
FREEZE = "8d6a0b0036db3f28dd8b671a2950ceca9918a680"
PREREG = "3bcbe704ff5d3994c61aecb8cc6a451e81c1e4c67a4c72ec23b1d94a5f64610b"
BOOK = sys.argv[1]
ATTEMPT = f"{BOOK}_attempt1"
DEST = BASE / ATTEMPT

def now():
    return datetime.now(timezone.utc).isoformat()

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            h.update(block)
    return h.hexdigest()

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, default=str) + "\n", encoding="utf-8")

def append(value):
    with LEDGER.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"schema_version": 1, **value}, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())

def children():
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD),
                    ("pid", wintypes.DWORD), ("heap", ctypes.c_size_t),
                    ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("parent", wintypes.DWORD), ("priority", wintypes.LONG),
                    ("flags", wintypes.DWORD), ("exe", wintypes.WCHAR * 260)]
    kernel = ctypes.windll.kernel32
    kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError("Unable to sample owned process tree")
    entry, pairs = Entry(), []
    entry.size = ctypes.sizeof(entry)
    try:
        okay = kernel.Process32FirstW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
        while okay:
            pairs.append((entry.pid, entry.parent))
            okay = kernel.Process32NextW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
    finally:
        kernel.CloseHandle(ctypes.c_void_p(snapshot))
    owned = {os.getpid()}
    while True:
        extra = {pid for pid, parent in pairs if parent in owned} - owned
        if not extra:
            return owned
        owned.update(extra)

def terminate_owned(pids):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    for pid in pids - {os.getpid()}:
        handle = kernel.OpenProcess(1, False, pid)
        if handle:
            kernel.TerminateProcess(ctypes.c_void_p(handle), 42)
            kernel.CloseHandle(ctypes.c_void_p(handle))

def main():
    from reference_paths import reference_path
    from book_core.assembly.profile import load_profile
    template = next(row for row in map(json.loads, LEDGER.read_text("utf-8").splitlines())
                    if row["record_type"] == "template" and row["book_id"] == BOOK)
    existing = [json.loads(line) for line in LEDGER.read_text("utf-8").splitlines()]
    if any(row.get("attempt_id") == ATTEMPT for row in existing) or DEST.exists():
        raise RuntimeError("Attempt exists; no automatic retry is allowed")
    source = reference_path(template["source_key"])
    profile = load_profile()
    status = git("status", "--porcelain", "--untracked-files=all")
    diff = git("diff", "holdout-freeze-1", "--", "backend")
    commit_paths = git("diff", "--name-only", "holdout-freeze-1", "HEAD").splitlines()
    checks = {
        "backend_diff_empty": not diff,
        "only_untracked_ledger": status == "?? experiments/holdout_runs.jsonl",
        "approved_docs_only": set(commit_paths) == {"docs/step18_preregistration.md", "docs/step18_preregistration_addendum.md"},
        "tag_unchanged": git("rev-parse", "holdout-freeze-1") == FREEZE,
        "backend_tree_equal": git("rev-parse", "HEAD:backend") == git("rev-parse", "holdout-freeze-1:backend"),
        "preregistration_unchanged": sha(ROOT / "docs/step18_preregistration.md") == PREREG,
        "source_hash_equal": sha(source) == template["source_file_sha256"],
        "profile_hash_equal": profile.sha256 == template["profile_sha256"],
        "profile_file_equal": sha(ROOT / "backend/src/book_core/assembly/profiles/default.toml") == template["profile_file_sha256"],
    }
    free = shutil.disk_usage(ROOT).free
    checks["free_above_40GB"] = free > 40_000_000_000
    preflight = {"record_type": "preflight", "book_id": BOOK, "attempt_id": ATTEMPT,
                 "time": now(), "checks": checks, "free_bytes": free,
                 "git_status": status, "backend_diff": diff, "commit_paths": commit_paths,
                 "commit_hash": FREEZE, "workspace_head": git("rev-parse", "HEAD"),
                 "backend_tree": git("rev-parse", "HEAD:backend"),
                 "source_file_sha256": template["source_file_sha256"],
                 "profile_sha256": profile.sha256}
    append(preflight)
    if not all(checks.values()):
        print(json.dumps(preflight), flush=True)
        raise RuntimeError("Preflight failed; no pipeline started")
    DEST.mkdir(parents=True)
    write(DEST / "preflight.json", preflight)
    started, tick = now(), time.perf_counter()
    state = {"book_id": BOOK, "attempt_id": ATTEMPT, "start_time": started,
             "outcome": "running", "stage": "initialization", "pid": os.getpid(),
             "peak_tree_rss_bytes": 0, "minimum_free_bytes": free,
             "memory_method": "500ms sampled complete owned process tree RSS (Windows Toolhelp32)"}
    append({"record_type": "attempt_started", **state, "pipeline_started": True,
            "commit_hash": FREEZE, "workspace_head": preflight["workspace_head"]})
    stop = threading.Event()
    from book_core.process_metrics import rss
    def sample():
        owned = children()
        state["peak_tree_rss_bytes"] = max(state["peak_tree_rss_bytes"], sum(rss(pid) for pid in owned))
        state["free_bytes"] = shutil.disk_usage(ROOT).free
        state["minimum_free_bytes"] = min(state["minimum_free_bytes"], state["free_bytes"])
        state["elapsed_seconds"] = time.perf_counter() - tick
        state["updated_at"] = now()
        write(DEST / "live.json", state)
        if state["free_bytes"] < 5_000_000_000:
            state.update(outcome="reserve_stopped", end_time=now())
            write(DEST / "result.json", state)
            append({"record_type": "attempt_finished", **state, "pipeline_started": True})
            terminate_owned(owned)
            os._exit(42)
    def watch():
        while not stop.wait(0.5):
            try:
                sample()
            except BaseException:
                state.update(outcome="monitor_failed", monitor_traceback=traceback.format_exc(), end_time=now())
                write(DEST / "result.json", state)
                append({"record_type": "attempt_finished", **state, "pipeline_started": True})
                terminate_owned(children())
                os._exit(43)
    sample()
    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    try:
        from step17_ocr_cover import ocr_settings, CONFIG
        from step16_benchmark import make_engines
        from step16_downstream import visual_checks
        from book_core.ocr.prepare import prepare_book
        from book_core.book_run import run_book
        from book_core.caching import SCOPES, code_digest
        config = json.loads(CONFIG.read_text("utf-8"))
        settings = ocr_settings(config).model_copy(update={"device": "auto", "ocr_languages": ["spa", "eng"]})
        config = {**config, "device": "auto"}
        primary, secondary = make_engines(config)
        write(DEST / "effective_settings.json", settings.model_dump(mode="json"))
        state["stage"] = "ocr_eligibility_and_preparation"
        print(BOOK, state["stage"], "pid", os.getpid(), flush=True)
        ocr = prepare_book(source, DEST / "ocr_cache", settings, primary, secondary,
                           visual_checks=visual_checks(source, DEST / "ocr_cache"))
        write(DEST / "ocr_input.json", ocr.model_dump(mode="json"))
        def progress(stage, completed, total):
            state.update(stage=stage, completed=completed, total=total)
            if completed % 25 == 0 or completed == total:
                print(BOOK, stage, completed, total, flush=True)
        state["stage"] = "run_book_initialization"
        result = run_book(source, DEST / "published", DEST / "cache", mode="development",
                          workers=1, device="auto", settings=settings, progress=progress,
                          model_cache_dir=ROOT / ".cache/huggingface", ocr_input=ocr, profile=profile)
        write(DEST / "performance.json", {"run": result, "ocr": ocr.model_dump(mode="json"),
              "producers": {scope: code_digest(scope) for scope in SCOPES}})
        state.update(outcome="completed", stage="published", output=result.get("output"),
                     book_json=result.get("book_json"))
    except BaseException as error:
        state.update(outcome="failed", exception_type=type(error).__name__, error=str(error),
                     traceback=traceback.format_exc())
        print(state["traceback"], flush=True)
    finally:
        stop.set()
        thread.join()
        sample()
        state["end_time"] = now()
        write(DEST / "result.json", state)
        append({"record_type": "attempt_finished", **state, "pipeline_started": True})
        print(json.dumps(state), flush=True)
    return 0 if state["outcome"] == "completed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
