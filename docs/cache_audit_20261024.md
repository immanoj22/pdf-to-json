# Read-only project cache audit — 24 October 2026

**Nothing deleted.** The readable inventory contains **442,594 files / 34,309,865,864 bytes (34.310 GB)**. The four conditional proposal tiers contain **9,180,741,193 bytes (9.181 GB)**. There are **51 access-denied subtrees with unknown additional size**; they are excluded from every tier. The ranking and totals are therefore lower bounds for the readable scope, not an assertion that inaccessible folders are empty.

Inventory: 2026-10-24T02:12:22.713668+00:00 to 2026-10-24T02:13:02.216742+00:00. HEAD remains `d0625e841c6793dea6de7c2cb4a87e31694ff2c3`. Free space at inventory completion: 5,138,989,056 bytes; at proposal sealing: **5,717,512,192 bytes**. Free space varies with other processes; the sealed measurement is a point-in-time observation. Approval does not replace a new reserve preflight.

Only new audit helpers/reports were written. Helper validation updated Ruff's own lint-cache file; the entire lint cache (23 inventoried files, 37,138 bytes) was removed from the proposal. A further 94 bytecode files (1,263,941 bytes) inside cached historical source/evidence snapshots were excluded from the safest tier. Subsequent validation uses `--no-cache`. No converter cache, baseline, publication, registry, model, gold/reference/ledger, Git configuration or old project was edited. No hold-out, fresh Spanish invariant run, Step 18 or adapter was started. No proof was reused for this audit.

## Category totals

Each inventoried file occurs once. These are logical file lengths, not NTFS allocation measurements; directory overhead, compression, open handles and later changes can affect actual free-space gains. No hard-linked files or traversed links were found in the readable inventory. Environments, dependencies under `node_modules`, Git internals, and ordinary non-cache outputs are outside scope. Project `.cache`, frontend runtime caches, Python bytecode, named test caches and `.s17bt` retained test scratch are included.

| Category | Bytes | GB | Meaning |
|---|---:|---:|---|
| needed for freeze | 15,227,496,296 | 15.227 | Conservative retention set: baseline/parity/current-registry inputs, current publications, runtime models/assets, protected source/reference bundles, frontend-owned data. Not every file is read by every gate. |
| rebuildable | 5,342,482,258 | 5.342 | Known derived/tool/model material; some remains protected by ownership/model policy or unresolved evidence references. Rebuildable does not mean approved to remove. |
| superseded | 7,845,579,054 | 7.846 | Old registered producer versions or identified historical archives outside the protected Step 15–17b set. Historical replay is lost if removed. |
| unknown | 5,894,308,256 | 5.894 | Unregistered or incompletely traced lifecycle/dependencies. Book identity may be known while retirement safety or exact historical rebuilding remains unproved. Inaccessible bytes are additional, unquantified. |

## Top 30 readable folders

Rows are disjoint cache/stage groups, so parent/child bytes are not double-counted. Exact subfolder/fingerprint paths, per-book bytes and category splits are in [folder_audit_final.json](../experiments/out/cache_audit_20261024/folder_audit_final.json), [registry_entries.json](../experiments/out/cache_audit_20261024/registry_entries.json) and [archive_identities.json](../experiments/out/cache_audit_20261024/archive_identities.json). S = Spanish history; I = immigrant children; A = art therapy; M = medical anatomy; T = Statistics. `15/16/17/17b` indicates an explicit recorded baseline/performance input. `C` = current registry; `R` = shared runtime; `P` = protected model/reference policy; `D` = indirect native dependency closure; `F` = frontend ownership. ‘Mixed’ means prune only the exact proposed files, never the parent folder.

Rebuild times below are honest limits of existing evidence. No cold reconstruction was launched in this read-only task. A recorded stage pass may mostly read cache hits; it is **not a cold rebuild estimate**. Exact old fingerprints require their historical producer, configuration and runtime; current code produces new keys. `Unknown` means no defensible elapsed-time measurement exists, rather than a zero-cost rebuild.

