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

from book_adapters.engine.formats_run import SPECS as FORMAT_SPECS
from book_adapters.engine.formats_run import supported_formats
from book_adapters.engine.load import load_book
from book_adapters.engine.outline import build_document
from book_adapters.engine.run import WRITERS, ExportBlocked
from book_adapters.engine.settings import draft_settings, dump_settings, load_settings
from book_adapters.engine.text import render
from book_adapters.rules import RULES, active_rules
from book_adapters.writers.base import WriteContext
from book_core.structure import parts as book_parts

from . import check_delivery, edit_ops, effective, overlay
from . import details as details_mod
from .builds import Builds, Preparing
from .config import AppSettings
from .decisions import Decisions, item_key
from .jobs import JobError, JobStore, now, parts_hash, read_json, write_json
from .profiles import Profiles


DECISION_FIELDS = ("id", "action", "fix", "note", "who", "at")


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


REFERENCES_ONLY = "references_only"


def references_only_parts(pages: int) -> dict:
    """The parts of a PDF that is one reference list: the bibliography is every page."""
    return {**dict.fromkeys(book_parts.PARTS), "bibliography": {"first": 1, "last": pages}}


def validate_parts(parts: dict, pages: int, references_only: bool = False) -> list[dict]:
    """Problems in the book parts; a references-only document has one bibliography over every
    page and nothing else (a book needs a body)."""
    if not references_only:
        return book_parts.validate(parts, pages)
    if parts == references_only_parts(pages):
        return []
    return [{"part": "bibliography",
             "message": f"A references-only document is one reference list over pages 1 to {pages}."}]


def by_assistant(who: str | None) -> bool:
    """True when a record was made by the reviewing assistant (its name starts with "Claude
    Desktop"), not by a person. Same rule as isPerson() in the review screen: such a record
    stays open until a person confirms it."""
    return (who or "").strip().lower().startswith("claude desktop")


