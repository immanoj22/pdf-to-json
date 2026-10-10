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

## Step 8 (confirmed by the project owner before Step 8)

- **General content policy:** when a content choice is open, the default follows the conventions
  of the human-made reference XML. Client profiles may override the default.
- The Step 7 rules (sub-lanes, row-synchronised lanes, same-structure band merge) are
  **accepted**. Backlog: Step 4 should detect narrow index gutters at the source.
- Float anchors stay at the float's centre until paragraphs exist; Step 9 moves them to
  paragraph boundaries. Captions without a linked figure stay in the main flow until the
  figures step.
- **Repeated designed boxes** (for example CONÉCTATE) are **content on every page**, as in the
  human reference, tagged with the role `repeated_box`. A client-profile setting may drop them
  in an adapter. The converter never drops them.

## Step 8 (confirmed by the project owner during Step 8)

- **Step 8 cache key:** accepted without registering a scope in `caching.py`, on two
  conditions, both met in `furniture/keys.py`:
  1. The book key binds the furniture package, the reading-order producer, the layout and
     order fingerprints, a Step 6 evidence digest (book vocabulary plus native document
     metadata, which includes PDF page labels), the job settings, the stage configuration and
     the version.
  2. A cache-key closure test (`tests/test_furniture_cache.py`) fails when a module imported by
     the Step 8 entry points is missing from the scope.
- **Backlog: per-stage cache keys.** Today every scope includes `caching.py` and the other
  common files. Registering a new scope therefore edits `caching.py` and re-keys every
  derived cache: native, analysis, layout, reading order and alignment. Rebuilding them needs
  more than the free disk (Step 8: about 25 GB needed, 18 GB free). Each stage's key should
  depend on its own producers and on the keys of its inputs, not on the registry file.

## Step 9 (owner decisions on the Step 8 gate, recorded before Step 9)

- **CONÉCTATE** stays content, as a sidebar float placed after the main text, as in the human
  reference. The adapter decides its output tag.
- **No change to the folio threshold after the hold-out.** Correctness rule (logged): PDF
  page-label metadata is trusted only when it agrees with the fitted printed folios elsewhere
  in the book. It then labels front matter only (pages before the first printed run) that has
  no fitted printed folio, with `source = metadata`. A front-matter edge line that prints
  exactly that label is the folio. Inside and after the runs, the sequence infers labels and
  metadata only confirms them or flags a disagreement. Book 2 was re-run once for this rule
  (logged in `experiments/out/step8/holdout_runs.jsonl`). Before/after is in
  docs/step9_report.md.
- **Book 2 derived-gold markers 146/147** were fixed with evidence: page renders, alignment
  detail, printed folios and PDF label metadata in `experiments/out/step9/gold_fix/`. The fix
  is logged with before/after in `experiments/out/step5/holdout_runs.jsonl`. Gold stays
  `human_approved: false`.
- **`repeated_box` requires drawn box or frame geometry** (native drawings: fills that cover
  the line, or a stroked frame around it, smaller than 40% of the page). Repeated text without
  it stays plain content.
- **Cache housekeeping:** delete only cache entries whose producer digest is superseded. Never
  delete current keys, gold or outputs. `caching.py` is unchanged.

## Step 10 (owner decisions on the Step 9 gate, recorded before Step 10)

- **Float anchors:** keep the Step 7/8 anchors in the emitted order; the paragraph-boundary
  proposals stay recorded as `AnchorMove` evidence. Revisit after the lists step.
- **Page joins:** the model keeps logical paragraphs as linked per-page units. The NIMAS
  adapter default follows the human reference and splits at the page marker; a client profile
  may emit joined paragraphs.
- **Glossary order** (entry by entry, Spanish then English, as the reference) and "entries
  never join across pages" are scheduled for the lists step.
- **Hyphenated compounds:** keep the book's own spelling; record the reference spelling as an
  alternative; an adapter option may follow the reference spelling.
- **Housekeeping:** report cache disk use and delete only superseded entries (as in Step 9).
  `caching.py` is not changed. **Per-stage cache keys** remain the next infrastructure task
  (backlog, Step 8).

## Step 10 (owner instructions during Step 10)

- Heading precision must be addressed before freezing: break false headings down by class;
  styled units that the reference treats as paragraphs or box text get a non-heading role
  (`display_title`, `label`) and keep their style evidence; whole-book consistency of style
  groups is used; if rules stay below about 0.8 precision, try the HeadingClassifier slot
  (scikit-learn/LightGBM, book 1 only, page-block cross-validation) and report rules-only vs
  rules+classifier; do not trade recall below 0.85 for precision.

## Step 10 follow-up (confirmed by the project owner after the Step 10 gate)

- **Default heading decision: rules only.** The LightGBM HeadingClassifier is an opt-in
  client-profile setting, for books of the same series as its training book only
  (`step10_run.py --heading-classifier`). Step 10 numbers behind the decision:
  - book 1, rules only: precision 0.430, recall 0.856, F1 0.573; levels 0.749 exact / 0.998
    within one;
  - book 1, rules + classifier, page-block cross-validation: precision 0.952, recall 0.878;
  - book 2 (hold-out), rules only: precision 0.968, recall 0.617, F1 0.754;
  - book 2 (hold-out), rules + book-1 classifier: precision 0.947, recall 0.074.
- **Outline depth follows the book's contents depth:** where the contents link the numbered
  sections, titles inside a section become `display_title` (not headings). A client option
  (`outline = all`) emits every visual title as a heading.
- **Classifier evaluation:** before any wider use, the classifier needs leave-one-book-out
  evaluation on more books.
- **NIMAS adapter:** adds the reference's rear-matter wrapper (an empty level above the rear
  section titles), so rear levels match the reference.