| # | Folder | GB | Book / stage | Uses and reason previous dry run kept it | Rebuild and time |
|---:|---|---:|---|---|---|
| 1 | `.cache/step11d2/final_books` | 10.056 | S/I/A/M; semantic archives + publications | 15,16,17,17b; mixed baselines/history; unregistered outputs excluded by earlier policy. T4 selects only unneeded historical folders. | Current archive/publication rebuildable; historical exact rebuild unknown. See five-book timings below. |
| 2 | `.cache/step16/ocr` | 2.834 | shared; OCR packs, readers, downloads/build tree | 16/17/17b/R/P; model/runtime assets and unregistered build files protected. No OCR asset proposed. | Pinned assets can be reacquired; 2.83 GB local material, network/build time unmeasured. |
| 3 | `.cache/step7/figures` | 2.359 | S/I/A/M/T; figures | 15,16,17,17b,C; current/baseline portion protected; old registered producers only in T3; unregistered portions kept. | Current stage regenerable; cold time unknown. Recorded five-book stage passes total 9.0 s (mixed cache state). |
| 4 | `.cache/step6b/models` | 2.042 | shared; model: models | P; optional/older model, protected by standing instructions. Unregistered models were outside the old prune scope. | Reacquire pinned model bytes; download time unknown. Models remain excluded even when duplicate. |
| 5 | `.cache/step7/native` | 1.843 | S/I/A/M/T; native | 15,16,17,17b,C,D; current/baseline inputs and indirect native/analysis dependency closure retained in full; no files from this group proposed. | Current stage regenerable; cold time unknown. Recorded five-book stage passes total 1123.3 s (mixed cache state). |
| 6 | `.cache/step11/lists` | 1.697 | S/I/A/M/T; lists | 15,16,17,17b,C; current/baseline portion protected; old registered producers only in T3; unregistered portions kept. | Current stage regenerable; cold time unknown. Recorded five-book stage passes total 19.8 s (mixed cache state). |
| 7 | `.cache/step7/analysis` | 1.180 | S/I/A/M/T; analysis | 15,16,17,17b,C; current/baseline inputs and indirect native/analysis dependency closure retained in full; no files from this group proposed. | Current stage regenerable; cold time unknown. Recorded five-book stage passes total 544.9 s (mixed cache state). |
| 8 | `.cache/step13/final_books` | 1.056 | T; semantic archives + publications | 15,16,17,17b; mixed baselines/history; unregistered outputs excluded by earlier policy. T4 selects only unneeded historical folders. | Current archive/publication rebuildable; historical exact rebuild unknown. See five-book timings below. |
| 9 | `.cache/step13b/bundles` | 1.022 | S/I/A/M/T; bundles | All five; development-only math input bundles; no direct immutable gate dependence. Unregistered files excluded by prior policy. Conditional T2. | step13b_bundles.py; historical stage inputs needed. T3 also proposes four of its registered input keys per book. Exact rebuild after T3 needs those old stages restored; time unknown. |
| 10 | `.cache/step11c/book300` | 0.848 | S, explicit 300-page excerpt; Step 11c performance/parity experiment | Earlier performance/parity evidence, not direct 15–17b input; unregistered + incompletely traced nested outputs, including access-denied children. Kept. | Source known: step11c/book300/source.json. Historical cold production 22.60 min; resumed development 6.95 min; exact old environment required. |
| 11 | `.cache/huggingface/models--PaddlePaddle--PP-FormulaNet-L_safetensors` | 0.729 | shared; model: PaddlePaddle--PP-FormulaNet-L_safetensors | R/P; pinned runtime model, protected. Unregistered models were outside the old prune scope. | Reacquire pinned model bytes; download time unknown. Models remain excluded even when duplicate. |
| 12 | `frontend_temp/runtime/cache/huggingface/models--PaddlePaddle--PP-FormulaNet-L_safetensors` | 0.729 | shared; model: PaddlePaddle--PP-FormulaNet-L_safetensors | F/P; frontend server owns this cache. Unregistered models were outside the old prune scope. | Reacquire pinned model bytes; download time unknown. Models remain excluded even when duplicate. |
| 13 | `.cache/step6b/math_objects` | 0.644 | science_pdf (earlier development, not math hold-out); math_objects | Step 6b historical evidence, unregistered; exact retirement closure not established. Kept. | General derivation exists. Recorded detector 2,233.90 s + cached evidence pass 166.96 s; not a measured cold rebuild of this folder. |
| 14 | `.cache/step9/paragraphs` | 0.547 | S/I/A/M/T; paragraphs | 15,16,17,17b,C; current/baseline portion protected; old registered producers only in T3; unregistered portions kept. | Current stage regenerable; cold time unknown. Recorded five-book stage passes total 71.0 s (mixed cache state). |
| 15 | `.cache/huggingface/models--HuggingFaceTB--SmolVLM-256M-Instruct` | 0.518 | shared; model: HuggingFaceTB--SmolVLM-256M-Instruct | P; optional/older model, protected by standing instructions. Unregistered models were outside the old prune scope. | Reacquire pinned model bytes; download time unknown. Models remain excluded even when duplicate. |
| 16 | `.cache/objects/native` | 0.485 | fixture families / excerpt source hashes; some unmapped; legacy native objects | D; indirect retained-analysis dependencies; 15 restored fixture files demonstrate why tracked-key checks alone are insufficient. Unregistered/unknown identity protection. | Some fixtures can be regenerated; exact old versions and elapsed time unproved. No native deletion proposed. |
| 17 | `.cache/external/osbooks-college-algebra-bundle-1e` | 0.449 | math hold-out; sealed source/reference bundle | P; source/reference material, never a pruning candidate. Not a converted hold-out cache. | Do not rebuild/alter as cache; preserve verified original bundle. Reacquisition time unknown. |
| 18 | `.cache/huggingface/models--wanderkid--unimernet_tiny` | 0.432 | shared; model: wanderkid--unimernet_tiny | P; optional/older model, protected by standing instructions. Unregistered models were outside the old prune scope. | Reacquire pinned model bytes; download time unknown. Models remain excluded even when duplicate. |
| 19 | `.cache/huggingface/models--docling-project--docling-models` | 0.358 | shared; model: docling-project--docling-models | R/P; pinned runtime model, protected. Unregistered models were outside the old prune scope. | Reacquire pinned model bytes; download time unknown. Models remain excluded even when duplicate. |
| 20 | `frontend_temp/runtime/cache/huggingface/models--docling-project--docling-models` | 0.358 | shared; model: docling-project--docling-models | F/P; frontend server owns this cache. Unregistered models were outside the old prune scope. | Reacquire pinned model bytes; download time unknown. Models remain excluded even when duplicate. |
| 21 | `.cache/step7/layout` | 0.225 | S/I/A/M/T; layout | 15,16,17,17b,C; current/baseline portion protected; old registered producers only in T3; unregistered portions kept. | Current stage regenerable; cold time unknown. Recorded five-book stage passes total 455.0 s (mixed cache state). |
| 22 | `.cache/step6b/math_rasters` | 0.216 | science_pdf (earlier development, not math hold-out); math_rasters | Step 6b historical evidence, unregistered; exact retirement closure not established. Kept. | General derivation exists. Recorded detector 2,233.90 s + cached evidence pass 166.96 s; not a measured cold rebuild of this folder. |
| 23 | `.cache/step8/furniture` | 0.207 | S/I/A/M/T; furniture | 15,16,17,17b,C; current/baseline portion protected; old registered producers only in T3; unregistered portions kept. | Current stage regenerable; cold time unknown. Recorded five-book stage passes total 20.5 s (mixed cache state). |
| 24 | `.s17bt` | 0.185 | synthetic/repository test fixtures; retained test scratch | Earlier/final test receipt references need deeper path closure; not required as fresh test inputs. Unregistered scratch excluded by old plan. Kept from proposal. | Regenerated by relevant tests. Full current suite measured 17m56s; exact scratch recreation unmeasured. |
| 25 | `.cache/t17_all_entry_levels` | 0.183 | synthetic/repository test fixtures; retained test scratch | Earlier/final test receipt references need deeper path closure; not required as fresh test inputs. Unregistered scratch excluded by old plan. Kept from proposal. | Regenerated by relevant tests. Full current suite measured 17m56s; exact scratch recreation unmeasured. |
| 26 | `.cache/huggingface/models--docling-project--docling-layout-heron` | 0.172 | shared; model: docling-project--docling-layout-heron | R/P; pinned runtime model, protected. Unregistered models were outside the old prune scope. | Reacquire pinned model bytes; download time unknown. Models remain excluded even when duplicate. |
| 27 | `frontend_temp/runtime/cache/huggingface/models--docling-project--docling-layout-heron` | 0.172 | shared; model: docling-project--docling-layout-heron | F/P; frontend server owns this cache. Unregistered models were outside the old prune scope. | Reacquire pinned model bytes; download time unknown. Models remain excluded even when duplicate. |
| 28 | `.cache/t22` | 0.153 | synthetic/repository test fixtures; retained test scratch | Earlier/final test receipt references need deeper path closure; not required as fresh test inputs. Unregistered scratch excluded by old plan. Kept from proposal. | Regenerated by relevant tests. Full current suite measured 17m56s; exact scratch recreation unmeasured. |
| 29 | `.cache/step6/document` | 0.152 | four old development document keys; exact file-to-book mapping unverified; Step 6 document analysis | Historical Step 6/8 evidence; not a direct current gate input. Unregistered, lifecycle/provenance unresolved. Kept. | Historical document-analysis producer/config required; cold time unknown. |
| 30 | `.cache/step16/downstream` | 0.152 | S/I/M/T, derived native/scan pairs; Step 16 downstream comparison | 16 comparison/P; paired rasters and conversion inputs retained for replay; unregistered outside old plan. | step16_downstream.py; source/native stages retained, OCR/model time unmeasured. |

