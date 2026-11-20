"""Automatic cleanup of regenerable files in the app's data folder.

What it may remove, per job (a job is never touched while it is queued or converting):

* ``preview.tmp/`` and ``preview.old/``: leftovers of a preview build. Always, unless a build of
  that job is running (the job lock is held).
* ``preview/`` (the export preview) and ``pagecache/`` (page images): when the job is not open and
  either its last export finished ``after_export_hours`` ago or nothing has happened on the job
  for ``idle_days``. Both are rebuilt on demand.
* A child of ``converter_out/`` that nothing refers to. Each one is checked against four things,
  and the proof is written into the report: it is not the job's publication, it is not the
  ``final_key`` archive the publication's manifest names (read by "Find similar"), no file of the
  publication links to it, and no top-level job file or export record names it.
* ``cache/`` (the converter's per-page results) is only reported. It takes hours to rebuild, so it
  is removed only when ``delete_converter_cache`` is switched on.

It never touches ``input.pdf``, ``job.json``, ``decisions.json`` and the other edit and settings
files, ``exports/``, or the job's current publication.

Modes: ``off``, ``dry_run`` (the default: plan, write the report and the log, delete nothing) and
``delete`` (every real deletion goes to ``cleanup.log`` and ``cleanup_log.jsonl``)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .jobs import ID_RE, read_json

MODES = ("off", "dry_run", "delete")
RUNNING = {"queued", "converting"}
# the only folders of a job folder that may ever be removed
REMOVABLE = {"preview", "preview.tmp", "preview.old", "pagecache", "converter_out", "cache"}
LEFTOVERS = ("preview.tmp", "preview.old")
SMALL = 20 * 1024 * 1024  # top-level job files searched for a name

log = logging.getLogger("book_app.cleanup")


def setup_log(data_path: Path) -> None:
    """One file, ``cleanup.log`` in the data folder (the app's own log shows warnings only)."""
    if any(getattr(h, "_cleanup", False) for h in log.handlers):
        return
    handler = logging.FileHandler(Path(data_path) / "cleanup.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    handler._cleanup = True  # type: ignore[attr-defined]
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


def parse_time(text) -> float | None:
    try:
        return datetime.fromisoformat(str(text)).timestamp()
    except (TypeError, ValueError):
        return None


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def measure(path: Path) -> tuple[int, int, int]:
    """(files, bytes, bytes freed). A file with another hard link (a copied job shares its files)
    gives its bytes back only with its last link. Symbolic links are never followed."""
    files = total = freed = 0
    stack = [Path(path)]
    while stack:
        current = stack.pop()
        try:
            st = current.lstat()
        except OSError:
            continue
        if current.is_symlink() or not current.is_dir():
            files += 1
            total += st.st_size
            if st.st_nlink <= 1:
                freed += st.st_size
            continue
        try:
            with os.scandir(current) as it:
                stack.extend(Path(e.path) for e in it)
        except OSError:
            continue
    return files, total, freed


# ------------------------------------------------------------------ is anything referring to it


def reference_proof(folder: Path, job: dict, child: Path) -> tuple[bool, list[str]]:
    """(referenced, the checks made and what each found) for one child of ``converter_out``."""
    checks: list[str] = []
    referenced = False
    rel = job.get("publication")
    pub = folder / rel if rel else None
    if pub is not None and pub.is_dir() and pub.resolve() == child.resolve():
        return True, [f"is the job's publication ({rel})"]
    checks.append(f"is not the job's publication ({rel})")
    final = None
    manifest = pub / "manifest.json" if pub is not None else None
    if manifest is not None and manifest.is_file():
        try:
            final = json.loads(manifest.read_text("utf-8")).get("final_key")
        except (OSError, ValueError):
            final = None
    if final and final == child.name:
        return True, checks + [
            "is the final_key archive of the publication manifest (Find similar reads it)"
        ]
    checks.append(f"is not the manifest's final_key ({str(final)[:12] if final else 'none'})")
    # files of the publication that are links into this folder
    inodes = set()
    for p in child.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                st = p.lstat()
                inodes.add((st.st_dev, st.st_ino))
        except OSError:
            continue
    linked = 0
    if pub is not None and pub.is_dir():
        for p in pub.rglob("*"):
            try:
                if p.is_symlink():
                    if child.resolve() in Path(os.path.realpath(p)).parents:
                        linked += 1
                elif p.is_file():
                    st = p.lstat()
                    if (st.st_dev, st.st_ino) in inodes:
                        linked += 1
            except OSError:
                continue
    if linked:
        referenced = True
        checks.append(f"{linked} file(s) of the publication link into it")
    else:
        checks.append("no file of the publication links into it")
    needle = child.name.encode()
    mentions = []
    candidates = [p for p in folder.iterdir() if p.is_file()]
    candidates += list((folder / "exports").glob("*/export.json"))
    if manifest is not None and manifest.is_file():
        candidates.append(manifest)
    for p in candidates:
        try:
            if p.stat().st_size <= SMALL and needle in p.read_bytes():
                mentions.append(p.name)
        except OSError:
            continue
    if mentions:
        referenced = True
        checks.append("its name is written in " + ", ".join(sorted(set(mentions))))
    else:
        checks.append(
            f"its name is in none of the {len(candidates)} job and export records checked"
        )
    return referenced, checks


# ------------------------------------------------------------------ the plan


def found_in(proof: list[str]) -> str:
    """The check of a proof that found a reference (the others say it found none)."""
    negative = ("is not ", "no file ", "its name is in none")
    return next((c for c in proof if not c.startswith(negative)), proof[-1])


def _item(
    path: Path,
    folder: Path,
    category: str,
    action: str,
    rule: str,
    reason: str,
    proof: list[str] | None = None,
) -> dict:
    files, total, freed = measure(path)
    return {
        "path": str(path.relative_to(folder)),
        "category": category,
        "action": action,
        "rule": rule,
        "reason": reason,
        "files": files,
        "bytes": total,
        "freed": freed,
        "proof": proof or [],
    }


def settled(job: dict, folder: Path, cfg, now_ts: float, touched: float) -> tuple[bool, str]:
    """Whether preview/ and pagecache/ of the job are due, and why or why not."""
    quiet = now_ts - touched
    if quiet < cfg.open_minutes * 60:
        return False, f"job was open {quiet / 60:.0f} min ago (waits {cfg.open_minutes:g} min)"
    exported = parse_time((job.get("last_export") or {}).get("at"))
    if exported is not None and now_ts - exported >= cfg.after_export_hours * 3600:
        return True, f"last export finished {(now_ts - exported) / 3600:.1f} h ago"
    stamps = [parse_time(job.get("updated_at")), exported]
    for name in ("decisions.json", "details.json"):
        try:
            stamps.append((folder / name).stat().st_mtime)
        except OSError:
            continue
    last = max((s for s in stamps if s), default=None)
    if last is not None and now_ts - last >= cfg.idle_days * 86400:
        return True, f"no activity for {(now_ts - last) / 86400:.1f} days"
    if exported is not None:
        left = cfg.after_export_hours * 3600 - (now_ts - exported)
        return (
            False,
            f"export finished {(now_ts - exported) / 3600:.1f} h ago ({left / 3600:.1f} h left)",
        )
    days = (now_ts - last) / 86400 if last else 0
    return False, f"not exported; last activity {days:.1f} days ago (waits {cfg.idle_days:g} days)"


def plan_job(folder: Path, job: dict, cfg, now_ts: float, touched: float) -> list[dict]:
    items: list[dict] = []
    state = job.get("state")
    if state in RUNNING:
        return [
            {
                "path": ".",
                "category": "job",
                "action": "keep",
                "rule": "job is running",
                "reason": f"state {state}: nothing is touched",
                "files": 0,
                "bytes": 0,
                "freed": 0,
                "proof": [],
            }
        ]
    for name in LEFTOVERS:
        if (folder / name).exists():
            items.append(
                _item(
                    folder / name,
                    folder,
                    "export preview (leftover)",
                    "delete",
                    "always",
                    "leftover of a preview build",
                )
            )
    due, why = settled(job, folder, cfg, now_ts, touched)
    for name, category in (("preview", "export preview"), ("pagecache", "page images")):
        if (folder / name).exists():
            items.append(
                _item(
                    folder / name,
                    folder,
                    category,
                    "delete" if due else "keep",
                    "settled job" if due else "not due",
                    why,
                )
            )
    out = folder / "converter_out"
    if out.is_dir():
        for child in sorted(out.iterdir()):
            if not child.is_dir() or child.is_symlink():
                continue
            if not job.get("publication"):
                items.append(
                    _item(
                        child,
                        folder,
                        "converter output",
                        "keep",
                        "no publication",
                        "the job has no publication, so nothing can be proved",
                    )
                )
                continue
            referenced, proof = reference_proof(folder, job, child)
            if referenced:
                items.append(
                    _item(
                        child,
                        folder,
                        "converter output",
                        "keep",
                        "referenced",
                        found_in(proof),
                        proof,
                    )
                )
            else:
                items.append(
                    _item(
                        child,
                        folder,
                        "converter output",
                        "delete",
                        "unreferenced",
                        "nothing refers to it (see proof)",
                        proof,
                    )
                )
    cache = folder / "cache"
    if cache.exists():
        if cfg.delete_converter_cache and due:
            items.append(
                _item(cache, folder, "converter cache", "delete", "converter cache on", why)
            )
        else:
            items.append(
                _item(
                    cache,
                    folder,
                    "converter cache",
                    "report",
                    "never by default",
                    "regenerable but takes hours to rebuild: reported, not removed",
                )
            )
    return items


def plan(jobs_root: Path, cfg, now_ts: float, touched: dict[str, float], started: float) -> dict:
    jobs = []
    for folder in sorted(Path(jobs_root).iterdir()):
        if not ID_RE.match(folder.name):
            continue
        job = read_json(folder / "job.json")
        if not job:
            continue
        seen = max(touched.get(folder.name, 0.0), started)
        items = plan_job(folder, job, cfg, now_ts, seen)
        jobs.append(
            {
                "id": folder.name,
                "name": job.get("name"),
                "state": job.get("state"),
                "last_export": (job.get("last_export") or {}).get("at"),
                "items": items,
            }
        )
    total = {"delete": [0, 0], "keep": [0, 0], "report": [0, 0]}
    for j in jobs:
        for i in j["items"]:
            total[i["action"]][0] += i["bytes"]
            total[i["action"]][1] += i["freed"]
    return {
        "at": iso(now_ts),
        "settings": {
            "mode": cfg.mode,
            "interval_minutes": cfg.interval_minutes,
            "after_export_hours": cfg.after_export_hours,
            "idle_days": cfg.idle_days,
            "open_minutes": cfg.open_minutes,
            "delete_converter_cache": cfg.delete_converter_cache,
        },
        "jobs": jobs,
        "totals": {k: {"bytes": v[0], "freed": v[1]} for k, v in total.items()},
    }


# ------------------------------------------------------------------ doing it


def guard(folder: Path, rel: str) -> Path:
    """The path to remove, or an error: only a known folder of a job (or a child of its
    converter_out), a real directory, inside the job folder."""
    parts = Path(rel).parts
    if not parts or parts[0] not in REMOVABLE or ".." in parts or len(parts) > 2:
        raise ValueError(f"not a removable path: {rel}")
    if len(parts) == 2 and parts[0] != "converter_out":
        raise ValueError(f"not a removable path: {rel}")
    path = folder / rel
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"not a plain folder: {rel}")
    if folder.resolve() not in path.resolve().parents:
        raise ValueError(f"outside the job folder: {rel}")
    return path


def execute(
    report: dict, jobs_root: Path, cfg, locks_for: Callable[[str], list], data_path: Path
) -> list[dict]:
    """Remove what the plan says, re-checking each item just before. Returns what was removed."""
    removed = []
    for job in report["jobs"]:
        folder = Path(jobs_root) / job["id"]
        for item in job["items"]:
            if item["action"] != "delete":
                continue
            held = []
            try:
                current = read_json(folder / "job.json") or {}
                if current.get("state") in RUNNING:
                    continue
                path = guard(folder, item["path"])
                if item["category"] == "converter output":
                    referenced, _ = reference_proof(folder, current, path)
                    if referenced or not current.get("publication"):
                        log.info(
                            "kept %s/%s: referenced when checked again", job["id"], item["path"]
                        )
                        continue
                for lock in locks_for(job["id"]):
                    if not lock.acquire(blocking=False):
                        raise BlockingIOError("busy")
                    held.append(lock)
                files, total, freed = measure(path)
                shutil.rmtree(path)
                entry = {
                    "at": iso(time.time()),
                    "job": job["id"],
                    "path": item["path"],
                    "category": item["category"],
                    "rule": item["rule"],
                    "files": files,
                    "bytes": total,
                    "freed": freed,
                    "reason": item["reason"],
                }
                removed.append(entry)
                log.info(
                    "DELETED job=%s path=%s files=%d bytes=%d freed=%d rule=%s (%s)",
                    job["id"],
                    item["path"],
                    files,
                    total,
                    freed,
                    item["rule"],
                    item["reason"],
                )
                with open(Path(data_path) / "cleanup_log.jsonl", "a", encoding="utf-8") as out:
                    out.write(json.dumps(entry) + "\n")
            except BlockingIOError:
                log.info(
                    "skipped job=%s path=%s: a build of the job is running", job["id"], item["path"]
                )
            except (ValueError, OSError) as exc:
                log.warning("not removed job=%s path=%s: %s", job["id"], item["path"], exc)
            finally:
                for lock in held:
                    lock.release()
    return removed


def run_once(
    jobs_root: Path,
    data_path: Path,
    cfg,
    touched: dict[str, float],
    started: float,
    locks_for: Callable[[str], list],
) -> dict:
    report = plan(jobs_root, cfg, time.time(), touched, started)
    t = report["totals"]
    verb = {"dry_run": "WOULD delete", "delete": "deleting"}.get(cfg.mode, "plan")
    for job in report["jobs"]:
        for i in job["items"]:
            if i["action"] == "delete":
                log.info(
                    "%s job=%s path=%s files=%d bytes=%d freed=%d rule=%s (%s)",
                    verb,
                    job["id"],
                    i["path"],
                    i["files"],
                    i["bytes"],
                    i["freed"],
                    i["rule"],
                    i["reason"],
                )
    log.info(
        "%s: %.1f MB (%.1f MB freed) in %d place(s); kept %.1f MB; "
        "converter cache reported %.1f MB",
        verb,
        t["delete"]["bytes"] / 1e6,
        t["delete"]["freed"] / 1e6,
        sum(1 for j in report["jobs"] for i in j["items"] if i["action"] == "delete"),
        t["keep"]["bytes"] / 1e6,
        t["report"]["bytes"] / 1e6,
    )
    if cfg.mode == "delete":
        report["removed"] = execute(report, jobs_root, cfg, locks_for, data_path)
    tmp = Path(data_path) / "cleanup_report.json.tmp"
    tmp.write_text(json.dumps(report, indent=1), "utf-8")
    tmp.replace(Path(data_path) / "cleanup_report.json")
    return report


class _NoBuild:
    """Looks like a lock that is taken while the job has work running in the worker pool."""

    def __init__(self, service, job_id: str):
        self.service, self.job_id = service, job_id

    def acquire(self, blocking: bool = True) -> bool:
        return not self.service.builds.busy(self.job_id)

    def release(self) -> None:
        pass


class Cleaner:
    """The background task: every ``interval_minutes`` it plans (and, in delete mode, removes)."""

    def __init__(self, settings, service, store):
        self.cfg = settings.cleanup
        self.data_path = settings.data_path
        self.service = service
        self.store = store
        self.touched: dict[str, float] = {}
        self.started = time.time()  # a restart gives every job the "open" grace period
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.last: dict | None = None

    def touch(self, job_id: str) -> None:
        self.touched[job_id] = time.time()

    def locks_for(self, job_id: str) -> list:
        """What must be free before a job's files are removed: no review or preview build is
        running for it (they work in preview.tmp and effective/), and nobody is swapping."""
        return [self.service.lock(job_id), self.service.swap_lock(job_id), _NoBuild(self.service, job_id)]

    def plan_only(self) -> dict:
        """A fresh plan; nothing is removed (the report endpoint uses it before the first run)."""
        return plan(self.data_path / "jobs", self.cfg, time.time(), self.touched, self.started)

    def run_once(self) -> dict:
        self.last = run_once(
            self.data_path / "jobs",
            self.data_path,
            self.cfg,
            self.touched,
            self.started,
            self.locks_for,
        )
        return self.last

    def loop(self) -> None:
        while not self.stop_event.wait(self.cfg.interval_minutes * 60 if self.last else 60):
            try:
                self.run_once()
            except Exception:  # noqa: BLE001 - a cleanup failure must never stop the app
                log.exception("cleanup run failed")

    def start(self) -> None:
        if self.cfg.mode == "off" or self.thread:
            return
        setup_log(self.data_path)
        log.info("cleanup started: mode=%s every %g min", self.cfg.mode, self.cfg.interval_minutes)
        self.thread = threading.Thread(target=self.loop, daemon=True, name="cleanup")
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()


def main(argv: list[str] | None = None) -> int:
    """``python -m book_app.cleanup [DATA_FOLDER]``: print the plan; deletes nothing."""
    import argparse

    from .config import CleanupSettings

    parser = argparse.ArgumentParser(description="Show what the cleanup would remove (read-only).")
    parser.add_argument("data", nargs="?", default="app_data")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    cfg = CleanupSettings(mode="dry_run")
    report = plan(Path(args.data) / "jobs", cfg, time.time(), {}, 0.0)
    if args.json:
        print(json.dumps(report, indent=1))
        return 0
    print(format_report(report))
    return 0


def format_report(report: dict) -> str:
    def mb(n):
        return f"{n / 1048576:8.1f} MB"

    lines = []
    s = report["settings"]
    lines.append(
        f"Cleanup plan at {report['at']}  (after export {s['after_export_hours']:g} h, idle "
        f"{s['idle_days']:g} days, open window {s['open_minutes']:g} min)"
    )
    for job in report["jobs"]:
        lines.append(f"\njob {job['id']}  {job['state']}  {str(job['name'])[:46]}")
        for i in job["items"]:
            lines.append(
                f"  {i['action'].upper():7} {mb(i['bytes'])}  {i['path']:<58} "
                f"{i['category']}: {i['reason']}"
            )
            for p in i["proof"]:
                lines.append(f"            - {p}")
    t = report["totals"]
    lines.append(
        "\nWould delete : "
        + mb(t["delete"]["bytes"])
        + f"  ({mb(t['delete']['freed']).strip()} actually freed)"
    )
    lines.append("Kept         : " + mb(t["keep"]["bytes"]))
    lines.append("Reported only: " + mb(t["report"]["bytes"]) + "  (converter cache)")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
