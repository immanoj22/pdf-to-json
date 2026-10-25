"""Focused local cancellation check; only the approved art PDF is submitted.

Run after smoke_check.py has finished. The running converter is cancelled promptly
after its process starts; the queued job must never start a converter.
"""

import http.client
import json
import threading
import time

import server
from smoke_check import art_source


def main():
    root = server.ROOT
    settings = json.loads((root / "settings.json").read_text("utf-8"))
    runtime = root / "runtime"
    # Constructing App recovers unfinished statuses, so refuse to disturb another run.
    for path in (runtime / "jobs").glob("*/status.json"):
        status = json.loads(path.read_text("utf-8"))
        if status["state"] not in server.TERMINAL:
            raise RuntimeError("Finish the existing local job before running cancellation checks.")

    source = art_source()
    cache = runtime / "cache"
    cached_before = {path.relative_to(cache).as_posix()
                     for path in cache.rglob("*") if path.is_file()}
    report = {"passed": [], "source_key": "art_index_pdf", "success": False}
    app = httpd = None
    failure = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["passed"].append(name)
        print("PASS", name, flush=True)

    def call(method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", 8766, timeout=30)
        request_headers = {"X-Upload-Token": app.token, **(headers or {})}
        if isinstance(body, dict):
            body = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        try:
            connection.request(method, path, body, request_headers)
            response = connection.getresponse()
            payload = response.read()
            if response.status != 200:
                raise AssertionError((method, path, response.status, payload[:500]))
            return json.loads(payload)
        finally:
            connection.close()

    def upload():
        job = call("POST", "/api/jobs", {"name": source.name, "size": source.stat().st_size})
        with source.open("rb") as stream:
            while block := stream.read(server.CHUNK):
                job = call("PUT", f"/api/jobs/{job['id']}/chunk", block,
                           {"X-Upload-Offset": str(job["received"])})
        return job

    def persisted(job_id):
        folder = app.jobs[job_id]["folder"]
        return json.loads((folder / "status.json").read_text("utf-8"))

    try:
        app = server.App(settings)
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 8766), server.Handler)
        httpd.app = app
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        first = upload()["id"]
        report["running_job_id"] = first
        call("POST", f"/api/jobs/{first}/finish")
        deadline = time.monotonic() + 20
        process = None
        while time.monotonic() < deadline:
            state = call("GET", f"/api/jobs/{first}")
            with app.lock:
                candidate = app.jobs[first]["process"]
                if state["state"] == "running" and candidate is not None:
                    process = candidate
            if process is not None:
                break
            if state["state"] in server.TERMINAL:
                raise AssertionError(f"Converter finished before cancellation: {state}")
            time.sleep(0.02)
        check("running converter process observed", process is not None and process.poll() is None)
        report["converter_pid"] = process.pid

        second = upload()["id"]
        report["queued_job_id"] = second
        queued = call("POST", f"/api/jobs/{second}/finish")
        check("second art upload queued while first converter runs",
              queued["state"] == "queued"
              and call("GET", f"/api/jobs/{first}")["state"] == "running"
              and process.poll() is None)
        check("queued status persisted", persisted(second)["state"] == "queued")
        cancelled = call("POST", f"/api/jobs/{second}/cancel")
        check("queued cancellation persisted",
              cancelled["state"] == "failed" and cancelled.get("cancelled") is True
              and persisted(second) == cancelled)

        started_cancel = time.monotonic()
        call("POST", f"/api/jobs/{first}/cancel")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = call("GET", f"/api/jobs/{first}")
            if status["state"] in server.TERMINAL:
                break
            time.sleep(0.05)
        check("running cancellation reaches failed status",
              status["state"] == "failed" and status.get("cancelled") is True)
        check("converter process terminated", process.poll() is not None)
        check("running cancellation status persisted", persisted(first) == status)
        report["cancel_seconds"] = round(time.monotonic() - started_cancel, 3)
        report["converter_returncode"] = process.returncode

        deadline = time.monotonic() + 5
        while app.pending.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.02)
        check("cancelled queued job never starts converter",
              not app.pending.unfinished_tasks
              and app.jobs[second]["process"] is None
              and not (app.jobs[second]["folder"] / "command.json").exists())
        missing = sorted(name for name in cached_before if not (cache / name).is_file())
        check("all existing converter cache files retained", not missing)
        check("cancelled uploads retained",
              all((app.jobs[job_id]["folder"] / "input.pdf").is_file()
                  for job_id in (first, second)))
        report["existing_cache_files_checked"] = len(cached_before)
        report["success"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        failure = exc
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if app is not None:
            app.close()
        server.save_json(root / "cancel_check_results.json", report)
    if failure is not None:
        raise failure


if __name__ == "__main__":
    main()