## Baselines, parity and the future freeze

The dependency map reads **29 Step 15/16/17/17b performance records**, plus Step 17b before-publication and worker-parity paths. Every actual `cache_keys` value, named output/publication and assembly-history publication is protected, including unregistered files containing a protected key in their path. Every current registry file is excluded. Tracked mentions are separately reported; a key found only in an old cleanup list is not represented as a live Step 15–17b dependency. Old native caches and retained analyses are conservatively kept as a closure set rather than repeating the earlier fixture cleanup gap.

There is **no local Step 18 freeze-check specification or tag**. For capacity planning the future-freeze retention set preserves all the above, the latest five publications and their archives, pinned runtime assets, and the selected review commit `d0625e8`. This is an explicit conservative assumption, not a claim to have run a Step 18 gate. The pending fresh Spanish I1–I7 needs the 758-page native/analysis/layout/list keys recorded in Step 17b; all remain protected. It has **not run**. The old approved Step 17b proof reuse stays recorded as historical evidence, never relabelled fresh.

The earlier empty disk-budget dry run protected every registered fingerprint with any tracked witness, all native caches, all unregistered files and every current entry. Its zero eligible bytes was correct for that narrow policy; it did not prove that the whole disk was indispensable. The new conditional T3 separates live baseline inputs from earlier tracked replay history. T1/T2/T4 deliberately need explicit approval beyond ordinary registered-only pruning. Per-entry reasons and all tracked witnesses are retained in registry_entries.json. Access-denied subtree paths and errors are in inventory_summary.json and prune_plan.json; no ACL/ownership changes were attempted.

