# Pre-freeze disk budget ? 2026-10-24

**STOP: insufficient disk space.** The three books need **28.22 GB** of planned retained cache/output storage, **33.22 GB** including the 5 GB reserve, or **39.22 GB** with provisional transient working headroom. Latest free space is **5.15 GB**, leaving only **0.15 GB** above reserve. This is a point-in-time measurement, not a stable allocation guarantee.

The dry-run prune list contains **0 eligible files / 0 reclaimable bytes**. All existing superseded registered cache files have tracked frozen-evidence references and remain protected. No deletion or sealed-book run occurred. The fresh Spanish I1?I7 check on **d0625e8** has **not run** because disk headroom is insufficient; **no proof was reused** for this request. No tag was created.

## Planned storage

GB are decimal; the runner's 12 MiB/page allowance uses binary MiB. Counts are existing recorded intake/seal metadata: ENT 612 pages, Algebra and Trigonometry 1e 1,220 pages, Mideast 317 pages. Source PDFs already occupy this drive and are not budgeted a second time. Only source-file byte identity was hashed; no hold-out PDF content was extracted, OCRed or evaluated and no reference truth was read again.

| Book | Pages | Cache + semantic archive GB | Additional JSON/assets GB | Retained total GB | Free needed with 5 GB reserve |
|---|---:|---:|---:|---:|---:|
| ENT | 612 | 7.701 | 0.337 | 8.037 | 13.037 |
| Math hold-out | 1,220 | 15.351 | 0.671 | 16.022 | 21.022 |
| Mideast | 317 | 3.989 | 0.174 | 4.163 | 9.163 |
| **All three** | **2,149** | **27.041** | **1.182** | **28.223** | **33.223** |

Even the smallest individual plan, Mideast, requires 9.16 GB free including reserve and before transient headroom. None fits now. With all three books' results retained, the current shortfall is **28.07 GB** before transient headroom, or **34.07 GB** including it.

The adopted cache/archive allowance is the existing runner's full **12 MiB/page** capacity rule for an uncached book. It includes both stage caches and the semantic archive; it is not charged twice. The separate publication can duplicate images/review crops, so it is added using the highest measured publication bytes/page among the five development books (Spanish: 549977.3 bytes/page). The plan assumes one book/process at a time, retains all three books' caches and outputs, and assumes installed model weights need no new download. No cache may be pruned during a sealed run.

The **6 GB** transient allowance is shared by serial jobs, not added for each book. It gives margin above the roughly 3.8 GB free-space drop in the prior unfinished Spanish proof. Its cause was not established and the unfinished proof does not establish a maximum. Neither this allowance nor 12 MiB/page is an upper bound on unseen vector/scan/model workloads. Reserve monitoring and a fresh preflight remain required.

## Measured analogues, not capacity permission

Existing five-book caches and current semantic/publication folders were measured read-only. The following extrapolations show plausible data composition; they do **not** justify reducing the adopted allowance for unseen books. Cache values include registered stage files plus the exact unregistered assembly mark files. Shared model weights, global formula/table/OCR experiment stores and duplicate historical configurations are excluded from these analogue totals. The full-run allowance, rather than these smaller extrapolations, is used for the go/no-go decision.

| Book | Development analogue | Stage cache GB | Semantic archive GB | JSON/assets GB |
|---|---|---:|---:|---:|
| ENT | medical anatomy | 0.353 | 0.255 | 0.273 |
| Math hold-out | statistics | 0.267 | 0.084 | 0.129 |
| Mideast | spanish us history | 0.946 | 0.154 | 0.174 |

Detailed per-stage measurements and source identities are in [measurements.json](../experiments/out/prefreeze_disk_budget/measurements.json) and [disk_budget.json](../experiments/out/prefreeze_disk_budget/disk_budget.json). No stage cache for these three source hashes is registered in the audited main cache.

## Exact dry-run result

[cache_prune_dry_run.json](../experiments/out/prefreeze_disk_budget/cache_prune_dry_run.json) audits **388 registry entries**, protects **39,959 current registry files** and records tracked-evidence witnesses for **370 registered fingerprints**. Existing superseded entries occupy **2.515 GB**; all are excluded by tracked frozen-reference protection. Some unreferenced old entries have no files left, so they reclaim nothing.

The policy keeps every current entry, every key referenced by tracked evidence/source, all native caches (including retained analysis's indirect dependencies), and all unregistered files. Hold-outs, gold, references, models, ledgers, published outputs and baselines/parity inputs are never candidates. This is a conservative registered-cache audit, not a claim that all disk data is indispensable. It does not inspect or propose unrelated user files or disposable-looking unregistered directories.

The plan has no apply function. Its SHA-256 is `d3e41c01cc42c4906f2bedad24ec48e2ee84a33b5c7e065c869ed13132208b4d`. The registry hash was unchanged throughout the audit and is recorded in the plan/snapshot. Any future nonempty approved plan must verify its exact frozen hash, index identity and every listed file's bytes/hash/timestamps, without discovering extra deletions. There is **no nonempty eligible cleanup to approve here**; storage must be supplied or a different explicitly authorized storage scope chosen before proceeding.

## Fresh Spanish gate

The user explicitly selected review commit **d0625e841c6793dea6de7c2cb4a87e31694ff2c3**. Existing Step 17b reports, proofs and receipts remain unchanged. [spanish_fresh_status.json](../experiments/out/prefreeze_disk_budget/spanish_fresh_status.json) explicitly says `not_run_insufficient_disk_headroom`, `fresh_every_page_completed: false`, and `proof_reused: false`.

The previous isolated fresh proof started near 7.77 GB free, reached at least the page-650 progress marker and stopped with 3.97 GB free. Current capacity is lower, so repeating that workload is refused at preflight. A provisional retry threshold is **11 GB free on C:** (5 GB reserve + 6 GB working headroom), with no concurrent heavy project job. That threshold is not proof of sufficient capacity. The eventual check must freshly run the unmodified review commit's I1?I7 checker and line/unit ownership on **all 758 pages**, use a new evidence destination, monitor the actual interpreter and stop below reserve. Only complete new results may be labelled fresh; interruption must be reported, never converted to proof reuse.

A different cache/output drive can supply data capacity, but does not by itself establish adequate C: working/system headroom for this check. This audit changes no pagefile or system settings.

## Capacity observations and stop point

Audit-start free space was **6.74 GB**; the completion snapshot recorded **4.51 GB**. A separate observation recorded **3.66 GB**, below reserve, followed by recovery. Latest reading is **5.15 GB** at **2026-10-24T07:35:00.814674+05:30**. The newly written audit data before this report totals 338,660 bytes. A separate `frontend_temp/smoke_check.py` conversion with its own `frontend_temp/runtime` cache was observed; this audit did not start, stop or modify it. These facts do not establish the cause of the free-space fluctuations. Full capacity must be rechecked when other jobs are idle.

[latest_capacity.json](../experiments/out/prefreeze_disk_budget/latest_capacity.json) records that observation and the available system counters. No production/test source, frozen Step 17b evidence, source PDF, gold/reference/ledger, model, registry or Git configuration was changed. No new commit/tag or hold-out run was started. Stop for the owner's storage decision; **do not freeze or begin the sealed run**.
