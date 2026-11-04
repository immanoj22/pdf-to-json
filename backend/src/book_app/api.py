"""The web API (FastAPI) and the single-page app. Local by default; nothing is fetched from
outside; every id is a hex string checked before it touches a path."""

from __future__ import annotations

import json
import re
import secrets
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from book_adapters.engine.formats_run import SPECS as FORMAT_SPECS

from . import __version__, pdfpages
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
from .service import Service

STATIC = Path(__file__).parent / "static"
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
    converter.resume_queued(store.recover())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        converter.stop()  # a stopped app leaves running conversions recoverable

    app = FastAPI(
        title="PDF to DocBook", version=__version__, docs_url=None, redoc_url=None,
        openapi_url=None, lifespan=lifespan,
    )  # fmt: skip
    app.state.settings, app.state.store, app.state.service = settings, store, service
    app.state.converter, app.state.profiles = converter, profiles

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
            "models_ready": bool(models and models.is_dir() and any(models.glob("models--*"))),
            "data_folder": str(data),
        }

    # ------------------------------------------------------------------ profiles

    @app.get("/api/profiles")
    def list_profiles():
        return {"profiles": profiles.list()}

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
        return {"jobs": store.list()}

    @app.put("/api/jobs")
    async def upload_pdf(request: Request, filename: str = Query(..., max_length=400)):
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
            return job
        finally:
            tmp.unlink(missing_ok=True)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = store.get(job_id)
        job["disk"] = None
        return job

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str, confirm: str = ""):
        if confirm != "yes":
            raise JobError(400, "Deleting needs confirmation.", "confirm")
        store.delete(job_id)
        service.cache.clear()
        return {"deleted": job_id}

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
    def convert(job_id: str):
        return converter.submit(job_id)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        return converter.cancel(job_id)

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

    # ------------------------------------------------------------------ review

    @app.get("/api/jobs/{job_id}/review")
    def get_review(job_id: str):
        store.publication(job_id)
        return service.review(job_id)

    @app.post("/api/jobs/{job_id}/review/refresh")
    def refresh_review(job_id: str):
        store.publication(job_id)
        service.ensure_preview(job_id, force=True)
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
        return {"event": event}

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

    @app.post("/api/jobs/{job_id}/edits")
    def post_edit(job_id: str, body: dict):
        body = json_body(body)
        store.publication(job_id)
        edit = body.get("edit") or {}
        if edit.get("op") not in EDIT_OPS:
            raise JobError(422, "Unknown change.", "bad_edit")
        event = service.decisions(job_id).edit(body.get("who") or "", edit, source=None)
        eff, _, failed = service.effective_book(job_id)
        mine = [f for f in failed if f["edit"] == event["id"]]
        if mine:  # refuse a change that cannot be applied, with the plain reason
            service.decisions(job_id).revoke(body.get("who") or "system", event["id"])
            service.cache.clear()
            raise JobError(422, mine[0]["reason"], "edit_failed")
        return {"event": event}

    @app.delete("/api/jobs/{job_id}/decisions/{event_id}")
    def undo(job_id: str, event_id: str, who: str = ""):
        store.folder(job_id)
        return {"event": service.decisions(job_id).revoke(who, event_id)}

    # ------------------------------------------------------------------ export

    @app.post("/api/jobs/{job_id}/export")
    def export(job_id: str, body: dict):
        body = json_body(body)
        fmt = body.get("format") or "docbook"
        known = ("docbook", "epub", *sorted(FORMAT_SPECS))
        formats = tuple(body.get("formats") or ()) or (
            ("docbook", "epub") if fmt == "both" else (fmt,)
        )
        if any(f not in known for f in formats):
            raise JobError(400, f"format is one of {', '.join(known)}.", "bad_format")
        return service.export(
            job_id,
            body.get("who") or "",
            bool(body.get("allow_alt_text_placeholders")),
            formats,
        )

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

    @app.get("/api/jobs/{job_id}/exports/{n}/book.epub")
    def export_epub(job_id: str, n: int):
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
    def export_format_zip(job_id: str, n: int, fmt: str):
        base = _format_folder(job_id, n, fmt)
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
    def export_zip(job_id: str, n: int):
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
