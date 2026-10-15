"""Conservative cache inventory and planned removal of explicitly superseded entries."""

import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path

from book_core.cache_store import read_json, write_json

INDEX = ".cache-index.json"
RESERVE_BYTES = 5_000_000_000
LOW_DISK_BYTES = 10_000_000_000
CACHE_STAGES = {
    "native",
    "analysis",
    "paint",
    "characters",
    "figures",
    "equations",
    "layout",
    "reading_order",
    "text",
    "furniture",
    "paragraphs",
    "structure_evidence",
    "structure",
    "lists",
}


def _cache_file(stage, key, name):
    """An index can never turn a source, gold file or arbitrary output into a cache."""
    if stage not in CACHE_STAGES or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise ValueError("Invalid registered cache stage or fingerprint")
    parts = Path(name).parts
    if stage == "structure_evidence":
        valid = parts[-3:] == ("structure", "evidence", f"{key}.json.gz")
    elif stage == "figures":
        # Page records, the book record and the exported images of one figures key.
        page = len(parts) >= 3 and parts[-3:-1] == (stage, key)
        image = len(parts) >= 4 and parts[-4:-2] == (stage, key) and parts[-2] == "images"
        valid = (page and (Path(name).stem.isdecimal() or parts[-1] == "book.json")) or (
            image and name.endswith((".jpg", ".png"))
        )
        if not valid:
            raise ValueError("Registered path is not a stage cache payload")
        return
    elif stage == "equations":
        # Page records and the book record of one equations key.
        valid = (
            len(parts) >= 3
            and parts[-3:-1] == (stage, key)
            and (Path(name).stem.isdecimal() or parts[-1] == "book.json")
        )
    elif stage in {"native", "analysis", "paint", "characters", "layout", "reading_order", "text"}:
        valid = len(parts) >= 3 and parts[-3:-1] == (stage, key) and Path(name).stem.isdecimal()
    else:
        valid = parts[-3:] == (stage, "book", f"{key}.json") or (
            len(parts) >= 4
            and parts[-4] == stage
            and parts[-3] in {"page", "definitions"}
            and parts[-2] == key
            and Path(name).stem.isdecimal()
        )
    if not valid or not name.endswith((".json", ".json.gz")):
        raise ValueError("Registered path is not a stage cache payload")


