"""The profile store: built-in profiles (read-only, in the repository) and profiles any user
uploads. An upload is validated at once, kept as a new immutable version (a file is never
overwritten) and marked ``untested`` until it has been run against example deliveries."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from .paths import profiles_root, store_root
from .profile import Problem, Profile, ProfileError, load_profile

SKIP_DIRS = {"schema", "examples", "_store", "_test"}


@dataclass(frozen=True)
class StoredProfile:
    profile: str
    version: str
    sha256: str
    file: Path
    origin: str  # builtin | uploaded
    status: str  # builtin | untested | tested
    revision: int = 0

    @property
    def ref(self) -> str:
        suffix = f"#r{self.revision}" if self.origin == "uploaded" else ""
        return f"{self.profile}@{self.version}{suffix}"

    def as_dict(self) -> dict:
        return {
            "ref": self.ref,
            "profile": self.profile,
            "version": self.version,
            "sha256": self.sha256,
            "file": str(self.file),
            "origin": self.origin,
            "status": self.status,
        }


class ProfileStore:
    def __init__(self, root: Path | None = None, store: Path | None = None):
        self.root = Path(root) if root else profiles_root()
        self.store = Path(store) if store else store_root()

    # ------------------------------------------------------------------ listing

    def builtin(self) -> list[StoredProfile]:
        out = []
        for path in sorted(self.root.rglob("*.yaml")):
            rel = path.relative_to(self.root)
            if set(rel.parts[:-1]) & SKIP_DIRS:
                continue
            try:
                head, digest = _head(path)
            except yaml.YAMLError:
                continue
            if not isinstance(head, dict) or "profile" not in head:
                continue
            out.append(
                StoredProfile(
                    str(head["profile"]),
                    str(head.get("version")),
                    digest,
                    path,
                    "builtin",
                    "builtin",
                )
            )
        return out

    def uploaded(self) -> list[StoredProfile]:
        index = self.store / "index.jsonl"
        if not index.exists():
            return []
        out = []
        for line in index.read_text("utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                out.append(
                    StoredProfile(
                        row["profile"],
                        row["version"],
                        row["sha256"],
                        self.store / row["file"],
                        "uploaded",
                        row["status"],
                        row["revision"],
                    )
                )
        return out

    def list(self) -> list[StoredProfile]:
        return self.builtin() + self.uploaded()

    # ------------------------------------------------------------------ add / find

    def roots(self) -> list[Path]:
        return [self.root, self.store]

    def validate(self, path: Path) -> Profile:
        return load_profile(path, self.roots())

    def add(self, path: Path) -> StoredProfile:
        """Validate and store an uploaded profile as a new version. Identical bytes already
        stored are returned as they are; nothing existing is ever overwritten."""
        path = Path(path)
        profile = self.validate(path)
        digest = _sha(path)
        for existing in self.list():
            if existing.sha256 == digest:
                return existing
        revision = 1 + sum(
            1 for p in self.uploaded() if p.profile == profile.name and p.version == profile.version
        )
        rel = Path(profile.name) / profile.version / f"r{revision}_{digest[:12]}.yaml"
        target = self.store / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "xb") as out:  # never overwrite
            with open(path, "rb") as src:
                shutil.copyfileobj(src, out)
        row = {
            "profile": profile.name,
            "version": profile.version,
            "sha256": digest,
            "file": rel.as_posix(),
            "status": "untested",
            "revision": revision,
            "source_name": path.name,
        }
        with open(self.store / "index.jsonl", "a", encoding="utf-8") as index:
            index.write(json.dumps(row, sort_keys=True) + "\n")
        return StoredProfile(
            profile.name, profile.version, digest, target, "uploaded", "untested", revision
        )

    def find(self, ref: str) -> StoredProfile:
        """``name``, ``name@version`` or ``name@version#rN``; the newest match wins
        (built-in before uploads of the same version)."""
        name, _, rest = ref.partition("@")
        version, _, rev = rest.partition("#r")
        matches = [
            p
            for p in self.list()
            if p.profile == name
            and (not version or p.version == version)
            and (not rev or p.revision == int(rev))
        ]
        if not matches:
            known = sorted({p.ref for p in self.list()})
            raise ProfileError(
                [Problem(ref, None, "profile", f"no profile {ref!r}; known: {', '.join(known)}")]
            )
        matches.sort(key=lambda p: (_version_key(p.version), p.origin == "builtin", p.revision))
        builtin = [p for p in matches if p.origin == "builtin" and p.version == matches[-1].version]
        return builtin[-1] if builtin and not rev else matches[-1]

    def load(self, ref_or_path: str) -> tuple[Profile, StoredProfile]:
        candidate = Path(ref_or_path)
        if candidate.suffix in {".yaml", ".yml"} and candidate.is_file():
            stored = self.add(candidate)
        else:
            stored = self.find(ref_or_path)
        return load_profile(stored.file, self.roots()), stored


_HEADS: dict = {}


def _head(path: Path) -> tuple:
    """A profile file's parsed content and checksum, kept until the file changes (parsing
    every profile on every request was most of the review list's time)."""
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    hit = _HEADS.get(key)
    if hit is None:
        raw = path.read_bytes()
        hit = (yaml.safe_load(raw.decode("utf-8")) or {}, hashlib.sha256(raw).hexdigest())
        _HEADS[key] = hit
    return hit


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _version_key(version: str) -> tuple:
    try:
        return tuple(int(x) for x in version.split("."))
    except ValueError:
        return (0,)
