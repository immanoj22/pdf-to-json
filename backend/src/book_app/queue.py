"""The conversion queue, the reviewers of each book, and the app's audit log.

Queue: books are converted in the queue's order, up to ``max_parallel_jobs`` at a time. The
order and the paused books are kept in ``<data>/queue.json``, so the queue survives a restart
(a conversion that was running when the app stopped goes back to the front and resumes from
its cache). A failed or cancelled book leaves the queue; it never blocks the books after it.

Assignments: a manager gives a converted book to one or more reviewers, each with a page
range or the whole book (``<job>/assignments.json``).

Audit log: every action of a person (upload, queue, pause, move, cancel, assign, review,
export, delete) as one JSON line in ``<data>/audit.jsonl``.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .jobs import JobError, now, read_json, write_json

ROLES = ("manager", "reviewer")
_lock = threading.RLock()


class Queue:
    def __init__(self, data: Path):
        self.path = Path(data) / "queue.json"

    def load(self) -> dict:
        state = read_json(self.path, {}) or {}
        return {"order": list(state.get("order") or []), "paused": list(state.get("paused") or [])}

    def save(self, state: dict) -> None:
        write_json(self.path, state)

    def add(self, job_id: str, front: bool = False) -> None:
        with _lock:
            state = self.load()
            if job_id in state["order"]:
                state["order"].remove(job_id)
            if front:
                state["order"].insert(0, job_id)
            else:
                state["order"].append(job_id)
            self.save(state)

    def remove(self, job_id: str) -> None:
        with _lock:
            state = self.load()
            state["order"] = [j for j in state["order"] if j != job_id]
            state["paused"] = [j for j in state["paused"] if j != job_id]
            self.save(state)

    def move(self, job_id: str, direction: str) -> None:
        with _lock:
            state = self.load()
            order = state["order"]
            if job_id not in order:
                raise JobError(409, "This book is not in the queue.", "not_queued")
            i = order.index(job_id)
            j = i - 1 if direction == "up" else i + 1 if direction == "down" else None
            if j is None:
                raise JobError(422, "A book moves up or down.", "bad_direction")
            if 0 <= j < len(order):
                order[i], order[j] = order[j], order[i]
            self.save(state)

    def pause(self, job_id: str, paused: bool) -> None:
        with _lock:
            state = self.load()
            if job_id not in state["order"]:
                raise JobError(409, "This book is not in the queue.", "not_queued")
            state["paused"] = [j for j in state["paused"] if j != job_id] + ([job_id] if paused else [])
            self.save(state)

    def is_paused(self, job_id: str) -> bool:
        return job_id in self.load()["paused"]

    def first_waiting(self, waiting: set[str]) -> str | None:
        """The first book of the queue that is waiting to start and not paused."""
        state = self.load()
        paused = set(state["paused"])
        return next((j for j in state["order"] if j in waiting and j not in paused), None)


class Audit:
    def __init__(self, data: Path):
        self.path = Path(data) / "audit.jsonl"

    def log(self, who: str, action: str, job: str | None = None, **details) -> dict:
        entry = {"at": now(), "who": (who or "").strip() or "unknown", "action": action,
                 "job": job, **details}  # fmt: skip
        with _lock, open(self.path, "a", encoding="utf-8") as out:
            out.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return entry

    def entries(self, job: str | None = None, limit: int = 500) -> list[dict]:
        if not self.path.is_file():
            return []
        rows = [json.loads(line) for line in self.path.read_text("utf-8").splitlines() if line]
        if job:
            rows = [r for r in rows if r.get("job") == job]
        return rows[-limit:]


def clean_assignments(rows, pages: int) -> list[dict]:
    """[{name, first, last}] (first/last None: the whole book), each checked."""
    out = []
    if not isinstance(rows, list) or not rows:
        raise JobError(422, "Name at least one reviewer.", "no_reviewers")
    for row in rows:
        name = str((row or {}).get("name") or "").strip()
        if not name:
            raise JobError(422, "Every reviewer needs a name.", "no_name")
        first, last = row.get("first"), row.get("last")
        if first in (None, "") and last in (None, ""):
            first = last = None
        else:
            try:
                first, last = int(first), int(last)
            except (TypeError, ValueError) as error:
                raise JobError(422, f"Give {name} a first and last page, or the whole book.",
                               "bad_range") from error  # fmt: skip
            if not 1 <= first <= last <= pages:
                raise JobError(422, f"{name}: pages run from 1 to {pages}.", "bad_range")
        out.append({"name": name, "first": first, "last": last})
    return out


def assignments(job_dir: Path) -> list[dict]:
    return (read_json(job_dir / "assignments.json", {}) or {}).get("reviewers", [])


def save_assignments(job_dir: Path, rows: list[dict], who: str) -> list[dict]:
    write_json(job_dir / "assignments.json", {"reviewers": rows, "by": who, "at": now()})
    return rows


__all__ = ["Audit", "Queue", "ROLES", "assignments", "clean_assignments", "save_assignments"]
