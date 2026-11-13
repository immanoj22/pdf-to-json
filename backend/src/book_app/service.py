"""The app's operations: draft run (review list), details, review items, browse view,
export, check of an edited delivery. Everything works on files in the job's folder."""

from __future__ import annotations

import functools
import hashlib
import json
import re
import shutil
import threading
from collections import OrderedDict
from pathlib import Path

from book_adapters.engine.epub_run import run_epub
from book_adapters.engine.formats_run import SPECS as FORMAT_SPECS
from book_adapters.engine.formats_run import run_format, supported_formats
from book_adapters.engine.load import load_book
from book_adapters.engine.outline import build_document
from book_adapters.engine.run import WRITERS, ExportBlocked, run_book
from book_adapters.engine.settings import draft_settings, dump_settings, load_settings
from book_adapters.rules import RULES, active_rules
from book_adapters.writers.base import WriteContext
from book_core.structure import parts as book_parts

from . import check_delivery, overlay
from . import details as details_mod
from .config import AppSettings
from .decisions import Decisions, item_key
from .jobs import JobError, JobStore, now, parts_hash, read_json, write_json
from .profiles import Profiles


def _sha(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]


OTHER_QC_KEYS = (
    "verdict", "reasons", "dtd", "house_rules", "lossless", "element_counts", "overrides",
    "warnings", "review", "confirm_with_client", "authors", "settings_to_supply", "profile",
)  # fmt: skip


