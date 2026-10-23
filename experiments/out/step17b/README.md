# Step 17b evidence

This directory records the pre-freeze investigation and its narrowly scoped assembly
corrections. Only the five development books are used. Step 17 publications and
Step 15/16 semantic baselines are retained unchanged.

- `inputs.json`: original publication paths, SHA-256 values and archive identities.
- `style_census.json`, `style_sample.json`, `style_verdicts.json`: initial content-only
  populations, deterministic samples and rendered-crop judgments (147 correct,
  12 wrong, one unclear). This cohort is retained as historical evidence.
- `all_text_style_census.json`, `all_text_style_sample.json`, `all_text_style_verdicts.json`,
  `all_text_hand_check_summary.json`: final content-plus-furniture populations and
  20 targets per requested cell (148 correct, 12 wrong, none unclear).
  `all_text_added_verdicts.json` records 60 additional crop judgments after the three
  furniture-containing cells were resampled with the same seed. The other five cells
  retain their original targets. The original unclear panel letter remains unresolved.
  `final/all_text_sample_after.json` verifies full character coverage of every correct
  final sample. All furniture fields are unchanged on all five books.
- `index_page_style_census.json`: separate whole-index-page styling counts, including
  letter/title headings outside serialized entry lists.
- `crops/`, `sheets/`: initial 160 styling and 30 figure-text targets plus 60 new
  cohort targets; 250 crop files and 54 contact sheets. Targets can overlap between
  cohorts; these are not counts of independent annotations.
- `target_disambiguation.json`, `target_recheck/`, `target_visual_recheck.json`:
  exact source-reference checks for three repeated strings in ID-less table fragments.
  One subscript crop was corrected and visually reviewed again; counts are unchanged.
- `index/`, `index_hand_count.json`: 15 full-page index inspections and explicit letters.
- `figure_verdicts.json`, `figure_ownership_trace.json`: visual categories for 30 targets
  and the complete cell-ownership census of the flagged paragraphs.
- `divider_candidate_audit.json`: every newly eligible divider heading, with navigation context.
- `underline_path_trace.json`, `border_trace.json`: native path primitives behind the errors.
- `rotation_trace.json`: the existing equation rule, separate source-line safeguard and test gap.
- `part_a_visual_record.json`, `part_a_decisions.json`: investigation completion and decisions.
- `final/epoch.json`: frozen production/test files and producers; explicit test-strengthening receipts.
- `final/performance/`: new assembly publication records, preserving original archive measurements.
- `final/lossless/`, `contracts/`, `changes/`, `sample_after/`: exact final checks and before/after counts.
  In the census, `type:text_fragment` groups text leaves without a serialized `type`
  discriminator (including `FigureText` and `TextFragment`); it is not a new output type.
- `final/after/*_full_gates.json`, `final/validation/proof_*.json`: every-page I1–I7
  and exact line-ownership results. A proof is final only with its new validation receipt;
  the initial `after` directory was copied from Step 17 as identity input.
- `spanish_proof_reuse_candidate.json`, `final/proof_input_closure/`: unchanged
  Spanish proof/code/input-key comparison and all 3,032 current cache fingerprints,
  payload checksums and file hashes. This closure is not an invariant calculation.
  The guarded `reuse_proof` action requires `proof_reuse_approval.json` from an explicit
  user reply, then rechecks all closed bytes and labels the proof as not fresh.
- `final/table_input_checks/`: seeded real-page equality of the bounded audit reader's
  table-consumed features and all paths against the ordinary reader; separate stress
  checks cover each book's largest native cache. Stress checks are not ordinary-reader
  comparisons. No production reader or table algorithm is changed.
- `final/parity_parts/`: fresh development assembly equality checkpoint for the bounded
  Spanish retry, before the separate table comparison. The first interrupted parity
  attempt had no such checkpoint and is not accepted.
- `final/source_crosscheck.json`, `final/final_outputs.json`, `final/full_book.json`:
  fresh source, archive asset/reference and ledger checks.
- `final/parity/`, `final/workers_book3.json`: development and worker/production equality.
- `final/workers_shared_cache_book3.json`, `final/validation/worker_cache_independence_record.json`:
  inherited shared-cache comparison, retained as history. The final worker gate requires
  independent initially absent extraction caches and records their separate paths.
- `final/reference_evaluation_comparison.json`: all five new JSON reference evaluations
  compared in full with Step 17; all records are identical.
- `final/validation/`: executed checks, log hashes and reserve monitors. The interrupted
  initial `full_suite` is not a passing final suite; `full_suite_final` is authoritative.
- `final/packaging/verification.json`: exact packaged schema/default-TOML verification.
  All 259 packaged Python sources are also compared byte for byte with the frozen tree.
- `audit_helper_correction.json`: optional `type` field errors in two initial comparison
  branches; both failed logs are preserved. `final_gates_complete.log` and its per-book
  execution receipts identify the corrected run. Production code/publications did not change.

The sampling seed is 17023, independently seeded by book/kind. Manual judgments were
made from the recorded rendered targets; they are a single review, not double annotation.
The JSON paths in `inputs.json` are machine-local generated publications, not source
paths embedded in the package. Source PDFs are resolved through `reference_paths`.

Audit helpers include `experiments/step17b_investigate.py`, `step17b_verdicts.py`,
`step17b_trace.py`, `step17b_all_text_styles.py` and `step17b_table_inputs.py`.
The verdict helpers encode completed manual reviews; running them
does not constitute a new visual inspection.

`experiments/step17b_finish.py` runs publication/proof/metrics/source/evaluate/parity/worker
and test phases into this directory. `init` is one-time and must not reset an existing epoch.
Heavy jobs run sequentially after concurrent processing temporarily reduced free disk space.
`step17b_watch.py` monitors an explicitly verified task PID and stops it below 5 GB;
it never enumerates or deletes caches. See `space_audit.json` and `test_path_failure.json`.
`step17b_validation_queue.py` runs requested final gate phases sequentially in a fresh
process per book/phase, monitors each actual child and records its successful execution
time. An earlier long-lived queue was interrupted below reserve after its JSON checks
had passed; its stopped monitor is historical, not an accepted final gate.
See `space_retry_audit.json`. The final full suite runs separately
after the report and all source files are frozen.
An independent Spanish parity attempt also stopped below reserve while materializing
large native objects for table evidence. Its monitor is historical. The bounded retry
validates the consumed fields/paths without retaining all typed vertices and still runs
the original fresh comparison. The user's invariant-only approval does not approve
parity proof reuse. A worker retry also corrects the audit queue's Windows console
encoding; `worker_console_retry_record.json` preserves the interrupted monitor identity.

The original long test directories, shorter `.s17bt` workspace and built wheel are local
generated scratch, excluded from Git. Their logs and verification receipts are retained.
No cache pruning, hold-out run, gold/reference/ledger edit or adapter work is part of this step.

The human-readable results are in `docs/step17b_report.md`. Final acceptance is recorded
only in `final/validation_record.json`, after all current gate receipts and the final
full suite pass. Its input hashes require the report, helpers and backend sources/tests
to remain unchanged after that suite starts. The step ends with one commit for review.
