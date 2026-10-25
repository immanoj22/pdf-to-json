"""Compare protected paths to the pre-run metadata inventory; never write to them."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def inventory(folder, relative, result, unreadable):
    try:
        entries = os.scandir(folder)
    except PermissionError:
        unreadable.append(relative)
        return
    with entries:
        for entry in entries:
            key = relative + "/" + entry.name
            if entry.is_dir(follow_symlinks=False):
                inventory(entry.path, key, result, unreadable)
            elif entry.is_file(follow_symlinks=True):
                stat = entry.stat()
                result[key] = [stat.st_size, stat.st_mtime_ns]


def main():
    before = json.loads((ROOT / "protected_before.json").read_text("utf-8"))
    after, unreadable = {}, []
    for name in ("backend", "docs", "experiments", ".cache"):
        inventory(REPO / name, name, after, unreadable)
    stat = (REPO / "AGENTS.md").stat()
    after["AGENTS.md"] = [stat.st_size, stat.st_mtime_ns]
    report = {
        "files_before": len(before), "files_after": len(after),
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": sorted(key for key in before.keys() & after.keys() if before[key] != after[key]),
        "comparison": "file size and nanosecond modification time",
        "unreadable_directories": unreadable,
    }
    (ROOT / "protected_check_results.json").write_text(json.dumps(report, indent=2) + "\n", "utf-8")
    print(json.dumps(report, indent=2), flush=True)
    if report["added"] or report["removed"] or report["changed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
