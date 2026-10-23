"""List unreferenced final archives and extraction caches; never delete anything.

Keep every directory whose key appears in a tracked evidence/source file or in a
Step 17 measurement, and every published book folder. Inspect only the project's
two final-archive roots and the early object-extraction cache roots. Protect all
current registry entries as well. Models, references and gold are excluded.
The owner must approve the saved, exact file list before a separate removal.
"""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step17/cache_prune_dry_run.json"
HEX = re.compile(rb"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
TEXT = {".json", ".md", ".py", ".toml", ".txt", ".log", ".sh"}
ARCHIVES = (".cache/step11d2/final_books", ".cache/step13/final_books")
OBJECTS = (".cache/objects/analysis", ".cache/objects/native")


def main():
    tracked = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
        .decode("utf-8")
        .split("\0")
    )
    evidence = {ROOT / p for p in tracked if p and Path(p).suffix in TEXT}
    evidence.update(
        p
        for p in (ROOT / "experiments/out/step17").rglob("*")
        if p.is_file() and p.suffix in TEXT and p != OUT
    )
    keys = set()
    for path in sorted(evidence):
        keys.update(m.decode("ascii") for m in HEX.findall(path.read_bytes()))
    import sys

    sys.path.insert(0, str(ROOT / "backend/src"))
    from book_core.cache_store import read_json

    index = read_json(ROOT / ".cache/.cache-index.json")
    for entry_id in index["current"].values():
        keys.add(index["entries"][entry_id]["key"])
    candidates, kept = [], []
    folders = []
    for name in ARCHIVES:
        for manifest in sorted((ROOT / name).rglob("manifest.json.gz")):
            folders.append((name, manifest.parent))
    for name in OBJECTS:
        folders.extend((name, p) for p in sorted((ROOT / name).iterdir()) if p.is_dir())
    for name, folder in folders:
        folder = folder.resolve()
        folder.relative_to((ROOT / name).resolve())
        if folder.name in keys:
            kept.append(folder.relative_to(ROOT).as_posix())
            continue
        files = []
        for path in sorted(folder.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Refusing a symlink in {folder}")
            if path.is_file():
                stat = path.stat()
                files.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "bytes": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                    }
                )
        candidates.append(
            {
                "path": folder.relative_to(ROOT).as_posix(),
                "bytes": sum(p["bytes"] for p in files),
                "files": files,
            }
        )
    data = {
        "rule": __doc__,
        "free_bytes": shutil.disk_usage(ROOT).free,
        "protected_keys": len(keys),
        "protected_archives": kept,
        "candidates": candidates,
        "reclaim_bytes": sum(p["bytes"] for p in candidates),
        "deleted": False,
    }
    encoded = json.dumps(data, indent=1) + "\n"
    OUT.write_text(encoded, "utf-8", newline="\n")
    print(
        json.dumps(
            {
                "plan": str(OUT),
                "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
                "archives": len(candidates),
                "bytes": data["reclaim_bytes"],
                "free_bytes": data["free_bytes"],
                "deleted": False,
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