## Duplicate books, fingerprints and profiles

Different keys for the same source are version/configuration variants, not automatically identical data. The registry alone has 69 book/stage groups with multiple existing fingerprints. The following table lists every populated registered stage; unregistered list/paragraph/furniture variants are separately mapped in unregistered_identities.json (sampled identity, not full-payload validation).

| Stage | S | I | A | M | T |
|---|---:|---:|---:|---:|---:|
| analysis | 1 | 2 | 1 | 1 | 1 |
| assembly_evidence | 1 | 1 | 2 | 1 | 1 |
| characters | 5 | 6 | 4 | 4 | 3 |
| continuity | 3 | 3 | 4 | 3 | 3 |
| equations | 5 | 6 | 5 | 5 | 8 |
| figures | 5 | 6 | 4 | 4 | 3 |
| furniture | 6 | 7 | 5 | 5 | 1 |
| layout | 4 | 5 | 4 | 4 | 1 |
| lists | 8 | 9 | 7 | 7 | 3 |
| mathml | 6 | 7 | 6 | 6 | 7 |
| native | 1 | 2 | 1 | 1 | 1 |
| paint | 2 | 3 | 2 | 2 | 1 |
| paragraphs | 6 | 7 | 5 | 5 | 1 |
| reading_order | 6 | 7 | 5 | 5 | 1 |
| structure | 7 | 8 | 6 | 6 | 2 |
| structure_evidence | 7 | 8 | 6 | 6 | 2 |
| tables | 4 | 6 | 5 | 4 | 4 |
| text | 1 | 2 | 1 | 1 | 1 |

