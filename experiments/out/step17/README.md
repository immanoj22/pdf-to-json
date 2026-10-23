# Step 17 evidence

The final result is described in `../../../docs/step17_report.md`. The consumer contract
is `../../../docs/json_schema.md`. Development trials are not final publications.

## Authoritative final records

- `final/gate_summary.json`: required gates and checksums of their JSON evidence.
- `final/report_data.json`: five-book schema, round-trip, token, review and performance
  measurements. The five `final/performance/*.json` files locate the published folders.
- `final/validation_record.json`: test, cache-closure, Ruff and wheel verification receipts.
- `final/after/*_full_gates.json`: every-page I1–I7 and ownership checks. The known
  Statistics I7 count remains one; the other invariant counts are zero.
- `final/lossless/*.json`, `final/source_crosscheck.json`, `final/full_book.json` and
  `final/final_outputs.json`: JSON token reconstruction, 30 fresh native pages, Spanish
  retained ledger and archive manifests/assets. Only explicit TrimBox tokens are discarded.
- `final/contract_check.json`: stable IDs, reciprocal continuation links and review targets.
- `final/parity/*.json`: independent continuity/table/publication parity. For the four
  unchanged archives, `final/parity_before_entry_levels` freezes the independent proof
  before the final entry-level correction. The final proof checks every added level
  against its archive unit and every other JSON field for exact equality. Book 2 has
  fresh full publication parity. This is scoped proof reuse, not five repeated renders.
- `final/workers_book3.json`: one-worker, two-worker and development output byte hashes.
- `final/book2_change_audit.json`: exhaustive Step 16 comparison, with the cover-title
  role change and English-only language annotation changes explicitly recorded.

Archive conversion timing and peak memory remain in the original run measurement.
Publication refreshes are separately timed; `assembly_history` preserves earlier
publications. The original and refreshed publication folders have not been deleted.

## Measurements and provenance

`before` holds the frozen Step 16 baselines; `continuity` holds accepted and rejected
variants. `json_eval` scores the actual final JSON. `styling` contains aligned counts,
the seeded hand-check sample, judgements and sheets. Weak style agreement is retained.
`ocr` contains page-flag folds and reader-specific calibration. `real_eval` records
common-page hypotheses, truth, scores and geometry-based primary-reader replay.
`real_data` records acquisition and source audits; the frozen 54-page dataset, revision
and licence records are in `../../test_data/step17_real_scans`. Its transcriptions come
from recorded Wikisource proofreading revisions, without a second local full-text audit.

The approved deletion is documented by `cache_cleanup_report.md`, the unchanged
`cache_prune_dry_run.json`, `cache_prune_audit.json`, `cache_deletion_record.json` and
`cache_fixture_restoration_record.json`. The 55 excluded folders and the restored 15
indirect fixture dependencies are recorded; no additional pruning was performed.

Raw development publications, wheel binaries and superseded run-history snapshots are
left on disk and excluded from the step commit. The wheel asset hashes are recorded in
`packaging/verification.json`. No hold-out book, gold or reference was modified.

Repository attributes preserve the exact bytes of Step 17 receipts and frozen source
downloads. Upstream transcription HTML retains its original whitespace; no cleanup or
line-ending conversion is applied to those read-only records.
