# Step 18 pre-registration addendum

Owner-approved additions, recorded on 2026-10-24 before any hold-out run.
This addendum supplements [the original pre-registration](step18_preregistration.md)
without editing it, its metric registry, the freeze tag, profiles or thresholds.
Converter freeze remains `holdout-freeze-1`, commit
`8d6a0b0036db3f28dd8b671a2950ceca9918a680`. The original protocol commit is
`781eb222273461c084a85cc0aef767c25f952796`.

## Owner expectation before results

Hold-out scores are expected at the **low end of the stated development bands
or below**, because the development books were tuned. Scores inside those bands
are not a surprise. Scores clearly above a band must be checked for coverage or
scoring problems before being interpreted as better generalisation. This changes
the expected interpretation, not any metric, denominator, threshold or scoring
rule. Keep the original bands visible alongside results.

## Judgment audit

After the agent's hand checks, the owner will re-judge a random **20 judgments**
using seed **`20261024:step18:v1:audit`**. If fewer than 20 judgments exist,
retain and select all of them and report the count. Sort the complete judgment
register by stable judgment ID, then select without replacement with
`random.Random("20261024:step18:v1:audit").sample(population, min(20, len(population)))`.
Save the selected IDs and the full population size; do not redraw difficult or
unclear targets. Owner verdicts remain pending until supplied by the owner.

For **every** agent judgment, save its stable judgment ID, book and metric/sample
family, target ID, original-source crop path(s), context image path(s), agent
verdict and notes. Preserve unclear/unscorable cases and identify the exact text
range/source refs for repeated strings or ID-less targets. Images and judgments
must remain available so the owner can re-check the same targets. Agent judgments
are **not independently verified**; viewing the target supports an agent visual
judgment, not independent confirmation. Report owner agreement/disagreement only
after owner re-judgment, separately from the original agent verdicts.

## Logged preflight before each book

Before starting **each** run, verify and append a preflight event to the
append-only `experiments/holdout_runs.jsonl`:

1. `git diff holdout-freeze-1 -- backend` is empty, including staged changes;
   no untracked backend source/test file is present. Record the empty result,
   tagged commit, current documentation HEAD and backend tree identity.
2. There are no staged changes or modified tracked files. The complete
   `git status --porcelain --untracked-files=all` output contains only
   `?? experiments/holdout_runs.jsonl`. This is the existing ledger template file;
   subsequent append-only preflight/attempt events remain in that same file.
   Commit differences from the tag are limited to the approved documentation.
   Keep execution receipts in ignored local evidence storage until the serial
   conversions finish, so newly exposed result files do not weaken this check.
3. Actual free space is **strictly above 40,000,000,000 bytes** (40 GB decimal).
   Record bytes, measurement time and the check result. This is the launch
   requirement; keep the separate 5,000,000,000-byte reserve monitor active for
   the entire job. A failed preflight prevents that run and is reported.

Also recheck the frozen source/profile identities and unchanged original
pre-registration/tag. Log the converter commit separately from documentation
HEAD rather than claiming the later documentation commits are the freeze tag.

## Execution, communication and stop conditions

After this **docs-only addendum commit**, run **ENT, then the math hold-out,
then Mideast**, serially, using the registered frozen converter/default profile.
Do the hand checks and scoring **after all three conversion attempts finish**.
Do not tune, fix, change thresholds or retry because of a result.

After each book, post a short chat status containing completed/failed, stage,
elapsed time, peak process-tree memory and free space, then continue to the next
book. A code failure is recorded without fixing and does not block the next
book. **Stop the queue** if the reserve monitor stops a job or an environmental
failure needs the owner's decision; preserve the attempt and report the cause.
An environmental failure is not automatic permission to retry.

No deletion, move, prune, Git configuration change, reference/gold/source-ledger
edit or `frontend_temp/` activity is authorized. The run-events ledger is the
explicitly authorized append-only exception. Do not edit the original
pre-registration or the tag. Verify that the addendum commit contains only this
document and that no tracked `backend/` file changed before starting Part 2.
