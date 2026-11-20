"""The web API (FastAPI) and the single-page app. Local by default; nothing is fetched from
outside; every id is a hex string checked before it touches a path."""

from __future__ import annotations

import json
import re
import secrets
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from book_adapters.engine.formats_run import SPECS as FORMAT_SPECS

from . import __version__, overlay, pdfpages
from .cleanup import Cleaner
from .config import LOOPBACK, AppSettings
from .decisions import EDIT_OPS
from .jobs import (
    ID_RE,
    Converter,
    JobError,
    JobStore,
    disk_requirement,
    now,
    read_json,
    safe_name,
    write_json,
)
from .profiles import Profiles
from .queue import ROLES, Audit, assignments, clean_assignments, save_assignments
from .service import Service

STATIC = Path(__file__).parent / "static"
JOB_PATH = re.compile(r"^/api/jobs/([0-9a-f]{16})(?:/|$)")
CHUNK = 1024 * 1024


def limit_gb(settings: AppSettings) -> str:
    return f"{settings.max_upload_bytes / 1e9:g}"


def _html_file(path: Path, name: str, download: bool) -> FileResponse:
    if download:
        return FileResponse(
            path, media_type="text/html", filename=name, content_disposition_type="attachment"
        )
    return FileResponse(path, media_type="text/html")


