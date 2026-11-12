"""Jobs: one folder per book under <data>/jobs/<id>/, state in job.json, kept across restarts.

input.pdf          the upload (always this name; the printed name is only a label)
job.json           state, profile, progress, failure record, last export
cache/             this job's converter cache (stage folders; models linked in)
converter_out/     the converter's publication (book-*/book.json, images/, review/)
converter.log      the converter's own output
details.json       book details confirmed by the user
decisions.json     review decisions (who, when, what); never edits converter_out
preview/           the adapter's draft run (review list, authors)
exports/<n>/       one export each: delivery, ZIP, QC report
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from .config import AppSettings

ID_RE = re.compile(r"^[0-9a-f]{16}$")
STAGES = (
    "native", "analysis", "paint", "text", "layout", "reading_order", "furniture",
    "paragraphs", "structure_evidence", "structure", "lists", "characters", "figures",
    "equations", "mathml", "tables", "continuity", "assembly_evidence",
)  # fmt: skip
STAGE_LABELS = {
    "native": "Reading the PDF text",
    "analysis": "Analysing the pages",
    "paint": "Reading colours and boxes",
    "text": "Building the text",
    "layout": "Finding columns, figures and tables",
    "reading_order": "Working out the reading order",
    "furniture": "Finding page numbers and running heads",
    "paragraphs": "Forming paragraphs",
    "structure_evidence": "Collecting heading evidence",
    "structure": "Finding headings and chapters",
    "lists": "Finding lists",
    "characters": "Checking characters",
    "figures": "Processing figures",
    "equations": "Processing equations",
    "mathml": "Converting equations",
    "tables": "Reading tables",
    "continuity": "Joining text across pages",
    "assembly_evidence": "Assembling the book",
}
TERMINAL = {"converted", "failed", "cancelled"}


class JobError(Exception):
    def __init__(self, status: int, message: str, code: str | None = None, **extra):
        super().__init__(message)
        self.status, self.message, self.code, self.extra = status, message, code, extra


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def safe_name(name: str | None) -> str:
    """A display label only: no path parts, no control characters, at most 200 characters."""
    name = unicodedata.normalize("NFC", (name or "").replace("\\", "/").split("/")[-1])
    name = "".join(ch for ch in name if ch.isprintable()).strip().strip(".")
    return name[:200] or "book.pdf"


def write_json(path: Path, data) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n", "utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return default


class JobStore:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.root = settings.data_path / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    # ------------------------------------------------------------------ access

    def folder(self, job_id: str) -> Path:
        if not ID_RE.match(job_id or ""):
            raise JobError(404, "No such book.", "not_found")
        folder = self.root / job_id
        if not folder.is_dir():
            raise JobError(404, "No such book.", "not_found")
        return folder

    def get(self, job_id: str) -> dict:
        data = read_json(self.folder(job_id) / "job.json")
        if data is None:
            raise JobError(404, "No such book.", "not_found")
        return data

    def update(self, job_id: str, **changes) -> dict:
        with self.lock:
            job = self.get(job_id)
            job.update(changes)
            job["updated_at"] = now()
            write_json(self.folder(job_id) / "job.json", job)
            return job

    def list(self) -> list[dict]:
        jobs = []
        for folder in self.root.iterdir():
            if ID_RE.match(folder.name):
                job = read_json(folder / "job.json")
                if job:
                    jobs.append(job)
        return sorted(jobs, key=lambda j: j.get("created_at", ""), reverse=True)

    def publication(self, job_id: str) -> Path:
        job = self.get(job_id)
        rel = job.get("publication")
        if job["state"] != "converted" or not rel:
            raise JobError(409, "The book has not been converted yet.", "not_converted")
        return self.folder(job_id) / rel

    # ------------------------------------------------------------------ create / delete

    def create(self, display_name: str, size: int, pages: int) -> tuple[dict, Path]:
        job_id = secrets.token_hex(8)
        folder = self.root / job_id
        folder.mkdir()
        job = {
            "id": job_id,
            "name": safe_name(display_name),
            "size": size,
            "pages": pages,
            "created_at": now(),
            "updated_at": now(),
            "state": "uploaded",
            "profile": None,
            "progress": None,
            "failure": None,
            "last_export": None,
            "exports": 0,
        }
        write_json(folder / "job.json", job)
        return job, folder / "input.pdf"

    def delete(self, job_id: str) -> None:
        folder = self.folder(job_id)
        job = self.get(job_id)
        if job["state"] in ("queued", "converting"):
            raise JobError(409, "Cancel the conversion before deleting the book.", "busy")
        if folder.resolve().parent != self.root.resolve():
            raise JobError(400, "Not a job folder.")
        shutil.rmtree(folder)

    def recover(self) -> list[str]:
        """After a restart: a conversion that was running stopped with the app. It is shown as
        failed with its own record (the converter's cache lets 'Convert again' resume);
        queued jobs go back in the queue."""
        queued = []
        for job in self.list():
            if job["state"] == "converting":
                self.update(
                    job["id"],
                    state="failed",
                    failure={
                        "stage": (job.get("progress") or {}).get("stage"),
                        "page": None,
                        "error_type": "Interrupted",
                        "message": "The app was closed while the book was converting. "
                        "Press Convert again: finished pages are kept.",
                    },
                )
            elif job["state"] == "queued":
                queued.append(job["id"])
        return queued


def disk_requirement(settings_path: Path, pdf_bytes: int, pages: int) -> dict:
    """The converter's disk rule: estimated bytes must fit in the free space, keeping its
    reserve. The estimate is conservative: 2 MB per page and three times the PDF."""
    try:
        from book_core.cache_admin import RESERVE_BYTES
    except Exception:  # pragma: no cover - converter missing
        RESERVE_BYTES = 5_000_000_000
    estimate = 3 * pdf_bytes + 2_000_000 * pages
    free = shutil.disk_usage(settings_path).free
    return {
        "estimated_bytes": estimate,
        "free_bytes": free,
        "reserve_bytes": RESERVE_BYTES,
        "ok": estimate <= free - RESERVE_BYTES,
    }


def converter_env(job_dir: Path) -> dict:
    env = os.environ.copy()
    tmp = job_dir / "tmp"
    tmp.mkdir(exist_ok=True)
    env.update(
        TMPDIR=str(tmp),
        TEMP=str(tmp),
        TMP=str(tmp),
        PYTHONDONTWRITEBYTECODE="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        DO_NOT_TRACK="1",
        MPLCONFIGDIR=str(tmp / "mpl"),
    )
    return env


def parts_hash(parts) -> str:
    """Identity of a set of confirmed book parts (what a converted book was built with)."""
    import hashlib

    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def stage_progress(cache: Path) -> dict | None:
    present = [i for i, s in enumerate(STAGES) if (cache / s).exists()]
    if not present:
        return {"stage": None, "index": 0, "total": len(STAGES), "label": "Starting"}
    i = max(present)
    return {
        "stage": STAGES[i],
        "index": i + 1,
        "total": len(STAGES),
        "label": STAGE_LABELS[STAGES[i]],
    }


class Converter:
    """Runs conversions in background threads, at most ``max_parallel_jobs`` at a time."""

    def __init__(self, store: JobStore):
        self.store = store
        self.settings = store.settings
        self.slots = threading.BoundedSemaphore(self.settings.max_parallel_jobs)
        self.cancel_flags: dict[str, threading.Event] = {}
        self.procs: dict[str, subprocess.Popen] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.stopping = threading.Event()

    def command(self, job_dir: Path) -> list[str]:
        base = self.settings.converter_command or [
            sys.executable,
            "-B",
            "-m",
            "book_core",
            "run-book",
        ]
        return [
            *base,
            str(job_dir / "input.pdf"),
            "--out",
            str(job_dir / "converter_out"),
            "--cache-dir",
            str(job_dir / "cache"),
            "--workers",
            str(self.settings.converter_workers),
            *self._parts_args(job_dir),
        ]

    @staticmethod
    def _parts_args(job_dir: Path) -> list[str]:
        """The confirmed book parts, when the person has confirmed them: authoritative zones."""
        path = job_dir / "parts_confirmed.json"
        return ["--parts", str(path)] if path.is_file() else []

    def submit(self, job_id: str) -> dict:
        job = self.store.get(job_id)
        if job["state"] in ("queued", "converting"):
            raise JobError(409, "This book is already being converted.", "busy")
        if not job.get("profile"):
            raise JobError(409, "Choose a profile first.", "no_profile")
        job_dir = self.store.folder(job_id)
        disk = disk_requirement(job_dir, job["size"], job["pages"])
        if not disk["ok"]:
            raise JobError(
                507,
                f"Not enough free disk space: this book needs about "
                f"{disk['estimated_bytes'] / 1e9:.1f} GB and the converter keeps "
                f"{disk['reserve_bytes'] / 1e9:.0f} GB free; "
                f"only {disk['free_bytes'] / 1e9:.1f} GB "
                "is free.",
                "disk_space",
                **disk,
            )
        job = self.store.update(
            job_id, state="queued", failure=None, progress=None, started_at=None, finished_at=None
        )
        self.start_thread(job_id)
        return job

    def start_thread(self, job_id: str) -> None:
        self.cancel_flags[job_id] = threading.Event()
        t = threading.Thread(
            target=self._run, args=(job_id,), name=f"convert-{job_id}", daemon=True
        )
        self.threads[job_id] = t
        t.start()

    def resume_queued(self, ids: list[str]) -> None:
        for job_id in ids:
            self.start_thread(job_id)

    def cancel(self, job_id: str) -> dict:
        job = self.store.get(job_id)
        if job["state"] not in ("queued", "converting"):
            raise JobError(409, "This book is not being converted.", "not_running")
        flag = self.cancel_flags.get(job_id)
        if flag:
            flag.set()
        proc = self.procs.get(job_id)
        if proc:
            self._kill(proc)
        return self.store.get(job_id)

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            proc.wait()

    def _link_models(self, cache: Path) -> None:
        models = self.settings.models_path
        link = cache / "huggingface"
        if models and models.is_dir() and not link.exists():
            link.symlink_to(models, target_is_directory=True)

    def _cleanup(self, job_dir: Path) -> None:
        for name in ("converter_out", "tmp"):
            shutil.rmtree(job_dir / name, ignore_errors=True)

    def _run(self, job_id: str) -> None:
        flag = self.cancel_flags[job_id]
        job_dir = self.store.folder(job_id)
        while not self.slots.acquire(timeout=0.3):
            if flag.is_set() or self.stopping.is_set():
                break
        else:
            try:
                self._convert(job_id, job_dir, flag)
            finally:
                self.slots.release()
                self.procs.pop(job_id, None)
            return
        self._finish_cancelled(job_id, job_dir)

    def _finish_cancelled(self, job_id: str, job_dir: Path) -> None:
        if self.stopping.is_set():
            return  # the app is closing: recover() handles it on the next start
        self._cleanup(job_dir)
        self.store.update(job_id, state="cancelled", progress=None, finished_at=now())

    def _convert(self, job_id: str, job_dir: Path, flag: threading.Event) -> None:
        started = time.time()
        self._cleanup(job_dir)
        cache = job_dir / "cache"
        cache.mkdir(exist_ok=True)
        self._link_models(cache)
        self.store.update(
            job_id, state="converting", started_at=now(), progress=stage_progress(cache)
        )
        try:
            with open(job_dir / "converter.log", "wb") as log:
                proc = subprocess.Popen(
                    self.command(job_dir),
                    cwd=job_dir,
                    env=converter_env(job_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                self.procs[job_id] = proc
                while proc.poll() is None:
                    if flag.is_set() or self.stopping.is_set():
                        self._kill(proc)
                        break
                    time.sleep(0.25)
                    self.store.update(job_id, progress=stage_progress(cache))
            if flag.is_set():
                self._finish_cancelled(job_id, job_dir)
                return
            if self.stopping.is_set():
                return
            publications = sorted((job_dir / "converter_out").glob("book-*/book.json"))
            if proc.returncode == 0 and len(publications) == 1:
                self.store.update(
                    job_id,
                    state="converted",
                    progress={
                        "stage": None,
                        "index": len(STAGES),
                        "total": len(STAGES),
                        "label": "Done",
                    },
                    publication=str(publications[0].parent.relative_to(job_dir)),
                    finished_at=now(),
                    failure=None,
                )
                shutil.rmtree(job_dir / "tmp", ignore_errors=True)
                self._mark_parts_built(job_dir)
                return
            failure = self.failure_record(job_dir, cache, started, proc.returncode)
            self.store.update(job_id, state="failed", failure=failure, finished_at=now())
        except Exception as error:  # the job must never stay 'converting'
            self.store.update(
                job_id,
                state="failed",
                finished_at=now(),
                failure={
                    "stage": None,
                    "page": None,
                    "error_type": type(error).__name__,
                    "message": str(error),
                },
            )

    @staticmethod
    def _mark_parts_built(job_dir: Path) -> None:
        """A finished conversion that was run with the confirmed parts is built with them."""
        path = job_dir / "parts.json"
        saved = read_json(path, {})
        if saved.get("confirmed") and (job_dir / "parts_confirmed.json").is_file():
            saved["built_with"] = parts_hash(saved["confirmed"]["parts"])
            write_json(path, saved)

    @staticmethod
    def failure_record(job_dir: Path, cache: Path, started: float, returncode) -> dict:
        """The converter's own failure record (page, stage, message), else the last line of
        its output. Never a stack trace."""
        records = (
            sorted((cache / "failures").glob("*.json")) if (cache / "failures").is_dir() else []
        )
        for path in reversed(records):
            if path.stat().st_mtime >= started - 2:
                data = read_json(path, {})
                return {
                    "stage": data.get("stage"),
                    "page": data.get("page"),
                    "error_type": data.get("error_type"),
                    "message": data.get("message") or "The converter stopped.",
                }
        tail = ""
        try:
            lines = (job_dir / "converter.log").read_text("utf-8", "replace").strip().splitlines()
            tail = lines[-1][:300] if lines else ""
        except OSError:
            pass
        return {
            "stage": None,
            "page": None,
            "error_type": "ConverterExit",
            "message": f"The converter stopped (exit code {returncode}). {tail}".strip(),
        }

    def stop(self) -> None:
        self.stopping.set()
        for proc in list(self.procs.values()):
            self._kill(proc)
        for t in list(self.threads.values()):
            t.join(timeout=10)
