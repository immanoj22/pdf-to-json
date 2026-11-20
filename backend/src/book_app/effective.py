"""The edited book on disk, and the work that builds it (run in a worker process).

A book is the converter's ``book.json`` plus the reviewer's edits. Building it means replaying
every edit, which takes minutes for a big book, so the result is saved under
``<job>/effective/<key>.json.gz`` and loaded from there:

    key = hash(format, code version of the edit code, the publication, every edit, the list marks,
               whether the result was checked against the schema)

A saved state also records its list of edit keys (``<key>.meta.json``). A new edit, an undo or a
restart finds the saved state whose edits are the longest prefix of the current list and replays
only the rest. A change of the edit code (overlay.py, edit_ops.py) changes the key, so a saved
book is never used for edits that would now give another result.

The functions here take and return plain data (paths, dicts), so a worker process can run them."""

from __future__ import annotations

import functools
import gzip
import hashlib
import json
import os
import time
from pathlib import Path

from . import overlay
from .decisions import Decisions

FORMAT = 1
KEEP = 3  # saved states kept per job


@functools.cache
def code_version() -> str:
    """Fingerprint of the code that turns edits into a book."""
    here = Path(__file__).parent
    digest = hashlib.sha256()
    for name in ("overlay.py", "edit_ops.py"):
        digest.update((here / name).read_bytes())
    return digest.hexdigest()[:16]


def edit_keys(edits: list[dict]) -> list[str]:
    return [overlay.edits_key([e]) for e in edits]


