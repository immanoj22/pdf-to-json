"""Focused local checks. Only art_index_pdf is converted; the dummy is never converted."""

import hashlib
import gzip
import http.client
import json
import os
from pathlib import Path
import shutil
import threading
import time
import tomllib
from unittest.mock import patch

import server

ROOT = server.ROOT
REPO = ROOT.parent


def art_source():
    config = Path(os.environ.get("BOOK_CONVERTER_REFERENCE_CONFIG",
                                 REPO / "experiments/references.toml"))
    paths = {}
    for path in (config, config.with_name(config.stem + ".local.toml")):
        if path.is_file():
            paths.update(tomllib.loads(path.read_text("utf-8"))["paths"])
    value = os.environ.get("BOOK_CONVERTER_ART_INDEX_PDF", paths.get("art_index_pdf", ""))
    if not value or not Path(value).is_file():
        raise RuntimeError("Configure the approved art_index_pdf reference first.")
    return Path(value)


def main():
    settings = json.loads((ROOT / "settings.json").read_text("utf-8"))
    app = server.App(settings)
    httpd = server.ThreadingHTTPServer(("127.0.0.1", settings["port"]), server.Handler)
    httpd.app = app
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    evidence = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        evidence.append(name)
        print("PASS", name, flush=True)

    def call(method, path, body=None, headers=None, expected=200, raw=False):
        connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=60)
        request_headers = {"X-Upload-Token": app.token, **(headers or {})}
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            request_headers["Content-Type"] = "application/json"
        connection.request(method, path, body, request_headers)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        if response.status != expected:
            raise AssertionError((method, path, response.status, payload[:500]))
        return payload if raw else json.loads(payload)

    def create(path):
        return call("POST", "/api/jobs", {"name": path.name, "size": path.stat().st_size})

    def upload(path):
        job = create(path)
        with path.open("rb") as source:
            while block := source.read(server.CHUNK):
                job = call("PUT", f"/api/jobs/{job['id']}/chunk", block,
                           {"X-Upload-Offset": str(job["received"])})
        return job

    dummy = ROOT / "synthetic_size_check.pdf"
    try:
        config = call("GET", "/api/config")
        check("default max is 2 GB and reserve is 5 GB", config["max_bytes"] == 2_000_000_000
              and config["reserve_bytes"] == 5_000_000_000)
        check("loopback bind", httpd.server_address[0] == "127.0.0.1")
        call("GET", "/api/config", headers={"Host": "example.invalid"}, expected=403)
        call("POST", "/api/jobs", {}, {"Origin": "http://example.invalid"}, expected=403)
        call("POST", "/api/jobs", {}, {"X-Upload-Token": "bad"}, expected=403)
        check("foreign Host, Origin and missing token rejected", True)
        with dummy.open("wb") as target:
            target.truncate(app.limit + 1)
        error = call("POST", "/api/jobs", {"name": dummy.name, "size": dummy.stat().st_size}, expected=413)
        check("2 GB + 1 byte dummy rejected before upload", "large" in error["error"])
        with dummy.open("r+b") as target:
            target.truncate(app.limit)
        disk = shutil.disk_usage(ROOT)
        free = server.RESERVE + dummy.stat().st_size - 1
        fake_disk = type(disk)(disk.total, disk.total - free, free)
        with patch.object(server.shutil, "disk_usage", return_value=fake_disk):
            error = call("POST", "/api/jobs", {"name": dummy.name, "size": dummy.stat().st_size}, expected=507)
        check("2 GB dummy rejected one byte below reserve + size", "5 GB reserve" in error["error"])
        with dummy.open("r+b") as target:
            target.truncate(server.CHUNK * 3)
        size = dummy.stat().st_size
        free = server.RESERVE + size * 2 - 1
        with patch.object(server.shutil, "disk_usage", return_value=type(disk)(disk.total, disk.total - free, free)):
            reserved = create(dummy)
            call("POST", "/api/jobs", {"name": dummy.name, "size": size}, expected=507)
        call("POST", f"/api/jobs/{reserved['id']}/cancel")
        check("outstanding upload reservations prevent overbooking", True)
        # Stream several real chunks without ever sending this dummy to the converter.
        job = upload(dummy)
        check("synthetic multi-chunk upload size preserved", job["received"] == size)
        call("POST", f"/api/jobs/{job['id']}/cancel")
        check("upload cancellation persisted", call("GET", f"/api/jobs/{job['id']}")["state"] == "failed")

        source = art_source()
        partial = create(source)
        call("PUT", f"/api/jobs/{partial['id']}/chunk", b"", {"X-Upload-Offset": "1"}, expected=409)
        call("POST", f"/api/jobs/{partial['id']}/finish", expected=409)
        call("POST", f"/api/jobs/{partial['id']}/cancel")
        check("bad offsets and incomplete submission rejected", True)

        job = upload(source)
        job_id = job["id"]
        folder = app.jobs[job_id]["folder"]
        check("uploaded art-therapy bytes match source", hashlib.sha256((folder / "upload.part").read_bytes()).digest()
              == hashlib.sha256(source.read_bytes()).digest())
        submitted = call("POST", f"/api/jobs/{job_id}/finish")
        check("queued status persisted", submitted["state"] == "queued")
        call("POST", f"/api/jobs/{job_id}/finish", expected=409)
        check("duplicate submission rejected", True)
        # The only actual converter invocation in this check is the art-therapy job.
        seen = {"queued"}
        last_report = 0
        while True:
            status = call("GET", f"/api/jobs/{job_id}")
            seen.add(status["state"])
            if time.monotonic() - last_report > 25:
                print("ART THERAPY", status["state"], status["message"], flush=True)
                last_report = time.monotonic()
            if status["state"] in server.TERMINAL:
                break
            time.sleep(0.5)
        check("background conversion reaches done", status["state"] == "done")
        check("running status observed", "running" in seen)
        publication = folder / status["publication"]
        book = json.loads(call("GET", status["downloads"]["book.json"], raw=True))
        review = json.loads(call("GET", status["downloads"]["review_list.json"], raw=True))
        manifest = json.loads(call("GET", status["downloads"]["manifest.json"], raw=True))
        check("review download equals embedded review", review == book["review"])
        check("manifest download equals converter manifest", manifest == json.loads((publication / "manifest.json").read_text("utf-8")))
        check("book download matches converter publication", book == json.loads((publication / "book.json").read_text("utf-8")))
        archive_manifests = list((folder / "output").glob("*/manifest.json.gz"))
        with gzip.open(archive_manifests[0], "rt", encoding="utf-8") as archive:
            metrics = json.load(archive)
        check("only approved nine-page book converted", metrics["pages"] == 9)
        report = {"passed": evidence, "job_id": job_id, "states_seen": sorted(seen),
                  "pages": metrics["pages"], "dummy_deleted": True}
        server.save_json(ROOT / "smoke_results.json", report)
    finally:
        # Explicit user-requested deletion of this synthetic file only. No cache deletion.
        if dummy.exists():
            dummy.unlink()
        for job in app.jobs.values():
            if job["status"]["name"] == dummy.name:
                part = job["folder"] / "upload.part"
                if part.exists():
                    part.unlink()
        httpd.shutdown()
        httpd.server_close()
        app.close()


if __name__ == "__main__":
    main()
