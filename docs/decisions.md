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

## Step 10b (owner decisions, recorded before Step 10b)

Already recorded above (Step 10 follow-up) and not repeated: rules-only heading default with
the classifier as an opt-in same-series client-profile setting that needs leave-one-book-out
evaluation on more books; outline depth follows the contents depth (`outline = all` client
option); the NIMAS adapter adds the reference's rear-matter wrapper.

- **Book 2 is promoted from hold-out to development** for headings and later steps. Its
  Step 7-10 hold-out results stay recorded as the honest hold-out numbers (docs/step7-10
  reports). Logged in `experiments/out/step10/holdout_runs.jsonl` (`promoted_to_development`);
  `step10_run.py` treats it as development.
- **Book 4 (medical textbook, DocBook 4) is the new hold-out.** Its files are read only from
  the folder the owner named (`Downloads/book4`, configured in `experiments/references.toml`);
  the single reference is the complete book file `XML/9789366165769/9789366165769.xml` (the
  chapter files are parts of it).

## Step 10b (owner instructions during Step 10b)

- **Infrastructure fix: per-dialect profile check.** A gold manifest is validated against the
  digest of the dialect profile it uses (common vocabulary plus its own dialect entry), not
  the digest of the whole profile file, so adding a dialect entry does not invalidate other
  books' gold. Books 1-3 gold is not regenerated: the per-dialect digests of the earlier
  profile file are recorded as data (`backend/reference_dialects/profile_digests.json`,
  computed before the book 4 entry was added). New gold also records its per-dialect digest.
  Code: `book_core/evaluation/dialect_profiles.py`; test: `tests/test_dialect_profiles.py`.
- **Disk:** before a book 4 run, estimate its cache need from its page count and book 1's
  per-page cache sizes, delete superseded cache entries only, and stop if the estimate exceeds
  free space minus 5 GB.

## Step 11 (owner decisions on the Step 10b gate, recorded before Step 11)

- **Book 1 heading precision 0.74 is accepted** as the rules-only result. A series-specific
  client profile (box titles and labels as paragraphs, as this reference series does) may come
  with the Stage 2 client profiles.
- **Book 4 stays the hold-out** until a new reference book arrives. Then it is promoted to
  development, and its heading levels (mostly one off) are investigated at that point.
- **Page labels:** accuracy is reported for body pages (Arabic gold labels) and for all
  markers. A reference that numbers its front matter in its own series (for example "FM 3")
  is flagged (`reference_own_front_numbering`); its body-page figure is the comparable one.
  Code: `evaluation/furniture.py` (`marker_scores`).
- **Zones, body start:** with fewer than two sectioning-word openers, the body starts at the
  first Arabic folio run. This is a general rule, developed on books 1-2 (both have more than
  two openers, so they are unchanged) with a synthetic test, and logged. Code:
  `structure/zones.py`.
- **Reader, page anchors (logged aligner change):** an element named as a dialect's page
  marker is a page marker only when its id matches the dialect's `page_marker_label` pattern.
  Marker labels are unchanged: the aligner reads them for folio evidence. Books 1-4 derived
  gold was re-derived with the new reader and is byte-identical except the version fields.
  Book 2's committed gold carries the logged Step 9 marker fix, so the same fix was re-applied
  before comparing. Evidence: `experiments/out/step11/reader_identity.json`; logged in
  `experiments/out/step5/holdout_runs.jsonl`.
- **Glossary reading order (Step 11, recorded with evidence):** on a row-synchronised glossary
  page, lines are read entry by entry, as the human reference does: the first column's entry
  (term, then definition), then its page reference, then the next column's entry. Evidence:
  book 1 glossary pages 664-683 (Step 7 read them row by row and interleaved the languages).
  Glossary definition descriptions went from 0.22 to 0.95 exact, and main-flow reading order
  did not get worse (docs/step11_report.md).
- **Entries never join across pages like prose:** a Step 9 page join between glossary, index,
  reference or contents entries is dropped (recorded). An index or reference entry whose
  continuation opens the next page (an indented line with no open entry) is linked as a
  continuation, never merged.

## Step 11b (owner decisions on the Step 11 gate, recorded before Step 11b)