class Service:
    def __init__(self, settings: AppSettings, store: JobStore, profiles: Profiles):
        self.settings = settings
        self.store = store
        self.profiles = profiles
        self.locks: dict[str, threading.Lock] = {}
        self.swap_locks: dict[str, threading.Lock] = {}
        self.cache: OrderedDict[tuple, dict] = OrderedDict()
        self.mem_lock = threading.RLock()  # short: only guards the cache and stage dictionaries
        self.builds = Builds(settings.build_workers)
        self.saves: dict[str, tuple] = {}  # job id -> the newest state waiting to be saved
        self.saving: set[str] = set()
        self.saves_lock = threading.Lock()
        self.review_static: dict[str, tuple] = {}  # job id -> (key, the review items, no decisions)
        self.review_items: dict[str, tuple] = {}  # job id -> (preview key, review_list.json)
        self.stages: OrderedDict[tuple, dict] = OrderedDict()
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
        with self.mem_lock:
            if key in self.cache:
                return self.cache[key]
        book = json.loads((self.store.publication(job_id) / "book.json").read_text("utf-8"))
        with self.mem_lock:
            self.cache[key] = book
            self._trim()
        return book

    INLINE_EDITS = 3  # a book that is a few edits behind a state in memory is brought up here
    COLD_INLINE = 10  # a book with this few edits in all is replayed here: not worth a worker

    def forget(self, job_id: str, base: bool = False) -> None:
        """Drop this book's edited copies from memory (other books stay; the unchanged base
        book too, unless ``base``)."""
        with self.mem_lock:
            for key in [k for k in self.cache if k[1] == job_id and (base or k[0] == "eff")]:
                del self.cache[key]
            self.review_static.pop(job_id, None)

    def effective_book(
        self, job_id: str, validate: bool = False, wait: bool = False
    ) -> tuple[dict, list[dict], list[dict]]:
        """The converter's book with the reviewer's edits applied (a copy). ``validate`` also
        checks the whole result against the book schema, refusing any edit that would break it
        (a draft run or an export always does it).

        The book is taken from memory, else from the copy saved on disk for these exact edits,
        else it is a few edits after a state in memory (done here), else the replay runs in a
        worker process and this raises ``Preparing`` at once: the page asks again. A caller that
        has just written a decision passes ``wait`` and gets the book, whatever it takes."""
        job = self.store.get(job_id)
        edits = self.decisions(job_id).edits()
        marks = self.profiles.list_marks(job["profile"]) if job.get("profile") else {}
        key = ("eff", job_id, overlay.edits_key(edits), job.get("profile"), validate)
        with self.mem_lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        publication = self.store.publication(job_id)
        folder = self.store.folder(job_id)
        keys = effective.edit_keys(edits)
        skey = effective.state_key(publication.name, keys, marks, validate)
        payload = effective.load(folder, skey)
        if payload is not None:
            result = self._adopt(job_id, job, keys, payload, validate)
        elif not validate and (self._near(job_id, job, keys) or len(edits) <= self.COLD_INLINE):
            result = self._apply_resumed(job_id, job, edits, marks)
            self._save_later(job_id, job, folder, skey, publication.name, keys, marks)
        else:
            self._build(job_id, folder, job, marks, validate, wait)  # raises Preparing, or waits
            payload = effective.load(folder, skey)
            if payload is None:  # the edits changed while it was built: ask again
                raise Preparing("book", 1)
            result = self._adopt(job_id, job, keys, payload, validate)
        with self.mem_lock:
            self.cache[key] = result
            self._trim()
        return result

    def _who(self, job_id: str, job: dict) -> tuple:
        return (job_id, job.get("profile"), job.get("publication"))

    def _adopt(self, job_id: str, job: dict, keys: list[str], payload: dict, validate: bool):
        """A saved state as the book. An unchecked one also becomes the state in memory that
        the next edit builds on."""
        if validate:
            return payload["book"], list(payload["applied"]), list(payload["failed"])
        pre, applied, failed = payload["pre"], payload["applied"], payload["failed"]
        with self.mem_lock:
            self.stages[self._who(job_id, job)] = {
                "keys": keys, "end": (pre, applied, failed), "prev": None,
            }
            while len(self.stages) > 2:
                self.stages.pop(next(iter(self.stages)))
        return overlay.finish(overlay.clone(pre), applied), list(applied), list(failed)

    def _resume_point(self, job_id: str, job: dict, keys: list[str]):
        old = self.stages.get(self._who(job_id, job))
        if old:
            n = len(old["keys"])
            if keys[:n] == old["keys"]:
                return old, old["end"], n
            if old["prev"] and keys[: n - 1] == old["keys"][: n - 1]:
                return old, old["prev"], n - 1
        return old, None, 0

    def _near(self, job_id: str, job: dict, keys: list[str]) -> bool:
        _, resume, skip = self._resume_point(job_id, job, keys)
        return resume is not None and len(keys) - skip <= self.INLINE_EDITS

    def _build(self, job_id, folder, job, marks, validate: bool, wait: bool) -> None:
        """Have the replay done in a worker process (once for everybody asking)."""
        work = ("book", job_id, bool(validate))
        error = self.builds.failure(work)
        if error is not None:
            raise JobError(500, f"The edited book could not be built: {error}", "build_failed")
        future = self.builds.submit(
            work, job_id, effective.build_task, str(folder), job["publication"], marks, validate
        )
        if wait or self.builds.workers == 0:
            future.result()
            return
        raise Preparing("book")

    def _save_later(self, job_id, job, folder, skey, publication, keys, marks) -> None:
        """Save the state in memory to disk in the background; of several waiting, the newest."""
        stage = self.stages.get(self._who(job_id, job))
        if not stage:
            return
        pre, applied, failed = stage["end"]
        with self.saves_lock:
            self.saves[job_id] = (folder, skey, effective.meta_of(publication, keys, marks, False),
                                  {"pre": pre, "applied": applied, "failed": failed})
            if job_id in self.saving:
                return
            self.saving.add(job_id)
        threading.Thread(target=self._saver, args=(job_id,), daemon=True, name="save-book").start()

    def _saver(self, job_id: str) -> None:
        while True:
            with self.saves_lock:
                item = self.saves.pop(job_id, None)
                if item is None:
                    self.saving.discard(job_id)
                    return
            folder, skey, meta, payload = item
            try:
                effective.save(folder, skey, meta, payload)
            except OSError:  # a deleted job: nothing to keep
                pass

    def _apply_resumed(self, job_id: str, job: dict, edits: list[dict], marks: dict):
        """``overlay.apply_edits`` that starts from the book of the last build when the edits
        only grew (a new edit) or lost their last one (an undo): the result is the same, and
        the work is one edit instead of all of them."""
        keys = [overlay.edits_key([e]) for e in edits]
        who = self._who(job_id, job)
        old, resume, skip = self._resume_point(job_id, job, keys)
        base = resume[0] if resume else self.base_book(job_id)
        pre, applied, failed, last = overlay.apply_stage(base, edits[skip:], marks, resume)
        prev = None
        if last and len(edits) > skip:
            content, furniture, na, nf = last
            before = {**pre, "content": content}
            if "furniture" in pre:
                before["furniture"] = furniture
            prev = (before, applied[:na], failed[:nf])
        with self.mem_lock:
            self.stages[who] = {"keys": keys, "end": (pre, applied, failed), "prev": prev}
            while len(self.stages) > 2:
                self.stages.pop(next(iter(self.stages)))
        return overlay.finish(overlay.clone(pre), applied), list(applied), list(failed)

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
        if self.refs_only(job_id):  # a reference list has no ISBN, title or authors to confirm
            chosen = {k: v for k, v in ((saved or {}).get("options") or {}).items() if k in options}
            defaults = {n: d.get("default") for n, d in options.items() if d.get("default") is not None}
            details = {"isbn": "", "title": "", "edition": "", "year": "", "authors": [], "sources": {},
                       **(saved or {}), "options": {**defaults, **chosen}}
            return {"confirmed": True, "details": details, "options": options, "references_only": True}
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
        problems = details_mod.validate_details(details, options, self.refs_only(job_id))
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

    def refs_only(self, job_id: str) -> bool:
        """True when the document is one reference list (document type "References only")."""
        return self.store.get(job_id).get("document_type") == REFERENCES_ONLY

    def set_document_type(self, job_id: str, document_type: str, who: str = "") -> dict:
        """The type of document this PDF is. ``references_only``: the whole PDF is one
        reference list, so its parts are fixed (a bibliography over every page, no chapter or
        heading is looked for) and confirmed by the type itself; it is chosen before the
        conversion. ``book`` (the default) removes it."""
        job = self.store.get(job_id)
        if document_type not in ("book", REFERENCES_ONLY):
            raise JobError(400, "The document type is book or references_only.", "bad_document_type")
        current = job.get("document_type") or "book"
        if document_type == current:
            return job
        if job["state"] in ("queued", "converting", "converted"):
            raise JobError(409, "The document type is chosen before the conversion. Copy the book "
                           "to convert it as another type.", "too_late")  # fmt: skip
        if document_type == REFERENCES_ONLY:
            parts = references_only_parts(job["pages"])
            who = (who or "").strip() or "document type: References only"
            write_json(self.parts_path(job_id),
                       {"confirmed": {"parts": parts, "by": who, "at": now()}, "built_with": None})
            write_json(self.confirmed_parts_path(job_id), parts)
        else:
            self.parts_path(job_id).unlink(missing_ok=True)
            self.confirmed_parts_path(job_id).unlink(missing_ok=True)
        return self.store.update(job_id, document_type=document_type)

    def get_parts(self, job_id: str) -> dict:
        saved = read_json(self.parts_path(job_id), {})
        guess, pages = self._parts_guess(job_id)
        confirmed = saved.get("confirmed")
        planned = saved.get("planned")
        # The ranges shown: the confirmed ones, else the ones given at upload, else the guess.
        parts = confirmed["parts"] if confirmed else planned["parts"] if planned else guess
        return {
            "planned": bool(planned) and not confirmed,
            "pages": pages,
            "keys": list(book_parts.PARTS),
            "parts": parts,
            "guess": guess,
            "confirmed": bool(confirmed)
            and not by_assistant(confirmed.get("by"))
            and saved.get("built_with") == parts_hash(confirmed["parts"]),
            "by_assistant": bool(confirmed) and by_assistant(confirmed.get("by")),
            "confirmed_by": confirmed.get("by") if confirmed else None,
            "confirmed_at": confirmed.get("at") if confirmed else None,
            "problems": validate_parts(parts, pages, self.refs_only(job_id)),
            "references_only": self.refs_only(job_id),
        }

    @staticmethod
    def _clean_parts(parts: dict) -> dict:
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
        return clean

    def planned_parts(self, job_id: str) -> dict:
        """The parts given at upload, before the book is converted (optional)."""
        job = self.store.get(job_id)
        saved = read_json(self.parts_path(job_id), {})
        planned = saved.get("planned")
        empty = {part: None for part in book_parts.PARTS}
        parts = planned["parts"] if planned else empty
        return {
            "pages": job["pages"], "keys": list(book_parts.PARTS), "parts": parts,
            "planned": bool(planned), "planned_by": planned.get("by") if planned else None,
            "problems": validate_parts(parts, job["pages"], self.refs_only(job_id)) if planned else [],
        }  # fmt: skip

    def plan_parts(self, job_id: str, parts: dict | None, who: str) -> dict:
        """Book parts given before the conversion: the converter reads them as it would
        confirmed parts (so a later confirmation of the same ranges converts nothing again).
        They are not a confirmation: the parts are still confirmed after the conversion,
        before any export. ``parts`` None removes the plan."""
        job = self.store.get(job_id)
        if job["state"] in ("converting", "converted"):  # waiting in the queue is still in time
            raise JobError(409, "Give the book parts before converting; after the conversion "
                           "confirm them on the Details page.", "too_late")  # fmt: skip
        if parts is None:
            self.parts_path(job_id).unlink(missing_ok=True)
            self.confirmed_parts_path(job_id).unlink(missing_ok=True)
            return self.planned_parts(job_id)
        who = (who or "").strip()
        if not who:
            raise JobError(422, "Enter your name first, so the parts can be traced.", "no_who")
        clean = self._clean_parts(parts)
        problems = validate_parts(clean, job["pages"], self.refs_only(job_id))
        if problems:
            raise JobError(422, "Some book parts need correcting.", "bad_parts", problems=problems)
        write_json(self.parts_path(job_id), {"planned": {"parts": clean, "by": who, "at": now()}})
        write_json(self.confirmed_parts_path(job_id), clean)
        return self.planned_parts(job_id)

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
        if self.refs_only(job_id):
            raise JobError(409, "A references-only document has one part: the reference list over "
                           "every page. Its parts cannot be changed.", "parts_fixed")  # fmt: skip
        guess, pages = self._parts_guess(job_id)
        clean = self._clean_parts(parts)
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
            {
                **({"planned": saved["planned"]} if saved.get("planned") else {}),
                "confirmed": record,
                "built_with": parts_hash(clean) if unchanged else None,
            },
        )
        write_json(self.confirmed_parts_path(job_id), clean)
        self.forget(job_id, base=True)
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
        if by_assistant(confirmed.get("by")):
            raise JobError(
                409,
                f"The book parts were filled in by {confirmed['by']}. A person must check them "
                "against the printed book and confirm them on the Book details page.",
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

    def settings_text(self, job_id: str) -> str:
        job = self.store.get(job_id)
        saved = read_json(self.details_path(job_id))
        if self.refs_only(job_id):  # the profile and the options chosen: nothing else is printed
            declared = self.profiles.book_options(job["profile"])
            options = {k: v for k, v in ((saved or {}).get("options") or {}).items() if k in declared}
            return dump_settings({"profile": job["profile"], "options": options})
        if saved:
            declared = self.profiles.book_options(job["profile"])
            saved = {
                **saved,
                "options": {k: v for k, v in (saved.get("options") or {}).items() if k in declared},
            }
            return details_mod.settings_yaml(saved, job["profile"])
        eff, _, _ = self.effective_book(job_id)
        data, _ = draft_settings(eff, job["profile"])
        return dump_settings(data)

    def settings_yaml(self, job_id: str, folder: Path) -> Path:
        path = folder / "settings.yaml"
        path.write_text(self.settings_text(job_id), "utf-8")
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
                self.store.get(job_id).get("document_type"),
            ]
        )

    def ensure_preview(self, job_id: str, force: bool = False) -> dict:
        """The adapter's draft run of the edited book in ``preview/`` (alt text may still be a
        placeholder): the review list, the title-page authors and the count of alt-text
        placeholders. Returns it when it is up to date; otherwise the run is started in a worker
        process (once, however many ask) and this raises ``Preparing``. The run builds into
        ``preview.tmp/`` and replaces ``preview/`` by renaming, so reviewers keep reading the
        old list meanwhile."""
        root = self.store.folder(job_id)
        folder = root / "preview"
        key = self._run_key(job_id)
        state = read_json(folder / "preview.json")
        if state and state.get("key") == key and not force:
            return state
        job = self.store.get(job_id)
        if not job.get("profile"):
            raise JobError(409, "Choose a profile first.", "no_profile")
        work = ("preview", job_id)
        error = self.builds.failure(work)
        if error is not None:
            raise JobError(500, f"The review list could not be prepared: {error}", "preview_failed")
        if not self.builds.running(work):
            text = self.settings_text(job_id)  # may itself have to wait for the edited book
            marks = self.profiles.list_marks(job["profile"])
            self.builds.submit(
                work, job_id, effective.preview_task, str(root), job["publication"], marks,
                job["profile"], str(self.profiles.store.store), text,
                "tail" if self.refs_only(job_id) else "docbook",
                then=lambda result: self._finish_preview(job_id, key, result),
            )
        state = read_json(folder / "preview.json")
        if self.builds.workers == 0 and state and state.get("key") == key:
            return state
        raise Preparing("review list")

    def _finish_preview(self, job_id: str, key: str, result: dict) -> None:
        """In this process, once the worker is done: write the state and swap the folders."""
        root = self.store.folder(job_id)
        folder, build, old = root / "preview", root / "preview.tmp", root / "preview.old"
        report = result["report"]
        main = None
        if report.get("root"):
            root_path = Path(report["root"])  # inside preview.tmp/ until the swap
            if root_path.is_relative_to(build):
                root_path = folder / root_path.relative_to(build)
            main = root_path / report["delivery"]["main_file"]
        state = {
            "key": key, "at": now(), "main_xml": str(main) if main else None,
            "alt_text": report["alt_text"], "failed_edits": result["failed"],
            "authors": report.get("authors"),
        }
        write_json(build / "preview.json", state)
        with self.swap_lock(job_id):
            if folder.exists():
                folder.rename(old)
            build.rename(folder)
        if old.exists():
            shutil.rmtree(old, ignore_errors=True)

    # ------------------------------------------------------------------ review list

    def _read_preview(self, job_id: str) -> tuple[dict | None, list]:
        """The preview's state and review list, read together from one finished build."""
        folder = self.store.folder(job_id) / "preview"
        with self.swap_lock(job_id):
            state = read_json(folder / "preview.json")
            if state is None:
                return None, []
            with self.mem_lock:
                kept = self.review_items.get(job_id)
            if kept is not None and kept[0] == state.get("key"):
                return state, kept[1]
            path = folder / "out" / "report" / "review_list.json"
            items = json.loads(path.read_text("utf-8"))
            with self.mem_lock:
                self.review_items[job_id] = (state.get("key"), items)
            return state, items

    def review_progress(self, job_id: str) -> dict | None:
        """Items decided / total, for the book and for each assigned reviewer's pages; None
        until the review list has been prepared once."""
        from .queue import assignments

        state, items = self._read_preview(job_id)
        if state is None:
            return None
        decided = self.decisions(job_id).current()
        done = [item_key(i) in decided for i in items]
        rows = []
        for a in assignments(self.store.folder(job_id)):
            mine = [d for i, d in zip(items, done, strict=True)
                    if a["first"] is None or (i.get("page") and a["first"] <= i["page"] <= a["last"])]  # fmt: skip  # noqa: E501
            rows.append({**a, "total": len(mine), "decided": sum(mine)})
        return {"total": len(items), "decided": sum(done), "reviewers": rows}

    def review(self, job_id: str, offset: int = 0, limit: int | None = None) -> dict:
        """The review list with the decisions made so far. ``limit`` returns only a page of it
        (``offset``, ``limit``) with the totals of the whole list, so the first screen can be
        shown while the rest is fetched. The part that costs time (each item with its unit,
        box and editor) is built once per preview and edit list and kept per book."""
        state, items = self._read_preview(job_id)
        if state is None:
            self.ensure_preview(job_id)
            state, items = self._read_preview(job_id)
        stale = state["key"] != self._run_key(job_id)
        eff, _, failed = self.effective_book(job_id)
        edits_key = overlay.edits_key(self.decisions(job_id).edits())
        key = (state["key"], edits_key)
        with self.mem_lock:
            kept = self.review_static.get(job_id)
        if kept is not None and kept[0] == key:
            static = kept[1]
        else:
            static = self._review_static(job_id, items, eff)
            with self.mem_lock:
                self.review_static[job_id] = (key, static)
        decided = self.decisions(job_id).current()
        shown = {i["key"] for i in static}
        resolved = self._review_resolved(decided, shown)
        total = len(static) + len(resolved)
        done = sum(1 for i in static if i["key"] in decided) + len(resolved)
        must = sum(1 for i in static if i["severity"] == "must_check") + sum(
            1 for i in resolved if i["severity"] == "must_check"
        )
        end = total if limit is None else offset + limit
        window = []
        for i in static[offset:end]:
            d = decided.get(i["key"])
            window.append({**i, "decision": {k: d[k] for k in DECISION_FIELDS} if d else None})
        window += resolved[max(0, offset - len(static)) : max(0, end - len(static))]
        return {
            "stale": stale,
            "items": window,
            "total": total,
            "decided": done,
            "must_check": must,
            "offset": offset,
            "has_more": end < total,
            "alt_text_placeholders": state["alt_text"]["placeholders"],
            "failed_edits": failed,
        }

    def _review_static(self, job_id: str, items: list, eff: dict) -> list[dict]:
        ix = overlay.index_units(eff)
        base_items = (self.base_book(job_id).get("review") or {}).get("items") or []
        boxes = {(i.get("unit"), i.get("kind")): i.get("box") for i in base_items if i.get("box")}
        out = []
        for item in items:
            key = item_key(item)
            unit = ix.get(item.get("unit") or "", (None,))[0]
            box = boxes.get((item.get("unit"), item.get("kind")))
            if box is None and unit and unit.get("boxes"):
                box = unit["boxes"][0]
            if box is None and unit and unit.get("pages"):
                box = None
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
                    "current": self.unit_summary(unit, item["kind"] == "reference") if unit else None,
                }
            )
        return out

    @staticmethod
    def _review_resolved(decided: dict, shown: set) -> list[dict]:
        out = []
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
        return out

    @staticmethod
    def editor_for(item: dict, unit: dict | None) -> str:
        kind, reason = item["kind"], (item.get("reason") or "").lower()
        if kind == "alt_text":
            return "alt_text"
        if kind == "character" and "en dash or minus" in reason:
            return "dash"
        if kind == "character" and "Hyphen followed by a space" in reason:
            return "hyphen_space"
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
        if kind == "reference":
            return "reference"
        if unit and unit["type"] in ("heading", "paragraph", "list", "list_item"):
            return "role"
        return "plain"

    @staticmethod
    def unit_summary(unit: dict, full: bool = False) -> dict:
        """The unit as the review shows it; ``full``: its whole text too (a form that corrects the
        text must start from all of it)."""
        content = unit.get("content") or {}
        out = {
            "id": unit["id"],
            "type": unit["type"],
            "role": unit.get("role"),
            "level": unit.get("level"),
            **({"full_text": content.get("text") or ""} if full else {}),
            "text": (content.get("text") or "")[:600],
            "clean": Service.clean_text((content.get("text") or "")[:600], content),  # the book's reading of it
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
        return {
            "page": number,
            "label": page.get("label"),
            "width": page["width"],
            "height": page["height"],
            "zone": page.get("zone"),
            "units": self.page_rows(eff, number),
            "marks": {},
            "pages": len(eff["pages"]),
            "failed_edits": failed,
        }

    # ---- lines of the PDF text that the book keeps out of its text (Browse: "Restore as…")

    FURNITURE_NAMES = {"running_head": "Running head", "running_foot": "Running foot",
                       "folio": "Page number", "production_mark": "Printer's mark"}  # fmt: skip

    def restorable_lines(self, job_id: str, number: int) -> dict:
        """The PDF text lines of one page that the book holds as page furniture. A *candidate*
        is a running head that the page before does not carry too: books print no running
        head on the page where a chapter or part opens, so such a line is a title the
        converter read as a running head. The others are listed as left out (a running head
        that repeats, a page number, a printer's mark), and only a running head or foot can
        be restored anyway. Every line is the PDF's own text (never typed)."""
        eff, _, _ = self.effective_book(job_id)
        if not 1 <= number <= len(eff["pages"]):
            raise JobError(404, "No such page.", "no_page")
        furniture = eff.get("furniture") or []
        norm = lambda f: " ".join(((f.get("content") or {}).get("text") or "").split())  # noqa: E731
        candidates = {f["id"] for f in edit_ops.lines_not_in_book(eff, number)}
        lines = []
        for f in furniture:
            if f["page"] != number or not norm(f):
                continue
            kind = f["kind"]
            gone = edit_ops.removed_info(f)
            if gone:
                status, why = "removed", f"Removed from the book by {gone['who'] or 'a reviewer'}."
            elif f["id"] in candidates:
                status, why = "candidate", "No running head with this text on the page before."
            elif kind == "running_head":
                status, why = "left_out", "A running head: the page before has the same one."
            elif kind == "running_foot":
                status, why = "left_out", "A running foot."
            else:
                status, why = "left_out", f"{self.FURNITURE_NAMES.get(kind, kind)}: not book text."
            place = None
            if kind in edit_ops.RESTORABLE:
                found = edit_ops.restore_place(eff, f)
                if found:
                    siblings, at = found
                    def label(u):  # a neighbour on this page: its text, or what it is
                        if not u or number not in (u.get("pages") or []):
                            return None
                        text = self.clean_text(((u.get("content") or {}).get("text") or ""))[:70]
                        return text or f"the {u['type'].replace('_', ' ')}"
                    nxt = next((u for u in siblings[at:] if u["type"] != "page_marker"), None)
                    prev = next((u for u in reversed(siblings[:at]) if u["type"] != "page_marker"), None)
                    place = {"before": label(nxt), "after": label(prev)}
            lines.append({
                "id": f["id"], "text": self.clean_text((f.get("content") or {}).get("text") or ""),
                "kind": kind,
                "kind_name": "Removed block" if gone else self.FURNITURE_NAMES.get(kind, kind),
                "status": status, "why": why, "box": (f.get("boxes") or [None])[0],
                "can_restore": kind in edit_ops.RESTORABLE and not gone, "place": place,
                "removed": ({"who": gone["who"], "event": gone["event"], "block": gone["block"]}
                            if gone else None),
                "level_default": overlay._chapter_level(eff) + 1,
            })  # fmt: skip
        return {"page": number, "lines": lines, "missing": len(candidates)}

    CONTAINERS = ("list", "list_item", "box", "question_set", "question_entry", "question",
                  "answer")  # fmt: skip

    @classmethod
    def page_rows(cls, book: dict, number: int) -> list[dict]:
        """The browse rows of one page: every unit on it, nested units after their holder."""
        units = []

        def visit(us, depth, parent):
            for i, u in enumerate(us):
                if u["type"] == "page_marker":
                    continue
                if number in (u.get("pages") or []):
                    units.append(cls.browse_row(u, depth, parent, us, i))
                for key in ("items", "children"):
                    if u.get(key) and u["type"] in cls.CONTAINERS:
                        visit(u[key], depth + 1, u["id"])

        visit(book["content"], 0, None)
        return units

    def preview_edit(self, job_id: str, edit: dict) -> dict:
        """What one change would do, without saving it: the rows of the changed pages before
        and after, the headings that change level, and the chapters and parts after it."""
        before, _, _ = self.effective_book(job_id)
        job = self.store.get(job_id)
        marks = self.profiles.list_marks(job["profile"]) if job.get("profile") else {}
        after, _, bad = overlay.apply_edits(before, [{**edit, "id": "preview"}], marks)
        if bad:
            raise JobError(422, bad[0]["reason"], "edit_failed")
        return {
            "pages": self.changed_pages(before, after, edit),
            "headings": overlay.heading_changes(before, after),
            "chapters": overlay.chapter_rows(after),
        }

    NOT_REPEATED = ("caption", "table_text", "char", "alt_text", "heading_text", "heading_number",
                    "split", "decorative", "restore_line", "remove_char", "remove_block", "add_block", "edit_text")  # changes tied to one block's own text or target

    def similar(self, job_id: str, event_id: str) -> dict:
        """Blocks printed like the first block of a saved change and of the same element it
        was before the change (other changes applied), each with the change it would get."""
        from . import similar

        edits = self.decisions(job_id).edits()
        source = next((e for e in edits if e["id"] == event_id), None)
        if source is None:
            raise JobError(404, "No such change.", "not_found")
        if source["op"] in self.NOT_REPEATED:
            return {"anchor": None, "style": None, "matches": [], "repeatable": False}
        job = self.store.get(job_id)
        marks = self.profiles.list_marks(job["profile"]) if job.get("profile") else {}
        before, _, _ = overlay.apply_edits(
            self.base_book(job_id), [e for e in edits if e["id"] != event_id], marks
        )
        publication = self.store.publication(job_id)
        lines = similar.style_index(publication, self.store.folder(job_id))
        return {**similar.matches(before, source, lines), "repeatable": True}

    def apply_group(self, job_id: str, who: str, event_id: str, edits: list[dict]) -> dict:
        """The same change on the chosen similar blocks: each a change of its own in the audit
        log, all in one group with the first change (one Undo takes back the group). A block
        the change cannot be applied to is left as it was and listed with the reason."""
        import secrets

        if not edits:
            raise JobError(422, "Choose at least one block.", "no_items")
        log = self.decisions(job_id)
        if not any(e["id"] == event_id for e in log.edits()):
            raise JobError(404, "No such change.", "not_found")
        before, _, _ = self.effective_book(job_id)
        group = "g" + secrets.token_hex(5)
        events = [log.edit(who, {**e, "group": group, "group_anchor": event_id}) for e in edits]
        self.forget(job_id)
        after, _, failed = self.effective_book(job_id, wait=True)
        bad = {f["edit"]: f["reason"] for f in failed}
        refused = []
        for event in events:
            if event["id"] in bad:
                log.revoke(who or "system", event["id"])
                refused.append({"unit": (event.get("units") or [event.get("unit")])[0],
                                "reason": bad[event["id"]]})  # fmt: skip
        if refused:
            self.forget(job_id)
            after, _, _ = self.effective_book(job_id, wait=True)
        union = {"units": [u for e in events if e["id"] not in bad
                           for u in (e.get("units") or [e.get("unit")])]}  # fmt: skip
        return {"group": group, "applied": len(events) - len(refused), "refused": refused,
                "pages": self.changed_pages(before, after, union),
                "chapters": overlay.chapter_rows(after)}  # fmt: skip

    def undo_group(self, job_id: str, who: str, group: str) -> dict:
        """Take back a group: its first change and every change made from it."""
        log = self.decisions(job_id)
        members = [e for e in log.edits() if e.get("group") == group]
        if not members:
            raise JobError(404, "No such group of changes.", "not_found")
        anchor = members[0].get("group_anchor")
        members += [e for e in log.edits() if e["id"] == anchor]
        before, _, _ = self.effective_book(job_id)
        for event in members:
            log.revoke(who, event["id"])
        self.forget(job_id)
        after, _, _ = self.effective_book(job_id, wait=True)
        union = {"units": [u for e in members for u in (e.get("units") or [e.get("unit")])
                           if u]}  # fmt: skip
        return {"undone": len(members), "pages": self.changed_pages(before, after, union),
                "chapters": overlay.chapter_rows(after)}  # fmt: skip

    def changed_pages(self, before: dict, after: dict, edit: dict) -> list[dict]:
        """Per page the change touches: the rows before and after (the browser replaces only
        the rows that differ)."""
        named = set(overlay._named(edit))
        pages = sorted({p for book in (before, after) for u, _ in overlay.walk(book["content"])
                        if u.get("id") in named for p in u.get("pages") or []})  # fmt: skip
        if edit.get("op") == "restore_line":  # the line is page furniture before the change
            pages += [f["page"] for f in before.get("furniture") or [] if f["id"] == edit["line"]]
        if edit.get("op") == "add_block" and edit.get("page"):
            pages.append(int(edit["page"]))
        pages += [h["page"] for h in overlay.heading_changes(before, after)]
        out = []
        for number in sorted(set(pages)):
            out.append({"page": number, "before": self.page_rows(before, number),
                        "after": self.page_rows(after, number)})  # fmt: skip
        return out

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
            added_by=edit_ops.added_by(u),
            flags=[f for f in u.get("flags") or [] if f in ("quote", "pull_quote",
                                                            "chapter_authors")],  # fmt: skip
            box_kind=u.get("box_kind"),
            list_type=u.get("list_type"),
            item_level=u.get("level") if u["type"] == "list_item" else None,
        )
        row["text"] = (
            text[:2000]
            if u["type"] in ("paragraph", "heading", "list_item", "caption")
            else row["text"]
        )
        row.update(Service.clean_fields(u, text))
        return row

    # ---- the one-line "clean" view of a block (display only; the book text is untouched)

    @staticmethod
    def clean_text(text: str, content: dict | None = None) -> str:
        """Wrapped lines joined into one line, as the book reads them. With the text record
        (``content``) the converter's join decisions apply, exactly as the export applies them:
        a word broken at a line end by a soft hyphen is one word again ("militar-ily" reads
        "militarily"), a real hyphen that was kept stays ("well-known"), and a line end with no
        join decision is a space. Without the record (no decisions to follow) a soft hyphen at
        a line end joins its two parts and a hyphen keeps its place; no character is invented."""
        text = (text or "").replace("\b", " ")
        if content is not None and content.get("joins") is not None:
            chars = render({**content, "text": text}, [(0, len(text))], text)
            return " ".join("".join(c for c, _ in chars).split())
        out = ""
        for line in (ln.strip() for ln in re.sub("\u00ad\\s*\n", "\u00ad\n", text).split("\n")):
            if not line:
                continue
            if out.endswith("\u00ad"):
                out = out[:-1] + line
            else:
                out = out + line if out.endswith("-") else (f"{out} {line}" if out else line)
        return " ".join(out.replace("\u00ad", "").split())

    @staticmethod
    def _cell_text(cell: dict) -> str:
        parts = cell.get("content") or []
        if isinstance(parts, dict):
            parts = [parts]
        return " ".join(filter(None, (Service.clean_text(
            (p.get("content") or {}).get("text") or "", p.get("content"))
            for p in parts if isinstance(p, dict))))

    @staticmethod
    def clean_fields(u: dict, text: str) -> dict:
        kind = u["type"]
        out: dict = {"clean": Service.clean_text(text, u.get("content"))}
        if kind == "list":
            items = []
            for item, _ in overlay.walk(u["items"]):
                if item.get("type") == "list_item":
                    items.append({"id": item["id"], "level": item.get("level") or 1,
                                  "text": Service.clean_text(
                                      (item.get("content") or {}).get("text") or "",
                                      item.get("content"))})  # fmt: skip
            out.update(items=items, item_ids=[i["id"] for i in items])
        elif kind == "table":
            cells = u.get("cells") or []
            rows: dict = {}
            for c in cells:
                rows.setdefault(c.get("row", 0), {})[c.get("column", 0)] = Service._cell_text(c)
            grid = [[r[k] for k in sorted(r)] for _, r in sorted(rows.items())]
            out.update(grid=grid[:8], rows=len(grid), cols=max((len(r) for r in grid), default=0))
        elif kind == "box":
            out["clean"] = ""
        return out

    def search(self, job_id: str, query: str, limit: int = 200) -> dict:
        """Where a text is in the book: page, block and a short piece around it."""
        needle = " ".join((query or "").lower().split())
        if len(needle) < 2:
            return {"query": query, "hits": [], "more": False}
        eff, _, _ = self.effective_book(job_id)
        hits = []
        for u, _ in overlay.walk(eff["content"]):
            if u["type"] == "page_marker" or u["type"] in self.CONTAINERS and u["type"] != "list_item":
                continue
            if u["type"] == "table":
                text = " ".join(self._cell_text(c) for c in u.get("cells") or [])
            else:
                text = self.clean_text(((u.get("content") or {}).get("text")) or "", u.get("content"))
            at = text.lower().find(needle)
            if at < 0 or not u.get("pages"):
                continue
            a = max(0, at - 40)
            hits.append({"page": u["pages"][0], "unit": u["id"], "type": u["type"],
                         "snippet": ("…" if a else "") + text[a : at + len(needle) + 60]
                         + ("…" if at + len(needle) + 60 < len(text) else "")})  # fmt: skip
            if len(hits) > limit:
                break
        return {"query": query, "hits": hits[:limit], "more": len(hits) > limit}

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
        progress=None,
    ) -> dict:
        note = progress or (lambda fmt, state: None)
        order = ("docbook", "epub", *sorted(FORMAT_SPECS))
        formats = tuple(f for f in order if f in formats)
        if not formats:
            raise JobError(400, "Choose at least one output format.", "no_format")
        profile_obj, _ = self.profiles.store.load(self.store.get(job_id)["profile"])
        if self.refs_only(job_id) and formats != ("tail",):
            raise JobError(400, "A references-only document is exported as the reference list "
                           "(tail) only.", "format_not_supported")  # fmt: skip
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
            if not read_json(self.details_path(job_id)) and not self.refs_only(job_id):
                raise JobError(409, "Confirm the book details first.", "no_details")
            parts_record = self.require_parts(job_id)
            n = job.get("exports", 0) + 1
            folder = self.store.folder(job_id) / "exports" / f"{n:03d}"
            if folder.exists():
                shutil.rmtree(folder)
            folder.mkdir(parents=True)
            eff, _, failed = self.effective_book(job_id, validate=True, wait=True)
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
                    note("docbook", "running")
                    reports["docbook"] = self._export_run(
                        job_id, n, "docbook", book_dir, folder / "out", settings_path,
                        job["profile"], allow_placeholders, {},
                    )  # fmt: skip
                    note("docbook", "done")
                if "epub" in formats:
                    note("epub", "running")
                    reports["epub"] = self._export_run(
                        job_id, n, "epub", book_dir, folder / "epub", settings_path,
                        job["profile"], allow_placeholders,
                        {"modified": modified, "epubcheck_jar": self.settings.epubcheck_jar or None},
                    )  # fmt: skip
                    note("epub", "done")
                for fmt in formats:
                    if fmt in FORMAT_SPECS:
                        note(fmt, "running")
                        source = self.store.folder(job_id) / "input.pdf"
                        reports[fmt] = self._export_run(
                            job_id, n, fmt, book_dir, folder / fmt, settings_path,
                            job["profile"], allow_placeholders,
                            {"source_pdf": str(source) if source.is_file() else None},
                        )  # fmt: skip
                        note(fmt, "done")
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

    def _export_run(self, job_id, n, kind, book_dir, out, settings_path, profile, allow, extra):
        """One format of an export, made in a worker process while this thread waits (so other
        requests are not held), and alongside the exports of other books."""
        future = self.builds.submit(
            ("export", job_id, n, kind), job_id, effective.export_task, kind, str(book_dir),
            str(out), str(settings_path), profile, str(self.profiles.store.store), allow, extra,
        )
        try:
            result = future.result()
        except Exception:
            self.builds.failure(("export", job_id, n, kind))  # taken off the list: raised here
            raise
        if "blocked" in result:
            raise ExportBlocked("alt-text placeholders remain", result["blocked"])
        return result["report"]

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
        eff, _, _ = self.effective_book(job_id, validate=True, wait=True)
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
