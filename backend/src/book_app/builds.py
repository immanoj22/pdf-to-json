"""Heavy work in worker processes, shared by everyone who asks for it.

Replaying a book's edits, building a preview and the adapter run take seconds to minutes of pure
Python. In the web process that work holds the interpreter lock, so every other request waits.
Here it runs in a pool of worker processes (one fewer than the computer has cores), and a request
that needs it gets ``Preparing`` at once and asks again.

* The same work asked for twice (same key) runs once: the second asker shares the first's future.
* Work on different books runs side by side; nothing here is global to the app.
* ``workers = 0`` runs the work in the asking thread (the tests, and a single-user setup).
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor

from .jobs import JobError

log = logging.getLogger("book_app.builds")


class Preparing(JobError):
    """The work this request needs is running; ask again in ``retry_after`` seconds."""

    def __init__(self, what: str, retry_after: int = 2):
        super().__init__(
            202,
            f"Preparing the {what}. This page will continue by itself.",
            "preparing",
            what=what,
            retry_after=retry_after,
        )


def default_workers() -> int:
    return max(1, (os.cpu_count() or 2) - 1)


def _worker_start() -> None:
    """Workers yield to the web process and to conversions, and end with the app: a worker whose
    parent is gone (the app was killed) would otherwise stay for ever, holding memory."""
    try:
        os.nice(5)
    except OSError:
        pass
    parent = os.getppid()

    def watch() -> None:
        while True:
            time.sleep(3)
            if os.getppid() != parent:
                os._exit(0)

    threading.Thread(target=watch, daemon=True, name="parent-watch").start()


def _noop() -> None:
    from . import effective, overlay  # noqa: F401 - the imports are the point


class Builds:
    def __init__(self, workers: int = -1):
        self.workers = default_workers() if workers < 0 else workers
        self.lock = threading.Lock()
        self.pool: ProcessPoolExecutor | None = None
        self.futures: dict[tuple, Future] = {}
        self.errors: dict[tuple, tuple[float, Exception]] = {}
        self.jobs: dict[tuple, str] = {}  # key -> job id, for "is anything running for this job"

    def _pool(self) -> ProcessPoolExecutor:
        if self.pool is None:
            self.pool = ProcessPoolExecutor(
                max_workers=self.workers,
                mp_context=multiprocessing.get_context("spawn"),
                initializer=_worker_start,
                max_tasks_per_child=20,
            )
        return self.pool

    def warm(self) -> None:
        """Start the worker processes now (importing the app takes seconds), so the first
        heavy request after a restart does not wait for that."""
        if self.workers == 0:
            return
        pool = self._pool()
        for _ in range(self.workers):
            pool.submit(_noop)

    def busy(self, job_id: str) -> bool:
        with self.lock:
            return any(j == job_id and k in self.futures for k, j in self.jobs.items())

    def running(self, key: tuple) -> bool:
        with self.lock:
            return key in self.futures

    def failure(self, key: tuple) -> Exception | None:
        """The error of the last run of this work, once; asking again then starts it anew."""
        with self.lock:
            found = self.errors.pop(key, None)
        return found[1] if found else None

    def submit(
        self, key: tuple, job_id: str, fn: Callable, *args, then: Callable | None = None
    ) -> Future:
        """Start the work, or return the running one for the same key. ``then(result)`` runs
        once, in this process, when the work succeeded."""
        with self.lock:
            existing = self.futures.get(key)
            if existing is not None:
                return existing
            if self.workers == 0:
                future: Future = Future()
                self.futures[key], self.jobs[key] = future, job_id
            else:
                future = self._pool().submit(fn, *args)
                self.futures[key], self.jobs[key] = future, job_id
        if self.workers == 0:
            try:
                future.set_result(fn(*args))
            except Exception as exc:  # noqa: BLE001 - handed on to the asker
                future.set_exception(exc)
        future.add_done_callback(lambda f: self._done(key, f, then))
        if self.workers == 0:
            return future
        return future

    def _done(self, key: tuple, future: Future, then: Callable | None) -> None:
        error: Exception | None = future.exception()
        result = None if error else future.result()
        try:
            if error is None and then is not None:
                then(result)
        except Exception as exc:  # noqa: BLE001
            error = exc
            log.exception("after-work step of %s failed", key)
        with self.lock:
            self.futures.pop(key, None)
            self.jobs.pop(key, None)
            if error is not None:
                self.errors[key] = (time.time(), error)
                log.warning("work %s failed: %s", key, error)

    def stop(self) -> None:
        if self.pool is not None:
            self.pool.shutdown(wait=False, cancel_futures=True)
            self.pool = None
