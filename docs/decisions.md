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

## Step 6b (confirmed by the project owner)

- Math is required. Equations must become MathML in output. Digital equations are rebuilt from glyph geometry; image equations use a formula-recognition model. Original image assets and original alt text are always retained. Step 6b adds evidence and extension contracts; it does not convert book equations.
- Repeated elements are furniture only with explicit evidence, never repetition alone. The book 1 reference retains the repeated CONÉCTATE box as content on every occurrence. Final policy for repeated boxes remains pending the owner's decision.
- Step 6 navigation is evidence only. TOC/index confusion must be resolved before the heading step relies on it. Printed TOC target pages await folio mapping in the furniture step.
- Clearly restricted candidates (GPL, AGPL, non-commercial weights, or revenue/user thresholds) are excluded and documented; they are never installed or smoke-tested. Continue with verified permissive code and weights. Stop for an unclear license or a slot without a permissive candidate.

## Step 7 (confirmed by the project owner)

- Bundled compiler runtimes licensed GPL WITH the GCC Runtime Library Exception (as in the NumPy and SciPy Windows wheels) are **allowed**: the exception does not apply the GPL to our code. This supersedes the Step 6b exclusion of the standard SciPy Windows distribution. Other GPL/AGPL code, non-commercial weights and revenue/user-threshold terms remain excluded.
- scikit-learn, LightGBM and UniMERNet move from excluded to allowed. scikit-learn and LightGBM are installed as the optional `classical-ml` extra and stay unused by the pipeline until a later step needs them.
- UniMERNet is **deferred**: allowed, but blocked on CPython 3.14 (see dependencies.md). No separate interpreter is installed for it. PP-FormulaNet-L remains the formula-recognition candidate.
