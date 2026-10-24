"""Read-only cache inventory. Writes new audit evidence only; no deletion action."""
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/cache_audit_20261024"
sys.path.insert(0, str(ROOT / "backend/src"))
from book_core.cache_store import read_json


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(name, value):
    path = OUT / name
    assert not path.exists(), path
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", "utf-8")


def inventory():
    OUT.mkdir(parents=True, exist_ok=True)
    assert not (OUT / "inventory.json.gz").exists()
    started = datetime.now(timezone.utc).isoformat()
    registry = ROOT / ".cache/.cache-index.json"
    registry_before = sha(registry)
    roots = [ROOT / ".cache", ROOT / ".s17bt", ROOT / ".ruff_cache"]
    # Discover project-local cache roots without entering environments, dependencies,
    # Git internals, or a cache twice. No content inspection or source PDF access.
    skip = {".git", ".venv", "node_modules", ".cache", ".s17bt", ".ruff_cache"}
    for parent, dirs, _ in os.walk(ROOT, followlinks=False):
        for name in list(dirs):
            path = Path(parent) / name
            if name in skip or path.is_symlink() or path.is_junction():
                dirs.remove(name)
            elif name.lower() in {"cache", "__pycache__", ".pytest_cache", ".mypy_cache", ".vite"}:
                roots.append(path)
                dirs.remove(name)
    rows, skipped, errors = [], [], []
    for root in roots:
        if not root.exists():
            continue
        pending = [root]
        while pending:
            parent = pending.pop()
            try:
                with os.scandir(parent) as entries:
                    for entry in entries:
                        rel = Path(entry.path).relative_to(ROOT).as_posix()
                        if entry.is_symlink() or entry.is_junction():
                            skipped.append(rel)
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            s = entry.stat(follow_symlinks=False)
                            rows.append([rel, s.st_size, s.st_mtime_ns, s.st_ino, s.st_nlink])
            except OSError as error:
                errors.append({"path": str(parent), "error": str(error)})
        print("inventoried", root.relative_to(ROOT), len(rows), flush=True)
    index = read_json(registry)
    write("registry_snapshot.json", index)
    groups = Counter()
    for path, size, *_ in rows:
        parts = path.split("/")
        group = "/".join(parts[:3]) if parts[0] == ".cache" and len(parts) > 3 else "/".join(parts[:-1])
        groups[group] += size
    with (OUT / "inventory.json.gz").open("xb") as stream:
        stream.write(gzip.compress(json.dumps(rows, separators=(",", ":")).encode(), mtime=0))
    write("inventory_summary.json", {
        "started": started, "finished": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "roots": [r.relative_to(ROOT).as_posix() for r in roots if r.exists()],
        "files": len(rows), "logical_bytes": sum(row[1] for row in rows),
        "free_bytes": shutil.disk_usage(ROOT).free,
        "registry_sha256_before": registry_before, "registry_sha256_after": sha(registry),
        "skipped_links_or_junctions": skipped, "errors": errors,
        "groups": [{"path": p, "bytes": n} for p, n in groups.most_common()],
        "columns": ["path", "bytes", "mtime_ns", "inode", "link_count"],
        "scope": "Project caches, Python bytecode and retained test scratch; excludes environments, node_modules, Git internals and non-cache outputs.",
        "deleted": False,
    })
    print(json.dumps(groups.most_common(40)), flush=True)


def group_of(path):
    parts = path.split("/")
    if parts[0] == ".cache":
        if len(parts) < 4:
            return ".cache/root_metadata" if len(parts) == 2 else "/".join(parts[:2])
        if parts[1].startswith(("t17", "pytest", "tmp")) or parts[1] in {"a21", "ct17", "ct18", "t20", "t22", "t23"}:
            return "/".join(parts[:2])
        return "/".join(parts[:3])
    if path.startswith("frontend_temp/runtime/cache/"):
        return "/".join(parts[:5]) if parts[3] == "huggingface" else "/".join(parts[:4])
    if parts[0] in {".s17bt", ".ruff_cache"}:
        return parts[0]
    return "/".join(parts[:4]) if path.startswith("experiments/out/step17b/test_runs/") else "/".join(parts[:-1])


def relative(value):
    return Path(value).relative_to(ROOT).as_posix()


