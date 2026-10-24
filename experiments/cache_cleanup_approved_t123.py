"""Apply only the owner's sealed T1/T2/T3 file selection; never scan for candidates."""

import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/cache_audit_20261024"
PLAN = OUT / "prune_plan_final.json"
EXPECTED = "020e3eec989ff1505a0d101ff187bb0de83b266f945f2b20869883d3354b5a84"
TIERS = ("T1_tool_caches", "T2_dev_bundles", "T3_superseded_registered")
BOOKS = {"spanish_us_history", "immigrant_children", "art_therapy_index", "medical_anatomy", "statistics"}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path):
    return json.loads(path.read_text("utf-8"))


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    require(sys.argv[1:] == ["--apply-approved-t123"], "Explicit approved apply argument required")
    record_path = OUT / "approved_t123_deletion_record.json"
    require(not record_path.exists(), "Deletion record already exists; do not repeat")
    record = {"started": now(), "plan_sha256": EXPECTED, "approved_tiers": list(TIERS),
              "deleted_files": 0, "deleted_bytes": 0, "deleted_by_tier": {},
              "status": "preflight", "t4_approved": False,
              "freeze_started": False, "fresh_spanish_started": False, "holdout_started": False}
    started = time.monotonic()
    delete_start = None
    try:
        require(sha(PLAN) == EXPECTED, "Plan changed: STOP")
        plan = load(PLAN)
        proposal_path, receipt_path = ROOT / plan["proposal_path"], ROOT / plan["candidate_hash_receipt"]
        require(sha(proposal_path) == plan["proposal_sha256"], "Proposal changed: STOP")
        require(sha(receipt_path) == plan["candidate_hash_receipt_sha256"], "Hash receipt changed: STOP")
        proposal = load(proposal_path)
        receipts = {r[0]: r for r in json.loads(gzip.decompress(receipt_path.read_bytes()))}
        excluded = {r[0] for r in plan["additional_exclusions"]}
        selected = [(tier, *r) for tier in TIERS for r in proposal["tiers"][tier]["entries"] if r[0] not in excluded]
        paths = {r[1] for r in selected}
        require(len(paths) == len(selected) == 113072, "Selection count differs")
        require(sum(r[2] for r in selected) == 3850056473, "Selection bytes differ")
        require(paths <= receipts.keys(), "Selection missing from sealed receipt")
        t4 = proposal["tiers"]["T4_historical_archives"]["entries"]
        require(paths.isdisjoint(r[0] for r in t4), "T4 intersection")
        deps = load(OUT / "dependencies.json")
        protected_keys = {key for key, uses in deps["protected_keys"].items() if uses}
        snapshot = load(OUT / "registry_snapshot.json")
        current_files = {".cache/" + p.replace("\\", "/") for eid in snapshot["current"].values()
                         for p in snapshot["entries"][eid]["files"]}
        require(paths.isdisjoint(current_files), "Current registry file selected")
        eligible_t3 = set()
        for entry in load(OUT / "registry_entries.json"):
            if (entry["book"] in BOOKS and not entry["current"] and entry["superseded_producer"]
                    and not entry["baseline_or_parity_uses"] and entry["stage"] not in {"native", "analysis"}):
                eligible_t3.update(".cache/" + p.replace("\\", "/") for p in snapshot["entries"][entry["id"]]["files"])
        parents = set()
        for tier, p, *_ in selected:
            parts = PurePosixPath(p).parts
            require(not PurePosixPath(p).is_absolute() and ".." not in parts and "\\" not in p and ":" not in p,
                    "Unsafe path: " + p)
            path_keys = set(re.findall(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", p))
            require(not path_keys & protected_keys, "Protected fingerprint: " + p)
            require(not any(p == r or p.startswith(r + "/") for r in deps["protected_roots"]), "Protected root: " + p)
            if tier == TIERS[0]:
                require(p.startswith((".cache/pip/", "backend/src/", "backend/tests/", "experiments/__pycache__/", "backend/.pytest_cache/")), "Invalid T1 path")
                require(p.startswith((".cache/pip/", "backend/.pytest_cache/")) or ("/__pycache__/" in p and p.endswith(".pyc")), "Non-bytecode T1 path")
            elif tier == TIERS[1]:
                require(p.startswith((".cache/step13b/bundles/", ".cache/step14b/pages/", ".cache/step15/pages/")), "Invalid T2 path")
            else:
                require(p in eligible_t3, "T3 not superseded eligible development cache: " + p)
            for parent in (ROOT / p).parents:
                if parent == ROOT:
                    break
                parents.add(parent)
        for parent in parents:
            require(parent.resolve(strict=True).is_relative_to(ROOT), "Path escapes workspace")
            require(not parent.is_symlink() and not parent.is_junction(), "Linked/junction parent")
        frozen_path = ROOT / "experiments/out/step17b/final/validation/final_suite_inputs.json"
        require(sha(frozen_path) == plan["frozen_input_record_sha256"], "Frozen input record changed")
        frozen = load(frozen_path)
        require(paths.isdisjoint(p.replace("\\", "/") for p in frozen), "Frozen input selected")
        for p, digest in frozen.items():
            require(sha(ROOT / p) == digest, "Frozen source/report changed: " + p)
        evidence = load(ROOT / "experiments/out/step17b/evidence_manifest.json")["files"]
        for p, data in evidence.items():
            require(sha(ROOT / p) == data["sha256"], "Frozen evidence changed: " + p)
        require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == plan["target_commit"], "HEAD changed")
        sys.path.insert(0, str(ROOT / "backend/src"))
        from book_core.cache_admin import cache_lock

        def matching_stat(p, size, mtime):
            st = (ROOT / p).stat(follow_symlinks=False)
            require(stat.S_ISREG(st.st_mode) and not st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    and st.st_nlink == 1, "Not a plain single-link file: " + p)
            require((st.st_size, st.st_mtime_ns, st.st_ctime_ns) == (size, mtime, receipts[p][2]), "File changed: " + p)
            return st

        def checked_hash(row):
            _, p, size, mtime = row
            matching_stat(p, size, mtime)
            require(sha(ROOT / p) == receipts[p][1], "File bytes changed: " + p)
            matching_stat(p, size, mtime)
            return p

        with cache_lock(ROOT / ".cache"):
            require(sha(ROOT / ".cache/.cache-index.json") == plan["registry_sha256"], "Registry changed: STOP")
            with ThreadPoolExecutor(max_workers=4) as workers:
                for count, _ in enumerate(workers.map(checked_hash, selected, buffersize=32), 1):
                    if count % 10000 == 0:
                        print("verified", count, "/", len(selected), round(time.monotonic() - started, 1), flush=True)
            # Entire metadata pass must still match before the first unlink.
            for _, p, size, mtime in selected:
                matching_stat(p, size, mtime)
            for p, size, mtime in t4:
                matching_stat(p, size, mtime)
            require(sha(ROOT / ".cache/.cache-index.json") == plan["registry_sha256"], "Registry changed before deletion")
            record["preflight_seconds"] = time.monotonic() - started
            record["verified_files"] = len(selected)
            record["free_bytes_before_deletion"] = shutil.disk_usage(ROOT).free
            record["plan_hash_verified_immediately_before_deletion"] = sha(PLAN)
            require(record["plan_hash_verified_immediately_before_deletion"] == EXPECTED, "Plan changed immediately before deletion: STOP")
            record["deletion_started"] = now()
            delete_start = time.monotonic()
            record["status"] = "deleting"
            with record_path.open("x", encoding="utf-8") as stream:
                json.dump(record, stream, indent=1)
            counts, sizes = Counter(), Counter()
            journal_path = OUT / "approved_t123_deleted_files.jsonl"
            with journal_path.open("x", encoding="utf-8", buffering=1) as journal:
                for tier, p, size, mtime in selected:
                    matching_stat(p, size, mtime)
                    os.unlink(ROOT / p)  # Exact approved regular file only; no directory removal.
                    record["deleted_files"] += 1
                    record["deleted_bytes"] += size
                    counts[tier] += 1
                    sizes[tier] += size
                    record["deleted_by_tier"][tier] = {"files": counts[tier], "bytes": sizes[tier]}
                    journal.write(json.dumps([tier, p, size, now()], separators=(",", ":")) + "\n")
                    if record["deleted_files"] % 10000 == 0:
                        journal.flush()
                        os.fsync(journal.fileno())
                        print("deleted", record["deleted_files"], round(time.monotonic() - delete_start, 1), flush=True)
                journal.flush()
                os.fsync(journal.fileno())
            record["deleted_by_tier"] = {tier: {"files": counts[tier], "bytes": sizes[tier]} for tier in TIERS}
            record["deletion_finished"] = now()
            record["deletion_seconds"] = time.monotonic() - delete_start
            record["free_bytes_immediately_after_deletion"] = shutil.disk_usage(ROOT).free
            require(sha(PLAN) == EXPECTED, "Plan changed after deletion")
            require(sha(ROOT / ".cache/.cache-index.json") == plan["registry_sha256"], "Registry changed after deletion")
            require(not any((ROOT / p).exists() for p in paths), "Selected file remains")
            for p, size, mtime in t4:
                matching_stat(p, size, mtime)
            record["t4_files_retained_metadata_verified"] = len(t4)
            record["registry_unchanged"] = True
            record["plan_unchanged"] = True
            record["journal_sha256"] = sha(journal_path)
            record["status"] = "deletion_complete_closure_tests_pending"
    except BaseException as error:
        record["status"] = "stopped"
        record["error"] = f"{type(error).__name__}: {error}"
        if delete_start is not None:
            record["deletion_seconds"] = time.monotonic() - delete_start
        raise
    finally:
        record["finished"] = now()
        record["total_seconds"] = time.monotonic() - started
        record["free_bytes_at_record_finish"] = shutil.disk_usage(ROOT).free
        record_path.write_text(json.dumps(record, indent=1), "utf-8")
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
