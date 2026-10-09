# Confirmed decisions

Decisions confirmed by the project owner. Each entry names the step at which it was confirmed.

## Step 4a-v (taxonomy, confirmed after the Step 4a gate)

- A box that holds a whole section is a **callout scope with its own bands** (for example complex_sidebar panels, worksheet sections A/B).
- A caption box is a **callout with a caption child**.
- Card text is proposed as **`sidebar`** for now.

## Gold status

- Column gold (`backend/tests/gold/columns_*.json`) and role gold (`backend/tests/gold/roles_*.json`) remain `human_approved: false` until the owner approves them explicitly.

## Step 5 (confirmed after the Step 5 gate)

- Reference pairs: books 1-3 are usable (the T01 and 300-page excerpts count as book 1); book 2 is "identity by text only". The 48-page world-history pair stays excluded.
- Hold-out: tune on book 1 only; books 2 and 3 run once, and every later aligner or label change is logged in `experiments/out/step5/holdout_runs.jsonl`.
- Book 3 (art-therapy index) stays **anecdotal**; no chunked-placement fallback. Its page markers stay low confidence and excluded from gates.
- The aligner's furniture/folio causes are **diagnostics only**. The Step 8 furniture stage decides furniture, and no gate uses aligner causes.
- Derived gold (`backend/tests/gold_derived/`) stays committed and `human_approved: false`.
- Dialect labels: a title is a heading only when it belongs to a sectioning element or that element's info; titles inside bibliography or citation entries are part of that entry (Step 5b, logged label fix).