@contextmanager
def cache_lock(root):
    """OS-released lock, including after interruption; never relies on stale PID files."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".maintenance.lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("Cache is in use by another run or maintenance command") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _inside(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if Path(relative).is_absolute() or root not in path.resolve().parents:
        raise ValueError("Cache entry escapes its registered root")
    for ancestor in (path, *path.parents):
        if ancestor == root:
            break
        if ancestor.is_symlink() or (hasattr(ancestor, "is_junction") and ancestor.is_junction()):
            raise ValueError("Cache maintenance refuses links and junctions")
    return path


def _index(root):
    path = Path(root) / INDEX
    return read_json(path) if path.exists() else {"version": 1, "current": {}, "entries": {}}


def register(root, book, stage, key, paths, *, producer):
    """Register only actual stage cache files, with an explicit current key per owner."""
    root = Path(root).resolve()
    index = _index(root)
    owner = f"{book}/{stage}"
    entry_id = f"{owner}/{key}"
    relative = []
    for path in paths:
        name = Path(path).resolve().relative_to(root).as_posix()
        _cache_file(stage, key, name)
        checked = _inside(root, name)
        if checked.is_file():
            relative.append(name)
    index["entries"][entry_id] = {
        "book": book,
        "stage": stage,
        "key": key,
        "producer": producer,
        "files": sorted(set(relative)),
    }
    index["current"][owner] = entry_id
    write_json(root / INDEX, index)


def report(root):
    root = Path(root).resolve()
    index = _index(root)
    current = set(index["current"].values())
    rows = []
    for entry_id, entry in sorted(index["entries"].items()):
        for name in entry["files"]:
            _cache_file(entry["stage"], entry["key"], name)
        paths = [_inside(root, name) for name in entry["files"]]
        sizes = [p.stat().st_size for p in paths if p.exists()]
        owner = f"{entry['book']}/{entry['stage']}"
        latest = index["entries"][index["current"][owner]]
        superseded = entry_id not in current and entry["producer"] != latest["producer"]
        rows.append(
            {
                **{k: v for k, v in entry.items() if k != "files"},
                "superseded": superseded,
                "current": entry_id in current,
                "bytes": sum(sizes),
                "files": len(sizes),
                "bytes_per_file": sum(sizes) / max(1, len(sizes)),
            }
        )
    return {
        "version": 1,
        "entries": rows,
        "registered_bytes": sum(r["bytes"] for r in rows),
        "superseded_bytes": sum(r["bytes"] for r in rows if r["superseded"]),
        "free_bytes": shutil.disk_usage(root).free,
    }


def prune_plan(root, budget_bytes=None):
    root = Path(root).resolve()
    index = _index(root)
    current = set(index["current"].values())
    protected = {name for key in current for name in index["entries"][key]["files"]}
    files = {}
    for key, entry in index["entries"].items():
        for name in entry["files"]:
            _cache_file(entry["stage"], entry["key"], name)
        if key in current:
            continue
        owner = f"{entry['book']}/{entry['stage']}"
        latest = index["entries"][index["current"][owner]]
        if entry["producer"] == latest["producer"]:
            continue
        for name in entry["files"]:
            if name in protected:
                continue
            path = _inside(root, name)
            if path.exists():
                stat = path.stat()
                files[name] = [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
    info = report(root)
    reclaim = sum(stat[0] for stat in files.values())
    return {
        "version": 1,
        "index_sha256": hashlib.sha256((root / INDEX).read_bytes()).hexdigest()
        if (root / INDEX).exists()
        else None,
        "files": files,
        "reclaim_bytes": reclaim,
        "budget_bytes": budget_bytes,
        "budget_satisfied": budget_bytes is None
        or info["registered_bytes"] - reclaim <= budget_bytes,
    }


def apply_plan(root, plan):
    """Caller holds cache_lock; validate the complete dry run before deleting any file."""
    fresh = prune_plan(root, plan.get("budget_bytes"))
    if fresh != plan:
        raise ValueError("Cache changed since dry-run; create a new prune plan")
    for name in plan["files"]:
        _inside(root, name).unlink()
    return {
        "deleted_files": len(plan["files"]),
        "reclaimed_bytes": plan["reclaim_bytes"],
        "budget_satisfied": plan["budget_satisfied"],
    }


def disk_check(root, estimated_bytes, *, maintenance_root=None):
    """Conservative requirement for intermediate + final data, with a 5 GB reserve."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    maintenance_root = Path(maintenance_root or root)
    free = shutil.disk_usage(root).free
    cleanup = None
    if free < LOW_DISK_BYTES:
        plan = prune_plan(maintenance_root)
        # Persist the inspectable dry run before applying the authorized housekeeping rule.
        (maintenance_root / "disk_cleanup_dry_run.json").write_text(
            json.dumps(plan, indent=2) + "\n", "utf8"
        )
        cleanup = apply_plan(maintenance_root, plan)
        free = shutil.disk_usage(root).free
    if estimated_bytes > free - RESERVE_BYTES:
        raise OSError(
            f"Insufficient disk space: estimated {estimated_bytes:,} bytes, "
            f"free {free:,}; keep {RESERVE_BYTES:,} bytes in reserve. "
            "Prune superseded caches or choose another cache/output drive."
        )
    return {
        "estimated_bytes": estimated_bytes,
        "free_bytes": free,
        "reserve_bytes": RESERVE_BYTES,
        "cleanup": cleanup,
    }
