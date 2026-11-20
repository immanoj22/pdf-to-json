"""Profiles for the app: the adapters' own store (append-only versions) with listing, upload
validation messages for people, and the profile-maker material."""

from __future__ import annotations

import datetime as dt
import re
import tempfile
import threading
from pathlib import Path

import yaml

from book_adapters.engine.paths import profiles_root
from book_adapters.engine.profile import ProfileError
from book_adapters.engine.profile_store import ProfileStore, StoredProfile

from .jobs import JobError, safe_name

REPO_FILES = ("tools", "profile_maker", "prompt_for_ai_chat.md")


class Profiles:
    def __init__(self, data_path: Path, max_bytes: int):
        self.max_bytes = max_bytes
        self.tmp = data_path / "tmp"
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.store = ProfileStore(store=data_path / "profile_store")
        self._marks: dict = {}
        # (fingerprint, rows) of the last listing: replaced as one tuple, never changed in place
        self._rows: tuple | None = None
        self._rows_lock = threading.Lock()  # one rebuild at a time; the others reuse its result

    def fingerprint(self) -> tuple:
        """Name, size and change time of every file in the built-in and the uploaded profile
        store. A profile is read from these files (and the ones it extends), so the listing
        stays valid until one of them is added, replaced or removed."""
        files = []
        for root in (self.store.root, self.store.store):
            for f in sorted(Path(root).rglob("*")):
                if f.is_file():
                    st = f.stat()
                    files.append((str(f), st.st_mtime_ns, st.st_size))
        return tuple(files)

    def entry(self, p: StoredProfile) -> dict:
        head = yaml.safe_load(Path(p.file).read_text("utf-8")) or {}
        added = None
        if p.origin == "uploaded":
            added = (
                dt.datetime.fromtimestamp(Path(p.file).stat().st_mtime, dt.UTC).date().isoformat()
            )
        try:
            from book_adapters.engine.formats_run import supported_formats

            formats = supported_formats(self.store.load(p.ref)[0])
        except ProfileError:  # an unreadable profile is listed without formats
            formats = ["docbook"]
        return {
            "ref": p.ref,
            "formats": formats,
            "standard": p.profile.endswith("_base"),
            "name": p.profile,
            "version": p.version,
            "revision": p.revision,
            "origin": p.origin,
            # Built-in profiles were run against finished deliveries; uploads have not been.
            "status": "tested" if p.status == "builtin" else p.status,
            "date": str(head.get("date") or "") or None,
            "added": added,
            "description": head.get("description") or head.get("guideline"),
            "client": head.get("client"),
            "sha256": p.sha256,
        }

    def list(self) -> list[dict]:
        """The profile rows. Every profile is read in full to find its formats (seconds in all),
        so the rows are kept until a profile file changes (see ``fingerprint``)."""
        key = self.fingerprint()
        kept = self._rows  # one read: key and rows always belong together
        if kept is None or kept[0] != key:
            with self._rows_lock:
                kept = self._rows
                if kept is None or kept[0] != key:
                    rows = [self.entry(p) for p in self.store.list()]
                    rows.sort(key=lambda r: (r["name"], r["version"], r["revision"]))
                    kept = self._rows = (key, rows)  # one assignment swaps the whole listing
        return [dict(r) for r in kept[1]]

    def resolve(self, ref: str) -> StoredProfile:
        try:
            return self.store.find(ref)
        except ProfileError as exc:
            raise JobError(404, "That profile does not exist.", "no_profile") from exc

    def book_options(self, ref: str) -> dict:
        stored = self.resolve(ref)
        profile, _ = self.store.load(stored.ref if stored.origin == "uploaded" else ref)
        return profile.get("book_options") or {}

    def list_marks(self, ref: str) -> dict:
        stored = self.resolve(ref)
        # kept until a profile file changes (the profile and the ones it extends)
        files = sorted(self.store.root.rglob("*.yaml")) + [stored.file]
        key = (stored.ref, tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in files))
        if key not in self._marks:
            profile, _ = self.store.load(stored.ref)
            self._marks[key] = profile.get("lists.marks") or {}
        return self._marks[key]

    # ------------------------------------------------------------------ upload

    def _check_text(self, raw: bytes) -> str:
        if len(raw) > self.max_bytes:
            raise JobError(413, "That profile file is too large.", "too_large")
        if not raw.strip():
            raise JobError(400, "The profile file is empty.", "empty")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise JobError(400, "A profile is a text file (UTF-8 YAML).", "not_text") from exc

    def validate(self, raw: bytes, filename: str = "profile.yaml") -> dict:
        text = self._check_text(raw)
        name = safe_name(filename)
        if not re.search(r"\.ya?ml$", name, re.I):
            name += ".yaml"
        with tempfile.TemporaryDirectory(dir=self.tmp) as folder:
            path = Path(folder) / name
            path.write_text(text, "utf-8")
            try:
                profile = self.store.validate(path)
            except ProfileError as exc:
                return {
                    "ok": False,
                    "errors": [
                        {
                            "file": p.file,
                            "line": p.line,
                            "field": p.path,
                            "message": p.message,
                            "suggestion": p.suggestion,
                        }
                        for p in exc.problems
                    ],
                }
            except yaml.YAMLError as exc:  # pragma: no cover - mapped by the adapter normally
                return {"ok": False, "errors": [{"line": None, "field": "", "message": str(exc)}]}
        return {"ok": True, "name": profile.name, "version": profile.version, "date": profile.date}

    def add(self, raw: bytes, filename: str = "profile.yaml") -> dict:
        result = self.validate(raw, filename)
        if not result["ok"]:
            return result
        name = safe_name(filename)
        if not re.search(r"\.ya?ml$", name, re.I):
            name += ".yaml"
        with tempfile.TemporaryDirectory(dir=self.tmp) as folder:
            path = Path(folder) / name
            path.write_bytes(raw)
            before = {p.ref for p in self.store.list()}
            stored = self.store.add(path)
        entry = self.entry(stored)
        entry["new"] = stored.ref not in before
        return {"ok": True, "profile": entry}

    # ------------------------------------------------------------------ profile maker

    @staticmethod
    def repo_root() -> Path:
        return profiles_root().parent

    def maker_prompt(self) -> str:
        path = self.repo_root().joinpath(*REPO_FILES)
        if not path.is_file():
            raise JobError(404, "The profile-maker prompt is missing from this installation.")
        return path.read_text("utf-8")

    def schema_path(self) -> Path:
        return profiles_root() / "schema" / "profile.schema.json"

    BASES = (
        "docbook_base",
        "html_base",
        "dtbook_nimas_base",
        "daisy3_base",
        "jats_base",
        "bits_base",
        "tail_base",
    )

    def base_path(self, name: str = "docbook_base") -> Path:
        if name not in self.BASES:
            raise JobError(404, "No such base profile.", "no_profile")
        return profiles_root() / "_base" / f"{name}.yaml"