def create_app(settings: AppSettings) -> FastAPI:
    data = settings.data_path
    data.mkdir(parents=True, exist_ok=True)
    (data / "tmp").mkdir(exist_ok=True)
    store = JobStore(settings)
    profiles = Profiles(data, settings.max_profile_bytes)
    service = Service(settings, store, profiles)
    converter = Converter(store)
    cleaner = Cleaner(settings, service, store)
    audit = Audit(data)
    converter.resume_queued(store.recover())

    def warm_review() -> None:
        """Prepare the edited book and review list of the two books worked on last, so the first
        review screen after a restart opens at once (was ~30 s). Changes nothing on disk that
        the reviewer sees; failures are ignored."""
        try:
            jobs = [j for j in store.list() if j.get("state") == "converted" and j.get("profile")]
            for job in sorted(jobs, key=lambda j: j.get("updated_at", ""), reverse=True)[:2]:
                try:
                    service.review(job["id"])
                except JobError:  # "preparing": the work is started, that is all a warm-up needs
                    pass
        except Exception:  # noqa: BLE001 - a warm-up must never stop the app
            pass

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        threading.Thread(target=warm_review, daemon=True, name="warm-review").start()
        threading.Thread(target=service.builds.warm, daemon=True, name="warm-pool").start()
        cleaner.start()
        yield
        cleaner.stop()
        service.builds.stop()
        converter.stop()  # a stopped app leaves running conversions recoverable

    app = FastAPI(
        title="Book Converter", version=__version__, docs_url=None, redoc_url=None,
        openapi_url=None, lifespan=lifespan,
    )  # fmt: skip
    app.state.settings, app.state.store, app.state.service = settings, store, service
    app.state.converter, app.state.profiles, app.state.audit = converter, profiles, audit
    app.state.cleaner = cleaner

    def person(request: Request) -> tuple[str, str]:
        """The name and role picked at login (headers X-User, X-Role; no passwords: the app is
        for the office network). A request without a role acts as a manager (API scripts)."""
        from urllib.parse import unquote

        who = unquote(request.headers.get("x-user") or "").strip()
        role = (request.headers.get("x-role") or "manager").strip().lower()
        return who, role if role in ROLES else "reviewer"

    def manager(request: Request) -> str:
        who, role = person(request)
        if role != "manager":
            raise JobError(403, "Only a manager can do this (upload, queue, assign, export, delete).",
                           "manager_only")  # fmt: skip
        return who

    # ------------------------------------------------------------------ guards

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if not settings.allow_lan and host not in LOOPBACK:
            return JSONResponse(
                {"detail": "This app only answers on this computer.", "code": "host"}, 403
            )
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
                return JSONResponse(
                    {"detail": "Request from another site refused.", "code": "origin"}, 403
                )
        match = JOB_PATH.match(request.url.path)
        if match:
            cleaner.touch(match.group(1))  # a job someone is using is open: not cleaned
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(JobError)
    async def job_error(_: Request, exc: JobError):
        body = {"detail": exc.message, "code": exc.code, **exc.extra}
        return JSONResponse(body, status_code=exc.status)

    def json_body(raw: dict | None) -> dict:
        if not isinstance(raw, dict):
            raise JobError(400, "The request was not understood.", "bad_request")
        return raw

    # ------------------------------------------------------------------ health

    @app.get("/api/health")
    def health():
        models = settings.models_path
        free = shutil.disk_usage(data).free
        return {
            "version": __version__,
            "free_bytes": free,
            "max_upload_bytes": settings.max_upload_bytes,
            "max_parallel_jobs": settings.max_parallel_jobs,
            "lan": settings.allow_lan,
            "add_text_by": settings.add_text_by,
            "models_ready": bool(models and models.is_dir() and any(models.glob("models--*"))),
            "data_folder": str(data),
        }

    # ------------------------------------------------------------------ profiles

    @app.get("/api/profiles")
    def list_profiles():
        return {"profiles": profiles.list()}

    @app.get("/api/cleanup")
    def cleanup_report(request: Request):
        """The last cleanup plan (what it would remove or removed, with the proof for each
        converter-output folder). Managers only."""
        manager(request)
        return cleaner.last or cleaner.plan_only()

    @app.post("/api/profiles/validate")
    async def validate_profile(request: Request, filename: str = "profile.yaml"):
        return profiles.validate(await request.body(), filename)

    @app.post("/api/profiles")
    async def upload_profile(request: Request, filename: str = "profile.yaml"):
        result = profiles.add(await request.body(), filename)
        return JSONResponse(result, 200 if result["ok"] else 422)

    @app.get("/api/profile-options")
    def profile_options(ref: str):
        profiles.resolve(ref)
        return {"options": profiles.book_options(ref)}

    @app.get("/api/profile-maker/prompt")
    def maker_prompt():
        return {"prompt": profiles.maker_prompt()}

    @app.get("/api/profile-maker/schema")
    def maker_schema():
        return FileResponse(
            profiles.schema_path(), filename="profile.schema.json", media_type="application/json"
        )

    @app.get("/api/profile-maker/base")
    def maker_base(name: str = "docbook_base"):
        path = profiles.base_path(name)
        return FileResponse(path, filename=path.name, media_type="text/yaml")

    # ------------------------------------------------------------------ jobs

    @app.get("/api/jobs")
    def list_jobs():
        """Every book, with its reviewers and review progress (items decided / total)."""
        jobs = store.list()
        for job in jobs:
            job["assigned_to"] = assignments(store.folder(job["id"]))
            job["review_progress"] = (service.review_progress(job["id"])
                                      if job["state"] == "converted" else None)  # fmt: skip
            saved = read_json(store.folder(job["id"]) / "details.json", {}) or {}
            job["isbn"] = re.sub(r"[\s\-]", "", str(saved.get("isbn") or "")) or None
        return {"jobs": jobs}

    @app.post("/api/jobs/{job_id}/copy")
    def copy_job(request: Request, job_id: str, body: dict | None = None):
        """A new book from an existing one, marked COPY. A converted book is copied ready at
        once (cache shared by hard links); the copy is never queued by itself: Start is manual.
        ``decisions``: "with" copies the review decisions and edits, "clean" starts without."""
        from .copyjob import make_copy

        who = manager(request)
        mode = json_body(body or {}).get("decisions") or "clean"
        job = make_copy(store, job_id, who, mode)
        audit.log(who, "copy", job["id"], name=job["name"], source=job_id, decisions=mode,
                  shared=bool(job.get("shared_cache")))  # fmt: skip
        return job

    @app.put("/api/jobs")
    async def upload_pdf(request: Request, filename: str = Query(..., max_length=400)):
        manager(request)
        declared = request.headers.get("content-length")
        if declared and int(declared) > settings.max_upload_bytes:
            raise JobError(
                413,
                f"The file is too large: the limit is {limit_gb(settings)} GB.",
                "too_large",
            )
        if declared and int(declared) == 0:
            raise JobError(400, "The file is empty.", "empty")
        free = shutil.disk_usage(data).free
        if declared and int(declared) > free:
            raise JobError(507, "Not enough free disk space for this file.", "disk_space")
        tmp = data / "tmp" / f"upload-{secrets.token_hex(8)}.part"
        size = 0
        try:
            with open(tmp, "wb") as out:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise JobError(
                            413,
                            f"The file is too large: the limit is {limit_gb(settings)} GB.",
                            "too_large",
                        )
                    out.write(chunk)
            if size == 0:
                raise JobError(400, "The file is empty.", "empty")
            pages, problem = pdfpages.check_pdf(tmp)
            if problem:
                raise JobError(415, problem, "not_pdf")
            job, target = store.create(filename, size, pages)
            shutil.move(tmp, target)
            who = manager(request) or (request.query_params.get("who") or "").strip()
            job = store.update(job["id"], uploaded_by=who or None)
            ref = request.query_params.get("profile")
            if ref:
                stored = profiles.resolve(ref)
                job = store.update(job["id"], profile=stored.ref if stored.origin == "uploaded"
                                   else f"{stored.profile}@{stored.version}")  # fmt: skip
            audit.log(who, "upload", job["id"], name=job["name"], pages=pages, profile=job["profile"])
            return job
        finally:
            tmp.unlink(missing_ok=True)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = store.get(job_id)
        job["disk"] = None
        return job

    @app.delete("/api/jobs/{job_id}")
    def delete_job(request: Request, job_id: str, confirm: str = ""):
        who = manager(request)
        if confirm != "yes":
            raise JobError(400, "Deleting needs confirmation.", "confirm")
        name = store.get(job_id)["name"]
        if service.builds.busy(job_id) or export_runs.get(job_id, {}).get("state") == "running":
            raise JobError(409, "A review list or an export of this book is still being made. "
                                "Try again in a minute.", "busy")  # fmt: skip
        gone = store.delete(job_id)
        audit.log(who, "delete", job_id, name=name, freed_bytes=gone["freed_bytes"])
        service.forget(job_id, base=True)
        export_runs.pop(job_id, None)
        return {"deleted": job_id, **gone}

    @app.put("/api/jobs/{job_id}/profile")
    def set_profile(job_id: str, body: dict):
        ref = json_body(body).get("ref")
        stored = profiles.resolve(ref or "")
        job = store.get(job_id)
        if job["state"] in ("queued", "converting"):
            raise JobError(409, "Wait for the conversion to finish first.", "busy")
        return store.update(
            job_id,
            profile=stored.ref
            if stored.origin == "uploaded"
            else f"{stored.profile}@{stored.version}",
        )

    @app.post("/api/jobs/{job_id}/convert")
    def convert(request: Request, job_id: str):
        who = manager(request)
        job = converter.submit(job_id)
        audit.log(who, "queue", job_id, name=job["name"])
        return job

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(request: Request, job_id: str):
        who = manager(request)
        job = converter.cancel(job_id)
        audit.log(who, "cancel", job_id, name=job["name"])
        return job

    # ------------------------------------------------------------------ queue

    def _eta(jobs: list[dict]) -> dict[str, dict]:
        """Seconds to finish each queued or converting book: the measured seconds per page
        of this app's finished conversions (median), else 8 s a page."""
        import statistics
        from datetime import datetime

        def seconds(a, b):
            return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()

        rates = [seconds(j["started_at"], j["finished_at"]) / max(1, j["pages"]) for j in jobs
                 if j["state"] == "converted" and j.get("started_at") and j.get("finished_at")
                 and not j.get("resumed_at")]  # fmt: skip
        rate = statistics.median(rates) if rates else 8.0
        out, ahead = {}, [0.0] * settings.max_parallel_jobs
        order = converter.queue.load()["order"]
        by_id = {j["id"]: j for j in jobs}
        for job_id in order:
            job = by_id.get(job_id)
            if not job or job["state"] not in ("queued", "converting"):
                continue
            total = rate * job["pages"]
            if job["state"] == "converting" and job.get("started_at"):
                left = max(60.0, total - seconds(job["started_at"], now()))
            else:
                left = total
            slot = ahead.index(min(ahead))
            start = ahead[slot] if job["state"] == "queued" else 0.0
            ahead[slot] = start + left
            out[job_id] = {"starts_in": round(start), "finishes_in": round(start + left)}
        return out

    @app.get("/api/queue")
    def queue_list():
        """The queue in order (then the other books, newest first) with their state and the
        estimated time; and the books' reviewers and review progress."""
        jobs = store.list()
        state = converter.queue.load()
        order = state["order"]
        eta = _eta(jobs)
        rank = {j: i for i, j in enumerate(order)}
        rows = sorted(jobs, key=lambda j: (j["id"] not in rank, rank.get(j["id"], 0)))
        out = []
        for job in rows:
            out.append({
                "id": job["id"], "name": job["name"], "pages": job["pages"],
                "profile": job.get("profile"), "uploaded_by": job.get("uploaded_by"),
                "state": job["state"], "progress": job.get("progress"),
                "failure": job.get("failure"), "position": rank[job["id"]] + 1 if job["id"] in rank else None,
                "paused": job["id"] in state["paused"], "eta": eta.get(job["id"]),
                "created_at": job.get("created_at"),
            })  # fmt: skip
        return {"queue": out, "max_parallel_jobs": settings.max_parallel_jobs}

    @app.get("/api/converting")
    def converting():
        """The conversions running now, for the banner on every page: name, step, percent and
        the estimated minutes left."""
        jobs = store.list()
        running = [j for j in jobs if j["state"] == "converting"]
        eta = _eta(jobs) if running else {}
        rows = []
        for job in running:
            progress = job.get("progress") or {}
            total = progress.get("total") or 18
            step = progress.get("index") or 0
            left = (eta.get(job["id"]) or {}).get("finishes_in")
            rows.append({
                "id": job["id"], "name": job["name"], "step": step, "steps": total,
                "label": progress.get("label"), "percent": min(99, round(100 * step / total)),
                "minutes_left": None if left is None else max(1, round(left / 60)),
            })  # fmt: skip
        return {"converting": rows, "night": converter.in_night()}

    @app.post("/api/queue/{job_id}/move")
    def queue_move(request: Request, job_id: str, body: dict):
        who = manager(request)
        direction = json_body(body).get("direction")
        converter.queue.move(store.get(job_id)["id"], direction)
        audit.log(who, "move", job_id, direction=direction)
        return queue_list()

    @app.post("/api/queue/{job_id}/pause")
    def queue_pause(request: Request, job_id: str, body: dict):
        who = manager(request)
        paused = bool(json_body(body).get("paused", True))
        job = store.get(job_id)
        if job["state"] == "converting":  # a running conversion: stopped, kept in its cache
            if not paused:
                raise JobError(409, "This book is already converting.", "running")
            converter.pause(job_id)
            audit.log(who, "pause", job_id)
            return queue_list()
        if job["state"] != "queued":
            raise JobError(409, "Only a book waiting in the queue can be paused.", "not_queued")
        converter.queue.pause(job_id, paused)
        audit.log(who, "pause" if paused else "resume", job_id)
        return queue_list()

    # ------------------------------------------------------------------ reviewers

    @app.get("/api/jobs/{job_id}/assignments")
    def get_assignments(job_id: str):
        folder = store.folder(job_id)
        return {"reviewers": assignments(folder), "progress": service.review_progress(job_id)
                if store.get(job_id)["state"] == "converted" else None}  # fmt: skip

    @app.put("/api/jobs/{job_id}/assignments")
    def put_assignments(request: Request, job_id: str, body: dict):
        who = manager(request)
        job = store.get(job_id)
        if job["state"] != "converted":
            raise JobError(409, "Assign reviewers once the book is converted.", "not_converted")
        rows = clean_assignments(json_body(body).get("reviewers"), job["pages"])
        save_assignments(store.folder(job_id), rows, who)
        audit.log(who, "assign", job_id, reviewers=rows)
        return get_assignments(job_id)

    @app.get("/api/audit")
    def audit_log(job: str | None = None):
        return {"entries": audit.entries(job)}

    @app.get("/api/jobs/{job_id}/log")
    def converter_log(job_id: str):
        folder = store.folder(job_id)
        path = folder / "converter.log"
        text = path.read_text("utf-8", "replace")[-20000:] if path.is_file() else ""
        return PlainTextResponse(text)

    # ------------------------------------------------------------------ details

    @app.get("/api/jobs/{job_id}/details")
    def get_details(job_id: str):
        store.publication(job_id)
        return service.get_details(job_id)

    @app.put("/api/jobs/{job_id}/details")
    def put_details(job_id: str, body: dict):
        store.publication(job_id)
        return {"details": service.save_details(job_id, json_body(body))}

    # ------------------------------------------------------------------ book parts

    @app.get("/api/jobs/{job_id}/parts")
    def get_parts(job_id: str):
        store.publication(job_id)
        return service.get_parts(job_id)

    @app.get("/api/jobs/{job_id}/parts/plan")
    def get_planned_parts(job_id: str):
        return service.planned_parts(job_id)

    @app.put("/api/jobs/{job_id}/parts/plan")
    def put_planned_parts(job_id: str, body: dict):
        """Book parts given at upload, before Convert (optional): the conversion follows them.
        They are confirmed after the conversion like any parts; there is no export before."""
        body = json_body(body)
        return service.plan_parts(job_id, body.get("parts"), body.get("who") or "")

    @app.put("/api/jobs/{job_id}/parts")
    def put_parts(job_id: str, body: dict):
        """Confirm the book parts. When they differ from what the converted book was built
        with, the converter runs again (cached stages are reused; structure onwards re-run)."""
        store.publication(job_id)
        body = json_body(body)
        result = service.save_parts(job_id, body.get("parts") or {}, body.get("who") or "")
        if result["rerun"]:
            converter.submit(job_id)
        else:
            service.parts_built(job_id)
        return result

    # ------------------------------------------------------------------ review

    @app.get("/api/jobs/{job_id}/review")
    def get_review(job_id: str, offset: int = Query(0, ge=0), limit: int | None = Query(None, ge=1)):
        """The review list; with ``limit`` one page of it (and the totals of the whole list)."""
        store.publication(job_id)
        return service.review(job_id, offset, limit)

    @app.post("/api/jobs/{job_id}/review/refresh")
    def refresh_review(job_id: str):
        store.publication(job_id)
        # Rebuilt only when the edits, details or profile changed since the last build: a
        # second reviewer pressing Refresh right after the first gets the same list at once.
        service.ensure_preview(job_id)
        return service.review(job_id)

    @app.get("/api/jobs/{job_id}/crops/{name}")
    def crop(job_id: str, name: str):
        report = store.folder(job_id) / "preview" / "out" / "report" / "review_crops"
        if not re.fullmatch(r"[0-9A-Za-z_\-.]+\.(png|jpg)", name):
            raise JobError(404, "No such picture.", "not_found")
        path = report / name
        if not path.is_file():
            raise JobError(404, "No such picture.", "not_found")
        return FileResponse(path, headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/jobs/{job_id}/pages")
    def pages(job_id: str):
        store.folder(job_id)
        info = pdfpages.page_info(store.folder(job_id) / "input.pdf")
        book = None
        if store.get(job_id)["state"] == "converted":
            labels = [p.get("label") for p in service.base_book(job_id)["pages"]]
            book = labels
        for p in info:
            p["label"] = book[p["index"] - 1] if book and p["index"] <= len(book) else None
        return {"pages": info}

    @app.get("/api/jobs/{job_id}/pages/{number}/image")
    def page_image(job_id: str, number: int, scale: float = 1.5):
        folder = store.folder(job_id)
        job = store.get(job_id)
        if not 1 <= number <= job["pages"]:
            raise JobError(404, "No such page.", "no_page")
        path = pdfpages.page_png(folder / "input.pdf", number, scale, folder / "pagecache")
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "max-age=600"})

    @app.get("/api/jobs/{job_id}/pages/{number}/units")
    def page_units(job_id: str, number: int):
        store.publication(job_id)
        return service.page_units(job_id, number)

    @app.get("/api/jobs/{job_id}/pages/{number}/restorable")
    def page_restorable(job_id: str, number: int):
        store.publication(job_id)
        return service.restorable_lines(job_id, number)

    @app.get("/api/jobs/{job_id}/search")
    def search_book(job_id: str, q: str = ""):
        store.publication(job_id)
        return service.search(job_id, q)

    @app.get("/api/jobs/{job_id}/decisions")
    def get_decisions(job_id: str):
        store.folder(job_id)
        d = service.decisions(job_id)
        data = d.load()
        return {
            "events": data["events"],
            "decisions": d.current(),
            "edits": d.edits(),
        }

    @app.post("/api/jobs/{job_id}/decisions")
    def post_decision(job_id: str, body: dict):
        body = json_body(body)
        store.publication(job_id)
        fix = body.get("fix")
        if fix and fix.get("author") is not None:
            _apply_author_fix(job_id, fix)
        event = service.decisions(job_id).decide(
            body.get("who") or "", body.get("key") or "", body.get("item_kind") or "",
            body.get("action") or "", fix, body.get("note") or "", body.get("item"),
        )  # fmt: skip
        audit.log(event["who"], "review", job_id, decision=event.get("action"), item=event.get("key"))
        return {"event": event}

    @app.post("/api/jobs/{job_id}/decisions/bulk")
    def post_decisions_bulk(job_id: str, body: dict):
        body = json_body(body)
        store.publication(job_id)
        entries = body.get("items") or []
        if not isinstance(entries, list) or not entries:
            raise JobError(422, "Select at least one item.", "no_items")
        who = (body.get("who") or "").strip()
        group = "d" + secrets.token_hex(5) if body.get("group") else None
        n = service.decisions(job_id).decide_many(
            who, body.get("action") or "", entries, body.get("note") or "", group
        )
        if group:
            audit.log(who, "review_group", job_id, decision=body.get("action"), count=n, group=group)
        if body.get("action") == "fix":
            service.forget(job_id)
        return {"count": n, "group": group}

    @app.delete("/api/jobs/{job_id}/decision-groups/{group}")
    def undo_decision_group(job_id: str, group: str, who: str = ""):
        store.publication(job_id)
        targets = service.decisions(job_id).revoke_group(who, group)
        service.forget(job_id)
        audit.log(who or "unknown", "review_group_undo", job_id, group=group, count=len(targets))
        return {"undone": len(targets)}

    def _apply_author_fix(job_id: str, fix: dict) -> None:
        saved = read_json(service.details_path(job_id))
        if not saved:
            return  # the details are confirmed later; the decision is still kept
        index = int(fix["author"])
        if 0 <= index < len(saved.get("authors", [])):
            for k in ("firstname", "surname", "degrees"):
                if k in fix:
                    saved["authors"][index][k] = str(fix[k]).strip()
            write_json(service.details_path(job_id), saved)

    def may_add_text(request: Request, edit: dict) -> None:
        """Typing new text into the book: reviewers and managers, unless the settings say managers only."""
        if edit.get("op") == "add_block" and settings.add_text_by == "managers":
            if person(request)[1] != "manager":
                raise JobError(403, "Only a manager can add text to the book "
                                    "(the settings can allow reviewers too).", "manager_only")  # fmt: skip

    @app.post("/api/jobs/{job_id}/edits")
    def post_edit(request: Request, job_id: str, body: dict):
        body = json_body(body)
        edit = body.get("edit") or {}
        may_add_text(request, edit)
        store.publication(job_id)
        if edit.get("op") not in EDIT_OPS:
            raise JobError(422, "Unknown change.", "bad_edit")
        if edit.get("scope") not in (None, "block", "follow"):
            raise JobError(422, "Apply it to this block only, or to it and what follows.",
                           "bad_scope")  # fmt: skip
        before, _, _ = service.effective_book(job_id)
        if edit["op"] == "heading_text":  # the audit log keeps the title as it was
            found = overlay.index_units(before).get(edit.get("unit"))
            if found and found[0]["type"] == "heading":
                edit = {**edit, "before": found[0]["content"]["text"]}
        event = service.decisions(job_id).edit(body.get("who") or "", edit, source=None)
        eff, _, failed = service.effective_book(job_id, wait=True)
        mine = [f for f in failed if f["edit"] == event["id"]]
        if mine:  # refuse a change that cannot be applied, with the plain reason
            service.decisions(job_id).revoke(body.get("who") or "system", event["id"])
            service.forget(job_id)
            raise JobError(422, mine[0]["reason"], "edit_failed")
        audit.log(event["who"], "edit", job_id, op=edit["op"], event=event["id"])
        # The rows of the changed pages, so the browser replaces only those (no reload).
        return {"event": event, "pages": service.changed_pages(before, eff, edit),
                "chapters": overlay.chapter_rows(eff)}  # fmt: skip

    @app.post("/api/jobs/{job_id}/edits/similar")
    def similar_blocks(job_id: str, body: dict):
        """Blocks printed like the saved change's block (same style and element), with the
        change each would get; nothing is saved."""
        body = json_body(body)
        store.publication(job_id)
        return service.similar(job_id, body.get("event") or "")

    @app.post("/api/jobs/{job_id}/edits/group")
    def apply_similar(job_id: str, body: dict):
        """Apply a change to the chosen similar blocks: one change each, one group."""
        body = json_body(body)
        store.publication(job_id)
        edits = body.get("edits") or []
        if not isinstance(edits, list) or any(e.get("op") not in EDIT_OPS for e in edits):
            raise JobError(422, "Unknown change.", "bad_edit")
        if any(e.get("op") in ("add_block", "remove_block") for e in edits):
            raise JobError(422, "Adding and removing blocks is done one block at a time.", "bad_edit")
        who = (body.get("who") or "").strip()
        if not who:
            raise JobError(422, "Enter your name first, so the change can be traced.", "no_who")
        return service.apply_group(job_id, who, body.get("event") or "", edits)

    @app.delete("/api/jobs/{job_id}/groups/{group}")
    def undo_group(job_id: str, group: str, who: str = ""):
        store.publication(job_id)
        result = service.undo_group(job_id, who or "unknown", group)
        audit.log(who or "unknown", "undo_group", job_id, group=group, undone=result["undone"])
        return result

    @app.post("/api/jobs/{job_id}/edits/preview")
    def preview_edit(request: Request, job_id: str, body: dict):
        """What a change would do (rows before/after, heading levels, chapters); not saved."""
        body = json_body(body)
        edit = body.get("edit") or {}
        may_add_text(request, edit)
        store.publication(job_id)
        if edit.get("op") not in EDIT_OPS:
            raise JobError(422, "Unknown change.", "bad_edit")
        return service.preview_edit(job_id, edit)

    @app.get("/api/jobs/{job_id}/chapters")
    def chapters(job_id: str):
        """Every part and chapter as the export will have them (edits applied)."""
        store.publication(job_id)
        eff, _, _ = service.effective_book(job_id)
        return {"chapters": overlay.chapter_rows(eff)}

    @app.delete("/api/jobs/{job_id}/decisions/{event_id}")
    def undo(job_id: str, event_id: str, who: str = ""):
        store.folder(job_id)
        target = next((e for e in service.decisions(job_id).edits() if e["id"] == event_id), None)
        if target is None or store.get(job_id).get("state") != "converted":
            return {"event": service.decisions(job_id).revoke(who, event_id)}  # a decision, not an edit
        before, _, _ = service.effective_book(job_id)
        event = service.decisions(job_id).revoke(who, event_id)
        after, _, _ = service.effective_book(job_id, wait=True)
        audit.log(who or "unknown", "undo", job_id, op=target.get("op"), event=event_id)
        # Undo of a change: the rows of the pages it touched, as after a change.
        return {"event": event, "pages": service.changed_pages(before, after, target),
                "chapters": overlay.chapter_rows(after)}  # fmt: skip

    # ------------------------------------------------------------------ export

    @app.post("/api/jobs/{job_id}/export")
    def export(request: Request, job_id: str, body: dict):
        manager(request)
        body = json_body(body)
        fmt = body.get("format") or "docbook"
        known = ("docbook", "epub", *sorted(FORMAT_SPECS))
        formats = tuple(body.get("formats") or ()) or (
            ("docbook", "epub") if fmt == "both" else (fmt,)
        )
        if any(f not in known for f in formats):
            raise JobError(400, f"format is one of {', '.join(known)}.", "bad_format")
        result = service.export(
            job_id,
            body.get("who") or "",
            bool(body.get("allow_alt_text_placeholders")),
            formats,
        )
        audit.log(body.get("who") or person(request)[0], "export", job_id, formats=list(formats))
        return result

    # Export with progress: the same service.export, run in a thread; the screen polls.
    export_runs: dict[str, dict] = {}

    @app.post("/api/jobs/{job_id}/export/start")
    def export_start(request: Request, job_id: str, body: dict):
        who = manager(request)
        body = json_body(body)
        formats = tuple(body.get("formats") or ())
        known = ("docbook", "epub", *sorted(FORMAT_SPECS))
        if not formats or any(f not in known for f in formats):
            raise JobError(400, f"formats are from {', '.join(known)}.", "bad_format")
        store.folder(job_id)
        if export_runs.get(job_id, {}).get("state") == "running":
            raise JobError(409, "An export of this book is already running.", "export_running")
        order = [f for f in ("docbook", "epub", *sorted(FORMAT_SPECS)) if f in formats]
        run = {"state": "running", "formats": {f: "waiting" for f in order}}
        export_runs[job_id] = run
        by = body.get("who") or who

        def work():
            try:
                result = service.export(job_id, by, bool(body.get("allow_alt_text_placeholders")),
                                        tuple(order), lambda f, st: run["formats"].__setitem__(f, st))
                audit.log(by or "unknown", "export", job_id, formats=order)
                run.update(state="done", n=result["n"])
            except JobError as e:
                run.update(state="error", error=e.message if hasattr(e, "message") else str(e),
                           code=getattr(e, "code", None), extra=getattr(e, "extra", None))
            except Exception as e:  # shown to the person, never swallowed
                run.update(state="error", error=f"The export failed: {e}")
        threading.Thread(target=work, daemon=True, name=f"export-{job_id}").start()
        return run

    @app.get("/api/jobs/{job_id}/export/progress")
    def export_progress(job_id: str):
        return export_runs.get(job_id) or {"state": "idle"}

    @app.get("/api/jobs/{job_id}/export-history")
    def export_history(job_id: str):
        """Who exported, who downloaded what and when, and with what result."""
        keep = ("export", "download", "download_override")
        events = [e for e in audit.entries(job_id, 5000) if e.get("action") in keep]
        return {"exports": service.exports(job_id), "events": events}

    @app.put("/api/jobs/{job_id}/cover")
    async def cover_upload(job_id: str, request: Request, filename: str = "cover"):
        store.folder(job_id)
        data = await request.body()
        if len(data) > 20_000_000:
            raise JobError(413, "The cover image is larger than 20 MB.", "too_large")
        return service.save_cover(job_id, filename, data)

    @app.get("/api/jobs/{job_id}/cover")
    def cover_info(job_id: str):
        path = service.cover_path(job_id)
        return {"cover": path.name if path else None}


    def lossless_gate(request: Request, job_id: str, n: int, part: str, override: str = ""):
        """A download whose lossless check is not 0 missing / 0 extra is refused. A manager can
        download it anyway (override=yes); the audit log records who did."""
        folder = service.export_folder(job_id, n)
        report = read_json(folder / part / "report" / "qc_report.json", {}) or {}
        loss = report.get("lossless") or {}
        if not (loss.get("missing") or loss.get("extra")):
            who, _ = person(request)
            audit.log(who or "unknown", "download", job_id, export=n, part=part)
            return
        if override != "yes":
            raise JobError(409, f"This file does not hold all the book's text ({loss.get('missing', 0)} "
                           f"words missing, {loss.get('extra', 0)} extra). It is not released. Fix the "
                           "edits or export again; a manager can download it anyway.",
                           "lossless_failed")  # fmt: skip
        who = manager(request)
        audit.log(who or "unknown", "download_override", job_id, export=n, part=part,
                  missing=loss.get("missing", 0), extra=loss.get("extra", 0))  # fmt: skip

    @app.get("/api/jobs/{job_id}/exports/{n}/book.epub")
    def export_epub(request: Request, job_id: str, n: int, override: str = ""):
        lossless_gate(request, job_id, n, "epub", override)
        folder = service.export_folder(job_id, n)
        record = read_json(folder / "export.json")
        if not record.get("epub"):
            raise JobError(404, "This export has no ePub.", "not_found")
        return FileResponse(
            folder / "epub" / record["epub"],
            filename=record["epub"],
            media_type="application/epub+zip",
        )

    def _format_folder(job_id: str, n: int, fmt: str) -> Path:
        if fmt not in FORMAT_SPECS:
            raise JobError(404, "No such format.", "not_found")
        folder = service.export_folder(job_id, n)
        if fmt not in read_json(folder / "export.json").get("others", {}):
            raise JobError(404, "This export has no such format.", "not_found")
        return folder / fmt

    @app.get("/api/jobs/{job_id}/exports/{n}/formats/{fmt}/delivery.zip")
    def export_format_zip(request: Request, job_id: str, n: int, fmt: str, override: str = ""):
        base = _format_folder(job_id, n, fmt)
        lossless_gate(request, job_id, n, fmt, override)
        name = read_json(service.export_folder(job_id, n) / "export.json")["others"][fmt]["zip"]
        return FileResponse(base / name, filename=name, media_type="application/zip")

    @app.get("/api/jobs/{job_id}/exports/{n}/formats/{fmt}/qc_report.html")
    def export_format_qc(job_id: str, n: int, fmt: str, download: bool = False):
        base = _format_folder(job_id, n, fmt)
        return _html_file(base / "report" / "qc_report.html", f"{fmt}_qc_report.html", download)

    @app.get("/api/jobs/{job_id}/exports/{n}/formats/{fmt}/report/{name:path}")
    def export_format_report_file(job_id: str, n: int, fmt: str, name: str):
        base = (_format_folder(job_id, n, fmt) / "report").resolve()
        path = (base / name).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise JobError(404, "No such file.", "not_found")
        return FileResponse(path)

    @app.get("/api/jobs/{job_id}/exports/{n}/epub_qc_report.html")
    def export_epub_qc(job_id: str, n: int, download: bool = False):
        folder = service.export_folder(job_id, n)
        path = folder / "epub" / "report" / "qc_report.html"
        return _html_file(path, "epub_qc_report.html", download)

    @app.get("/api/jobs/{job_id}/exports/{n}/epub_report/{name:path}")
    def export_epub_report_file(job_id: str, n: int, name: str):
        base = (service.export_folder(job_id, n) / "epub" / "report").resolve()
        path = (base / name).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise JobError(404, "No such file.", "not_found")
        return FileResponse(path)

    @app.get("/api/jobs/{job_id}/exports")
    def exports(job_id: str):
        return {"exports": service.exports(job_id)}

    @app.get("/api/jobs/{job_id}/exports/{n}")
    def export_one(job_id: str, n: int):
        return service.export_result(job_id, n)

    @app.get("/api/jobs/{job_id}/exports/{n}/delivery.zip")
    def export_zip(request: Request, job_id: str, n: int, override: str = ""):
        lossless_gate(request, job_id, n, "out", override)
        folder = service.export_folder(job_id, n)
        record = read_json(folder / "export.json")
        if not record.get("zip"):
            raise JobError(404, "This export has no DocBook delivery.", "not_found")
        return FileResponse(
            folder / "out" / record["zip"], filename=record["zip"], media_type="application/zip"
        )

    @app.get("/api/jobs/{job_id}/exports/{n}/qc_report.html")
    def export_qc(job_id: str, n: int, download: bool = False):
        folder = service.export_folder(job_id, n)
        path = folder / "out" / "report" / "qc_report.html"
        return _html_file(path, "qc_report.html", download)

    @app.get("/api/jobs/{job_id}/exports/{n}/report/{name:path}")
    def export_report_file(job_id: str, n: int, name: str):
        base = (service.export_folder(job_id, n) / "out" / "report").resolve()
        path = (base / name).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise JobError(404, "No such file.", "not_found")
        return FileResponse(path)

    # ------------------------------------------------------------------ check an edited delivery

    @app.put("/api/checks")
    async def check_upload(request: Request, filename: str = Query(..., max_length=400),
                           job: str | None = None, profile: str | None = None):  # fmt: skip
        if job:
            store.folder(job)
        if profile:
            profiles.resolve(profile)
        if not job and not profile:
            raise JobError(422, "Choose the book or the profile to check against.", "no_profile")
        check_id = secrets.token_hex(8)
        folder = service.checks_root / check_id
        folder.mkdir()
        size = 0
        try:
            with open(folder / "upload.zip", "wb") as out:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > settings.max_check_zip_bytes:
                        raise JobError(413, "The ZIP is too large to check.", "too_large")
                    out.write(chunk)
            with open(folder / "upload.zip", "rb") as f:
                if f.read(4) != b"PK\x03\x04":
                    raise JobError(415, "This is not a ZIP file.", "not_zip")
            meta = {"id": check_id, "name": safe_name(filename), "size": size, "at": now()}
            write_json(folder / "meta.json", meta)
            result = service.run_check(check_id, job, profile)
            return {"id": check_id, "name": safe_name(filename), **result}
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

    @app.get("/api/checks")
    def list_checks():
        rows = [read_json(f) for f in sorted(service.checks_root.glob("*/meta.json"), reverse=True)]
        return {"checks": [r for r in rows if r]}

    @app.get("/api/checks/{check_id}")
    def get_check(check_id: str):
        folder = service.check_dir(check_id)
        return {**read_json(folder / "meta.json"), **read_json(folder / "check.json", {})}

    @app.get("/api/checks/{check_id}/report.html")
    def check_report(check_id: str, download: bool = False):
        folder = service.check_dir(check_id)
        return _html_file(folder / "check.html", "check_report.html", download)

    @app.delete("/api/checks/{check_id}")
    def delete_check(check_id: str):
        shutil.rmtree(service.check_dir(check_id))
        return {"deleted": check_id}

    # ------------------------------------------------------------------ the single-page app

    @app.get("/api/disk-estimate")
    def disk_estimate(bytes: int, pages: int):
        return disk_requirement(data, bytes, pages)

    if STATIC.is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets") if (
            STATIC / "assets"
        ).is_dir() else None

        @app.get("/")
        def index():
            return FileResponse(STATIC / "index.html", media_type="text/html")

        @app.get("/favicon.ico")
        def favicon():
            return Response(status_code=204)

    return app


__all__ = ["create_app", "ID_RE", "json"]
