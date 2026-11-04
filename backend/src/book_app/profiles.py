"""Profiles for the app: the adapters' own store (append-only versions) with listing, upload
validation messages for people, and the profile-maker material."""

from __future__ import annotations

import datetime as dt
import re
import tempfile
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

    def entry(self, p: StoredProfile) -> dict:
        head = yaml.safe_load(Path(p.file).read_text("utf-8")) or {}
        added = None
        if p.origin == "uploaded":
            added = (
                dt.datetime.fromtimestamp(Path(p.file).stat().st_mtime, dt.UTC).date().isoformat()
            )
        return {
            "ref": p.ref,
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
        rows = [self.entry(p) for p in self.store.list()]
        return sorted(rows, key=lambda r: (r["name"], r["version"], r["revision"]), reverse=False)

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
        profile, _ = self.store.load(stored.ref)
        return profile.get("lists.marks") or {}

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

    def base_path(self) -> Path:
        return profiles_root() / "_base" / "docbook_base.yaml"
