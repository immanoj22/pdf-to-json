"""Read-only capacity planning before a sealed run; there is no apply/delete action.

Use recorded intake page counts, never inspect hold-out page content or references.
Only new budget evidence is written. Existing caches, registry, publications,
gold, references, ledger, Git configuration and sealed evidence stay unchanged.
"""
import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.cache_store import read_json
from reference_paths import reference_path
from step7_layouts import CACHE

OUT = ROOT / "experiments/out/prefreeze_disk_budget"
BOOKS = ("spanish_us_history", "immigrant_children", "art_therapy_index",
         "medical_anatomy", "statistics")
TARGET = "d0625e841c6793dea6de7c2cb4a87e31694ff2c3"
RESERVE = 5_000_000_000
PER_PAGE = 12 * 1024 * 1024
# Planning headroom only, not a demonstrated bound on the unfinished Spanish proof.
TRANSIENT = 6_000_000_000


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def write(name, value):
    path = OUT / name
    assert not path.exists(), f"Preserve previous evidence: {path}"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", "utf-8")


def folder_bytes(path):
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())


def measured_books(index):
    measured = {}
    for name in BOOKS:
        path = ROOT / f"experiments/out/step17b/final/performance/{name}.json"
        run = json.loads(path.read_text("utf-8"))["run"]
        native = [e for e in index["entries"].values()
                  if e["stage"] == "native" and e["key"] == run["cache_keys"]["native"]]
        assert len(native) == 1
        source = native[0]["book"]
        paths, by_stage = set(), {}
        for stage, key in run["cache_keys"].items():
            assert isinstance(key, str), (name, stage)
            entries = [e for e in index["entries"].values()
                       if (e["book"], e["stage"], e["key"]) == (source, stage, key)]
            files = {p for e in entries for p in e["files"]}
            assert all((ROOT / ".cache" / p).is_file() for p in files)
            paths.update(files)
            by_stage[stage] = sum((ROOT / ".cache" / p).stat().st_size for p in files)
        # Assembly refresh writes marks at the page-cache root, outside the main registry.
        marks = list((CACHE / "assembly_evidence" / run["cache_keys"]["assembly_evidence"]).glob("*.json"))
        assert len(marks) == run["pages"]
        mark_bytes = sum(p.stat().st_size for p in marks)
        measured[name] = {
            "pages": run["pages"], "source_sha256": source,
            "performance_record": path.relative_to(ROOT).as_posix(), "performance_sha256": sha(path),
            "registered_stage_bytes": sum((ROOT / ".cache" / p).stat().st_size for p in paths),
            "registered_stage_breakdown": by_stage,
            "unregistered_assembly_marks_bytes": mark_bytes,
            "cache_bytes": sum((ROOT / ".cache" / p).stat().st_size for p in paths) + mark_bytes,
            "archive_bytes": folder_bytes(run["output"]),
            "publication_bytes": folder_bytes(run["book_json"]),
            "excludes": "Shared model weights, global formula/table/OCR experiment caches and duplicate historical configurations.",
        }
        print("measured", name, measured[name]["cache_bytes"], flush=True)
    return measured


