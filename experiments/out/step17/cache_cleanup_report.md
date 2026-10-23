# Approved Step 17 cache cleanup

The original dry-run plan was frozen and checked before deletion:
`cache_prune_dry_run.json`, SHA-256
`f7956e2fead2ff25601019908304b3d6de0ecf29811e358bc05870c15d21d793`.
It listed 614 folders and 5,886,003,040 bytes. It was not regenerated or expanded.

The audit protected Step 15/16/17 baseline and parity keys, current registry keys and
referenced paths. No listed folder was identified as a baseline, parity input or
current registry entry. Another 55 folders (464,223,869 bytes) were excluded because
their source could not be verified as an allowed development source. Their exact
paths and reasons remain in `cache_prune_audit.json`. Nothing was selected from
hold-out sources, gold, references or models.

The approved subset contained 559 folders, 30,935 files and 5,421,779,171 bytes.
Every listed file's recorded size and timestamp was verified before the first
deletion. Only those files and their now-empty directories were removed; deletion
did not discover additional candidates. See `cache_deletion_record.json` for the
machine-readable outcome.

- Start: 2026-10-23 07:00:20 UTC.
- Finish: 2026-10-23 07:03:16 UTC.
- Elapsed: 176.356 seconds.
- Deleted: 30,935 files, 5,421,779,171 bytes; 568 directories including image subfolders.
- Free space immediately afterwards: 11,864,662,016 bytes (11.86 GB decimal).
- Errors: none.

The cache-closure verification started after deletion completed and passed:
`test_cache_keys.py` plus
`test_assembly.py::test_cache_closure_covers_the_assembly_stages`, **62 passed in
67.43 seconds**. Output: `cache_closure_after_cleanup.log`.

The first Statistics retry could not acquire the cache maintenance lock because
the earlier OCR-cover conversion was still running. After that run released the
lock, the next retry passed the required 5 GB reserve preflight and started its
871 pages (`resume_statistics_after_lock.log`). No further pruning was attempted.

## Indirect fixture dependency found after cleanup

The broader backend suite subsequently exposed an audit gap: retained derived
fixture-analysis caches referenced 15 native fixture caches in the approved deletion
subset. The audit protected recorded baseline/parity keys and current registry files
but did not follow these indirect cache references. The first failure was
`test_invariants_hold_on_unseen_pages[u01_art_index_3col]` after 571 passing tests.

All 15 missing fixture-native files were rebuilt from unchanged repository fixture
PDFs through `PyMuPDFExtractor`. Restoration required the freshly computed current
native fingerprint to match the deleted directory key; no old key was fabricated.
The repair restored 15,140,963 bytes in 67.759 seconds. Exact sources, paths, keys,
times and free space are in `cache_fixture_restoration_record.json`. The deletion
record and frozen plan remain unchanged. No additional cache deletion was performed.
The affected invariant tests and remaining backend tests passed: 621 tests in 550.59
seconds. Together with the earlier 571 passes (20 overlaps), all 1,172 unique tests
then collected were covered. Statistics completed all 871 pages after its reserve
preflight; its final frozen-producer publication passes with the other four books.

The final complete backend suite passes **1,183 tests in 1,762.25 seconds**. All five
JSON schema, round-trip, lossless, ownership and parity gates pass, retaining the
allowed Statistics I7 = 1 exception. Final gate free space was **9,062,596,608 bytes**
(9.06 GB decimal), above the required reserve. The original approved plan hash is
still unchanged; no further pruning was performed. See `final/gate_summary.json`
and `final/validation_record.json` for the final checks and log checksums.
