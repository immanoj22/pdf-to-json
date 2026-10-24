# Approved cache cleanup ? 24 October 2026

**Completed T1?T3 only: 113,072 files / 3,850,056,473 bytes in 72.527 seconds.** The complete preflight took 418.403 seconds; all selected SHA-256 values and metadata matched before deletion. All 61 cache-closure tests passed after cache deletion (44.91 seconds including pytest startup).

The exact approved plan remains SHA-256 `020e3eec989ff1505a0d101ff187bb0de83b266f945f2b20869883d3354b5a84`. It was checked immediately before the first unlink and again afterward. No candidate scan added files. Only exact listed regular files were unlinked; empty cache folders were retained. The current registry bytes are unchanged; all 39,959 readable current-registry files remain. All 333 frozen source/report inputs still match their recorded hashes.

| Tier | Files | Logical bytes deleted |
|---|---:|---:|
| T1_tool_caches | 554 | 110,135,216 |
| T2_dev_bundles | 6,614 | 1,225,026,923 |
| T3_superseded_registered | 105,904 | 2,514,894,334 |

Free space immediately before deletion: 6,375,944,192 bytes. Immediately afterward: 10,463,252,480 bytes. Final measurement after tests and the separate metadata cleanup: **10,369,028,096 bytes (10.369 GB)**. Logical file lengths and actual free-space changes differ because of allocation, audit/test artifacts and concurrent activity.

**T4 was not approved or deleted.** All 43,264 T4 files retained their recorded size/mtime/ctime after deletion. No baseline/parity/freeze input, model, source/reference/gold/ledger, hold-out or frontend runtime file was selected. No freeze, fresh Spanish check, hold-out run or adapter was started. The frozen review commit remains unchanged; no commit was made for this maintenance action.

## The three external directories

| Directory | Result | Evidence |
|---|---|---|
| `C:/coeik/projects/pdf to xml converter` | Retained, unchanged | Local reference configuration points `legacy_upgrade`, `old_original` and `spanish_cache` here. Fixture experiments, benchmark truth and Step 7 gates use the Spanish cache. |
| `C:/coeik/projects/nimas` | Retained, unchanged | Configured `old_root`; corpus inventory/audit and earlier repository-verification tools use its profiles/history. |
| `C:/coeik/projects/deterministic_pdf_to_xml.egg-info` | Deleted under the later explicit conditional instruction | Six generated packaging metadata files, 2,763 bytes; no current dependency/import/environment path or installed distribution uses it. `pdf_to_xml` is not importable in the current environment. Metadata contents/hashes were saved first; no source code was deleted. |

The small egg-info removal is separate from the sealed T1?T3 selection and deletion counts. The two legacy reference projects were read only. Local reference configuration and project code were not edited.

## T4 move proposal, pending destination

After the owner supplies a destination drive/folder, prepare an exact move plan for the existing T4 list only: 43,264 files / 5,330,684,720 logical bytes, plus filesystem overhead. Preserve project-relative paths. Before copying, check the source against the sealed SHA-256/metadata receipt and check destination capacity and existing files. Copy, then independently checksum every destination file against that receipt and save a manifest. Source removal must be covered by the subsequent move approval and occur only after complete destination verification; no wildcards or parent-folder removal. Stop on any changed/missing file or checksum mismatch. No T4 copy/move/deletion has been performed. Never perform maintenance during a sealed run.

## Records

- [Approved cache deletion record](../experiments/out/cache_audit_20261024/approved_t123_deletion_record.json)
- [Exact per-file deletion journal](../experiments/out/cache_audit_20261024/approved_t123_deleted_files.jsonl)
- [Cache-closure test log](../experiments/out/cache_audit_20261024/approved_t123_cache_closure.log)
- [Separate egg-info deletion record](../experiments/out/cache_audit_20261024/unused_egg_info_deletion_record.json)
- [Egg-info metadata backup](../experiments/out/cache_audit_20261024/unused_egg_info_metadata_backup.json)

A preliminary guard treated empty dependency lists as protected and stopped with zero deletions. That guard was corrected to check actual recorded uses, without changing the approved plan or candidates. The zero-deletion attempt is preserved in `approved_t123_preflight_stopped.json`. The completed attempt verified all selected files before any deletion.

**Stopped as requested.**
