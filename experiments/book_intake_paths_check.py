"""Book intake: prove that moving real paths to references.local.toml changes no resolution.

Snapshot mode records, for every configured key, the SHA-256 of the resolved absolute path
string, the file size and the file SHA-256 (never the name), and a digest of the cache file
listing. Compare mode checks two snapshots key by key.

Usage:
  python book_intake_paths_check.py snapshot <out.json> [--keys-from <toml>]
  python book_intake_paths_check.py compare <before.json> <after.json>
"""

import hashlib
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402

CACHE = ROOT / ".cache"
CACHE_SKIP = {"pip", "pytest", "pytest-cache-keys", "huggingface"}


def file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 22):
            digest.update(chunk)
    return digest.hexdigest()


def cache_listing() -> list[str]:
    entries = []
    for child in sorted(CACHE.iterdir()):
        if child.name in CACHE_SKIP:
            continue
        files = [child] if child.is_file() else sorted(p for p in child.rglob("*") if p.is_file())
        entries += [f"{p.relative_to(CACHE).as_posix()}\t{p.stat().st_size}" for p in files]
    return entries


def snapshot(keys) -> dict:
    paths = {}
    for key in sorted(keys):
        resolved = reference_path(key).resolve()
        paths[key] = {
            "path_sha256": hashlib.sha256(str(resolved).encode("utf-8")).hexdigest(),
            "exists": resolved.exists(),
            "is_dir": resolved.is_dir(),
            "size": resolved.stat().st_size if resolved.is_file() else None,
            "file_sha256": file_digest(resolved),
        }
    listing = cache_listing()
    return {
        "paths": paths,
        "cache_entries": len(listing),
        "cache_listing_sha256": hashlib.sha256("\n".join(listing).encode("utf-8")).hexdigest(),
    }


def main():
    mode, *rest = sys.argv[1:]
    if mode == "snapshot":
        out = Path(rest[0])
        source = Path(rest[rest.index("--keys-from") + 1]) if "--keys-from" in rest else None
        source = source or ROOT / "experiments/references.toml"
        keys = tomllib.loads(source.read_text("utf-8"))["paths"]
        out.write_text(json.dumps(snapshot(keys), indent=1) + "\n", "utf-8")
    elif mode == "compare":
        before, after = (json.loads(Path(p).read_text("utf-8")) for p in rest[:2])
        same = before == after
        diff = sorted(k for k in before["paths"] if before["paths"][k] != after["paths"].get(k))
        print(json.dumps({"identical": same, "keys": len(before["paths"]), "changed": diff}))
        raise SystemExit(0 if same else 1)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
