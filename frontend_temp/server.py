"""Temporary loopback upload server. Python standard library only; no core imports."""

import argparse
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
RESERVE = 5_000_000_000
CHUNK = 4 * 1024 * 1024
BUFFER = 64 * 1024
TERMINAL = {"done", "failed"}


class RequestError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def save_json(path, data):
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
    pending.replace(path)


class App:
    def __init__(self, settings, runtime=None):
        self.limit = settings["max_upload_bytes"]
        if type(self.limit) is not int or not 0 < self.limit <= 2**53 - 1:
            raise ValueError("max_upload_bytes must be a positive integer below 2**53")
        self.python = (ROOT / settings["converter_python"]).resolve()
        if not self.python.is_file():
            raise ValueError(f"Converter Python does not exist: {self.python}")
        self.runtime = (runtime or ROOT / "runtime").resolve()
        if not self.runtime.is_relative_to(ROOT):
            raise ValueError("Runtime must be inside frontend_temp")
        (self.runtime / "jobs").mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.jobs, self.pending = {}, queue.Queue()
        self.stopping = threading.Event()
        # Never silently rerun an interrupted conversion or delete its artifacts.
        for path in (self.runtime / "jobs").glob("*/status.json"):
            status = json.loads(path.read_text("utf-8"))
            if status["state"] not in TERMINAL:
                status.update(state="failed", message="Server stopped before completion.")
                save_json(path, status)
            self.jobs[status["id"]] = self.make_job(path.parent, status)
        self.worker = threading.Thread(target=self.work, daemon=True)
        self.worker.start()

    @staticmethod
    def make_job(folder, status):
        return {"folder": folder, "status": status, "cancel": threading.Event(),
                "active": False, "process": None}

    def persist(self, job, **changes):
        job["status"].update(changes, updated_at=time.time())
        save_json(job["folder"] / "status.json", job["status"])
        return dict(job["status"])

    def get(self, job_id):
        if job_id not in self.jobs:
            raise RequestError(404, "Job not found.")
        return self.jobs[job_id]

    def check_disk(self, extra=0):
        outstanding = sum(j["status"]["size"] - j["status"]["received"]
                          for j in self.jobs.values() if j["status"]["state"] == "uploading")
        needed = RESERVE + outstanding + extra
        free = shutil.disk_usage(self.runtime).free
        if free < needed:
            raise RequestError(507, f"Not enough free disk: need {needed:,} bytes "
                               f"including the 5 GB reserve; {free:,} bytes available.")

    def create(self, data):
        name, size = data.get("name"), data.get("size")
        if not isinstance(name, str) or not name.lower().endswith(".pdf") or len(name) > 255:
            raise RequestError(400, "Choose a PDF file with a name of at most 255 characters.")
        if type(size) is not int or size <= 0:
            raise RequestError(400, "The PDF must have a positive integer file size.")
        if size > self.limit:
            raise RequestError(413, f"File is too large: maximum {self.limit:,} bytes "
                               f"({self.limit / 1e9:g} GB).")
        with self.lock:
            self.check_disk(size)
            job_id = secrets.token_hex(16)
            folder = self.runtime / "jobs" / job_id
            folder.mkdir()
            (folder / "upload.part").touch()
            status = {"id": job_id, "name": name, "size": size, "received": 0,
                      "state": "uploading", "message": "Uploading PDF."}
            job = self.make_job(folder, status)
            self.jobs[job_id] = job
            return self.persist(job)

    def chunk(self, job_id, offset, length, stream):
        with self.lock:
            job = self.get(job_id)
            status = job["status"]
            if status["state"] != "uploading" or job["active"]:
                raise RequestError(409, "This upload is no longer accepting chunks.")
            if offset != status["received"]:
                raise RequestError(409, "Upload offset does not match; start a new upload.")
            if not 0 < length <= CHUNK or offset + length > status["size"]:
                raise RequestError(413, "Chunk exceeds the chunk limit or declared file size.")
            self.check_disk()
            job["active"] = True
        try:
            # Bounded reads and writes: the PDF is never buffered as a whole.
            with (job["folder"] / "upload.part").open("r+b") as target:
                target.seek(offset)
                remaining = length
                while remaining:
                    if job["cancel"].is_set():
                        raise RequestError(409, "Upload cancelled.")
                    block = stream.read(min(BUFFER, remaining))
                    if not block:
                        raise RequestError(400, "Upload interrupted before the chunk completed.")
                    target.write(block)
                    remaining -= len(block)
                    with self.lock:
                        status["received"] += len(block)
                target.flush()
            with self.lock:
                return self.persist(job)
        except Exception:
            with self.lock:
                if status["state"] == "uploading":
                    self.persist(job, state="failed", message="Upload interrupted; start a new upload.")
            raise
        finally:
            with self.lock:
                job["active"] = False

    def finish(self, job_id):
        with self.lock:
            job = self.get(job_id)
            status = job["status"]
            if status["state"] != "uploading" or job["active"] or status["received"] != status["size"]:
                raise RequestError(409, "Upload is incomplete or already submitted.")
            part = job["folder"] / "upload.part"
            with part.open("rb") as source:
                if b"%PDF-" not in source.read(1024):
                    self.persist(job, state="failed", message="File does not have a PDF header.")
                    raise RequestError(415, "File does not have a PDF header.")
            part.replace(job["folder"] / "input.pdf")
            result = self.persist(job, state="queued", message="Waiting for the converter.")
            self.pending.put(job_id)
            return result

    def cancel(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job["status"]["state"] in TERMINAL:
                return dict(job["status"])
            job["cancel"].set()
            if job["status"]["state"] == "running":
                return self.persist(job, message="Cancelling converter…")
            return self.persist(job, state="failed", message="Cancelled by user.", cancelled=True)

    def environment(self):
        env = os.environ.copy()
        locations = {"TEMP": "tmp", "TMP": "tmp", "TMPDIR": "tmp",
                     "XDG_CACHE_HOME": "cache", "HF_HOME": "cache/huggingface",
                     "TORCH_HOME": "cache/torch", "MPLCONFIGDIR": "cache/matplotlib",
                     "APPDATA": "appdata", "LOCALAPPDATA": "appdata/local"}
        for key, relative in locations.items():
            path = self.runtime / relative
            path.mkdir(parents=True, exist_ok=True)
            env[key] = str(path)
        env.update(PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1",
                   TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1",
                   HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1")
        return env

    @staticmethod
    def terminate(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def work(self):
        while not self.stopping.is_set():
            try:
                job_id = self.pending.get(timeout=0.5)
            except queue.Empty:
                continue
            job = self.jobs[job_id]
            try:
                with self.lock:
                    if job["status"]["state"] != "queued":
                        continue
                    self.check_disk()
                    self.persist(job, state="running", message="Converting with the default profile.")
                folder = job["folder"]
                command = [str(self.python), "-B", "-m", "book_core", "run-book",
                           str(folder / "input.pdf"), "--out", str(folder / "output"),
                           "--cache-dir", str(self.runtime / "cache"), "--workers", "1"]
                save_json(folder / "command.json", command)
                with (folder / "converter.log").open("wb") as log:
                    process = subprocess.Popen(command, cwd=folder, env=self.environment(),
                                               stdin=subprocess.DEVNULL, stdout=log,
                                               stderr=subprocess.STDOUT,
                                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    job["process"] = process
                    while process.poll() is None:
                        if job["cancel"].wait(0.2) or self.stopping.is_set():
                            self.terminate(process)
                    if job["cancel"].is_set() or self.stopping.is_set():
                        raise RuntimeError("Cancelled; generated files and caches have been retained.")
                    if process.returncode:
                        raise RuntimeError(f"Converter exited with code {process.returncode}. "
                                           "See converter.log in this job's folder.")
                publications = list((folder / "output").glob("book-*/book.json"))
                if len(publications) != 1 or not publications[0].with_name("manifest.json").is_file():
                    raise RuntimeError("Converter did not publish book.json and manifest.json.")
                # The existing command embeds review in book.json; expose a convenience export.
                with publications[0].open(encoding="utf-8") as book:
                    review = json.load(book)["review"]
                save_json(folder / "review_list.json", review)
                with self.lock:
                    if job["cancel"].is_set() or self.stopping.is_set():
                        raise RuntimeError("Cancelled; generated files and caches have been retained.")
                    self.persist(job, state="done", message="Conversion complete.",
                                 publication=str(publications[0].parent.relative_to(folder)),
                                 downloads={name: f"/api/jobs/{job_id}/download/{name}"
                                            for name in ("book.json", "review_list.json", "manifest.json")})
            except Exception as exc:
                with self.lock:
                    self.persist(job, state="failed", message=str(exc),
                                 cancelled=job["cancel"].is_set())
            finally:
                job["process"] = None
                self.pending.task_done()

    def download(self, job_id, name):
        with self.lock:
            job = self.get(job_id)
            status = job["status"]
            if status["state"] != "done" or name not in status.get("downloads", {}):
                raise RequestError(404, "Download not available.")
            path = job["folder"] / ("review_list.json" if name == "review_list.json"
                                     else str(Path(status["publication"]) / name))
            if not path.resolve().is_relative_to(job["folder"].resolve()):
                raise RequestError(404, "Download not available.")
            return path

    def close(self):
        self.stopping.set()
        with self.lock:
            for job in self.jobs.values():
                if job["status"]["state"] not in TERMINAL:
                    job["cancel"].set()
                    if job["status"]["state"] != "running":
                        self.persist(job, state="failed", message="Server stopped before completion.")
        self.worker.join(timeout=10)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Status polling is frequent; conversion details live in each job's log.
        pass

    def respond(self, code, body, content_type="application/json; charset=utf-8", download=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.headers_common(download)
        self.end_headers()
        self.wfile.write(body)

    def headers_common(self, download=None):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; "
                         "style-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'none'")
        self.send_header("Connection", "close")
        self.close_connection = True
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')

    def length(self, maximum):
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
            raise RequestError(411, "Send exactly one Content-Length; transfer coding is not supported.")
        value = self.headers["Content-Length"]
        if not re.fullmatch(r"\d{1,16}", value):
            raise RequestError(400, "Invalid Content-Length.")
        length = int(value)
        if length > maximum:
            raise RequestError(413, "Request exceeds the chunk or metadata limit.")
        return length

    def handle_request(self):
        self.connection.settimeout(30)
        try:
            expected = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected:
                raise RequestError(403, "Use the printed 127.0.0.1 URL.")
            if self.headers.get("Origin", f"http://{expected}") != f"http://{expected}":
                raise RequestError(403, "Only same-origin local requests are accepted.")
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise RequestError(403, "Cross-site requests are refused.")
            method, path = self.command, urlsplit(self.path).path
            app = self.server.app
            if method != "GET" and not secrets.compare_digest(self.headers.get("X-Upload-Token", ""), app.token):
                raise RequestError(403, "Missing local upload token; reload this page.")
            static = {"/": ("index.html", "text/html"), "/style.css": ("style.css", "text/css"),
                      "/app.js": ("app.js", "text/javascript")}
            if method == "GET" and path in static:
                name, content_type = static[path]
                self.respond(200, (ROOT / name).read_bytes(), content_type + "; charset=utf-8")
                return
            if method == "GET" and path == "/api/config":
                result = {"max_bytes": app.limit, "reserve_bytes": RESERVE,
                          "chunk_bytes": CHUNK, "token": app.token}
            elif method == "POST" and path == "/api/jobs":
                raw = self.rfile.read(self.length(4096))
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise RequestError(400, "Expected a JSON object.")
                result = app.create(data)
            else:
                match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})(?:/(chunk|finish|cancel|download/(book\.json|review_list\.json|manifest\.json)))?", path)
                if not match:
                    raise RequestError(404, "Not found.")
                job_id, action, name = match.groups()
                if method == "GET" and action is None:
                    with app.lock:
                        # Read the persisted status file rather than inferred process state.
                        result = json.loads((app.get(job_id)["folder"] / "status.json").read_text("utf-8"))
                elif method == "GET" and name:
                    with app.download(job_id, name).open("rb") as source:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(os.fstat(source.fileno()).st_size))
                        self.headers_common(name)
                        self.end_headers()
                        shutil.copyfileobj(source, self.wfile, BUFFER)
                    return
                elif method == "PUT" and action == "chunk":
                    offset = self.headers.get("X-Upload-Offset", "")
                    if not re.fullmatch(r"\d{1,16}", offset):
                        raise RequestError(400, "A numeric X-Upload-Offset is required.")
                    result = app.chunk(job_id, int(offset), self.length(CHUNK), self.rfile)
                elif method == "POST" and action in {"finish", "cancel"}:
                    if self.length(0):
                        raise RequestError(400, "Expected an empty request.")
                    result = app.finish(job_id) if action == "finish" else app.cancel(job_id)
                else:
                    raise RequestError(405, "Method not allowed.")
            self.respond(200, json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except RequestError as exc:
            self.respond(exc.code, json.dumps({"error": exc.message}).encode())
        except (ValueError, UnicodeError) as exc:
            self.respond(400, json.dumps({"error": f"Invalid request: {exc}"}).encode())
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (OSError, TimeoutError) as exc:
            try:
                self.respond(500, json.dumps({"error": f"Local I/O error: {exc}"}).encode())
            except OSError:
                pass

    do_GET = do_POST = do_PUT = handle_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=ROOT / "settings.json")
    args = parser.parse_args()
    settings = json.loads(args.settings.read_text("utf-8"))
    port = settings["port"]
    if type(port) is not int or not 0 < port < 65536:
        parser.error("port must be between 1 and 65535")
    app = App(settings)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.app = app
    print(f"Local upload page: http://127.0.0.1:{port} (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()


if __name__ == "__main__":
    main()
