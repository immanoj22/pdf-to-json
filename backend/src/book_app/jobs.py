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
        """After a restart: a conversion that was running stopped with the app; it goes back
        to the front of the queue and resumes from its cache (finished stages are kept).
        Queued books stay in the queue in its saved order. Returns the books to start."""
        from .queue import Queue

        queue = Queue(self.settings.data_path)
        jobs = {job["id"]: job for job in self.list()}
        resumed = [j for j, job in jobs.items() if job["state"] == "converting"]
        for job_id in resumed:
            self.update(job_id, state="queued", progress=None, resumed_at=now())
        order = queue.load()["order"]
        for job_id in reversed(resumed):
            if job_id in order:
                order.remove(job_id)
            order.insert(0, job_id)
        queued = [j for j, job in jobs.items() if job["state"] in ("queued", "converting")]
        order = [j for j in order if j in queued] + sorted(
            (j for j in queued if j not in order), key=lambda j: jobs[j].get("created_at", "")
        )
        queue.save({**queue.load(), "order": order})
        return order


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
    """Runs conversions in background threads in the queue's order, at most
    ``max_parallel_jobs`` at a time (``queue.Queue``: order and paused books)."""

    def __init__(self, store: JobStore):
        from .queue import Queue

        self.store = store
        self.settings = store.settings
        self.queue = Queue(self.settings.data_path)
        self.slots = threading.BoundedSemaphore(self.settings.max_parallel_jobs)
        self.cancel_flags: dict[str, threading.Event] = {}
        self.pause_flags: dict[str, threading.Event] = {}
        self.procs: dict[str, subprocess.Popen] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.stopping = threading.Event()

    def workers_now(self, at: datetime | None = None) -> int:
        """CPU workers for a conversion starting now. By day the people reviewing keep two cores
        (and ``converter_workers`` is the most); inside the night window every core is used."""
        cores = os.cpu_count() or 2
        if self.in_night(at):
            return self.settings.converter_night_workers or cores
        return max(1, min(self.settings.converter_workers, cores - 2))

    def in_night(self, at: datetime | None = None) -> bool:
        local = (at or datetime.now()).strftime("%H:%M")
        start, end = self.settings.converter_night_start, self.settings.converter_night_end
        return local >= start or local < end if start > end else start <= local < end

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
            str(self.workers_now()),
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
            job_id, state="queued", failure=None, progress=None, started_at=None, finished_at=None,
            queued_at=now(),
        )
        self.queue.add(job_id)
        self.start_thread(job_id)
        return job

    def start_thread(self, job_id: str) -> None:
        self.cancel_flags[job_id] = threading.Event()
        self.pause_flags[job_id] = threading.Event()
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
        if flag is None:  # no thread (a queue left from an earlier run): cancelled here
            self.queue.remove(job_id)
            self.store.update(job_id, state="cancelled", progress=None, finished_at=now())
        return self.store.get(job_id)

    def pause(self, job_id: str) -> dict:
        """Stop a running conversion and put it back, paused, at its place in the queue. What it
        finished stays in its cache, so Resume (``queue.pause(job, False)``) goes on from there."""
        job = self.store.get(job_id)
        flag = self.pause_flags.get(job_id)
        if job["state"] != "converting" or flag is None:
            raise JobError(409, "Only a running conversion can be paused.", "not_running")
        self.queue.pause(job_id, True)
        flag.set()
        return job

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

    def _waiting(self) -> set[str]:
        return {j for j, t in self.threads.items() if t.is_alive()
                and j not in self.procs and not self.cancel_flags[j].is_set()}  # fmt: skip

    def _my_turn(self, job_id: str) -> bool:
        """The first unpaused book of the queue among the ones waiting for a slot."""
        try:
            if self.store.get(job_id).get("state") != "queued":
                return False
        except JobError:
            return False
        return self.queue.first_waiting(self._waiting()) == job_id

    def _run(self, job_id: str) -> None:
        flag = self.cancel_flags[job_id]
        job_dir = self.store.folder(job_id)
        while True:
            acquired = False
            while not (flag.is_set() or self.stopping.is_set()):
                if self._my_turn(job_id) and self.slots.acquire(timeout=0.3):
                    acquired = True
                    self.procs[job_id] = None  # taken: the next book of the queue may go
                    break
                time.sleep(0.3)
            if not acquired:
                break
            paused = False
            try:
                paused = self._convert(job_id, job_dir, flag)
            finally:
                self.slots.release()
                self.procs.pop(job_id, None)
            if not paused:  # converted, failed or cancelled: out of the queue
                if not self.stopping.is_set():
                    self.queue.remove(job_id)
                return
            # paused: waits in the queue (skipped there while paused) and starts again on Resume
        self.procs.pop(job_id, None)
        if not self.stopping.is_set():
            self.queue.remove(job_id)
        self._finish_cancelled(job_id, job_dir)

    def _finish_cancelled(self, job_id: str, job_dir: Path) -> None:
        if self.stopping.is_set():
            return  # the app is closing: recover() handles it on the next start
        self._cleanup(job_dir)
        self.store.update(job_id, state="cancelled", progress=None, finished_at=now())

    def _convert(self, job_id: str, job_dir: Path, flag: threading.Event) -> bool:
        """Run one conversion. True when it was paused (the book goes back to the queue)."""
        pause = self.pause_flags[job_id]
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
                try:  # yield to the people using the app; its workers inherit this
                    os.setpriority(os.PRIO_PROCESS, proc.pid, self.settings.converter_nice)
                except OSError:
                    pass
                while proc.poll() is None:
                    if flag.is_set() or self.stopping.is_set() or pause.is_set():
                        self._kill(proc)
                        break
                    time.sleep(0.25)
                    self.store.update(job_id, progress=stage_progress(cache))
            if pause.is_set() and not flag.is_set() and not self.stopping.is_set():
                pause.clear()
                self.store.update(
                    job_id, state="queued", progress=stage_progress(cache), paused_at=now()
                )
                return True
            if flag.is_set():
                self._finish_cancelled(job_id, job_dir)
                return False
            if self.stopping.is_set():
                return False
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
                return False
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
        return False

    @staticmethod
    def _mark_parts_built(job_dir: Path) -> None:
        """A finished conversion that was run with the confirmed parts is built with them."""
        path = job_dir / "parts.json"
        saved = read_json(path, {})
        given = saved.get("confirmed") or saved.get("planned")  # confirmed, or given at upload
        if given and (job_dir / "parts_confirmed.json").is_file():
            saved["built_with"] = parts_hash(given["parts"])
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
            if proc is not None:
                self._kill(proc)
        for t in list(self.threads.values()):
            t.join(timeout=10)
