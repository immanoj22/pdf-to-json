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
ATTEMPT = f"{BOOK}_attempt{2 if BOOK == 'ent_textbook' else 1}"
DEST = BASE / ATTEMPT
CACHE = {"ent_textbook": ROOT / ".cache/h18/e2", "math_holdout": Path("C:/h/m"),
         "mideast": Path("C:/h/d")}[BOOK]
SHORT_ID = {"ent_textbook": "e2", "math_holdout": "m", "mideast": "d"}[BOOK]
OCR_CACHE = ROOT / ".cache/h18" / (SHORT_ID + "o")
PUBLISHED = ROOT / ".cache/h18" / (SHORT_ID + "p")
REUSED = ["book_metadata", "native", "analysis", "layout", "reading_order", "furniture",
          "paragraphs", "structure_evidence", "structure", "lists", "characters", "figures",
          "equations", "mathml"] if BOOK == "ent_textbook" else []

def path_preflight():
    digest, uuid = "f" * 64, "a" * 32
    candidates = {}
    for family in ("formula_readings", "table_readings"):
        path = CACHE.resolve() / family / digest / "ff" / f".{digest}.json.{uuid}.tmp"
        candidates[family] = {"path": str(path), "characters": len(str(path))}
    # All other fixed cache record layouts have one digest level and a shorter filename.
    # Figure/equation asset names use the frozen page-label naming patterns.
    maximum = max(p["characters"] for p in candidates.values())
    limit = 260 if BOOK == "ent_textbook" else 200
    return {"cache_root": str(CACHE.resolve()), "ocr_cache_root": str(OCR_CACHE.resolve()),
            "publication_root": str(PUBLISHED.resolve()), "expected_deepest": candidates,
            "maximum_expected_characters": maximum, "strict_limit": limit,
            "passed": maximum < limit}


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
        stream.write(json.dumps({"schema_version": 1,
            **({"reason": "path_length_wrapper_error", "failure_class": "environmental",
                "from_attempt_id": "ent_textbook_attempt1"} if BOOK == "ent_textbook" else {}),
            **value}, default=str) + "\n")
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
    if any(row.get("attempt_id") == ATTEMPT and row.get("record_type") in {"preflight", "attempt_started", "attempt_finished"} for row in existing) or DEST.exists():
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
    paths = path_preflight()
    checks["cache_paths_within_limit"] = paths["passed"]
    if BOOK == "ent_textbook":
        reuse = json.loads((BASE / "retry_preparation/reuse_receipt.json").read_text("utf8"))
        checks["reuse_preparation_verified"] = reuse["sha256_verified"] and reuse["attempt1_all_files_unchanged"]
        checks["supplemental_record_audit_passed"] = json.loads((BASE / "retry_preparation/supplemental_gzip_audit.json").read_text())["passed"]
    else:
        checks["cold_cache_empty"] = CACHE.exists() and not any(CACHE.iterdir())
    free = shutil.disk_usage(ROOT).free
    checks["free_above_40GB"] = free > 40_000_000_000
    preflight = {"record_type": "preflight", "book_id": BOOK, "attempt_id": ATTEMPT,
                 "time": now(), "checks": checks, "free_bytes": free,
                 "git_status": status, "backend_diff": diff, "commit_paths": commit_paths,
                 "commit_hash": FREEZE, "workspace_head": git("rev-parse", "HEAD"),
                 "backend_tree": git("rev-parse", "HEAD:backend"),
                 "source_file_sha256": template["source_file_sha256"],
                 "profile_sha256": profile.sha256, "path_preflight": paths,
                 "stage_reuse": {stage: "reused from attempt 1" for stage in REUSED},
                 "recomputed": ["ocr_eligibility_and_preparation", "book_evidence"],
                 "fresh": ["tables (model detections reused from attempt 1)" if REUSED else "tables",
                           "continuity", "final_output", "assembly"]}
    append(preflight)
    if not all(checks.values()):
        print(json.dumps(preflight), flush=True)
        raise RuntimeError("Preflight failed; no pipeline started")
    DEST.mkdir(parents=True)
    write(DEST / "cache_reuse.json", {"stages": {s: "reused from attempt 1" for s in REUSED},
        "note": "Retry timings for reused stages measure cache validation/use, not fresh computation. OCR preparation and book evidence are recomputed. Tables reuse detector evidence but table structure/assembly are fresh."})
    write(DEST / "preflight.json", preflight)
    started, tick = now(), time.perf_counter()
    state = {"book_id": BOOK, "attempt_id": ATTEMPT, "start_time": started,
             "outcome": "running", "stage": "initialization", "pid": os.getpid(),
             "stage_reuse": {stage: "reused from attempt 1" for stage in REUSED},
             "peak_tree_rss_bytes": 0, "minimum_free_bytes": free,
             "memory_method": "500ms sampled complete owned process tree RSS (Windows Toolhelp32)"}
    append({"record_type": "attempt_started", **state, "pipeline_started": True,
            "commit_hash": FREEZE, "workspace_head": preflight["workspace_head"]})
    stop = threading.Event()
    from book_core.process_metrics import rss
    import ast
    stage_spans = []
    tree = ast.parse((ROOT / "backend/src/book_core/book_run.py").read_text("utf8"))
    run_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_run")
    for node in ast.walk(run_node):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "measure" and len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
                    stage_spans.append((node.lineno, node.end_lineno, call.args[1].value))
    last_observed = [None]
    def observed_stage():
        frame = sys._current_frames().get(threading.main_thread().ident)
        while frame is not None:
            if frame.f_code.co_name == "_run" and Path(frame.f_code.co_filename).name == "book_run.py":
                candidates = [(end-start, name) for start,end,name in stage_spans if start <= frame.f_lineno <= end]
                if candidates:
                    return min(candidates)[1]
            frame = frame.f_back
        return None
    def sample():
        stage = observed_stage()
        if stage is not None:
            label = "reused from attempt 1" if stage in REUSED else ("fresh table structure/assembly; detections reused from attempt 1" if stage == "tables" and REUSED else "fresh/recomputed")
            state.update(stage=stage, stage_execution_status=label)
            if stage != last_observed[0]:
                with (DEST / "stage_events.jsonl").open("a", encoding="utf8") as events:
                    events.write(json.dumps({"time": now(), "stage": stage, "execution_status": label,
                        "elapsed_seconds": time.perf_counter() - tick,
                        "observation": "500ms main-thread frame sampling; not fresh-compute stage timing"}) + "\n")
                last_observed[0] = stage
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
        ocr = prepare_book(source, OCR_CACHE, settings, primary, secondary,
                           visual_checks=visual_checks(source, OCR_CACHE))
        if BOOK == "ent_textbook":
            old_ocr = json.loads((BASE / "ent_textbook_attempt1/ocr_input.json").read_text("utf8"))
            assert ocr.fingerprint == old_ocr["fingerprint"], "Regenerated OCR fingerprint changed"
            assert settings.model_dump(mode="json") == json.loads((BASE / "ent_textbook_attempt1/effective_settings.json").read_text("utf8")), "Settings changed"
        write(DEST / "ocr_input.json", ocr.model_dump(mode="json"))
        def progress(stage, completed, total):
            state.update(stage=stage, completed=completed, total=total)
            if completed % 25 == 0 or completed == total:
                print(BOOK, stage, completed, total, flush=True)
        state["stage"] = "run_book_initialization"
        result = run_book(source, PUBLISHED, CACHE, mode="development",
                          workers=1, device="auto", settings=settings, progress=progress,
                          model_cache_dir=ROOT / ".cache/huggingface", ocr_input=ocr, profile=profile)
        for name, measurement in result.get("stages", {}).items():
            if name in REUSED:
                measurement.update(execution_status="reused from attempt 1",
                    timing_scope="cache validation/use; not a fresh computation timing")
            elif name == "tables" and REUSED:
                measurement.update(execution_status="fresh table structure/assembly; detector evidence reused from attempt 1")
            else:
                measurement.update(execution_status="recomputed" if name == "book_evidence" else "fresh")
        write(DEST / "performance.json", {"run": result, "ocr": ocr.model_dump(mode="json"),
              "producers": {scope: code_digest(scope) for scope in SCOPES}})
        state.update(outcome="completed", stage="published", output=result.get("output"),
                     book_json=result.get("book_json"))
    except BaseException as error:
        state.update(outcome="failed", failure_stage_note="See traceback for actual stage; progress callbacks cover page stages only",
                     exception_type=type(error).__name__, error=str(error),
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