def prefix(path, amount=16384):
    with Path(path).open("rb") as stream:
        magic = stream.read(2)
        stream.seek(0)
        if magic == b"\x1f\x8b":
            with gzip.GzipFile(fileobj=stream) as decoded:
                return decoded.read(amount).decode("utf-8", errors="replace").replace('\\"', '"')
        return stream.read(amount).decode("utf-8", errors="replace").replace('\\"', '"')


def analyze():
    rows = json.loads(gzip.decompress((OUT / "inventory.json.gz").read_bytes()))
    index = json.loads((OUT / "registry_snapshot.json").read_text("utf-8"))
    oldplan = json.loads((ROOT / "experiments/out/prefreeze_disk_budget/cache_prune_dry_run.json").read_text("utf-8"))
    old_by_id = {e["entry_id"]: e for e in oldplan["entries_audited"]}
    measured = json.loads((ROOT / "experiments/out/prefreeze_disk_budget/measurements.json").read_text("utf-8"))
    books = {v["source_sha256"]: k for k, v in measured.items()}
    books["d02f2b77b0f62c9c89f8428142af0f04fdbcacb89abe7b4ed10da9370bd5121d"] = "science_pdf (Step 6b development)"
    # Repository fixture identity only, without PDF parsing.
    for folder in ("experiments/fixtures", "experiments/fixtures_unseen"):
        for path in (ROOT / folder).glob("*.pdf"):
            books[sha(path)] = "fixture:" + path.stem
    by_path = {r[0]: r for r in rows}
    keys = {e["key"] for e in index["entries"].values()}
    refs, protected_keys, protected_roots, timings = defaultdict(list), defaultdict(set), defaultdict(set), {}
    records = []
    for step in ("step15", "step16", "step17", "step17b"):
        for path in sorted((ROOT / f"experiments/out/{step}").rglob("*.json")):
            if path.parent.name != "performance":
                continue
            data = json.loads(path.read_text("utf-8"))
            run = data.get("run", {})
            if not run or not isinstance(run.get("cache_keys"), dict):
                continue
            label = path.relative_to(ROOT).as_posix()
            records.append(label)
            for stage, key in run["cache_keys"].items():
                if isinstance(key, str):
                    protected_keys[key].add(step + ":" + stage)
            for field in ("output", "book_json"):
                if run.get(field):
                    protected_roots[relative(run[field])].add(step + ":" + field)
            # Keep previous publications used by Step 17 correction/parity proofs.
            for history in data.get("assembly_history", []):
                if history.get("book_json"):
                    protected_roots[relative(history["book_json"])].add(step + ":assembly_history")
            if step == "step17b" and path.parent.parent.name == "final":
                timings[path.stem] = {
                    "source": label, "stages_wall_seconds": {s: v.get("wall_seconds", 0) for s, v in run["stages"].items()},
                    "archive_complete_wall_seconds": run["total"]["wall_seconds"],
                    "publication_wall_seconds": data.get("assembly_refresh", {}).get("stages", {}).get("assembly", {}).get("wall_seconds"),
                    "caveat": "Observed mixed cache-hit/miss run, NOT a cold rebuild bound; historical producers need their old code/config/environment.",
                }
    # Worker artifacts are parity evidence, even though they are not main-registry entries.
    worker = json.loads((ROOT / "experiments/out/step17b/final/workers_book3.json").read_text())
    for value in worker["cache_directories"].values():
        protected_roots[relative(value)].add("step17b:worker parity")
    for value in json.loads((ROOT / "experiments/out/step17b/inputs.json").read_text()).values():
        protected_roots[relative(value["json"]) .rsplit("/", 1)[0]].add("step17b:before publication")
    pattern = re.compile(rb"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for i, name in enumerate(tracked):
        path = ROOT / name
        if not name or path.suffix not in {".json", ".jsonl", ".md", ".py", ".toml", ".txt", ".log", ".sh"}:
            continue
        for key in {v.decode() for v in pattern.findall(path.read_bytes())} & keys:
            refs[key].append(name)
        if i % 1200 == 0:
            print("reference inventory", i, flush=True)
    current = set(index["current"].values())
    entry_for_path, entries = {}, []
    for eid, entry in index["entries"].items():
        paths = [".cache/" + p.replace("\\", "/") for p in entry["files"]]
        existing = [p for p in paths if p in by_path]
        latest = index["entries"][index["current"][entry["book"] + "/" + entry["stage"]]]
        row = {"id": eid, "book": books.get(entry["book"], "unidentified source:" + entry["book"]),
               "source_sha256": entry["book"], "stage": entry["stage"], "key": entry["key"],
               "producer": entry["producer"], "current": eid in current,
               "superseded_producer": entry["producer"] != latest["producer"],
               "files": len(existing), "bytes": sum(by_path[p][1] for p in existing),
               "baseline_or_parity_uses": sorted(protected_keys[entry["key"]]),
               "prior_dry_run_exclusions": old_by_id.get(eid, {}).get("protected_reasons", []),
               "tracked_mentions": refs[entry["key"]],
               "profile": "Not stored by registry; key binds stage configuration. Distinct keys are not assumed interchangeable."}
        entries.append(row)
        for p in existing:
            entry_for_path.setdefault(p, []).append(row)
    # Small manifests identify archive book, stage keys and publication ancestry.
    archives, pub_pending = {}, []
    for path, *_ in rows:
        if path.endswith("/manifest.json.gz") and "/final_books/" in path:
            d = read_json(ROOT / path)
            archives[path.rsplit("/", 1)[0]] = {
                "book": books.get(d.get("source_sha256"), "unidentified source:" + str(d.get("source_sha256"))),
                "source_sha256": d.get("source_sha256"), "pages": d.get("pages"), "keys": d.get("keys", {}),
                "complete": d.get("complete"), "type": "semantic archive", "manifest_sha256": sha(ROOT / path),
                "profile": "Not a publication profile; semantic archive inputs are the listed stage keys."}
        elif path.endswith("/manifest.json") and "/final_books/" in path:
            pub_pending.append(path)
    by_final_key = {p.rsplit("/", 1)[1]: d for p, d in archives.items()}
    for path in pub_pending:
        d = read_json(ROOT / path)
        parent = path.rsplit("/", 1)[0]
        ancestor = by_final_key.get(d.get("final_key"), {})
        # Publication metadata is small relative to content; parse one document at a time.
        document = ROOT / parent / "book.json"
        meta = {}
        if document.exists():
            data = json.loads(document.read_text("utf-8"))
            meta = data.get("metadata", {})
            del data
        archives[parent] = {"book": ancestor.get("book", "unknown publication ancestor"),
                            "source_sha256": ancestor.get("source_sha256"), "type": "publication",
                            "final_key": d.get("final_key"), "profile": meta.get("profile"),
                            "producer": meta.get("converter"), "manifest_sha256": sha(ROOT / path)}
    print("archive identities", len(archives), flush=True)
    # Discover old object-cache identities from a bounded serialized prefix. Never
    # instantiate native geometry or execute cached pickles.
    object_groups = defaultdict(list)
    for p, *_ in rows:
        if p.startswith((".cache/objects/native/", ".cache/objects/analysis/")):
            object_groups["/".join(p.split("/")[:4])].append(p)
    identities = {}
    for folder, paths in object_groups.items():
        sample = paths[0]
        hit = re.search(r'"source_sha256"\s*:\s*"([0-9a-f]{64})"', prefix(ROOT / sample))
        source = hit[1] if hit else None
        identities[folder] = {"book": books.get(source, "unidentified source:" + str(source)),
                              "source_sha256": source, "sample": sample,
                              "scope": "Folder identity inferred from one prefix; no whole-folder identity assertion."}
    frozen_prefixes = sorted(protected_roots, key=len, reverse=True)
    archive_prefixes = sorted(archives, key=len, reverse=True)
    files, groups, totals, proposed = [], {}, Counter(), defaultdict(list)
    for p, size, mtime, inode, nlink in rows:
        group = group_of(p)
        g = groups.setdefault(group, {"path": group, "bytes": 0, "files": 0, "books": Counter(),
                                      "categories": Counter(), "uses": Counter(), "prior_exclusions": Counter()})
        es = entry_for_path.get(p, [])
        uses = set()
        for e in es:
            uses.update(e["baseline_or_parity_uses"])
            if e["current"]:
                uses.add("current registry")
        root_use = next((f for f in frozen_prefixes if p.startswith(f + "/")), None)
        if root_use:
            uses.update(protected_roots[root_use])
        archive = next((f for f in archive_prefixes if p.startswith(f + "/")), None) if "/final_books/" in p else None
        book = es[0]["book"] if es else archives[archive]["book"] if archive else None
        if not book:
            obj = "/".join(p.split("/")[:4])
            book = identities.get(obj, {}).get("book")
        if not book:
            book = next((b for b in measured if "/" + b + "/" in p), None)
        shared = p.startswith((".cache/huggingface/", ".cache/models/", ".cache/step6b/models/", ".cache/step16/ocr/"))
        reference = p.startswith(".cache/external/")
        active = p.startswith("frontend_temp/runtime/cache/")
        if shared:
            uses.add("shared models/runtime assets (model weights protected)")
            book = book or "shared, no single book"
        if reference:
            uses.add("external source/reference material, protected")
            book = "external source/reference:" + p.split("/")[2]
        if active:
            uses.add("frontend server cache; active scope protected")
            book = book or "frontend job/shared models; source not mapped"
        # Native caches are kept even for old fingerprints: retained analyses can
        # reference them indirectly. Unknown identities remain unknown, not disposable.
        native_closure = "/native/" in p and p.startswith((".cache/step7/", ".cache/objects/"))
        if native_closure:
            uses.add("native dependency closure retained conservatively")
        category, tier = "unknown", None
        if uses and (not native_closure or len(uses) > 1):
            category = "needed_for_freeze"
        elif native_closure:
            category = "unknown"
        elif es:
            category = "superseded" if all(e["superseded_producer"] for e in es) else "rebuildable"
            if category == "superseded" and all(e["source_sha256"] in measured_sources(measured) for e in es):
                tier = "T3_superseded_registered"
        elif archive and archives[archive].get("source_sha256") in measured_sources(measured):
            category, tier = "superseded", "T4_historical_archives"
        elif "__pycache__/" in p or p.startswith((".cache/pip/", ".ruff_cache/", "backend/.pytest_cache/")):
            category, tier = "rebuildable", "T1_tool_caches"
        elif p.startswith((".cache/step13b/bundles/", ".cache/step14b/pages/", ".cache/step15/pages/")):
            category, tier = "rebuildable", "T2_dev_bundles"
        elif p.startswith(".s17bt/") or (p.startswith(".cache/") and p.split("/")[1].startswith(("pytest", "t17", "tmp"))):
            # Retained test files are still evidence references; they are not included
            # in the safest tier without checking their linked validation receipts.
            category = "rebuildable"
        if p == ".cache/.cache-index.json" or p.startswith(".cache/root_metadata/"):
            category, tier = "needed_for_freeze", None
            uses.add("registry/maintenance metadata")
        if nlink > 1:
            tier = None
            uses.add("multiple hard links; physical reclaim unverified")
        g["bytes"] += size
        g["files"] += 1
        g["books"][book or "unknown identity"] += size
        g["categories"][category] += size
        g["uses"].update(uses)
        for e in es:
            g["prior_exclusions"].update(e["prior_dry_run_exclusions"])
        if not es:
            g["prior_exclusions"].update(["outside previous registered-only dry-run scope"])
        totals[category] += size
        files.append([p, size, mtime, category, tier])
        if tier:
            proposed[tier].append([p, size, mtime])
    for p, d in archives.items():
        d["path"] = p
        d["bytes"] = sum(r[1] for r in rows if r[0].startswith(p + "/"))
        d["baseline_or_parity_uses"] = sorted(protected_roots.get(p, []))
    duplicate_groups = []
    by_owner = defaultdict(list)
    for e in entries:
        if e["files"]:
            by_owner[(e["book"], e["stage"])].append(e)
    for (book, stage), values in sorted(by_owner.items()):
        if len(values) > 1:
            duplicate_groups.append({"book": book, "stage": stage, "fingerprints": len(values),
                                     "bytes": sum(e["bytes"] for e in values), "entries": values,
                                     "meaning": "Same source and stage under different fingerprints; NOT proven byte duplicates."})
    write("dependencies.json", {"performance_records": records, "protected_keys": {k: sorted(v) for k, v in protected_keys.items()},
                                "protected_roots": {k: sorted(v) for k, v in protected_roots.items()}, "timings": timings})
    write("registry_entries.json", entries)
    write("archive_identities.json", list(archives.values()))
    write("old_object_identities.json", identities)
    write("duplicates_by_book_stage.json", duplicate_groups)
    write("folder_audit.json", sorted(groups.values(), key=lambda x: -x["bytes"]))
    with (OUT / "classified_files.json.gz").open("xb") as stream:
        stream.write(gzip.compress(json.dumps(files, separators=(",", ":")).encode(), mtime=0))
    write("proposal_paths.json", {"dry_run": True, "deleted": False, "approval_required": True,
          "registry_sha256": sha(ROOT / ".cache/.cache-index.json"),
          "status": "Proposal only; exact file hashes and absence of live locks must be verified before any separately approved deletion.",
          "tiers": {k: {"bytes": sum(r[1] for r in v), "files": len(v), "entries": v} for k, v in proposed.items()},
          "totals": totals})
    print("categories", dict(totals), "tiers", {k: sum(r[1] for r in v) for k, v in proposed.items()}, flush=True)


def measured_sources(measured):
    return {v["source_sha256"] for v in measured.values()}


def refine():
    """Add unregistered stage identities; retain the first-pass evidence separately."""
    rows = json.loads(gzip.decompress((OUT / "inventory.json.gz").read_bytes()))
    classified = json.loads(gzip.decompress((OUT / "classified_files.json.gz").read_bytes()))
    entries = json.loads((OUT / "registry_entries.json").read_text())
    deps = json.loads((OUT / "dependencies.json").read_text())
    known = {e["source_sha256"]: e["book"] for e in entries}
    known["d02f2b77b0f62c9c89f8428142af0f04fdbcacb89abe7b4ed10da9370bd5121d"] = "science_pdf (Step 6b development)"
    for d in json.loads((OUT / "old_object_identities.json").read_text()).values():
        if d["source_sha256"] and not d["book"].startswith("unidentified"):
            known[d["source_sha256"]] = d["book"]
    candidates = defaultdict(list)
    key_books = defaultdict(set)
    for e in entries:
        key_books[e["key"]].add(e["book"])
    for p, *_ in rows:
        if p.startswith((".cache/step", ".cache/objects/")) and p.endswith(".json") and "/models/" not in p:
            parts = p.split("/")
            pos = next((i for i, part in enumerate(parts) if re.fullmatch("[0-9a-f]{64}", part)), None)
            folder = "/".join(parts[:pos+1]) if pos is not None else p
            if len(candidates[folder]) < 2:
                candidates[folder].append(p)
    identities = {}
    source_pattern = re.compile(r'"source_sha256"\s*:\s*"([0-9a-f]{64})"')
    for folder, samples in candidates.items():
        sources = set()
        for sample in samples:
            hit = source_pattern.search(prefix(ROOT / sample, 4096))
            if hit:
                sources.add(hit[1])
        if sources:
            identities[folder] = {"sources": sorted(sources), "books": sorted({known.get(s, "unidentified source:" + s) for s in sources}),
                                  "samples": samples, "method": "Source identities in bounded prefixes of up to two cache files; not a payload/full-folder validation."}
    print("bounded identity folders", len(identities), flush=True)
    archive_data = json.loads((OUT / "archive_identities.json").read_text())
    archive_books = {a["path"]: a["book"] for a in archive_data}
    active_models = {"docling-project--docling-layout-heron", "PaddlePaddle--PP-DocLayoutV3_safetensors", "PaddlePaddle--PP-FormulaNet-L_safetensors",
                     "microsoft--table-transformer-detection", "microsoft--table-transformer-structure-recognition", "docling-project--docling-models"}
    native_note = "Kept: native/analysis dependency closure, including restored fixtures; no native deletion proposed."
    totals, groups, proposed, changes = Counter(), {}, defaultdict(list), Counter()
    for row in classified:
        p, size, mtime, category, tier = row
        group = group_of(p)
        parts = p.split("/")
        pathkeys = [part.removesuffix(".json") for part in parts if re.fullmatch(r"[0-9a-f]{64}(?:\.json)?", part)]
        uses = {use for key in pathkeys for use in deps["protected_keys"].get(key, [])}
        book_names = set()
        for key in pathkeys:
            book_names.update(key_books.get(key, []))
        for n in range(len(parts), 2, -1):
            parent = "/".join(parts[:n])
            if parent in identities:
                book_names.update(identities[parent]["books"])
                break
            if parent in archive_books:
                book_names.add(archive_books[parent])
                break
        named = next((name for name in known.values() if "/" + name + "/" in p and not name.startswith("unidentified")), None)
        if named:
            book_names.add(named)
        if uses:
            category, tier = "needed_for_freeze", None
        if p.startswith(".cache/step6b/models/") or (p.startswith(".cache/huggingface/models--") and not any("models--" + model + "/" in p for model in active_models)):
            category, tier = "rebuildable", None
            uses.add("models protected by standing instructions; optional/older model, no deletion proposed")
        if p.startswith(".cache/step16/ocr/source_build/"):
            category, tier = "rebuildable", None
            uses.add("OCR build sources/tools; preserve until runtime provenance is verified; not model weights")
        if p.startswith(".cache/step6b/") and not book_names and not p.startswith(".cache/step6b/models/"):
            book_names.add("science_pdf (Step 6b development)" if "/math_" in p or "/science_" in p else "unmapped Step 6b experiment")
        if p.startswith(".cache/step11c/book300/"):
            book_names = {"300-page Step 11c excerpt; source via recorded excerpt provenance"}
        if p.startswith(".cache/step16/downstream/"):
            uses.add("Step 16 native-vs-scan comparison evidence; protect existing paired inputs")
            category, tier = "needed_for_freeze", None
        if not book_names:
            book_names.add("shared models/runtime" if "/models" in p or "/ocr/" in p else "unknown / mixed test fixtures")
        if "/native/" in p or p.startswith(".cache/objects/analysis/"):
            uses.add(native_note)
            tier = None
        if row[3] != category:
            changes[row[3] + " -> " + category] += size
        row[3:5] = [category, tier]
        totals[category] += size
        g = groups.setdefault(group, {"path": group, "bytes": 0, "files": 0, "books": Counter(), "categories": Counter(), "uses": Counter()})
        g["bytes"] += size
        g["files"] += 1
        g["categories"][category] += size
        g["books"]["; ".join(sorted(book_names))] += size
        g["uses"].update(uses)
        if tier:
            proposed[tier].append([p, size, mtime])
    # Metadata-read-only audit. No apply function and no unsupported guarantee that a
    # historical producer can recreate byte-identical output under today's runtime.
    write("unregistered_identities.json", identities)
    write("folder_audit_final.json", sorted(groups.values(), key=lambda g: -g["bytes"]))
    with (OUT / "classified_files_final.json.gz").open("xb") as stream:
        stream.write(gzip.compress(json.dumps(classified, separators=(",", ":")).encode(), mtime=0))
    proposal = {"dry_run": True, "deleted": False, "approval_required": True,
                "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "registry_sha256": sha(ROOT / ".cache/.cache-index.json"),
                "columns": ["path", "logical_bytes", "mtime_ns"],
                "apply_guard": "No apply action exists. Approval must name exact tiers and plan hash. Before deletion verify frozen plan hash, registry hash, every listed file size/mtime and saved SHA-256, dependency closure, no active writer; abort if changed. Do not rescan to add candidates; never prune during a sealed run.",
                "tiers": {k: {"bytes": sum(r[1] for r in v), "files": len(v), "entries": v} for k, v in sorted(proposed.items())},
                "totals": totals, "refinement_bytes": changes,
                "notes": ["No native caches, baseline/performance keys, registered current files, models, references or frontend caches are proposed.",
                          "T1/T2/T4 are outside normal registered-only pruning policy and require explicit owner approval for those precise paths.",
                          "T3 requires explicit retirement of older pre-Step-15 replay caches mentioned by tracked historical records."]}
    write("prune_proposal.json", proposal)
    print("final categories", dict(totals), "tiers", {k: sum(r[1] for r in v) for k, v in proposed.items()}, flush=True)


def seal():
    import time
    from concurrent.futures import ThreadPoolExecutor

    proposal_path = OUT / "prune_proposal_v2.json"
    proposal = json.loads(proposal_path.read_text())
    assert sha(ROOT / ".cache/.cache-index.json") == proposal["registry_sha256"]
    rows = json.loads(gzip.decompress((OUT / "inventory.json.gz").read_bytes()))
    by_path = {r[0]: r for r in rows}
    index = json.loads((OUT / "registry_snapshot.json").read_text())
    current_files = {".cache/" + p.replace("\\", "/") for eid in index["current"].values() for p in index["entries"][eid]["files"]}
    seen, receipts, started = set(), [], time.monotonic()
    protected = json.loads((OUT / "dependencies.json").read_text())
    roots = protected["protected_roots"]
    def checked_hash(item):
        p, size, mtime = item
        path = ROOT / p
        path.resolve().relative_to(ROOT.resolve())
        before = path.stat()
        assert (before.st_size, before.st_mtime_ns) == (size, mtime), p
        digest = sha(path)
        after = path.stat()
        assert (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_size, after.st_mtime_ns, after.st_ctime_ns), p
        return [p, digest, before.st_ctime_ns]

    for data in proposal["tiers"].values():
        for p, _, _ in data["entries"]:
            assert p not in seen and p not in current_files
            assert not any(p == f or p.startswith(f + "/") for f in roots), p
            assert not p.startswith(("frontend_temp/", ".cache/external/", ".cache/models/", ".cache/huggingface/", ".cache/step6b/models/", ".cache/step16/ocr/")), p
            assert "/native/" not in p and "/analysis/" not in p, p
            seen.add(p)
    with ThreadPoolExecutor(max_workers=4) as workers:
        for tier, data in proposal["tiers"].items():
            for count, receipt in enumerate(workers.map(checked_hash, data["entries"], buffersize=32), 1):
                receipts.append(receipt)
                if count % 10000 == 0:
                    print("sealed", tier, count, round(time.monotonic() - started, 1), flush=True)
            print("tier receipt complete", tier, len(data["entries"]), flush=True)
    receipt_path = OUT / "candidate_hashes.json.gz"
    with receipt_path.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(receipts, separators=(",", ":")).encode(), mtime=0))
    # Actual byte duplicates of model files, distinct from different book fingerprints.
    possible, exact = defaultdict(list), defaultdict(list)
    for row in rows:
        p, size, *_ = row
        if size >= 1_000_000 and ("/huggingface/" in p or p.startswith(".cache/step6b/models/")):
            possible[size].append(p)
    for size, paths in possible.items():
        if len(paths) < 2:
            continue
        for p in paths:
            stat = (ROOT / p).stat()
            assert [stat.st_size, stat.st_mtime_ns] == by_path[p][1:3], p
            exact[(size, sha(ROOT / p))].append(p)
    duplicate_models = [{"bytes_each": size, "sha256": digest, "paths": paths,
                         "duplicate_logical_bytes": size * (len(paths) - 1), "proposed_for_deletion": False,
                         "reason": "Model protection and frontend runtime ownership; sharing requires a separate reviewed configuration change."}
                        for (size, digest), paths in exact.items() if len(paths) > 1]
    write("exact_model_duplicates.json", sorted(duplicate_models, key=lambda d: -d["duplicate_logical_bytes"]))
    frozen = json.loads((ROOT / "experiments/out/step17b/evidence_manifest.json").read_text())
    for p, record in frozen["files"].items():
        assert sha(ROOT / p) == record["sha256"], p
    frozen_inputs_path = ROOT / "experiments/out/step17b/final/validation/final_suite_inputs.json"
    frozen_inputs = json.loads(frozen_inputs_path.read_text())
    write("prune_plan.json", {"dry_run": True, "deleted": False, "approval_required": True,
          "created": datetime.now(timezone.utc).isoformat(), "target_commit": proposal["head"],
          "proposal_path": proposal_path.relative_to(ROOT).as_posix(), "proposal_sha256": sha(proposal_path),
          "candidate_hash_receipt": receipt_path.relative_to(ROOT).as_posix(), "candidate_hash_receipt_sha256": sha(receipt_path),
          "hash_receipt_columns": ["path", "file_sha256", "ctime_ns"],
          "registry_sha256": sha(ROOT / ".cache/.cache-index.json"),
          "tiers": {k: {f: v[f] for f in ("files", "bytes")} for k, v in proposal["tiers"].items()},
          "files_hash_verified": len(receipts), "bytes": sum(v["bytes"] for v in proposal["tiers"].values()),
          "category_totals": proposal["totals"], "free_bytes_after_audit": shutil.disk_usage(ROOT).free,
          "step17b_evidence_files_rechecked": len(frozen["files"]),
          "frozen_input_record_sha256": sha(frozen_inputs_path), "frozen_input_record_keys": list(frozen_inputs),
          "apply_guard": proposal["apply_guard"],
          "unreadable_subtrees_excluded": json.loads((OUT / "inventory_summary.json").read_text())["errors"],
          "approval_scope": "No existing deletion authorization applies to this new proposal. Stop for the owner's explicit tier/plan approval.",
          "fresh_spanish_check": "NOT RUN; no proof reused; target remains d0625e8. No holdout or sealed run started."})
    print("read-only sealing completed", len(receipts), round(time.monotonic() - started, 1), flush=True)


if __name__ == "__main__":
    if "--seal" in sys.argv:
        seal()
    elif "--refine" in sys.argv:
        refine()
    elif "--analyze" in sys.argv:
        analyze()
    else:
        inventory()