def estimate(measured, index, free):
    inventory_path = ROOT / "experiments/out/book_intake/inventory.json"
    seal_path = ROOT / "experiments/out/step13/holdout_runs.jsonl"
    inventory = json.loads(inventory_path.read_text("utf-8"))
    seal = [json.loads(line) for line in seal_path.read_text("utf-8").splitlines()
            if json.loads(line).get("action") == "sealed"][-1]
    specs = (
        ("ent_textbook", "ent_textbook_pdf", inventory["ent_textbook"]["pdf"]["pages"], "medical_anatomy"),
        ("math_holdout", "math_holdout_pdf", seal["pdf_pages"], "statistics"),
        ("mideast", "mideast_pdf", inventory["deanta_pdf_mideast"]["pdf"]["pages"], "spanish_us_history"),
    )
    publication_rate = max(v["publication_bytes"] / v["pages"] for v in measured.values())
    rows = {}
    for name, key, pages, analogue in specs:
        source = reference_path(key)
        digest = sha(source)  # byte identity only: no PDF parsing, OCR, extraction or evaluation
        if name == "math_holdout":
            assert digest == seal["pdf_sha256"]
        assert not any(e["book"] == digest for e in index["entries"].values()), "Hold-out cache needs separate audit"
        basis = measured[analogue]
        empirical = {part: math.ceil(pages * basis[part] / basis["pages"])
                     for part in ("cache_bytes", "archive_bytes", "publication_bytes")}
        nominal = pages * PER_PAGE
        publication = math.ceil(pages * publication_rate)
        rows[name] = {
            "source_key": key, "source_bytes_already_present": source.stat().st_size,
            "source_sha256": digest, "pages": pages,
            "analogue": analogue, "analogue_extrapolation": empirical,
            "cache_and_archive_allowance_bytes": nominal,
            "additional_publication_allowance_bytes": publication,
            "persistent_planning_bytes": nominal + publication,
            "free_required_including_reserve_bytes": nominal + publication + RESERVE,
            "free_required_including_reserve_and_transient_bytes": nominal + publication + RESERVE + TRANSIENT,
            "fits_now_even_without_transient_headroom": nominal + publication <= free - RESERVE,
            "holdout_pipeline_run": False,
        }
    persistent = sum(v["persistent_planning_bytes"] for v in rows.values())
    return {
        "books": rows, "total_pages": sum(v["pages"] for v in rows.values()),
        "intake_inventory_sha256": sha(inventory_path), "math_seal_log_sha256": sha(seal_path),
        "default_combined_cache_archive_bytes_per_page": PER_PAGE,
        "additional_publication_bytes_per_page": publication_rate,
        "publication_basis": "Highest measured publication bytes/page across all five development books, including images and review crops.",
        "assumptions": [
            "One book/process at a time; retain all three books' caches, semantic archives and publication folders.",
            "Existing source PDFs and installed models need no additional copy/download.",
            "12 MiB/page is the existing full-run capacity allowance, not an unseen-book upper bound; publication duplication is added separately.",
            "Analogue extrapolations are descriptive, not permission to lower the full-run allowance; no sealed content or references were evaluated.",
            "6 GB transient working headroom is one shared planning allowance for serial jobs, not a measured upper bound. Monitor the actual job and stop below reserve.",
            "Use an explicitly selected cache/output root before the sealed run; no pruning is permitted during it.",
        ],
        "reserve_bytes": RESERVE, "transient_planning_bytes": TRANSIENT,
        "persistent_planning_bytes": persistent,
        "required_free_without_transient_bytes": persistent + RESERVE,
        "required_free_with_transient_bytes": persistent + RESERVE + TRANSIENT,
        "shortfall_without_transient_bytes": max(0, persistent + RESERVE - free),
        "shortfall_with_transient_bytes": max(0, persistent + RESERVE + TRANSIENT - free),
    }