@functools.cache
def _adapter_code() -> str:
    """Fingerprint of the adapter's source: a preview built by older code is rebuilt."""
    import book_adapters

    root = Path(book_adapters.__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class Service:
    def __init__(self, settings: AppSettings, store: JobStore, profiles: Profiles):
        self.settings = settings
        self.store = store
        self.profiles = profiles
        self.locks: dict[str, threading.Lock] = {}
        self.swap_locks: dict[str, threading.Lock] = {}
        self.cache: OrderedDict[tuple, dict] = OrderedDict()
        self.checks_root = settings.data_path / "checks"
        self.checks_root.mkdir(parents=True, exist_ok=True)

    def lock(self, job_id: str) -> threading.Lock:
        return self.locks.setdefault(job_id, threading.Lock())

    def swap_lock(self, job_id: str) -> threading.Lock:
        """Held only while ``preview/`` is swapped for a new build and while it is read, so a
        reader never sees a half-built or half-swapped preview (the build itself runs in
        ``preview.tmp/`` without it)."""
        return self.swap_locks.setdefault(job_id, threading.Lock())

    # ------------------------------------------------------------------ book data

    def decisions(self, job_id: str) -> Decisions:
        return Decisions(self.store.folder(job_id))

    def base_book(self, job_id: str) -> dict:
        key = ("base", job_id)
        if key not in self.cache:
            self.cache[key] = json.loads(
                (self.store.publication(job_id) / "book.json").read_text("utf-8")
            )
            self._trim()
        return self.cache[key]

    def effective_book(
        self, job_id: str, validate: bool = False
    ) -> tuple[dict, list[dict], list[dict]]:
        """The converter's book with the reviewer's edits applied (a copy). ``validate`` also
        checks the whole result against the book schema (about 10 s for 130 pages), refusing
        any edit that would break it; the browse view skips that, a draft run or export
        always does it."""
        job = self.store.get(job_id)
        edits = self.decisions(job_id).edits()
        marks = self.profiles.list_marks(job["profile"]) if job.get("profile") else {}
        key = ("eff", job_id, overlay.edits_key(edits), job.get("profile"), validate)
        if key not in self.cache:
            apply = overlay.apply_checked if validate else overlay.apply_edits
            self.cache[key] = apply(self.base_book(job_id), edits, marks)
            self._trim()
        return self.cache[key]

    def _trim(self) -> None:
        while len(self.cache) > 6:
            self.cache.popitem(last=False)

    # ------------------------------------------------------------------ details

    def details_path(self, job_id: str) -> Path:
        return self.store.folder(job_id) / "details.json"

    def get_details(self, job_id: str) -> dict:
        saved = read_json(self.details_path(job_id))
        job = self.store.get(job_id)
        options = self.profiles.book_options(job["profile"])
        if saved:
            # options the profile now chosen does not declare (confirmed under another
            # profile) are dropped, so the form can be saved again
            saved = {
                **saved,
                "options": {k: v for k, v in (saved.get("options") or {}).items() if k in options},
            }
            return {"confirmed": True, "details": saved, "options": options}
        self.ensure_preview(job_id)
        eff, _, _ = self.effective_book(job_id)
        draft, missing = draft_settings(eff, job["profile"])
        preview = read_json(self.store.folder(job_id) / "preview" / "preview.json", {})
        authors = []
        if preview.get("main_xml"):
            authors = details_mod.authors_from_xml(Path(preview["main_xml"]))
        edition = draft.get("edition")
        details = {
            "isbn": draft.get("isbn") or "",
            "title": draft.get("title") or "",
            "edition": edition or "",
            "year": details_mod.year_from_edition(edition) or "",
            "authors": authors,
            "options": {
                n: d.get("default") for n, d in options.items() if d.get("default") is not None
            },
            "sources": draft.get("sources") or {},
        }
        return {"confirmed": False, "details": details, "options": options, "to_supply": missing}

    def save_details(self, job_id: str, details: dict) -> dict:
        job = self.store.get(job_id)
        options = self.profiles.book_options(job["profile"])
        details = {
            "isbn": details_mod.clean_isbn(details.get("isbn")),
            "title": (details.get("title") or "").strip(),
            "edition": (details.get("edition") or "").strip(),
            "year": str(details.get("year") or "").strip(),
            "publisher": (details.get("publisher") or "").strip(),
            "publication_date": (details.get("publication_date") or "").strip(),
            "rights": (details.get("rights") or "").strip(),
            "authors": [
                {k: (a.get(k) or "").strip() for k in ("role", "firstname", "surname", "degrees")}
                for a in details.get("authors") or []
            ],
            "options": {k: v for k, v in (details.get("options") or {}).items() if k in options},
        }
        problems = details_mod.validate_details(details, options)
        if problems:
            raise JobError(422, "Some details need correcting.", "bad_details", problems=problems)
        if not details["authors"]:
            details.pop("authors")
            details["authors"] = []
        details["saved_at"] = now()
        write_json(self.details_path(job_id), details)
        return details

    # ------------------------------------------------------------------ book parts

    def parts_path(self, job_id: str) -> Path:
        return self.store.folder(job_id) / "parts.json"

    def confirmed_parts_path(self, job_id: str) -> Path:
        """The confirmed ranges alone, as the converter reads them (``--parts``)."""
        return self.store.folder(job_id) / "parts_confirmed.json"

    def _parts_guess(self, job_id: str) -> tuple[dict, int]:
        """(the converter's own guess of the parts, number of pages) from the converted book."""
        book = self.base_book(job_id)
        zones = {p["index"]: p["zone"] for p in book["pages"]}
        rear = [
            (s["first_page"], s["last_page"], s["kind"])
            for s in book["navigation"]["sections"]
            if s["zone"] == "rear"
        ]
        return book_parts.prefill(zones, rear), len(book["pages"])

    def get_parts(self, job_id: str) -> dict:
        saved = read_json(self.parts_path(job_id), {})
        guess, pages = self._parts_guess(job_id)
        confirmed = saved.get("confirmed")
        parts = confirmed["parts"] if confirmed else guess
        return {
            "pages": pages,
            "keys": list(book_parts.PARTS),
            "parts": parts,
            "guess": guess,
            "confirmed": bool(confirmed)
            and saved.get("built_with") == parts_hash(confirmed["parts"]),
            "confirmed_by": confirmed.get("by") if confirmed else None,
            "confirmed_at": confirmed.get("at") if confirmed else None,
            "problems": book_parts.validate(parts, pages),
        }

    def save_parts(self, job_id: str, parts: dict, who: str) -> dict:
        """Confirm the book parts (every part a range or explicitly none). Returns
        ``{"rerun": bool, ...}``: when the ranges differ from what the converted book was
        built with, the caller re-runs the converter (cached stages are reused; the structure
        stage and after run again)."""
        who = (who or "").strip()
        if not who:
            raise JobError(
                422, "Enter your name first, so the confirmation can be traced.", "no_who"
            )
        guess, pages = self._parts_guess(job_id)
        clean = {}
        for part in book_parts.PARTS:
            value = (parts or {}).get(part, "missing")
            if value in (None, "none"):
                clean[part] = None
            elif isinstance(value, dict):
                try:
                    clean[part] = {"first": int(value["first"]), "last": int(value["last"])}
                except (KeyError, TypeError, ValueError):
                    clean[part] = {"first": None, "last": None}
        problems = book_parts.validate(clean, pages)
        if problems:
            raise JobError(422, "Some book parts need correcting.", "bad_parts", problems=problems)
        saved = read_json(self.parts_path(job_id), {})
        # The built book already follows the ranges when it was built with them, or when
        # they are the converter's own guess and no earlier confirmation changed the build.
        built_with = saved.get("built_with")
        unchanged = built_with == parts_hash(clean) or (clean == guess and built_with is None)
        record = {"parts": clean, "by": who, "at": now()}
        write_json(
            self.parts_path(job_id),
            {"confirmed": record, "built_with": parts_hash(clean) if unchanged else None},
        )
        write_json(self.confirmed_parts_path(job_id), clean)
        self.cache.clear()
        return {"rerun": not unchanged, **self.get_parts(job_id)}

    def parts_built(self, job_id: str) -> None:
        """Mark the confirmed parts as built into the converted book (after a re-run)."""
        saved = read_json(self.parts_path(job_id), {})
        if saved.get("confirmed"):
            saved["built_with"] = parts_hash(saved["confirmed"]["parts"])
            write_json(self.parts_path(job_id), saved)

    def require_parts(self, job_id: str) -> dict:
        """The confirmed parts, or a refusal: there is no export without them."""
        saved = read_json(self.parts_path(job_id), {})
        confirmed = saved.get("confirmed")
        if not confirmed:
            raise JobError(
                409,
                "Confirm the book parts first: say where the front matter, body and each "
                "back-matter part start and end.",
                "parts_not_confirmed",
            )
        if saved.get("built_with") != parts_hash(confirmed["parts"]):
            raise JobError(
                409,
                "The book is being converted again with the confirmed parts; export when it "
                "is done.",
                "parts_not_built",
            )
        return confirmed

    def settings_yaml(self, job_id: str, folder: Path) -> Path:
        job = self.store.get(job_id)
        saved = read_json(self.details_path(job_id))
        path = folder / "settings.yaml"
        if saved:
            declared = self.profiles.book_options(job["profile"])
            saved = {
                **saved,
                "options": {k: v for k, v in (saved.get("options") or {}).items() if k in declared},
            }
            path.write_text(details_mod.settings_yaml(saved, job["profile"]), "utf-8")
        else:
            eff, _, _ = self.effective_book(job_id)
            data, _ = draft_settings(eff, job["profile"])
            path.write_text(dump_settings(data), "utf-8")
        return path

    # ------------------------------------------------------------------ draft run

    def _run_key(self, job_id: str) -> str:
        job = self.store.get(job_id)
        stored = self.profiles.resolve(job["profile"])
        return _sha(
            [
                stored.sha256,
                _adapter_code(),
                self.decisions(job_id).edits(),
                read_json(self.details_path(job_id)),
                self.store.get(job_id).get("publication"),
            ]
        )

    def ensure_preview(self, job_id: str, force: bool = False) -> dict:
        """Run the adapter on the edited book into ``preview/`` (alt text may still be a
        placeholder). This gives the review list, the title-page authors and the count of
        alt-text placeholders. Skipped when nothing changed since the last run, unless
        ``force``. The run builds into ``preview.tmp/``, which then replaces ``preview/`` by
        renaming, so several reviewers can read the list while one of them refreshes it; a
        refresh waiting behind another one finds the list up to date and does not run again."""
        with self.lock(job_id):
            root = self.store.folder(job_id)
            folder, build, old = root / "preview", root / "preview.tmp", root / "preview.old"
            key = self._run_key(job_id)
            state = read_json(folder / "preview.json")
            if state and state.get("key") == key and not force:
                return state
            job = self.store.get(job_id)
            if not job.get("profile"):
                raise JobError(409, "Choose a profile first.", "no_profile")
            for leftover in (build, old):
                if leftover.exists():
                    shutil.rmtree(leftover)
            build.mkdir(parents=True)
            eff, _, failed = self.effective_book(job_id, validate=True)
            publication = self.store.publication(job_id)
            book_dir = overlay.write_overlay(publication, eff, build / "book", check=False)
            settings_path = self.settings_yaml(job_id, build)
            report = run_book(
                book_dir,
                build / "out",
                settings_path,
                job["profile"],
                self.profiles.store,
                validate=False,
                allow_alt_text_placeholders=True,
            )
            main = None
            if report.get("root"):
                root_path = Path(report["root"])  # inside preview.tmp/ until the swap
                if root_path.is_relative_to(build):
                    root_path = folder / root_path.relative_to(build)
                main = root_path / report["delivery"]["main_file"]
            state = {
                "key": key,
                "at": now(),
                "main_xml": str(main) if main else None,
                "alt_text": report["alt_text"],
                "failed_edits": failed,
                "authors": report.get("authors"),
            }
            write_json(build / "preview.json", state)
            with self.swap_lock(job_id):
                if folder.exists():
                    folder.rename(old)
                build.rename(folder)
            if old.exists():
                shutil.rmtree(old, ignore_errors=True)
            return state

    # ------------------------------------------------------------------ review list

    def _read_preview(self, job_id: str) -> tuple[dict | None, list]:
        """The preview's state and review list, read together from one finished build."""
        folder = self.store.folder(job_id) / "preview"
        with self.swap_lock(job_id):
            state = read_json(folder / "preview.json")
            if state is None:
                return None, []
            path = folder / "out" / "report" / "review_list.json"
            return state, json.loads(path.read_text("utf-8"))

    def review(self, job_id: str) -> dict:
        state, items = self._read_preview(job_id)
        if state is None:
            self.ensure_preview(job_id)
            state, items = self._read_preview(job_id)
        stale = state["key"] != self._run_key(job_id)
        eff, _, failed = self.effective_book(job_id)
        ix = overlay.index_units(eff)
        base_items = (self.base_book(job_id).get("review") or {}).get("items") or []
        boxes = {(i.get("unit"), i.get("kind")): i.get("box") for i in base_items if i.get("box")}
        decided = self.decisions(job_id).current()
        out = []
        for item in items:
            key = item_key(item)
            unit = ix.get(item.get("unit") or "", (None,))[0]
            box = boxes.get((item.get("unit"), item.get("kind")))
            if box is None and unit and unit.get("boxes"):
                box = unit["boxes"][0]
            if box is None and unit and unit.get("pages"):
                box = None
            d = decided.get(key)
            m = re.search(r"offset (\d+)", item.get("reason") or "")
            out.append(
                {
                    **{
                        k: item[k]
                        for k in (
                            "severity",
                            "kind",
                            "page",
                            "page_label",
                            "unit",
                            "reason",
                            "source",
                        )
                    },
                    "key": key,
                    "offset": int(m.group(1)) if m else None,
                    "box": box,
                    "crop": item.get("crop"),
                    "editor": self.editor_for(item, unit),
                    "current": self.unit_summary(unit) if unit else None,
                    "decision": {k: d[k] for k in ("id", "action", "fix", "note", "who", "at")}
                    if d
                    else None,
                }
            )
        shown = {i["key"] for i in out}
        for key, d in decided.items():  # decided items a fix has resolved no longer appear
            if key not in shown and d.get("item"):
                snap = d["item"]
                out.append(
                    {
                        **{
                            k: snap.get(k)
                            for k in (
                                "severity",
                                "kind",
                                "page",
                                "page_label",
                                "unit",
                                "reason",
                                "source",
                                "editor",
                            )
                        },
                        "key": key,
                        "offset": None,
                        "box": snap.get("box"),
                        "crop": None,
                        "current": None,
                        "resolved": True,
                        "decision": {k: d[k] for k in ("id", "action", "fix", "note", "who", "at")},
                    }
                )
        done = sum(1 for i in out if i["decision"])
        return {
            "stale": stale,
            "items": out,
            "total": len(out),
            "decided": done,
            "must_check": sum(1 for i in out if i["severity"] == "must_check"),
            "alt_text_placeholders": state["alt_text"]["placeholders"],
            "failed_edits": failed,
        }

    @staticmethod
    def editor_for(item: dict, unit: dict | None) -> str:
        kind, reason = item["kind"], (item.get("reason") or "").lower()
        if kind == "alt_text":
            return "alt_text"
        if kind == "character" and "en dash or minus" in reason:
            return "dash"
        if kind == "character":
            return "plain"
        if "author" in reason or (item.get("rule") or "").startswith("authors"):
            return "author"
        if kind == "heading":
            return "heading"
        if kind == "table":
            return "table"
        if kind == "figure":
            return "figure"
        if kind == "join":
            return "join"
        if unit and unit["type"] in ("heading", "paragraph", "list", "list_item"):
            return "role"
        return "plain"

    @staticmethod
    def unit_summary(unit: dict) -> dict:
        content = unit.get("content") or {}
        out = {
            "id": unit["id"],
            "type": unit["type"],
            "role": unit.get("role"),
            "level": unit.get("level"),
            "text": (content.get("text") or "")[:600],
        }
        if unit["type"] in ("figure", "equation"):
            alt = unit.get("alt_text") or {}
            out.update(
                alt_text=alt.get("text") or "",
                alt_source=alt.get("source"),
                decorative=bool(unit.get("decorative")),
                image=(unit.get("image") or {}).get("file"),
            )
        if unit["type"] == "list":
            out["text"] = " | ".join(
                (i.get("content") or {}).get("text", "")[:60] for i in unit["items"][:6]
            )
        if unit["type"] == "table":
            out["rows"] = len({c.get("row") for c in unit.get("cells") or []})
            out["text"] = ""
        return out

    # ------------------------------------------------------------------ browse a page

    def page_units(self, job_id: str, number: int) -> dict:
        eff, _, failed = self.effective_book(job_id)
        if not 1 <= number <= len(eff["pages"]):
            raise JobError(404, "No such page.", "no_page")
        page = eff["pages"][number - 1]
        units = []

        def visit(us, depth, parent):
            for i, u in enumerate(us):
                if u["type"] == "page_marker":
                    continue
                if number in (u.get("pages") or []):
                    units.append(self.browse_row(u, depth, parent, us, i))
                for key in ("items", "children"):
                    if u.get(key) and u["type"] in ("list", "list_item", "box"):
                        visit(u[key], depth + 1, u["id"])

        visit(eff["content"], 0, None)
        marks = {}
        return {
            "page": number,
            "label": page.get("label"),
            "width": page["width"],
            "height": page["height"],
            "zone": page.get("zone"),
            "units": units,
            "marks": marks,
            "pages": len(eff["pages"]),
            "failed_edits": failed,
        }

    @staticmethod
    def browse_row(u: dict, depth: int, parent, siblings: list, i: int) -> dict:
        row = Service.unit_summary(u)
        content = u.get("content") or {}
        text = content.get("text") or ""
        nxt = next((s for s in siblings[i + 1 :] if s["type"] != "page_marker"), None)
        row.update(
            depth=depth,
            parent=parent,
            box=(u.get("boxes") or [None])[0],
            lines=text.split("\n") if u["type"] == "paragraph" else None,
            can_join=u["type"] == "paragraph" and nxt is not None and nxt["type"] == "paragraph",
            joined_to=(u.get("continues_to") or {}).get("unit"),
            joined_by=(u.get("continues_from") or {}).get("unit"),
            reviewer_made="review" in (u.get("provenance") or {}).get("stages", []),
        )
        row["text"] = (
            text[:2000]
            if u["type"] in ("paragraph", "heading", "list_item", "caption")
            else row["text"]
        )
        return row

    # ------------------------------------------------------------------ export

    def cover_path(self, job_id: str) -> Path | None:
        folder = self.store.folder(job_id)
        return next(iter(sorted(folder.glob("cover.*"))), None)

    def save_cover(self, job_id: str, filename: str, data: bytes) -> dict:
        """The front cover image for the ePub (JPEG or PNG, checked by content)."""
        if data[:3] == b"\xff\xd8\xff":
            ext = "jpg"
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            ext = "png"
        else:
            raise JobError(400, "The cover must be a JPEG or PNG image.", "bad_cover")
        folder = self.store.folder(job_id)
        for old in folder.glob("cover.*"):
            old.unlink()
        (folder / f"cover.{ext}").write_bytes(data)
        return {"cover": f"cover.{ext}", "bytes": len(data)}

    def export(
        self,
        job_id: str,
        who: str,
        allow_placeholders: bool,
        formats: tuple[str, ...] = ("docbook",),
    ) -> dict:
        order = ("docbook", "epub", *sorted(FORMAT_SPECS))
        formats = tuple(f for f in order if f in formats)
        if not formats:
            raise JobError(400, "Choose at least one output format.", "no_format")
        profile_obj, _ = self.profiles.store.load(self.store.get(job_id)["profile"])
        unsupported = [f for f in formats if f not in supported_formats(profile_obj)]
        if unsupported:
            raise JobError(
                400,
                f"The profile does not support {', '.join(unsupported)}. "
                f"It supports {', '.join(supported_formats(profile_obj))}.",
                "format_not_supported",
            )
        with self.lock(job_id):
            job = self.store.get(job_id)
            if job["state"] != "converted":
                raise JobError(409, "Convert the book first.", "not_converted")
            if not read_json(self.details_path(job_id)):
                raise JobError(409, "Confirm the book details first.", "no_details")
            parts_record = self.require_parts(job_id)
            n = job.get("exports", 0) + 1
            folder = self.store.folder(job_id) / "exports" / f"{n:03d}"
            if folder.exists():
                shutil.rmtree(folder)
            folder.mkdir(parents=True)
            eff, _, failed = self.effective_book(job_id, validate=True)
            book_dir = overlay.write_overlay(
                self.store.publication(job_id), eff, folder / "book", check=False
            )
            settings_path = self.settings_yaml(job_id, folder)
            cover = self.cover_path(job_id)
            if cover is not None:
                import yaml

                data = yaml.safe_load(settings_path.read_text("utf-8")) or {}
                data["epub"] = {"cover_image": str(cover.resolve())}
                settings_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
            at = now()
            modified = at[:19] + "Z"
            reports: dict[str, dict] = {}
            try:
                if "docbook" in formats:
                    reports["docbook"] = run_book(
                        book_dir,
                        folder / "out",
                        settings_path,
                        job["profile"],
                        self.profiles.store,
                        allow_alt_text_placeholders=allow_placeholders,
                    )
                if "epub" in formats:
                    reports["epub"] = run_epub(
                        book_dir,
                        folder / "epub",
                        settings_path,
                        job["profile"],
                        self.profiles.store,
                        allow_alt_text_placeholders=allow_placeholders,
                        modified=modified,
                        epubcheck_jar=self.settings.epubcheck_jar or None,
                    )
                for fmt in formats:
                    if fmt in FORMAT_SPECS:
                        source = self.store.folder(job_id) / "input.pdf"
                        reports[fmt] = run_format(
                            fmt,
                            book_dir,
                            folder / fmt,
                            settings_path,
                            job["profile"],
                            self.profiles.store,
                            allow_alt_text_placeholders=allow_placeholders,
                            source_pdf=source if source.is_file() else None,
                        )
            except ExportBlocked as blocked:
                shutil.rmtree(folder, ignore_errors=True)
                alt = blocked.report["alt_text"]
                raise JobError(
                    409,
                    f"{alt['placeholders']} figure or equation description(s) are still missing. "
                    "Write them in the review, or tick the override to export anyway.",
                    "alt_text_placeholders",
                    placeholders=alt["placeholders"],
                    units=alt["units"][:50],
                ) from blocked
            parts_note = {
                "ranges": parts_record["parts"],
                "confirmed_by": parts_record["by"],
                "confirmed_at": parts_record["at"],
            }
            for fmt, sub in (("docbook", "out"), ("epub", "epub"), *((f, f) for f in FORMAT_SPECS)):
                qc_path = folder / sub / "report" / "qc_report.json"
                if fmt in reports and qc_path.is_file():
                    qc_doc = json.loads(qc_path.read_text("utf-8"))
                    qc_doc["book_parts"] = parts_note
                    write_json(qc_path, qc_doc)
            first = reports[formats[0]]
            override = bool(first["alt_text"]["override"])
            if override:
                self.decisions(job_id).override(
                    who, "export with alt-text placeholders", first["alt_text"]["placeholders"]
                )
            record = {
                "n": n,
                "at": at,
                "who": who,
                "formats": list(formats),
                "profile": first["profile"]["ref"],
                "profile_status": first["profile"]["status"],
                "override_alt_text": override,
                "failed_edits": failed,
                "book_parts": parts_note,
                "seconds": round(sum(r.get("seconds") or 0 for r in reports.values()), 2),
            }
            verdicts = {}
            if "docbook" in reports:
                rep = reports["docbook"]
                qc = json.loads((folder / "out" / "report" / "qc_report.json").read_text("utf-8"))
                zip_path = next(iter(sorted((folder / "out").glob("*.zip"))), None)
                if zip_path is None:
                    from book_adapters.engine.packager import write_zip

                    zip_path = write_zip(
                        Path(rep["root"]), folder / "out" / f"{Path(rep['root']).name}.zip"
                    )
                record["zip"] = zip_path.name
                record["isbn_folder"] = Path(rep["root"]).name
                verdicts["docbook"] = qc["verdict"]
            if "epub" in reports:
                qc = json.loads((folder / "epub" / "report" / "qc_report.json").read_text("utf-8"))
                record["epub"] = Path(reports["epub"]["epub"]).name
                record["epubcheck"] = qc["epubcheck"].get("status")
                verdicts["epub"] = qc["verdict"]
            others = {}
            for fmt in FORMAT_SPECS:
                if fmt in reports:
                    qc = json.loads((folder / fmt / "report" / "qc_report.json").read_text("utf-8"))
                    zip_name = Path(reports[fmt]["zip"]).name
                    others[fmt] = {"zip": zip_name, "verdict": qc["verdict"],
                                   "label": reports[fmt]["format_label"]}  # fmt: skip
                    verdicts[fmt] = qc["verdict"]
            if others:
                record["others"] = others
            record["verdicts"] = verdicts
            rank = {"fail": 2, "warn": 1, "pass": 0}
            record["verdict"] = max(verdicts.values(), key=lambda v: rank[v])
            write_json(folder / "export.json", record)
            self.store.update(
                job_id,
                exports=n,
                last_export={
                    "n": n,
                    "verdict": record["verdict"],
                    "verdicts": verdicts,
                    "formats": list(formats),
                    "at": record["at"],
                    "profile": record["profile"],
                },
            )
            return self.export_result(job_id, n)

    def export_folder(self, job_id: str, n: int) -> Path:
        folder = self.store.folder(job_id) / "exports" / f"{n:03d}"
        if not (folder / "export.json").is_file():
            raise JobError(404, "No such export.", "not_found")
        return folder

    def export_result(self, job_id: str, n: int) -> dict:
        folder = self.export_folder(job_id, n)
        record = read_json(folder / "export.json")
        qc = read_json(folder / "out" / "report" / "qc_report.json", {})
        epub_qc = read_json(folder / "epub" / "report" / "qc_report.json", {})
        return {
            **record,
            "epub_qc": {
                k: epub_qc.get(k)
                for k in (
                    "verdict",
                    "reasons",
                    "own_checks",
                    "epubcheck",
                    "lossless",
                    "counts",
                    "element_counts",
                    "overrides",
                    "warnings",
                    "review",
                    "confirm_with_client",
                    "profile",
                )
            }
            if epub_qc
            else None,
            "other_qc": {
                fmt: {
                    k: v
                    for k, v in read_json(folder / fmt / "report" / "qc_report.json", {}).items()
                    if k in OTHER_QC_KEYS
                }
                for fmt in record.get("others", {})
            },
            "qc": {
                k: qc.get(k)
                for k in (
                    "verdict",
                    "reasons",
                    "dtd",
                    "house_rules",
                    "lossless",
                    "element_counts",
                    "overrides",
                    "warnings",
                    "review",
                    "confirm_with_client",
                    "authors",
                    "settings_to_supply",
                    "profile",
                )
            },
        }

    def exports(self, job_id: str) -> list[dict]:
        base = self.store.folder(job_id) / "exports"
        rows = []
        for f in sorted(base.glob("*/export.json")) if base.is_dir() else []:
            rows.append(read_json(f))
        return rows

    # ------------------------------------------------------------------ check an edited delivery

    def build_expected(self, job_id: str, ref: str | None = None):
        """The converter's own export of the book in memory (document, delivery, book)."""
        job = self.store.get(job_id)
        ref = ref or job["profile"]
        work = self.store.folder(job_id) / "check_work"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir()
        eff, _, _ = self.effective_book(job_id, validate=True)
        book_dir = overlay.write_overlay(
            self.store.publication(job_id), eff, work / "book", check=False
        )
        settings_path = self.settings_yaml(job_id, work)
        profile, _ = self.profiles.store.load(ref)
        settings = load_settings(settings_path, profile)
        book = load_book(book_dir)
        rules_on = active_rules(profile, settings)
        doc = build_document(book, profile, settings, rules_on)
        for name in sorted(rules_on):
            if RULES[name].phase == "tree":
                RULES[name].func(doc, {"profile": profile, "settings": settings})
        delivery = WRITERS[profile.get("writer")]().write(
            doc, WriteContext(profile, settings, rules_on, book)
        )
        return (doc, delivery, book), profile

    def check_dir(self, check_id: str) -> Path:
        import re

        if not re.fullmatch(r"[0-9a-f]{16}", check_id or ""):
            raise JobError(404, "No such check.", "not_found")
        folder = self.checks_root / check_id
        if not folder.is_dir():
            raise JobError(404, "No such check.", "not_found")
        return folder

    def run_check(self, check_id: str, job_id: str | None, profile_ref: str | None) -> dict:
        folder = self.check_dir(check_id)
        meta = read_json(folder / "meta.json")
        expected, profile = None, None
        label = None
        if job_id:
            job = self.store.get(job_id)
            if job["state"] != "converted":
                raise JobError(409, "Convert that book first.", "not_converted")
            expected, profile = self.build_expected(job_id, profile_ref or job["profile"])
            label = job["name"]
        elif profile_ref:
            profile, _ = self.profiles.store.load(profile_ref)
        if profile is None:
            raise JobError(422, "Choose the profile (or the book) to check against.", "no_profile")
        result = check_delivery.run_check(folder / "upload.zip", folder, expected, profile, label)
        result["profile"] = profile.name + "@" + profile.version
        check_delivery.save(folder, result, meta["name"])
        write_json(
            folder / "meta.json",
            {**meta, "verdict": result["verdict"], "job": job_id, "checked_at": now()},
        )
        return result