Every full key, producer, book source hash, size, current status and protection reason is listed in [duplicates_by_book_stage.json](../experiments/out/cache_audit_20261024/duplicates_by_book_stage.json). Additional mapped unregistered source/stage variants are indexed in [all_identified_fingerprint_folders.json](../experiments/out/cache_audit_20261024/all_identified_fingerprint_folders.json).

| Book | Semantic archives | Publications | Total GB |
|---|---:|---:|---:|
| spanish_us_history | 13 | 6 | 7.087 |
| immigrant_children | 14 | 3 | 0.118 |
| art_therapy_index | 15 | 8 | 0.015 |
| medical_anatomy | 13 | 9 | 2.836 |
| statistics | 11 | 4 | 1.056 |

Across 30 identified publications, 29 use default profile 1.0.0 / `cbf9a836…`; the earlier art smoke publication `book-2d5f3235…` uses default 1.0.0 / `8b811d31…`. It is protected by the Step 17 smoke performance record. Matching profile versions with different hashes are not interchangeable. Publications also have distinct assembly producer/content hashes even when profile hashes match.

**11 exact model-file duplicate groups** were independently SHA-256 checked, with **3,011,422,479 duplicate logical bytes**. They include root/frontend model copies. Models remain protected; no model or frontend file is proposed. Exact paths, keep-all decision and hashes are in [exact_model_duplicates.json](../experiments/out/cache_audit_20261024/exact_model_duplicates.json). This task does not change model-sharing settings or stop the frontend server.

## Rebuild timing evidence

These are recorded complete Step 17 archive runs (original assembly included) and separately measured current Step 17b publication refreshes. They are contextual measurements, not promises for an uncached run or every old fingerprint. Do not add the archive and refresh columns and call that a new measured end-to-end run.

| Book | Recorded archive run s | Step 17b publication refresh s |
|---|---:|---:|
| spanish_us_history | 4726.4 | 2655.7 |
| immigrant_children | 4718.8 | 216.2 |
| art_therapy_index | 166.2 | 4.3 |
| medical_anatomy | 656.8 | 266.3 |
| statistics | 2076.7 | 519.6 |

The table-development bundle timings observed in final parity logs total **2,880 seconds (48 minutes)** across five books: Spanish 2,539 s (bounded reader), immigrant 220 s, art 2 s, anatomy 37 s, Statistics 82 s. The separate Step 13b math bundles have no recorded comparable cold rebuild time. Native/analysis and current Step 17b stage inputs remain available. The current parity bundle set under `step15/pages` has no proposed input keys. The older `step14b/pages` set has six proposed input keys per book, and opcode-only inspection of each Step 13b book bundle identifies four registered input keys per book in T3. Thus T2 alone removes rebuildable conveniences, but T2+T3 also retires part of their historical upstream cache. Exact old-bundle reconstruction would first need those stages restored under historical code/configuration; its elapsed cost is unknown. This interaction is recorded in [bundle_rebuild_dependencies.json](../experiments/out/cache_audit_20261024/bundle_rebuild_dependencies.json). No pickle was executed. Spanish current-parity regeneration must use the verified bounded table reader under the present resource limits.

