"""Recreate/verify this project's pre-change producer snapshot from committed sources.

This never reads or writes an old project's code or environment. Telemetry is an
unreferenced measurement helper under the old producer scopes.
"""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = "6ccc541"
PREFIX = "backend/src/book_core/"


def git(*arguments):
    return subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, check=True).stdout


def main():
    target = ROOT / ".cache/step11c/baseline_src/book_core"
    paths = git("ls-tree", "-r", "--name-only", REVISION, PREFIX).decode().splitlines()
    proof = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        data = git("show", f"{REVISION}:{path}")
        relative = path.removeprefix(PREFIX)
        destination = target / relative
        if destination.exists():
            if destination.read_bytes().replace(b"\r\n", b"\n") != data.replace(b"\r\n", b"\n"):
                raise ValueError(f"Preserved producer differs from {REVISION}: {relative}")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        proof[relative] = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
    helper = target / "telemetry.py"
    if not helper.exists():
        helper.write_bytes((ROOT / PREFIX / "telemetry.py").read_bytes())
    output = ROOT / "experiments/out/step11c/before/snapshot.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"revision": REVISION, "files": proof}, indent=2) + "\n", "utf8")
    print("Verified preserved producer files:", len(proof))


if __name__ == "__main__":
    main()