def prune_list(index, index_sha, allowed_sources):
    """Protect referenced keys and every native cache (including indirect dependencies)."""
    import re

    keys = {e["key"] for e in index["entries"].values()}
    hexes = re.compile(rb"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
    witnesses = {}
    tracked = [p for p in git("ls-files", "-z").decode("utf-8").split("\0") if p]
    for i, name in enumerate(tracked):
        path = ROOT / name
        if path.suffix not in {".json", ".jsonl", ".md", ".py", ".toml", ".txt", ".log", ".sh"}:
            continue
        hits = {x.decode() for x in hexes.findall(path.read_bytes())} & keys
        for hit in hits:
            if hit not in witnesses:
                witnesses[hit] = {"path": name, "sha256": sha(path)}
        if i % 500 == 0:
            print("protected-reference scan", i, "of", len(tracked), flush=True)
    current = set(index["current"].values())
    protected_files = {p for eid in current for p in index["entries"][eid]["files"]}
    entries, candidates = [], {}
    for eid, entry in sorted(index["entries"].items()):
        owner = f"{entry['book']}/{entry['stage']}"
        latest = index["entries"][index["current"][owner]]
        reasons = []
        if eid in current:
            reasons.append("current registry entry")
        if entry["producer"] == latest["producer"]:
            reasons.append("producer is not superseded")
        if entry["book"] not in allowed_sources:
            reasons.append("not one of the five development sources")
        if entry["key"] in witnesses:
            reasons.append("fingerprint referenced in tracked frozen evidence/source")
        if entry["stage"] == "native":
            reasons.append("all native caches protected against retained-analysis indirect dependencies")
        existing = []
        for name in entry["files"]:
            path = ROOT / ".cache" / name
            if path.is_file():
                stat = path.stat()
                existing.append((name, stat))
        row = {k: entry[k] for k in ("book", "stage", "key", "producer")}
        row.update(entry_id=eid, current=eid in current,
                   superseded=eid not in current and entry["producer"] != latest["producer"],
                   existing_files=len(existing), existing_bytes=sum(s.st_size for _, s in existing),
                   protected_reasons=reasons, tracked_witness=witnesses.get(entry["key"]))
        entries.append(row)
        if not reasons:
            for name, stat in existing:
                assert name not in protected_files
                path = (ROOT / ".cache" / name).resolve()
                path.relative_to((ROOT / ".cache").resolve())
                assert not path.is_symlink()
                relative = path.relative_to(ROOT).as_posix()
                candidates[relative] = {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                                        "ctime_ns": stat.st_ctime_ns, "sha256": sha(path)}
    return {
        "dry_run": True, "deleted": False, "approval_required": True,
        "target_commit": TARGET, "registry_sha256": index_sha,
        "policy": "Only registered superseded-producer files from five development books. Keep every current entry, tracked-key baseline/parity input, all native caches, and all unregistered files. Hold-outs, gold, references, models, ledgers and published outputs are never candidates.",
        "apply_guard": "There is no apply action. A separately approved action must verify this exact plan SHA, registry SHA and every listed file hash/size/time without rescanning candidates. No deletion during a sealed run.",
        "entries_audited": entries, "current_registry_files_protected": len(protected_files),
        "tracked_keys_protected": len(witnesses), "files": candidates,
        "reclaim_bytes": sum(v["bytes"] for v in candidates.values()),
        "superseded_existing_bytes": sum(e["existing_bytes"] for e in entries if e["superseded"]),
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    assert git("rev-parse", "HEAD").decode().strip() == TARGET
    assert not git("diff", "--name-only", TARGET), "Tracked review inputs changed"
    assert not OUT.exists(), "Preserve prior budget evidence; use a new explicit location"
    OUT.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()
    free = shutil.disk_usage(ROOT).free
    index_path = ROOT / ".cache/.cache-index.json"
    index_sha = sha(index_path)
    index = read_json(index_path)
    measured = measured_books(index)
    budget = estimate(measured, index, free)
    write("measurements.json", measured)
    write("disk_budget.json", {"started": started, "target_commit": TARGET,
          "free_at_start_bytes": free, "usable_above_reserve_bytes": free - RESERVE, **budget})
    print("budget persistent bytes", budget["persistent_planning_bytes"], "free", free, flush=True)
    plan = prune_list(index, index_sha, {v["source_sha256"] for v in measured.values()})
    assert sha(index_path) == index_sha, "Registry changed during audit; do not approve this snapshot"
    assert not git("diff", "--name-only", TARGET), "Tracked review inputs changed during audit"
    write("cache_prune_dry_run.json", plan)
    previous = ROOT / "experiments/out/step17b/final/validation/proof_spanish_us_history_reserve.json"
    status = {
        "target_commit": TARGET, "target_authorized_by": "Explicit user reply: Use current review commit d0625e8",
        "status": "not_run_insufficient_disk_headroom", "fresh_every_page_completed": False,
        "proof_reused": False, "old_step17b_proof_modified": False,
        "reason": "Prior fresh isolated proof stopped below the 5 GB reserve from about 7.77 GB free. Current free space is lower; do not start the same resource-heavy gate.",
        "previous_interrupted_monitor": previous.relative_to(ROOT).as_posix(),
        "previous_monitor_sha256": sha(previous),
        "free_at_start_bytes": free, "free_after_audit_bytes": shutil.disk_usage(ROOT).free,
        "reserve_bytes": RESERVE, "suggested_retry_free_bytes": RESERVE + TRANSIENT,
        "suggested_retry_limit": "11 GB is planning headroom, not a demonstrated bound. A fresh monitored all-758-page check must complete; stop below reserve and never substitute reused proof.",
        "future_check": "Unmodified d0625e8 step13_run.proof_math_book with MATH_BOOK=spanish_us_history, new evidence destination, existing exact cache keys, fresh_every_page=true only after all 758 pages finish.",
    }
    write("spanish_fresh_status.json", status)
    write("snapshot.json", {"finished": datetime.now(timezone.utc).isoformat(),
          "target_commit": TARGET, "local_tags": git("tag", "--list").decode().splitlines(),
          "registry_sha256_before_and_after": index_sha,
          "free_after_bytes": shutil.disk_usage(ROOT).free, "deletion_performed": False,
          "holdouts_run": False, "production_changes": False,
          "prune_plan_sha256": sha(OUT / "cache_prune_dry_run.json")})
    print(json.dumps({"free_bytes": shutil.disk_usage(ROOT).free,
          "persistent_budget_bytes": budget["persistent_planning_bytes"],
          "required_free_with_reserve_and_transient": budget["required_free_with_transient_bytes"],
          "prune_files": len(plan["files"]), "reclaim_bytes": plan["reclaim_bytes"],
          "spanish_fresh": status["status"], "deleted": False}), flush=True)


if __name__ == "__main__":
    main()
