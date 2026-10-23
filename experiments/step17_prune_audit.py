"""Audit the owner's frozen cleanup list without discovering new deletion candidates."""

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
from book_core.cache_store import read_json

PLAN = ROOT / "experiments/out/step17/cache_prune_dry_run.json"
EXPECTED = "f7956e2fead2ff25601019908304b3d6de0ecf29811e358bc05870c15d21d793"
OUT = PLAN.with_name("cache_prune_audit.json")
BOOKS = ("spanish_us_history", "immigrant_children", "art_therapy_index",
         "medical_anatomy", "statistics")
HEX = re.compile(rb"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
SOURCE = re.compile(r'"source_sha256"\s*:\s*"([0-9a-f]{64})"')


def main():
    encoded = PLAN.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != EXPECTED:
        raise ValueError("STOP: the approved dry-run file changed")
    plan = json.loads(encoded)
    assert len(plan["candidates"]) == 614 and plan["reclaim_bytes"] == 5886003040
    allowed = set()
    for name in BOOKS:
        p = ROOT / f"experiments/out/step16/final/performance/{name}.json"
        run = json.loads(p.read_text("utf-8"))["run"]
        allowed.add(read_json(Path(run["output"]) / "manifest.json.gz")["source_sha256"])
    # These repository fixtures predate the sealed hold-outs. Hashing them does not run
    # the converter or touch their gold/ledger; their caches are reproducible test data.
    for folder in ("experiments/fixtures", "experiments/fixtures_unseen"):
        for path in (ROOT / folder).glob("*.pdf"):
            allowed.add(hashlib.sha256(path.read_bytes()).hexdigest())
    protected = set()
    baseline_records = []
    for step in ("step15", "step16", "step17"):
        for path in (ROOT / f"experiments/out/{step}").rglob("*.json"):
            if "performance" in path.parts:
                protected.update(x.decode() for x in HEX.findall(path.read_bytes()))
                baseline_records.append(path.relative_to(ROOT).as_posix())
    index = read_json(ROOT / ".cache/.cache-index.json")
    current_paths = set()
    for eid in index["current"].values():
        entry = index["entries"][eid]
        protected.add(entry["key"])
        current_paths.update((ROOT / ".cache" / p).resolve() for p in entry["files"])
    approved, excluded = [], []
    for row in plan["candidates"]:
        folder = (ROOT / row["path"]).resolve()
        folder.relative_to((ROOT / ".cache").resolve())
        reasons = []
        if folder.name in protected:
            reasons.append("baseline, parity input or current registry key")
        sources = set()
        for item in row["files"]:
            path = (ROOT / item["path"]).resolve()
            path.relative_to(folder)
            if path.is_symlink() or folder.is_symlink():
                raise ValueError(f"STOP: symlink in approved list: {path}")
            stat = path.stat()
            if (stat.st_size, stat.st_mtime_ns) != (item["bytes"], item["mtime_ns"]):
                raise ValueError(f"STOP: listed file changed since the dry run: {path}")
            if path in current_paths:
                reasons.append("current registry file")
            if item["path"].endswith("manifest.json.gz"):
                sources.add(read_json(path)["source_sha256"])
            elif row["path"].startswith(".cache/objects/"):
                entry = read_json(path)
                sources.update(SOURCE.findall(entry.get("payload", json.dumps(entry))))
        if not sources or not sources <= allowed:
            reasons.append("source not proven to be an approved book or existing training fixture")
        result = {**row, "sources": sorted(sources)}
        (excluded if reasons else approved).append({**result, "exclusion_reasons": reasons})
    result = {"plan_sha256": EXPECTED, "baseline_records_checked": baseline_records,
              "current_registry_files_checked": len(current_paths),
              "approved": approved, "excluded": excluded,
              "approved_bytes": sum(r["bytes"] for r in approved),
              "excluded_bytes": sum(r["bytes"] for r in excluded), "deleted": False}
    OUT.write_text(json.dumps(result, indent=1) + "\n", "utf-8", newline="\n")
    print({"approved_folders": len(approved), "approved_bytes": result["approved_bytes"],
           "excluded_folders": len(excluded), "excluded_bytes": result["excluded_bytes"],
           "reasons": dict(Counter(why for r in excluded for why in r["exclusion_reasons"]))})


if __name__ == "__main__":
    main()
