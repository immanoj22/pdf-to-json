"""Render the read-only inventory and tier proposal; no cache writes/deletion."""
# Paragraphs are intentionally assembled from wrapped string literals.
# ruff: noqa: ISC004

import json
from collections import Counter

from cache_audit_readonly import OUT, ROOT, sha

BOOKS = ("spanish_us_history", "immigrant_children", "art_therapy_index", "medical_anatomy", "statistics")
SHORT = dict(zip(BOOKS, ("S", "I", "A", "M", "T")))


def load(name):
    return json.loads((OUT / name).read_text("utf-8"))


def main():
    folders = load("folder_audit_final.json")
    raw = {g["path"]: g for g in load("folder_audit.json")}
    proposal = load("prune_proposal_v2.json")
    deps, archives = load("dependencies.json"), load("archive_identities.json")
    summary = load("inventory_summary.json")
    models = load("exact_model_duplicates.json")
    plan = load("prune_plan_final.json")
    final_exclusions = {r[0] for r in plan["additional_exclusions"]}
    for tier in proposal["tiers"].values():
        tier["entries"] = [r for r in tier["entries"] if r[0] not in final_exclusions]
        tier["files"] = len(tier["entries"])
        tier["bytes"] = sum(r[1] for r in tier["entries"])
    entries = load("registry_entries.json")
    snapshots = load("unregistered_identities.json")
    timing = deps["timings"]
    total = sum(proposal["totals"].values())
    selected = sum(t["bytes"] for t in proposal["tiers"].values())
    lines = ["# Read-only project cache audit — 24 October 2026", "",
             f"**Nothing deleted.** The readable inventory contains **{summary['files']:,} files / {total:,} bytes ({total/1e9:.3f} GB)**. "
             f"The four conditional proposal tiers contain **{selected:,} bytes ({selected/1e9:.3f} GB)**. "
             f"There are **{len(summary['errors'])} access-denied subtrees with unknown additional size**; they are excluded from every tier. "
             "The ranking and totals are therefore lower bounds for the readable scope, not an assertion that inaccessible folders are empty.", "",
             f"Inventory: {summary['started']} to {summary['finished']}. HEAD remains `{summary['head']}`. "
             f"Free space at inventory completion: {summary['free_bytes']:,} bytes; at proposal sealing: **{plan['free_bytes_after_audit']:,} bytes**. "
             "Free space varies with other processes; the sealed measurement is a point-in-time observation. Approval does not replace a new reserve preflight.", "",
             "Only new audit helpers/reports were written. Helper validation updated Ruff's own lint-cache file; the entire lint cache (23 inventoried files, 37,138 bytes) was removed from the proposal. "
             "A further 94 bytecode files (1,263,941 bytes) inside cached historical source/evidence snapshots were excluded from the safest tier. "
             "Subsequent validation uses `--no-cache`. No converter cache, baseline, publication, registry, model, gold/reference/ledger, Git configuration or old project was edited. "
             "No hold-out, fresh Spanish invariant run, Step 18 or adapter was started. No proof was reused for this audit.", "",
             "## Category totals", "",
             "Each inventoried file occurs once. These are logical file lengths, not NTFS allocation measurements; directory overhead, compression, open handles and later changes can affect actual free-space gains. "
             "No hard-linked files or traversed links were found in the readable inventory. Environments, dependencies under `node_modules`, Git internals, and ordinary non-cache outputs are outside scope. "
             "Project `.cache`, frontend runtime caches, Python bytecode, named test caches and `.s17bt` retained test scratch are included.", "",
             "| Category | Bytes | GB | Meaning |", "|---|---:|---:|---|"]
    meanings = {
        "needed_for_freeze": "Conservative retention set: baseline/parity/current-registry inputs, current publications, runtime models/assets, protected source/reference bundles, frontend-owned data. Not every file is read by every gate.",
        "rebuildable": "Known derived/tool/model material; some remains protected by ownership/model policy or unresolved evidence references. Rebuildable does not mean approved to remove.",
        "superseded": "Old registered producer versions or identified historical archives outside the protected Step 15–17b set. Historical replay is lost if removed.",
        "unknown": "Unregistered or incompletely traced lifecycle/dependencies. Book identity may be known while retirement safety or exact historical rebuilding remains unproved. Inaccessible bytes are additional, unquantified.",
    }
    for key in ("needed_for_freeze", "rebuildable", "superseded", "unknown"):
        n = proposal["totals"][key]
        lines.append(f"| {key.replace('_', ' ')} | {n:,} | {n/1e9:.3f} | {meanings[key]} |")
    lines += ["", "## Top 30 readable folders", "",
              "Rows are disjoint cache/stage groups, so parent/child bytes are not double-counted. Exact subfolder/fingerprint paths, per-book bytes and category splits are in "
              "[folder_audit_final.json](../experiments/out/cache_audit_20261024/folder_audit_final.json), "
              "[registry_entries.json](../experiments/out/cache_audit_20261024/registry_entries.json) and "
              "[archive_identities.json](../experiments/out/cache_audit_20261024/archive_identities.json). "
              "S = Spanish history; I = immigrant children; A = art therapy; M = medical anatomy; T = Statistics. "
              "`15/16/17/17b` indicates an explicit recorded baseline/performance input. `C` = current registry; `R` = shared runtime; `P` = protected model/reference policy; `D` = indirect native dependency closure; `F` = frontend ownership. "
              "‘Mixed’ means prune only the exact proposed files, never the parent folder.", "",
              "Rebuild times below are honest limits of existing evidence. No cold reconstruction was launched in this read-only task. "
              "A recorded stage pass may mostly read cache hits; it is **not a cold rebuild estimate**. Exact old fingerprints require their historical producer, configuration and runtime; current code produces new keys. "
              "`Unknown` means no defensible elapsed-time measurement exists, rather than a zero-cost rebuild.", "",
              "| # | Folder | GB | Book / stage | Uses and reason previous dry run kept it | Rebuild and time |", "|---:|---|---:|---|---|---|"]
    for number, g in enumerate(folders[:30], 1):
        path = g["path"]
        uses = set(raw.get(path, {}).get("uses", {})) | set(g["uses"])
        flags = [s.removeprefix("step") for s in ("step15", "step16", "step17", "step17b") if any(u.startswith(s + ":") for u in uses)]
        if "current registry" in uses:
            flags.append("C")
        if path.startswith("frontend_temp/"):
            flags.append("F/P")
        if "/native" in path:
            flags.append("D")
        book_names = [SHORT[b] for b in BOOKS if any(b in name for name in g["books"])]
        book = "/".join(book_names) or "shared / unverified source"
        stage = path.rsplit("/", 1)[-1]
        rebuild = "Current derived data can be regenerated; exact old identity/time unproved."
        reason = ",".join(flags) + "; " if flags else "No direct 15–17b record mapped; "
        if "/final_books" in path:
            stage = "semantic archives + publications"
            reason += "mixed baselines/history; unregistered outputs excluded by earlier policy. T4 selects only unneeded historical folders."
            rebuild = "Current archive/publication rebuildable; historical exact rebuild unknown. See five-book timings below."
        elif path == ".cache/step16/ocr":
            book, stage = "shared", "OCR packs, readers, downloads/build tree"
            reason = "16/17/17b/R/P; model/runtime assets and unregistered build files protected. No OCR asset proposed."
            rebuild = "Pinned assets can be reacquired; 2.83 GB local material, network/build time unmeasured."
        elif "/huggingface/" in path or path == ".cache/step6b/models":
            book, stage = "shared", "model: " + stage.removeprefix("models--")
            protection = "P; optional/older model, protected by standing instructions. " if set(g["categories"]) == {"rebuildable"} else "R/P; pinned runtime model, protected. "
            reason = ("F/P; frontend server owns this cache. " if path.startswith("frontend_temp") else protection) + "Unregistered models were outside the old prune scope."
            rebuild = "Reacquire pinned model bytes; download time unknown. Models remain excluded even when duplicate."
        elif path == ".cache/external/osbooks-college-algebra-bundle-1e":
            book, stage = "math hold-out", "sealed source/reference bundle"
            reason = "P; source/reference material, never a pruning candidate. Not a converted hold-out cache."
            rebuild = "Do not rebuild/alter as cache; preserve verified original bundle. Reacquisition time unknown."
        elif path.startswith(".cache/objects/native"):
            book, stage = "fixture families / excerpt source hashes; some unmapped", "legacy native objects"
            reason = "D; indirect retained-analysis dependencies; 15 restored fixture files demonstrate why tracked-key checks alone are insufficient. Unregistered/unknown identity protection."
            rebuild = "Some fixtures can be regenerated; exact old versions and elapsed time unproved. No native deletion proposed."
        elif path == ".cache/step11c/book300":
            book, stage = "S, explicit 300-page excerpt", "Step 11c performance/parity experiment"
            reason = "Earlier performance/parity evidence, not direct 15–17b input; unregistered + incompletely traced nested outputs, including access-denied children. Kept."
            rebuild = "Source known: step11c/book300/source.json. Historical cold production 22.60 min; resumed development 6.95 min; exact old environment required."
        elif path.startswith(".cache/step6b/math_"):
            book = "science_pdf (earlier development, not math hold-out)"
            reason = "Step 6b historical evidence, unregistered; exact retirement closure not established. Kept."
            rebuild = "General derivation exists. Recorded detector 2,233.90 s + cached evidence pass 166.96 s; not a measured cold rebuild of this folder."
        elif path == ".cache/step13b/bundles":
            reason = "All five; development-only math input bundles; no direct immutable gate dependence. Unregistered files excluded by prior policy. Conditional T2."
            rebuild = "step13b_bundles.py; historical stage inputs needed. T3 also proposes four of its registered input keys per book. Exact rebuild after T3 needs those old stages restored; time unknown."
        elif path in {".s17bt", ".cache/t17_all_entry_levels", ".cache/t22"}:
            book, stage = "synthetic/repository test fixtures", "retained test scratch"
            reason = "Earlier/final test receipt references need deeper path closure; not required as fresh test inputs. Unregistered scratch excluded by old plan. Kept from proposal."
            rebuild = "Regenerated by relevant tests. Full current suite measured 17m56s; exact scratch recreation unmeasured."
        elif path == ".cache/step16/downstream":
            book, stage = "S/I/M/T, derived native/scan pairs", "Step 16 downstream comparison"
            reason = "16 comparison/P; paired rasters and conversion inputs retained for replay; unregistered outside old plan."
            rebuild = "step16_downstream.py; source/native stages retained, OCR/model time unmeasured."
        elif path == ".cache/step6/document":
            book, stage = "four old development document keys; exact file-to-book mapping unverified", "Step 6 document analysis"
            reason = "Historical Step 6/8 evidence; not a direct current gate input. Unregistered, lifecycle/provenance unresolved. Kept."
            rebuild = "Historical document-analysis producer/config required; cold time unknown."
        else:
            if stage in {"native", "analysis"}:
                reason += "current/baseline inputs and indirect native/analysis dependency closure retained in full; no files from this group proposed."
            else:
                reason += "current/baseline portion protected; old registered producers only in T3; unregistered portions kept."
            stage_name = stage
            recorded = sum(v["stages_wall_seconds"].get(stage_name, 0) for v in timing.values())
            rebuild = f"Current stage regenerable; cold time unknown. Recorded five-book stage passes total {recorded:.1f} s (mixed cache state)."
        lines.append(f"| {number} | `{path}` | {g['bytes']/1e9:.3f} | {book}; {stage} | {reason} | {rebuild} |")
    lines += ["", "## Baselines, parity and the future freeze", "",
              f"The dependency map reads **{len(deps['performance_records'])} Step 15/16/17/17b performance records**, plus Step 17b before-publication and worker-parity paths. "
              "Every actual `cache_keys` value, named output/publication and assembly-history publication is protected, including unregistered files containing a protected key in their path. "
              "Every current registry file is excluded. Tracked mentions are separately reported; a key found only in an old cleanup list is not represented as a live Step 15–17b dependency. "
              "Old native caches and retained analyses are conservatively kept as a closure set rather than repeating the earlier fixture cleanup gap.", "",
              "There is **no local Step 18 freeze-check specification or tag**. For capacity planning the future-freeze retention set preserves all the above, "
              "the latest five publications and their archives, pinned runtime assets, and the selected review commit `d0625e8`. This is an explicit conservative assumption, not a claim to have run a Step 18 gate. "
              "The pending fresh Spanish I1–I7 needs the 758-page native/analysis/layout/list keys recorded in Step 17b; all remain protected. It has **not run**. "
              "The old approved Step 17b proof reuse stays recorded as historical evidence, never relabelled fresh.", "",
              "The earlier empty disk-budget dry run protected every registered fingerprint with any tracked witness, all native caches, all unregistered files and every current entry. "
              "Its zero eligible bytes was correct for that narrow policy; it did not prove that the whole disk was indispensable. "
              "The new conditional T3 separates live baseline inputs from earlier tracked replay history. T1/T2/T4 deliberately need explicit approval beyond ordinary registered-only pruning. "
              "Per-entry reasons and all tracked witnesses are retained in registry_entries.json. Access-denied subtree paths and errors are in inventory_summary.json and prune_plan.json; no ACL/ownership changes were attempted.", "",
              "## Duplicate books, fingerprints and profiles", "",
              "Different keys for the same source are version/configuration variants, not automatically identical data. The registry alone has 69 book/stage groups with multiple existing fingerprints. "
              "The following table lists every populated registered stage; unregistered list/paragraph/furniture variants are separately mapped in unregistered_identities.json (sampled identity, not full-payload validation).", "",
              "| Stage | S | I | A | M | T |", "|---|---:|---:|---:|---:|---:|"]
    for stage in sorted({e["stage"] for e in entries}):
        counts = [sum(e["book"] == b and e["stage"] == stage and bool(e["files"]) for e in entries) for b in BOOKS]
        lines.append("| " + stage + " | " + " | ".join(map(str, counts)) + " |")
    lines += ["", "Every full key, producer, book source hash, size, current status and protection reason is listed in "
              "[duplicates_by_book_stage.json](../experiments/out/cache_audit_20261024/duplicates_by_book_stage.json). "
              "Additional mapped unregistered source/stage variants are indexed in "
              "[all_identified_fingerprint_folders.json](../experiments/out/cache_audit_20261024/all_identified_fingerprint_folders.json).", "",
              "| Book | Semantic archives | Publications | Total GB |", "|---|---:|---:|---:|"]
    for b in BOOKS:
        cohort = [a for a in archives if a["book"] == b]
        lines.append(f"| {b} | {sum(a['type']=='semantic archive' for a in cohort)} | {sum(a['type']=='publication' for a in cohort)} | {sum(a['bytes'] for a in cohort)/1e9:.3f} |")
    lines += ["", "Across 30 identified publications, 29 use default profile 1.0.0 / `cbf9a836…`; the earlier art smoke publication "
              "`book-2d5f3235…` uses default 1.0.0 / `8b811d31…`. It is protected by the Step 17 smoke performance record. "
              "Matching profile versions with different hashes are not interchangeable. Publications also have distinct assembly producer/content hashes even when profile hashes match.", "",
              f"**{len(models)} exact model-file duplicate groups** were independently SHA-256 checked, with **{sum(m['duplicate_logical_bytes'] for m in models):,} duplicate logical bytes**. "
              "They include root/frontend model copies. Models remain protected; no model or frontend file is proposed. Exact paths, keep-all decision and hashes are in "
              "[exact_model_duplicates.json](../experiments/out/cache_audit_20261024/exact_model_duplicates.json). This task does not change model-sharing settings or stop the frontend server.", "",
              "## Rebuild timing evidence", "",
              "These are recorded complete Step 17 archive runs (original assembly included) and separately measured current Step 17b publication refreshes. "
              "They are contextual measurements, not promises for an uncached run or every old fingerprint. Do not add the archive and refresh columns and call that a new measured end-to-end run.", "",
              "| Book | Recorded archive run s | Step 17b publication refresh s |", "|---|---:|---:|"]
    for b in BOOKS:
        t = timing[b]
        lines.append(f"| {b} | {t['archive_complete_wall_seconds']:.1f} | {t['publication_wall_seconds']:.1f} |")
    lines += ["", "The table-development bundle timings observed in final parity logs total **2,880 seconds (48 minutes)** across five books: "
              "Spanish 2,539 s (bounded reader), immigrant 220 s, art 2 s, anatomy 37 s, Statistics 82 s. The separate Step 13b math bundles have no recorded comparable cold rebuild time. "
              "Native/analysis and current Step 17b stage inputs remain available. The current parity bundle set under `step15/pages` has no proposed input keys. "
              "The older `step14b/pages` set has six proposed input keys per book, and opcode-only inspection of each Step 13b book bundle identifies four registered input keys per book in T3. "
              "Thus T2 alone removes rebuildable conveniences, but T2+T3 also retires part of their historical upstream cache. Exact old-bundle reconstruction would first need those stages restored under historical code/configuration; its elapsed cost is unknown. "
              "This interaction is recorded in [bundle_rebuild_dependencies.json](../experiments/out/cache_audit_20261024/bundle_rebuild_dependencies.json). "
              "No pickle was executed. Spanish current-parity regeneration must use the verified bounded table reader under the present resource limits.", "",
              "## Proposed tiers — approval required", "",
              "These tiers are disjoint exact file lists. They are not folder wildcards, and approval of a parent folder would be too broad. "
              "The hash receipts cover every listed file; before any approved operation, abort if the plan/registry/file bytes, metadata, dependencies or live-writer state changed. "
              "No rescan may add deletions. Never prune during a sealed run.", "",
              "| Tier | Files | Bytes freed (logical) | GB | Rebuild/replay cost and approval meaning |", "|---|---:|---:|---:|---|"]
    costs = {
        "T1_tool_caches": "Pip download cache, current backend/experiment bytecode, pytest metadata. No converter recomputation; automatic repopulation, download time unmeasured. Ruff and cached historical-source bytecode excluded. Explicit unregistered-tool-cache approval.",
        "T2_dev_bundles": "Math/table development bundles in .cache/step13b/bundles, step14b/pages and step15/pages. Current table-parity rebuild observed 48 min; math bundle time unknown. T3 also retires some old bundle inputs, so exact historical rebuilding then needs upstream restoration. Current freeze/parity inputs remain intact. Explicit unregistered-bundle approval.",
        "T3_superseded_registered": "Older producers from the five development books, outside current/15–17b keys. Retires pre-Step-15 replay convenience; cold recomputation and exact old-environment restoration unmeasured. Older tracked references will point to removed caches. Explicit historical-cache retirement approval.",
        "T4_historical_archives": "Identified older development semantic archives/publications outside protected output/history roots. Removes old intermediate replay artifacts, preserves recorded 15–17b baselines and latest outputs. Exact old rebuild may require historical code/environment; time unknown (five-book contextual timings above). Explicit archive-retirement approval.",
    }
    for k, v in proposal["tiers"].items():
        lines.append(f"| {k} | {v['files']:,} | {v['bytes']:,} | {v['bytes']/1e9:.3f} | {costs[k]} |")
    lines += ["", f"**All tiers: {sum(t['files'] for t in proposal['tiers'].values()):,} files / {selected:,} bytes ({selected/1e9:.3f} GB).** "
              f"If all bytes were reclaimed at the sealing free-space snapshot, free space would be about {(plan['free_bytes_after_audit']+selected)/1e9:.3f} GB, before filesystem effects and concurrent activity. "
              "T1+T2 alone reclaim about 1.335 GB. Even all tiers do not supply the earlier three-book retained-storage plan of 33.223 GB free including reserve (39.223 GB with provisional transient headroom). "
              "They may provide room for a future isolated Spanish retry, subject to a fresh 11 GB provisional headroom preflight and reserve monitoring; this audit does not start it.", "",
              "Recommended review order is T1, then T2; approve T3/T4 only if retiring those historical replay copies is acceptable. "
              "Unknown/unreadable caches, native closure, current registry, baseline/parity publications, gold/references/ledger, models and frontend runtime data remain excluded. "
              "No broader cleanup is authorized by approval of an earlier Step 17 list.", "",
              f"The approval target is [prune_plan_final.json](../experiments/out/cache_audit_20261024/prune_plan_final.json), SHA-256 **`{sha(OUT/'prune_plan_final.json')}`**. "
              "It binds [prune_proposal_v2.json](../experiments/out/cache_audit_20261024/prune_proposal_v2.json), subtracts its explicit 94-file exclusion list, and binds the final compressed per-file SHA-256/ctime receipt. "
              "The final receipt is the authoritative selection; older first-pass proposals and prune_plan.json are retained for provenance and are superseded, not approval targets.", "",
              f"Sealing rechecked {plan['step17b_evidence_files_rechecked']} frozen Step 17b evidence files. "
              "The final audit validation separately rechecks the 333 frozen source/report/helper inputs, registry and plan arithmetic. "
              "No converter tests or reprocessing are needed for this report-only change. Helpers pass Ruff with `--no-cache`. "
              "The audit files are uncommitted review artifacts; the frozen Step 17b review commit is unchanged. **Stop for the owner's explicit tier/plan approval.**", ""]
    target = ROOT / "docs/cache_audit_20261024.md"
    if target.exists():
        assert target.read_text("utf-8").startswith(lines[0] + "\n")
    target.write_text("\n".join(lines), "utf-8", newline="\n")
    # Index of unregistered fingerprints for readers needing all paths rather than
    # the top-30 aggregates. Prefix identities do not establish payload validity.
    counts = Counter()
    for folder, d in snapshots.items():
        if any(len(part) == 64 for part in folder.split("/")):
            counts[";".join(d["books"])] += 1
    report_index = {"report": target.relative_to(ROOT).as_posix(), "report_sha256": sha(target),
                    "unregistered_identity_folder_counts": counts,
                    "category_bytes_sum": total, "proposed_bytes_sum": selected}
    (OUT / "report_index.json").write_text(json.dumps(report_index, indent=1), "utf-8")


if __name__ == "__main__":
    main()