- **Book 4 is promoted from hold-out to development** (logged as `promoted_to_development` in
  `experiments/out/step10/holdout_runs.jsonl` and `experiments/out/step11/holdout_runs.jsonl`;
  `step10_run.py` treats it as development). Its Step 10b and Step 11 hold-out results stay
  recorded as the honest hold-out numbers (docs/step10b_report.md, docs/step11_report.md). The
  next new reference book becomes the hold-out.
- **Float anchors:** keep the Step 7/8 anchors.
- **Lists in table cells:** handled in the tables step.
- **Cross-reference words:** stay configuration data (locator kind only).
- **Contents depth:** mapped by the adapter (our indent levels onto the reference's depth).
- **No hold-out in Step 11b.** Every rule change is reported per book (1, 2, 3, 4); a change is
  kept only if it helps at least one book and does not make another worse beyond noise. Book 3
  (anecdotal) runs once per rule variant, logged in `experiments/out/step11b/runs.jsonl`.

## Step 11b (owner instructions during Step 11b)

- **Set-off list markers need repetition evidence.** A glyph set apart as its own span at the
  line start counts as a marker only when it is a known bullet glyph, or when the same glyph
  with the same font change starts at least two aligned lines of the block; colour is not
  required. A single italic letter or Greek symbol opening a line (statistics: "p < .001",
  "F(1, 147)", "α = .77") never counts.
- **Math operators are not markers** (Unicode Sm: = + < > ±), except the bullet-like dot
  operators ∙ ⋅ ∘. Dash lists must not swallow dialogue: a dash line whose text opens with an
  opening question, exclamation or quotation mark, or carries a dialogue tag, is not a dash
  item.
- **Single-item lists:** measured before any rule (counts in docs/step11b_report.md). The
  misses with a marker are below 1% of list items in every book, so no book-level rule was
  added; recorded as a known limitation.

## Step 11b (owner decisions on the Step 11b gate)

Step 11b is approved.

- **Index letter dividers are a reference convention.** In the next behaviour-changing step
  they get their own role, `index letter divider`. The evaluation scores them in a separate row
  and excludes them from heading precision and recall in all books. The adapter writes them as
  headings or not through a client-profile setting (default: heading). Gold is never edited.
- **Book 1 p215:** no action; the stream order is kept. To be re-checked in the
  character-repair / hidden-text step (the doubled lesson labels may be a hidden English
  layer).
- **Set-off markers without repetition evidence** (book 4: 19 block-boundary lines, 36 single
  lines) are accepted as text and recorded as known limitations. Revisit only if new books
  show more.
- **Next hold-out:** chosen from the new reference books in the book intake step, by a seeded
  random draw per category, before any pipeline run.

## Book intake (owner decisions on the intake report)

- **`ent_textbook` is the sealed hold-out** (JP category; seeded draw, seed 20261012, n = 1).
  Its evaluation is restricted to the pages its reference covers: the front matter and
  chapter 1, 46 pages. The pipeline may run all 612 pages for robustness only (no crash,
  ledger complete, I1-I7, timings), with no metrics on uncovered pages. Its results are
  labelled "small sample, same publisher as book 4". Logged as `sealed` in
  `experiments/out/book_intake/holdout_runs.jsonl`; not run in the intake step.
- **`deanta_pdf_mideast` is an unlabelled robustness book:** no reference and no metrics;
  only no crash, ledger, invariants and timings. `deanta_xml_canada` is not registered (its
  XML matches neither PDF). Deanta is redrawn with the same seed if a matching pair arrives.
- **Math hold-out: open need.** The owner supplies a book with math in its reference XML
  before Step 13.
- **Reference paths:** real paths live in the git-ignored `experiments/references.local.toml`,
  which `reference_paths.py` reads over `experiments/references.toml`. The committed file
  keeps keys only (empty values), for books 1-4 too; git history is not rewritten. Books 1-4
  resolve to the same files (path and SHA-256), and every existing metric and cache key is
  unchanged (evidence: `experiments/out/book_intake/`). The Step 6 rule audit's contract
  check of `references.toml` is historical and is not re-run.

## Step 11e (owner decision during the I5 correction)

- **Keep `unknown` plus `needs_review`.** A rotated fallback candidate that fails the
  existing I5 credit-evidence test remains retained as `unknown`, with its review flag.
  This is an insufficient-layout-evidence proposal, not a claim that the text has no
  semantic credit role: all five affected lines occur as credits in the human reference.
  Keep the checker and its thresholds unchanged. Make no further product change in
  Step 11e.
- **Page 724 is an accepted known limitation, not an accuracy pass.** The unchanged
  reading-order stage places the two newly unknown lines in the main stream between
  the second and third lines of reference paragraph 832. The paragraph splits after
  “alfombra,”, and two additional reference-unit pairs are reversed. Record the
  accuracy gate as **FAILED-FOR-REVIEW**; accepting the limitation does not waive it.
- **Alternative rejected for this step:** route unknown rotated lines near figures to
  a review stream in reading order. That would change another producer and is deferred
  for consideration in Step 12, where figures and credits are addressed. It is not an
  approved implementation rule or authorization to start Step 12.
- **Carry forward into the Step 12 and Step 17/adapter prompts:** `unknown` plus
  `needs_review` is the converter contract. Preserve source text, provenance and review
  state; do not silently promote these proposals to credits or discard them. Step 12
  is the natural place to resolve the page 724 interaction. Stage 2 mapping remains
  later work and is not implemented here.

## Step 11d continuation (hidden text and character evidence)

- **Hidden text is diagnosis only.** Render-confirmed opaque-cover evidence is computed,
  cached and kept on each layout page and in the final archive, and every confirmed or
  uncertain span gets a span review flag. Line building keeps native visibility. Applying
  the evidence (hiding the spans) was measured and rejected: on Spanish page 215 four
  visible-only table-of-contents units (04–07) became table text after the hidden English
  lines left, losing list-kind agreement on four reference items and adding a missed table
  anchor. Under the owner's rule a worse visible-only unit is a regression; no general
  narrowing of the hiding rule addresses a table-detection reaction, so the behaviour
  change is withdrawn. Changes that came only from hidden lines leaving the count (the six
  medical chapter-opener running heads, the other Spanish pages) were acceptable but are
  not applied either.
- **Character evidence is flags only.** A separate stage after lists flags spans whose
  decoded Unicode may not describe the painted glyph: a strict glyph-list name that
  disagrees after NFKC and case folding (format characters and first-character agreement
  of multi-character decodings exempt), or an unnamed/mismatched glyph repeated as a set-off
  list marker. No code point, font, book or page key. Original and NFKC text are never
  changed; no stage reads the flags.
- **Marker category experiment rejected** (it hurt Spanish US history and immigrant
  children; no change on art-therapy index or medical anatomy). List classification is
  unchanged.
- **Carry forward:** applying hidden-text evidence needs table/list detection that is robust
  to the removal (candidate for a later step); outline-based repair (beta-shaped `b`) and
  the three unflagged isolated `¾` markers remain open.

## Step 12 Part 0 (owner decisions for figures, captions and credits, recorded before Step 12)

- **Image file naming** is a client-profile setting (`FigureSettings`), default
  `page_{label}_{n}`: `label` is the printed page label (Step 8), `n` the figure's 1-based
  reading-order position on that page. An inferred label (Step 8 `inferred`) is used and the
  figure is marked `label_inferred` with a review flag; with no label at all the name is
  `page_pdf{index}_{n}` (physical PDF page) with a review flag. A composite figure is one file;
  a spread is one file named by its start page. Labels keep their form (`HT12`); characters
  that are not letters or digits become `-`; Windows device names are avoided. Names are never
  repeated in a book (case-insensitive; a numeric suffix with a review flag). The pattern is
  configurable without a code change (for example `page_no_{label}_picture_no_{n}`; fields
  `{label}`, `{n}`, `{index}` with format specs).
- **Format:** JPG for photographs, PNG for drawings, diagrams, maps and line art, decided from
  measured evidence only: raster share of the figure box (raster vs vector source) and colour
  and tonal statistics of the rendered crop. Mixed evidence is PNG with a review flag. File
  names are never consulted.
- **Alt text (option B):** every figure has an alt-text slot `{text, status, source}`, empty
  with status `needs_review` and source `none` by default. The optional draft generator
  (SmolVLM-256M-Instruct, Apache-2.0, immutable revision `7e3e67ed…`) is implemented behind
  `FigureSettings.alt_text_drafts`, **off by default**; drafts are English only, source
  `model_draft`, always `needs_review`, and the model rejects a verified draft. Licence and
  CPython 3.14.8 compatibility were verified first (smoke draft generated on CPU; evidence
  `experiments/out/step12/alt_text/smoke.json`). It uses the existing optional `models` extra
  (Transformers, Torch, Pillow); no new dependency.
- **Frameworks:** PyMuPDF (through the Extractor render), OpenCV (crop statistics and JPG/PNG
  encoding), Shapely and NumPy. Pillow is not used by the default path (only by the optional
  draft generator, already in the `models` extra). No new dependency.
- **Model placement:** figure records live in a new `figures` stage (`book_core.figures`),
  like every earlier stage's typed output, and are published in the final archive. The
  universal node module (`model/`) is not edited in this step: it belongs to the common cache
  scope, and an edit would re-key native extraction and analysis for every page without any
  change to their content. Figure settings are kept apart from the job `Settings` for the same
  reason (the job settings enter the furniture, paragraph, structure and list keys).
- **Carry-forwards:** (a) book 1 p724 is resolved through credit/figure association in the
  reading order (rotated `unknown` text within the existing credit reach of a figure is read
  with that figure; the region stays `unknown` and the link stays `needs_review`); (b) the
  hidden-text and marker flags of Step 11d stay flags only and are not changed.

## Step 12 (owner decisions on the Step 12 gate)

Step 12 is approved.

- **Credits are page-level records.** Each credit or source line is a page credit with the
  figure(s) its rule proposes, an explicit confidence and `review_required`; it is never
  linked to a figure. This matches the reference: in book 1, 467 of 468 credits are separate
  paragraphs (none inside a figure group's credit slot).
- **"Model disagrees" is a must-check flag.** A figure that not both layout models (Heron,
  PP-DocLayoutV3) find is flagged. The evidence is on by default whenever the models extra is
  installed; without it the run warns clearly that figure review flags are reduced. The flag
  never drops a figure.
- **Book 1 caption linking by reading order stays disabled** (books without caption
  numbering). A trained caption classifier is deferred to a figure follow-up after Step 14
  (tables), validated across books, never on one book alone.

Carry-forwards:

- **Step 17:** remove figure-internal and infographic text (not embedded by the layout) from
  paragraph units.
- **Figure follow-up:** book 4 figure placement (figure anchors 0.487); book 2 rotated
  thin-line diagrams (`pg129_1`, `pg175_1`).
- **Step 14 (tables):** unflagged false figures, starting with the p447 empty organizer table
  (also graphic-organizer pieces and map strips).
- **Later gold review:** derived-gold caption misalignment (84 book 4 caption links whose
  text is a reference figure title but whose tokens are aligned to `para` units). Gold is not
  edited until then.

## Step 13 Part 0 (math reference books, recorded before Step 13a)

- **Math development book: OpenStax *Statistics*** (the book titled exactly "Statistics";
  CC BY 4.0). The `math_book` folder was empty (absent), so the official PDF was downloaded
  from the OpenStax CMS record (`https://openstax.org/apps/cms/api/v2/pages/?type=books.Book&slug=statistics`,
  licence "Creative Commons Attribution License", `https://creativecommons.org/licenses/by/4.0/`):
  `https://assets.openstax.org/oscms-prodcms/media/documents/high-school-statistics_-_WEB.pdf`,
  871 pages, SHA-256 `6aef489acbf932c6d94e8b6bf5339f0eeb60835f928a72e34ad8f937551e8def`,
  stored in `Downloads/math_book/` (read-only; nothing else in Downloads is used). Reference
  key `statistics_pdf`.
- **Source:** `https://github.com/openstax/osbooks-statistics`, commit
  `7dea80ae2800386d470b11f6528962f9c4992d15`, cloned into the git-ignored
  `.cache/external/` (key `statistics_cnxml`). `LICENSE` is CC BY 4.0 and the only collection
  (`statistics.collection.xml`) declares CC BY 4.0; the 101 modules carry no licence element
  of their own (they inherit the collection's).
- **Edition check: same edition.** Title "Statistics" (PDF metadata and collection); the 13
  chapter titles match the PDF outline exactly; sample equations (pages 19 and 29) sit at the
  reference positions. The PDF was built 2026-04-20; the one later source commit
  (2026-04-23) rewords one preface paragraph without math. No mismatch.
- **Math hold-out: OpenStax *Algebra and Trigonometry* 1e, sealed.** Seeded draw (seed
  20261014, n = 1) between the two CC BY 4.0 first editions the owner named (College Algebra,
  Algebra and Trigonometry; branch `1e` of `osbooks-college-algebra-bundle`, commit
  `8322d84e2df67cad5ba6616fd306eb22427a50c4`, all four collections CC BY 4.0). Official PDF
  `https://assets.openstax.org/oscms-prodcms/media/documents/AlgebraAndTrigonometry-OP_1tE6R5r.pdf`,
  1,220 pages, SHA-256 `7bfd1ff40e044124fb32abada59fb6604f2f412a448a3e417c246f3352fa04bb`,
  in `Downloads/math_book/holdout/` (key `math_holdout_pdf`). Edition identity: title and all
  13 chapters (the PDF outline drops one serial comma; the first check compared punctuation
  and logged `edition_mismatch`, the corrected letters-and-digits check logged `sealed`; both
  records stay in `experiments/out/step13/holdout_runs.jsonl`). Never run until the final
  benchmark.
- **No NC/NC-SA book** was downloaded or used.
- **The CNXML reference is a math-only dialect** (`backend/reference_dialects/math_dialects.json`,
  its own file, never merged into `dialects.json`), used only to derive and score math gold;
  never a heading/paragraph/list style model. Gold records the profile, collection, module and
  PDF digests.
- **Frameworks:** fontTools 4.66.1 (MIT, pure Python, already installed for Step 11d) becomes a
  core dependency for font-program evidence. **UniMERNet re-checked: not added.** Licence
  passes (Apache-2.0, 0.2.3, unchanged since 2024-12-26), compatibility fails: its pins
  (`transformers==4.42.4`, `timm<0.10`, `opencv-python<5`) pull NumPy 1.26.4, which has no
  CPython 3.14 wheel and needs a C compiler (dry-run log
  `experiments/out/step13/dependencies/unimernet_dry_run.log`). PP-FormulaNet-L, SymPy,
  latex2mathml and the layout models stay as installed. No other new dependency.

## Step 13a (owner decisions on the Step 13a gate)

Step 13a is approved.

1. **Text-set math** (`p < .001`, `.15 + .25 = .40`): by default it stays text, owned by its
   text unit, with an equation record beside it (as the references keep it). A client-profile
   option may emit MathML (Step 13c).
2. **Equation regions take precedence over figure regions.** A figure region whose content is
   only equation glyphs becomes equation regions; a real figure containing math keeps the
   figure and also records the equation. Nothing may vanish: every drawn math glyph gets an
   owner.
3. **Verified gold** (1,254 equations, `human_approved: false`) is the Step 13c MathML scoring
   set, together with seeded manual checks.
4. **Layout-model formula boxes are support evidence only.**
5. **Step 13b** starts with boundaries (inline merges, display splits) and ownership; MathML is
   Step 13c.

Backlog: Statistics I7 = 1 (page 870, index gutter).

## Step 13b (owner instructions during Step 13b)

- **Disk check measures the real need (permanent rule, replaces the Step 10b four-book
  estimate).** A run needs the bytes of the stages its book has not cached under the current
  producers, plus the final archive (records and images), and keeps the 5 GB reserve. A stage
  is cached when the book's current registry entry was written by the current producer and
  all its files exist. Each missing stage costs, per page, the larger of an even share of the
  per-page estimate and its measured bytes per file; the final archive costs the larger of an
  even share and the measured sum of all stages; the total never exceeds the full estimate,
  which a book with nothing cached needs (`cache_admin.disk_need`, checked by `run_book`;
  experiment drivers only record free space).
- Superseded Step 13b Statistics archives were deleted after a dry-run list; the development
  bundles are kept; cleanup of earlier steps' superseded data is reported as a dry run only.
