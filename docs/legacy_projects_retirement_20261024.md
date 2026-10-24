# Legacy project retirement ? 24 October 2026

**Partially completed: Windows access permissions block the final remnants.** The owner explicitly selected both entire old project folders and their historical references for removal, while retaining any cache still used by the current project.

Deleted **270,279 regular files / 93,256,970,038 logical bytes (93.257 GB)** in 89.528 seconds, plus 22,007 empty directories. Removed two junctions without following their targets. Current free space: **93,057,077,248 bytes (93.057 GB)**, measured 2026-10-24T03:18:43.071834+00:00. Actual free-space gains differ from logical file lengths because of allocation, compression/hard links, and concurrent activity.

| Old root | Files deleted | Logical bytes deleted | Result |
|---|---:|---:|---|
| `C:\coeik\projects\pdf to xml converter` | 78,566 | 27,922,903,119 | Readable contents removed; denied remnants and ancestors remain. |
| `C:\coeik\projects\nimas` | 191,713 | 65,334,066,919 | Readable contents removed; denied remnants and ancestors remain. |

The initial inventory could not read **94 paths**. One inventoried file (151 bytes) also denied deletion. There are 110 retained directories including the inaccessible subtrees and their ancestors; the two root folder names therefore still exist. A non-recursive inherited-ACL reset on one denied subtree failed with Windows access denied (exit 5). No permission reset succeeded; no ownership takeover or recursive ACL change was attempted. **An Administrator terminal is required to finish these remnants.** Exact paths and errors are listed in [legacy_projects_remaining_paths.json](../experiments/out/cache_audit_20261024/legacy_projects_remaining_paths.json). The unknown contents of inaccessible paths are not included in deleted-byte totals.

## Cache that remains in use

`backend/tests/test_full_book.py` still reads the Spanish extraction benchmark. Preserved its complete required input set: **760 files / 407,480,401 bytes** (manifest, validation/exclusion records, and all 758 normalized page records), at [the retained cache](../.cache/retained_references/spanish_full_book). Every source/destination SHA-256 matched before removal; every retained file was independently checked again afterward. Text, exclusions, source identifiers and token truth were not edited.

Updated only the git-ignored `experiments/references.local.toml`: `spanish_cache` now resolves to this retained cache; `old_root`, `legacy_upgrade`, and `old_original` were explicitly retired. Older audit scripts needing those retired projects can no longer replay them. The current converter imports none of their code. Supplied current book PDFs/XML, current gold/ledger, models, registry, publications and other active caches were outside the deletion roots.

The relocated benchmark constructor succeeds and retains source SHA-256 `de9d916687ecbe556f7a01f1d871048ec89f362ae5c4b399bd08098b1fddc951`. All 333 frozen Step 17b source/report inputs, the cache registry and the approved T4 plan remain unchanged. **67/67 cache-closure and reference-configuration tests pass** after the deletion/relocation, with zero skips/failures/errors (30.76 seconds including startup). Both cleanup helpers pass Ruff with `--no-cache`. Tracked worktree remains unchanged; no Git commit/configuration change was made.

The earlier approved T1?T3 cleanup separately removed 113,072 files / 3,850,056,473 logical bytes. The unused `deterministic_pdf_to_xml.egg-info` was separately removed (six metadata files / 2,763 bytes). Their original records remain intact. T4 remains in place; no T4 move was started. No freeze, fresh Spanish I1?I7, hold-out, Step 18 or adapter was run.

## Records

- [Old-project deletion record](../experiments/out/cache_audit_20261024/legacy_projects_deletion_record.json)
- [Retained Spanish cache and per-file hashes](../experiments/out/cache_audit_20261024/retained_spanish_cache_relocation.json)
- [Final verification](../experiments/out/cache_audit_20261024/legacy_retirement_final_verification.json)
- [67-test result](../experiments/out/cache_audit_20261024/legacy_retirement_test_record.json)
- [T1?T3 deletion record](../experiments/out/cache_audit_20261024/approved_t123_deletion_record.json)

**Stopped with the permission-blocked remnants explicitly outstanding.**
