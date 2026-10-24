# Active Step 17 continuation notes

This is a working handoff, not a gate result. Do not make the Step 17 commit yet.
Read docs/step17_report.md and cache_cleanup_report.md for established results.

## Freeze while Statistics is publishing

Statistics is running from session 82855, log resume_statistics_after_lock.log.
Its 871 native and reading-order pages finished; it is in assembly pass 2. It passed
the 5 GB reserve check, free space is about 10 GB. Do not edit producer source until
it publishes: any assembly edit invalidates its loaded producer and aborts publication.

Backend suite: resume_frozen_full_tests.log has 571 passes, then a cache dependency
failure for u01_art_index_3col (not an invariant error). Restored all 15 matching
current native fixture keys with step17_restore_fixture_native.py, restoration record
cache_fixture_restoration_record.json. Session 26626 runs files from
test_layout_invariants.py onward, short basetemp .cache/t23, log resume_remaining_tests.log.
It was beyond 80% at last check. Do not repeat the first 571 tests unnecessarily.
Original 62-test closure check passed after approved deletion. Focused assembly 35 passed.

Completed refreshed JSONs are in final/performance for Spanish history, anatomy and
art-therapy index. Spanish history latest ordered refresh (book-8124...) passes the
full ledger 495751 + discarded 34160 exactly, recorded final/lossless and
resume_ordered_lossless_book1.log. Art index also 0/0. Anatomy still has 12 missing,
6 extra because whitespace-only hidden spans are skipped (CHAPTER + number concatenate).
Fix pending below. The refresh session 92333 finished all three books successfully,
but its outer PowerShell redirection was syntactically wrong AFTER the loop; exit 1
was that redirection error, not a conversion error. Performance records were written.

Old Claude cover job exited at assembly assertion (producer changed); upstream archive
and caches were preserved, no final performance record written. Its queue then ran
duplicate proofs. Stopped ONLY duplicate Spanish proof PID 9204; our completed 758-page
proof and comparisons are already saved. Queue finished, failed Statistics/cover proofs
because their final performance files did not exist yet; rerun after final runs.

## Batch remaining producer corrections after Statistics exits

1. assembly/build.py hidden loop currently skips `not span.raw_text.strip()`; retain
   whitespace-only spans with source_runs too, otherwise anatomy loses token boundaries.
   Keep truly empty spans skipped. Consider avoiding review clutter for whitespace-only
   records while retaining them. Rebuild assembly and recheck full ledger, especially anatomy.
2. schema.py TextContent validates source_runs bounds but Suppressed does not. Add common
   bounds/overlap validation for both, with negative tests. Regenerate committed schema
   only if generated text changes. No schema version bump is needed before initial release.
3. ocr/cache.py pp_first currently checks only PP reading geometry. Experiment
   step17_primary_policy.py and real_eval/primary_policy.json show it wrongly promotes
   one vertical print page. Requiring horizontal Han evidence from BOTH readings rejects
   all nine vertical pages and retains 8/9 simplified + 3/3 traditional horizontal pages.
   Extend pp_first to accept primary reading; recognize_page passes original Tesseract
   reading and PP reading. Update tests and replay script accordingly.
   real_eval/primary_geometry.json captures all 21 Chinese scans, all hypotheses match
   the frozen measurements. Do not re-run OCR unnecessarily. Existing primary_policy
   script currently uses 3-argument pp_first twice; adapt it when API changes.
4. OCR score granularity: OcrWord has granularity but OcrWordEvidence drops it. Preserve
   it. PP line confidence has not been calibrated as word confidence: mark its segment
   needs_review and its page must_check, calibration=None for that uncalibrated view,
   warning explicitly explaining line scores; retain raw confidence. Add focused test.
   assembly/build.py currently calls all flagged OCR words `ocr_word` with reason below
   threshold even if disagreement. Distinguish ocr_line review/action and accurate reason.
5. Profile alt_text.mode is accepted but ignored by book_run.py: it resolves figure
   settings before loading profile. Load profile early and apply mode to figure settings.
   Preserve legacy explicit figure_settings.alt_text_drafts when no explicit profile;
   an explicitly supplied profile should control its mode. Add API regression test using
   supplied stub generator. This changes FINAL producer and requires warm final runs
   for default books too, not merely pretending old archives were produced by new code.

Freeze all source after that batch, Ruff, focused tests + closure. New OCR digest means
cover OCR/view fingerprint changes and it needs a proper new run; do not fake old keys.
Resume cover only when Statistics frees the cache maintenance lock. Never bypass it.

## Final work

Need all five final runs and schema/lossless/roundtrip, source gates, metrics, cleanup
counts, parity, workers, final report_data. Scripts step17_measure_queue.sh list the
required commands, but do not run blindly on missing final records. Final reports
docs/step17_report.md (working now) and docs/json_schema.md. One commit, stop at gate.

