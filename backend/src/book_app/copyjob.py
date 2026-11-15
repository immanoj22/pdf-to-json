"""Copy a book: a new job from an existing one, for training or testing.

A converted book is copied *ready at once*: its converter cache, publication and page pictures are
shared with the original by hard links (no bytes are copied, so a 100 MB book costs nothing),
and the copy starts in the "converted" state. The copy never starts a conversion by itself; a
book that was not converted yet is copied as an upload and waits for the manual Start.

Hard links are safe here because the files are only read after the conversion: a conversion of
the copy first removes its own ``converter_out`` (only its links go) and writes new files; cache
stages are written whole, never edited in place (checked against the original's file hashes in
the Copy test). Review decisions are copied, never linked (each book keeps its own).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .jobs import JobError, JobStore, read_json

SHARED = ("cache", "converter_out", "pagecache")  # folders shared by hard links
COPIED = ("details.json", "parts.json", "parts_confirmed.json", "converter.log")
DECISIONS = {"with", "clean"}
MARK = "COPY - "


def link_tree(src: Path, dst: Path) -> int:
    """Mirror ``src`` under ``dst``: folders are made, symbolic links kept as links, files hard
    linked (a copy where linking is not possible). Returns the number of files."""
    n = 0
    dst.mkdir(parents=True, exist_ok=True)
    for entry in sorted(src.iterdir()):
        target = dst / entry.name
        if entry.is_symlink():
            os.symlink(os.readlink(entry), target)
        elif entry.is_dir():
            n += link_tree(entry, target)
        else:
            try:
                os.link(entry, target)
            except OSError:
                shutil.copy2(entry, target)
            n += 1
    return n


def ready_to_share(job: dict, folder: Path) -> bool:
    rel = job.get("publication")
    return bool(job.get("state") == "converted" and rel and (folder / rel / "book.json").is_file()
                and (folder / "cache").is_dir())  # fmt: skip


def make_copy(store: JobStore, job_id: str, who: str, decisions: str) -> dict:
    if decisions not in DECISIONS:
        raise JobError(422, "Choose: with the review decisions, or clean.", "bad_copy_mode")
    src = store.get(job_id)
    src_dir = store.folder(job_id)
    if not (src_dir / "input.pdf").is_file():
        raise JobError(409, "The PDF of this book is missing.", "no_pdf")
    share = ready_to_share(src, src_dir)
    job, target = store.create(f"{MARK}{src['name']}", src["size"], src["pages"])
    folder = store.folder(job["id"])
    try:
        try:
            os.link(src_dir / "input.pdf", target)
        except OSError:
            shutil.copyfile(src_dir / "input.pdf", target)
        for name in COPIED:
            if (src_dir / name).is_file():
                shutil.copyfile(src_dir / name, folder / name)
        if decisions == "with" and (src_dir / "decisions.json").is_file():
            shutil.copyfile(src_dir / "decisions.json", folder / "decisions.json")
        changes = {"profile": src.get("profile"), "uploaded_by": who or None, "copy_of": job_id,
                   "is_copy": True, "copy_decisions": decisions}  # fmt: skip
        if share:
            for name in SHARED:
                if (src_dir / name).is_dir():
                    link_tree(src_dir / name, folder / name)
            changes.update({k: src.get(k) for k in ("state", "progress", "publication", "started_at",
                                                    "finished_at")})  # fmt: skip
            changes["shared_cache"] = True
        return store.update(job["id"], **changes)
    except Exception:
        store.delete(job["id"])
        raise