def state_key(publication: str, keys: list[str], marks: dict, validate: bool) -> str:
    raw = json.dumps([FORMAT, code_version(), publication, keys, marks, validate], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def folder(job_folder: Path) -> Path:
    return Path(job_folder) / "effective"


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def save(job_folder: Path, key: str, meta: dict, payload: dict) -> None:
    """Write one saved state (the book first, then its meta file: a state without its meta file
    is never found), then drop the oldest ones."""
    root = folder(job_folder)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    _write_atomic(root / f"{key}.json.gz", gzip.compress(raw, compresslevel=1))
    _write_atomic(root / f"{key}.meta.json", json.dumps({**meta, "key": key}).encode())
    metas = sorted(root.glob("*.meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in metas[KEEP:]:
        stem = old.name[: -len(".meta.json")]
        for name in (f"{stem}.json.gz", old.name):
            try:
                (root / name).unlink()
            except OSError:
                pass


def load(job_folder: Path, key: str) -> dict | None:
    path = folder(job_folder) / f"{key}.json.gz"
    meta = folder(job_folder) / f"{key}.meta.json"
    if not (path.is_file() and meta.is_file()):
        return None
    try:
        return json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, ValueError, EOFError):
        return None


def find_resume(job_folder: Path, publication: str, marks: dict, keys: list[str]) -> dict | None:
    """The saved (unchecked) state whose edits are the longest prefix of ``keys``; its payload
    plus ``keys``, or None."""
    best = None
    for meta_path in folder(job_folder).glob("*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        saved = meta.get("keys") or []
        if (
            meta.get("format") == FORMAT
            and meta.get("code") == code_version()
            and meta.get("publication") == publication
            and meta.get("marks") == marks
            and not meta.get("validate")
            and saved == keys[: len(saved)]
            and (best is None or len(saved) > len(best["keys"]))
        ):
            best = meta
    if best is None:
        return None
    payload = load(job_folder, best["key"])
    return {**payload, "keys": best["keys"]} if payload else None


def meta_of(publication: str, keys: list[str], marks: dict, validate: bool) -> dict:
    return {
        "format": FORMAT, "code": code_version(), "publication": publication, "keys": keys,
        "marks": marks, "validate": validate, "at": time.time(),
    }  # fmt: skip


# ------------------------------------------------------------------ the work of a worker process


def build_task(job_folder: str, publication_rel: str, marks: dict, validate: bool) -> dict:
    """Replay the job's edits and save the result. Returns the key and a few counts. The edits
    are read here from the job's decision log, so what is built is what is on disk now."""
    job_folder = Path(job_folder)
    started = time.time()
    publication = job_folder / publication_rel
    edits = Decisions(job_folder).edits()
    keys = edit_keys(edits)
    name = publication.name
    key = state_key(name, keys, marks, validate)
    if load(job_folder, key) is not None:
        return {"key": key, "edits": len(edits), "seconds": 0.0, "reused": True}
    resume = None if validate else find_resume(job_folder, name, marks, keys)
    if resume is not None:
        skip = len(resume["keys"])
        stage = (resume["pre"], resume["applied"], resume["failed"])
    else:
        skip, stage = 0, None
    base = stage[0] if stage else json.loads((publication / "book.json").read_text("utf-8"))
    if validate:
        book, applied, failed = overlay.apply_checked(base, edits, marks)
        payload = {"book": book, "applied": applied, "failed": failed}
    else:
        pre, applied, failed, _ = overlay.apply_stage(base, edits[skip:], marks, stage)
        payload = {"pre": pre, "applied": applied, "failed": failed}
    save(job_folder, key, meta_of(name, keys, marks, validate), payload)
    return {
        "key": key, "edits": len(edits), "replayed": len(edits) - skip, "reused": False,
        "seconds": round(time.time() - started, 2), "failed": len(failed),
    }  # fmt: skip


def preview_task(
    job_folder: str,
    publication_rel: str,
    marks: dict,
    profile_ref: str,
    store_path: str,
    settings_text: str,
    fmt: str = "docbook",
) -> dict:
    """The adapter's draft run of the edited book into ``<job>/preview.tmp`` (the caller swaps it
    in). Returns the pieces of the run's report the app keeps. ``fmt`` is the output the book is
    made for: ``docbook`` (the draft of a book) or ``tail`` (a references-only document, whose
    review list is the references a person must look at)."""
    import shutil

    from book_adapters.engine.profile_store import ProfileStore
    from book_adapters.engine.run import run_book

    job_folder = Path(job_folder)
    started = time.time()
    build = job_folder / "preview.tmp"
    for leftover in (build, job_folder / "preview.old"):
        if leftover.exists():
            shutil.rmtree(leftover)
    build.mkdir(parents=True)
    built = build_task(str(job_folder), publication_rel, marks, True)
    payload = load(job_folder, built["key"])
    if payload is None:
        raise RuntimeError("the checked book was not saved")
    publication = job_folder / publication_rel
    book_dir = overlay.write_overlay(publication, payload["book"], build / "book", check=False)
    settings_path = build / "settings.yaml"
    settings_path.write_text(settings_text, "utf-8")
    if fmt == "docbook":
        report = run_book(
            book_dir,
            build / "out",
            settings_path,
            profile_ref,
            ProfileStore(store=Path(store_path)),
            validate=False,
            allow_alt_text_placeholders=True,
        )
    else:
        from book_adapters.engine.formats_run import run_format

        report = run_format(
            fmt, book_dir, build / "out", settings_path, profile_ref,
            ProfileStore(store=Path(store_path)), validate=False, allow_alt_text_placeholders=True,
        )  # fmt: skip
    return {
        "report": {
            "root": report.get("root"),
            "delivery": report.get("delivery"),
            "alt_text": report.get("alt_text"),
            "authors": report.get("authors"),
        },
        "failed": payload["failed"],
        "seconds": round(time.time() - started, 2),
    }


def export_task(
    kind: str, book_dir: str, out: str, settings_path: str, profile_ref: str, store_path: str,
    allow_placeholders: bool, extra: dict,
) -> dict:
    """One format of an export (``docbook``, ``epub`` or another format name), run in a worker
    process. Returns ``{"report": ...}``, or ``{"blocked": report}`` when alt-text placeholders
    stop the export (the app turns that into its plain message)."""
    from book_adapters.engine.epub_run import run_epub
    from book_adapters.engine.formats_run import run_format
    from book_adapters.engine.profile_store import ProfileStore
    from book_adapters.engine.run import ExportBlocked, run_book

    store = ProfileStore(store=Path(store_path))
    book_dir, out, settings_path = Path(book_dir), Path(out), Path(settings_path)
    try:
        if kind == "docbook":
            report = run_book(
                book_dir, out, settings_path, profile_ref, store,
                allow_alt_text_placeholders=allow_placeholders,
            )  # fmt: skip
        elif kind == "epub":
            report = run_epub(
                book_dir, out, settings_path, profile_ref, store,
                allow_alt_text_placeholders=allow_placeholders,
                modified=extra.get("modified"), epubcheck_jar=extra.get("epubcheck_jar"),
            )  # fmt: skip
        else:
            source = extra.get("source_pdf")
            report = run_format(
                kind, book_dir, out, settings_path, profile_ref, store,
                allow_alt_text_placeholders=allow_placeholders,
                source_pdf=Path(source) if source else None,
                options={k: extra[k] for k in ("job_id", "training_dir") if extra.get(k)},
            )  # fmt: skip
    except ExportBlocked as blocked:
        return {"blocked": blocked.report}
    return {"report": report}