No more pruning. Frozen original plan SHA f7956e2fead2ff25601019908304b3d6de0ecf29811e358bc05870c15d21d793.
614 originally; 55 unverifiable sources excluded; 559 selected, 5421779171 bytes removed.
15 fixture-native dependencies missed by audit were rebuilt (15140963 bytes); acknowledge
that audit gap, preserve original records. No hold-out, gold, reference or model deletion.
If Statistics cannot keep 5 GB reserve, stop and ask user; never prune more automatically.

Do not add unrelated preexisting dirty files (.vscode, step13c/14a/16 temporary evidence).
Ruff gate so far uses `ruff check backend`. Wheel test passed assets inclusion, rebuild
wheel after final changes if needed; do not commit .whl or arbitrary transient logs.

## Latest continuation — 2026-10-23 15:09 IST

- Full backend suite **1182 passed in 1609.96 s** (`final_full_suite.log`), session 2927
  exited 0. This predates the new entry-level regression below.
- Statistics parity finished successfully (`final_parity_statistics.log`, session 59419
  exit 0): continuity, assembly, and all 871 table pages. Art and anatomy parity also pass.
- Art/anatomy latest metrics were repeated successfully, session 69948 exit 0. All four
  completed books have lossless 0/0. Latest anatomy review count is **1065**, not 1053.
- Still live: actual cover run session **24685**, actual Python PID **7348**, launcher 9276,
  started 14:07, native and order complete; subsequent stages still consuming CPU (~3450 s
  at 15:08, ~2 GB RSS). No final cover performance record yet. **Do not edit producer source
  until this run completes**, and do not start another cover run.
- Still live: Spanish independent parity session **88317**, actual Python PID **19852**,
  launcher 18436, started 14:26. CPU ~2390 s at 15:08. No final output yet. Its old assembly
  module is loaded; its proof will remain valid for the frozen old publication.
- New discovered bug: `ListItem` omits original `ItemUnit.level`; a flat index list can
  contain entries of levels 1/2/3, but the JSON evaluator incorrectly uses enclosing list
  level 1 for every entry. Art index level accuracy fell .998821 -> .748821; anatomy
  .962480 -> .708809. A real source comparison confirmed source level 3 -> list level 1.
- New test added in `backend/tests/test_assembly.py`:
  `test_an_entry_keeps_its_own_level_inside_a_flat_index_list`. It builds a real fixture
  page, turns a paragraph into an index entry at levels 1/2/3 within list level 1, and checks
  conversion and round trip. **Red test reproduced the missing `ListItem.level` attribute**
  in 19.58 s (`final_entry_level_before.log`, session 34073 exited 1). It is an expected
  new regression failure, not a failure of the completed full suite.
- Required small source correction AFTER cover finishes: add nullable >=1 `level` to
  `assembly.schema.ListItem`; set `level=unit.level` in `PageBuild.unit_node`; regenerate
  committed schema. Keep schema version 1.0.0 (initial output not released). Update consumer
  docs to distinguish item level from enclosing `ListNode.level`. No other source changes
  are currently needed. The evaluator was already corrected to prefer `node.level` with
  list-level fallback in `step17_json_eval.py`.
- New `step17_entry_levels.py` captures and verifies scoped parity reuse: frozen independent
  dev proof plus old publication hash, exact upstream cache keys/book+manifest hashes;
  after refresh every other JSON field must be byte-equivalent (only producer/content hash
  excluded) and EVERY added item level must equal its original archive unit. Capture already
  saved art, anatomy and Statistics under `final/parity_before_entry_levels`. Capture Spanish
  once its parity finishes, BEFORE its publication is refreshed. Never overwrite frozen proof.
  After the fix, refresh all five publications (helper supports cover but `finish publish`
  skips it, so run `step17_refresh_assembly.py --book immigrant_children` explicitly). Verify
  the four scoped proofs; cover gets ordinary full `step17_parity.py --book immigrant_children`.
  This avoids repeating unchanged independent render evidence while still checking every
  final JSON field and all restored source levels. Explain method in final report.
- `step17_contract_check.py` now additionally fails any uncertain content unit lacking a
  review item. Read-only audit on all four current outputs found **zero** gaps, zero dangling
  review targets, and zero identity/continuation defects.
- `step17_gate_summary.py` now requires `final/validation_record.json` fields full_suite,
  cache_closure_after_cleanup, ruff, wheel_assets (each `.passed`); final assembly producer
  must equal `code_digest('assembly')` for all five; cover non-OCR page changes must be empty.
  It excludes `run_history` from evidence hashes. Generate validation receipt from real logs
  after final tests. Rebuild wheel after level/schema fix.
- Consumer docs clarify losslessness applies to complete default publication, not profiles
  omitting furniture/suppression sections. No source producer was edited during live cover.
- Still required after cover/source fix: focused assembly/closure (or full new1183 suite),
  publication refreshes5, cover full proof + source gates (finish proofs reuses4), exact
  book2 non-OCR audit, cover metrics, metrics4 refreshed for source-level evaluator, fresh
  worker comparison, report_data5/schema/roundtrip, contract5, gate summary, final report,
  selective staging and ONE commit. No adapter.