## Proposed tiers — approval required

These tiers are disjoint exact file lists. They are not folder wildcards, and approval of a parent folder would be too broad. The hash receipts cover every listed file; before any approved operation, abort if the plan/registry/file bytes, metadata, dependencies or live-writer state changed. No rescan may add deletions. Never prune during a sealed run.

| Tier | Files | Bytes freed (logical) | GB | Rebuild/replay cost and approval meaning |
|---|---:|---:|---:|---|
| T1_tool_caches | 554 | 110,135,216 | 0.110 | Pip download cache, current backend/experiment bytecode, pytest metadata. No converter recomputation; automatic repopulation, download time unmeasured. Ruff and cached historical-source bytecode excluded. Explicit unregistered-tool-cache approval. |
| T2_dev_bundles | 6,614 | 1,225,026,923 | 1.225 | Math/table development bundles in .cache/step13b/bundles, step14b/pages and step15/pages. Current table-parity rebuild observed 48 min; math bundle time unknown. T3 also retires some old bundle inputs, so exact historical rebuilding then needs upstream restoration. Current freeze/parity inputs remain intact. Explicit unregistered-bundle approval. |
| T3_superseded_registered | 105,904 | 2,514,894,334 | 2.515 | Older producers from the five development books, outside current/15–17b keys. Retires pre-Step-15 replay convenience; cold recomputation and exact old-environment restoration unmeasured. Older tracked references will point to removed caches. Explicit historical-cache retirement approval. |
| T4_historical_archives | 43,264 | 5,330,684,720 | 5.331 | Identified older development semantic archives/publications outside protected output/history roots. Removes old intermediate replay artifacts, preserves recorded 15–17b baselines and latest outputs. Exact old rebuild may require historical code/environment; time unknown (five-book contextual timings above). Explicit archive-retirement approval. |

**All tiers: 156,336 files / 9,180,741,193 bytes (9.181 GB).** If all bytes were reclaimed at the sealing free-space snapshot, free space would be about 14.898 GB, before filesystem effects and concurrent activity. T1+T2 alone reclaim about 1.335 GB. Even all tiers do not supply the earlier three-book retained-storage plan of 33.223 GB free including reserve (39.223 GB with provisional transient headroom). They may provide room for a future isolated Spanish retry, subject to a fresh 11 GB provisional headroom preflight and reserve monitoring; this audit does not start it.

Recommended review order is T1, then T2; approve T3/T4 only if retiring those historical replay copies is acceptable. Unknown/unreadable caches, native closure, current registry, baseline/parity publications, gold/references/ledger, models and frontend runtime data remain excluded. No broader cleanup is authorized by approval of an earlier Step 17 list.

The approval target is [prune_plan_final.json](../experiments/out/cache_audit_20261024/prune_plan_final.json), SHA-256 **`020e3eec989ff1505a0d101ff187bb0de83b266f945f2b20869883d3354b5a84`**. It binds [prune_proposal_v2.json](../experiments/out/cache_audit_20261024/prune_proposal_v2.json), subtracts its explicit 94-file exclusion list, and binds the final compressed per-file SHA-256/ctime receipt. The final receipt is the authoritative selection; older first-pass proposals and prune_plan.json are retained for provenance and are superseded, not approval targets.

Sealing rechecked 555 frozen Step 17b evidence files. The final audit validation separately rechecks the 333 frozen source/report/helper inputs, registry and plan arithmetic. No converter tests or reprocessing are needed for this report-only change. Helpers pass Ruff with `--no-cache`. The audit files are uncommitted review artifacts; the frozen Step 17b review commit is unchanged. **Stop for the owner's explicit tier/plan approval.**
