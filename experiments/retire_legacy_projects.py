"""Remove the two entire legacy roots explicitly retired by the owner."""

import gzip
import hashlib
import json
import os
import shutil
import stat
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/cache_audit_20261024"
TARGETS = (Path("C:/coeik/projects/pdf to xml converter"), Path("C:/coeik/projects/nimas"))
INVENTORY_SHA = "b896e636bea18b495fa6846d3af35431bc6ec50d95a34d6b4f82b804c087a54f"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    require(sys.argv[1:] == ["--apply-owner-retirement"], "Explicit apply argument required")
    record_path = OUT / "legacy_projects_deletion_record.json"
    require(not record_path.exists(), "Record exists; do not repeat")
    inventory_path = OUT / "legacy_projects_retirement_inventory.json.gz"
    require(sha(inventory_path) == INVENTORY_SHA, "Inventory changed")
    inventory = json.loads(gzip.decompress(inventory_path.read_bytes()))
    require(inventory["roots"] == [str(p) for p in TARGETS], "Wrong roots")
    for target in TARGETS:
        require(target.resolve(strict=True) == target and target.parent == Path("C:/coeik/projects"), "Wrong resolved target")
        require(target != ROOT and not ROOT.is_relative_to(target) and not target.is_relative_to(ROOT), "Active project overlap")
        for ancestor in (target, *target.parents):
            require(not ancestor.is_symlink() and not ancestor.is_junction(), "Linked root ancestor")
    relocation = json.loads((OUT / "retained_spanish_cache_relocation.json").read_text("utf-8"))
    kept = Path(relocation["destination"])
    require(kept.is_relative_to(ROOT), "Preserved cache outside active project")
    for p, size, digest in relocation["files"]:
        require((kept / p).stat().st_size == size and sha(kept / p) == digest, "Retained cache changed")
    require(sha(ROOT / "experiments/references.local.toml") == relocation["config_after_sha256"], "Local reference configuration changed")
    for idx, relative in inventory["directories"]:
        p = TARGETS[idx] / relative
        require(not PurePosixPath(relative).is_absolute() and ".." not in PurePosixPath(relative).parts,
                "Unsafe directory path")
        require(p.absolute().is_relative_to(TARGETS[idx]), "Directory escapes named root")
        require(not p.stat(follow_symlinks=False).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "Directory became linked")
    record = {"authorization": "Owner explicitly selected entire old project folders and references for deletion, retaining caches used by the current project.",
              "started": datetime.now(timezone.utc).isoformat(), "roots": [str(p) for p in TARGETS],
              "inventory_sha256": INVENTORY_SHA, "cache_preserved": relocation["destination"],
              "cache_preserved_bytes": relocation["bytes"], "unreadable_inventory_paths": inventory["errors"],
              "deleted_files": 0, "deleted_bytes": 0, "deleted_directories": 0, "removed_junctions": [],
              "file_errors": [], "directory_errors": [], "free_bytes_before": shutil.disk_usage(ROOT).free}
    started = time.monotonic()
    counts, sizes = Counter(), Counter()

    def unlink(row):
        idx, relative, size, mtime, _ = row
        require(not PurePosixPath(relative).is_absolute() and ".." not in PurePosixPath(relative).parts, "Unsafe inventory path")
        p = TARGETS[idx] / relative
        try:
            current = p.stat(follow_symlinks=False)
            require(stat.S_ISREG(current.st_mode) and not current.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT, "Not a plain file")
            require((current.st_size, current.st_mtime_ns) == (size, mtime), "Legacy file changed: " + str(p))
            try:
                p.unlink()
            except PermissionError:
                if not current.st_file_attributes & stat.FILE_ATTRIBUTE_READONLY or current.st_nlink != 1:
                    raise
                os.chmod(p, current.st_mode | stat.S_IWRITE)
                p.unlink()
            return idx, size, None
        except OSError as error:
            return idx, 0, [str(p), str(error)]

    try:
        with ThreadPoolExecutor(max_workers=8) as workers:
            for count, (idx, size, error) in enumerate(workers.map(unlink, inventory["files"], buffersize=32), 1):
                if error:
                    record["file_errors"].append(error)
                else:
                    counts[idx] += 1
                    sizes[idx] += size
                    record["deleted_files"] += 1
                    record["deleted_bytes"] += size
                if count % 10000 == 0:
                    print("processed", count, "deleted", record["deleted_files"], "GB", round(record["deleted_bytes"] / 1e9, 3), flush=True)
                    record_path.write_text(json.dumps(record, indent=1), "utf-8")
        for idx, relative, is_directory in inventory["links"]:
            p = TARGETS[idx] / relative
            target = os.readlink(p)
            if is_directory:
                os.rmdir(p)  # Remove the junction itself, never recurse into its target.
            else:
                p.unlink()
            record["removed_junctions"].append({"path": str(p), "target_not_followed": target})
        for idx, relative in sorted(inventory["directories"], key=lambda row: len(PurePosixPath(row[1]).parts), reverse=True):
            p = TARGETS[idx] / relative
            try:
                p.rmdir()  # Empty directory only; inaccessible contents are never traversed.
                record["deleted_directories"] += 1
            except OSError as error:
                record["directory_errors"].append([str(p), str(error)])
        record["status"] = "complete" if not any(p.exists() for p in TARGETS) else "partial_windows_access_denied"
    except BaseException as error:
        record["status"] = "stopped"
        record["error"] = str(error)
        raise
    finally:
        record["by_root"] = [{"root": str(p), "deleted_files": counts[idx], "deleted_bytes": sizes[idx]} for idx, p in enumerate(TARGETS)]
        record["seconds"] = time.monotonic() - started
        record["finished"] = datetime.now(timezone.utc).isoformat()
        record["free_bytes_after"] = shutil.disk_usage(ROOT).free
        record_path.write_text(json.dumps(record, indent=1), "utf-8")
        print(json.dumps({k: v for k, v in record.items() if k not in {"unreadable_inventory_paths", "file_errors", "directory_errors"}}), flush=True)


if __name__ == "__main__":
    main()
