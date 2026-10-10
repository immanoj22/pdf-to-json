# Step 10b: hold-out book 4 and a heading fix

Book 4 (a medical textbook, DocBook 4) is registered as the new hold-out. It was aligned once
with the frozen aligner, and its derived gold was written. The heading rules were then improved
on books 1 and 2, now both development books. After that every producer was frozen, and book 4
ran once through Steps 6–10. The text ledger and the committed gold of books 1–3 are unchanged,
and the old projects were not touched.

**Main findings**

- **Book 2 headings** went from precision 0.97 / recall 0.62 to **0.97 / 0.93**.
- **Book 1 headings** went from precision 0.43 / recall 0.86 to **0.74 / 0.85**. Book 1
  precision stays below the 0.85 target. The rest are reference conventions that no general
  rule separates (see Part B).
- **Book 4 (hold-out, run once):**
  - main-flow reading order 0.93;
  - body page labels 0.996;
  - furniture precision 0.96;
  - paragraph boundary F1 0.72;
  - headings precision 0.62 / recall 0.73, levels 0.16 exact but 0.97 within one;
  - zones 0.87 of pages.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | **807 passed**, 0 failed / 0 skipped (793 at Step 10 + 14 new) | [JUnit](../experiments/out/step10b/pytest.xml), [log](../experiments/out/step10b/pytest.log) |
| 24 measured pages vs original sources | **0 missing / 0 extra** | [cross-check](../experiments/out/step10b/original_source_crosscheck.json) |
| Full book | **495,751** retained tokens; passing | [full_book.json](../experiments/out/step10b/full_book.json) |
| I1–I7 on 24 pages | **0 each** | [invariants.json](../experiments/out/step10b/invariants.json) |
| Every line in exactly one unit and ordered once | 24 pages ([report](../experiments/out/step10b/units_every_line_once.json)); all lines of the four books, 0 problems (details below) | Step 10 summaries |
| Earlier metrics on books 1–2 not worse | Reading order, paragraphs, furniture and page labels: **identical**. Step 9 units are identical on every page (758 / 331), and no producer before Step 10 changed. Headings, levels, zones, contents links: **equal or better** (Part B) | Step 10 summaries |
| Ruff check / format, from backend/ | pass | [ruff.log](../experiments/out/step10b/ruff.log) |

Whole-book line gate details:

- **Books 1, 2 and 4:** checked by this step's Step 10 runs. Book 1 has 84,085 lines, book 2
  14,396 and book 4 20,142. Book 4's 20,142 lines are also checked by its Step 7, 8 and 9 runs.
- **Book 3:** 1,231 lines, from its Step 10 run. The Step 9 paragraph producer has not
  changed since then.

## Part 0: decisions

Recorded in [decisions.md](decisions.md).

- **Already recorded** (Step 10 follow-up, not repeated):
  - the heading default is rules only, with the classifier as an opt-in same-series profile
    setting that needs leave-one-book-out evaluation;
  - outline depth follows the contents depth;
  - the NIMAS adapter adds the rear-matter wrapper.
- **Book 2** is promoted to development for headings and later steps.
  - The promotion is logged as `promoted_to_development` in
    [step10/holdout_runs.jsonl](../experiments/out/step10/holdout_runs.jsonl).
  - Its Step 7–10 hold-out numbers stay the honest hold-out record.
- **Book 4** is the new hold-out.
- **Your instructions during this step** are recorded too:
  - the disk check;
  - the per-dialect profile check;
  - reading book 4 only from `Downloads/book4`.

**Infrastructure fix: per-dialect profile check (logged).**

- A gold manifest is now validated against the digest of *its own* dialect profile: the
  common vocabulary plus its dialect's entry. Previously it was checked against the digest of
  the whole profile file.
- Books 1–3 gold was **not** regenerated. Their per-dialect digests were computed from the old
  profile file before it changed and recorded as data in
  [profile_digests.json](../backend/reference_dialects/profile_digests.json). Adding the book 4
  entry left all three unchanged.
- New gold also records its per-dialect digest.
- The code is in
  [dialect_profiles.py](../backend/src/book_core/evaluation/dialect_profiles.py), outside the
  aligner's scope. Tests:
  [test_dialect_profiles.py](../backend/tests/test_dialect_profiles.py).
  - A new entry does not invalidate other books.
  - A changed entry invalidates only its own books.
  - A change to the common section invalidates all of them.
  - An unknown earlier file is never trusted.

## Part A: book 4 (hold-out) inventory and alignment

### Files

The folder you named (`Downloads/book4`) holds the PDF and a zip, which you extracted to
`XML/`. The package has 18 XML files:

- the complete book `9789366165769.xml`;
- its 16 parts (front matter, ch01–ch14, index);
- `page_info.xml`.

The complete book file is the reference. Nothing was modified, and no other folder in
Downloads was opened for book 4.

### Inventory

[book4_inventory.json](../experiments/out/step10b/book4_inventory.json)

| | |
|---|---|
| PDF | 314 pages (546×744 and 537×744 pt), InDesign 19.5; no PDF page labels; 16 outline entries |
| Digital vs scanned | **307 digital**; 6 blank or artwork-only (p6, 10, 14, 30, 40, 304); 1 image-only page (p2, no native text); **0 scanned text pages** |
| XML dialect | DocBook XML 4.2, root `book` without a namespace |
| Page markers | Empty `<anchor id="page…"/>` elements: 307 markers, FM3–FM35 (33) and 1–274 (274) |
| In-memory repairs | **none** |
| Reference units | 9,802: 7,204 paragraphs, 1,421 index entries, 538 headings, 359 other, 280 image descriptions |

**Dialect entry (data, logged).** `docbook4-page-anchors` was added to
[dialects.json](../backend/reference_dialects/dialects.json):

- it detects the root `book`, and it comes after the namespace-detected DocBook profile;
- its page markers are `anchor` elements.

The frozen reader takes a marker label only from element text or a `page` attribute. So the
entry also carries a data rule, `page_marker_label` (attribute `id`, pattern `^page(.+)$`),
which the gold writer applies (evaluation code). The reader treats *every* anchor as a page
marker. That holds for book 4, where all 307 anchors are page anchors (limitation 6).

### Aligner identity

The aligner's producer digest changed after Step 5b (`f092cfbf…` → `637e78c5…`). Before
aligning book 4, its behaviour was proven identical:

1. `git diff -w --ignore-cr-at-eol 0454d25 HEAD -- ledger reference`
   ([diff](../experiments/out/step10b/aligner_diff_since_5b.txt)):
   - the ledger has no change except line endings;
   - the reference package has only the atomic-retry write in `reference/cache.py`.
2. Book 3 was re-aligned with the current code. Its derived gold, written to a scratch folder,
   is byte-identical to the committed gold: `units.jsonl.gz`, `page_markers.json` and
   `pages.json`.
   - The manifest differs only in the two version fields, the alignment producer digest and
     the whole-file profile digest.
   - Evidence: [aligner_identity_book3.json](../experiments/out/step10b/aligner_identity_book3.json).
3. Both proofs are logged as "aligner digest changed, behaviour proven identical" in
   [step5/holdout_runs.jsonl](../experiments/out/step5/holdout_runs.jsonl).

An earlier book 4 alignment start was stopped on your instruction before it produced any
result. It is logged as `aborted`.

### Alignment coverage

One logged run: [summary](../experiments/out/step5/medical_anatomy/alignment_summary.json),
[gold](../backend/tests/gold_derived/medical_anatomy/), `human_approved: false`.

| | Book 4 |
|---|---:|
| **PDF tokens aligned** | **90,257 / 95,957 (94.1%)** |
| **XML tokens aligned** | **90,387 / 109,933 (82.2%)**; **99.3%** without image descriptions |
| Segments with tokens / located | 283 / 275 |
| Page markers placed | 283 of 307 |
| Placement jumps | 22 |
| Confidence median / lower quartile | 0.95 / 0.81 |

Unaligned tokens by cause (counts only; pages were not inspected):

| PDF-only cause | Tokens | XML-only cause | Tokens |
|---|---:|---|---:|
| furniture_candidate | 2,265 | image_description | **18,938** |
| figure_text_candidate | 911 | surplus_occurrence | 413 |
| surplus_occurrence | 854 | absent_from_pdf | 169 |
| absent_from_reference | 703 | segment_not_located | 23 |
| page_not_in_reference | 677 | no_native_pdf_text | 3 |
| folio_candidate | 290 | | |

Why the XML coverage is lower:

- The reference holds long written image descriptions (alt text, 280 units) that the PDF does
  not print, so they are unalignable by nature.
- 24 markers (FM6, FM10, FM26 and 21 body pages) open segments with no tokens, so they are
  not placed. Their cause was not inspected (hold-out).

## Part B: headings on books 1 and 2 (development)

### Classes before the fix

These are the committed Step 10 rules-only results.

**Book 1: 567 false headings after the contents-depth rule.**

| Class | Count | Examples |
|---|---:|---|
| Feature labels recurring once per section, set as paragraphs | 221 | "RELACIÓN CON LA GEOGRAFÍA" p32, p35; "PLANTEAR PREGUNTAS" p79 |
| Recurring and large in-section titles (protected as recurring or prominent) | 157 | "LA CONFEDERACIÓN IROQUESA" p26, "Tiempo y lugar: …" p28, "Avance" p30 |
| Box titles (callouts) | 54 | "[Preámbulo]" p38, "[Declaración de derechos naturales]" p38, "[Lista de agravios]" p39 |
| List items | 53 | "Divisiones políticas" p13, "El nuevo milenio" p13, "Referencia" p14 |
| Front-matter names and other subsections | 39 | "Davarian Baldwin, Ph.D." p6 (and two more names on p6) |
| Numbered lines | 19 | "C. Joseph Genetin-Pilawa, Ph.D." p6, "Artículo II" p65, "Artículo III" p67 |
| Figure and caption text | 16 | "La Constitución de Estados Unidos" p59, "Secesión de estados, 1860–1861" p90, "10 DE MAYO DE 1869 …" p116 |
| Table cells, front titles, book title, byline | 8 | "CORE", "NAACP", "SCLC" p465 |

The analysis also showed:

- **Style groups.** Six coarse style groups held 300+ false headings and no reference heading
  at all.
- **Part-bold lines.** 127 false headings were lines only partly bold: a bold lead running
  into regular text. No true heading in either book is part-bold.

**Book 2: 93 missed headings.**

| Class | Count | Examples |
|---|---:|---|
| Bold capitalised titles at body size, demoted by the label rule | 42 | "LESSONS FROM THE LISA STUDY" p26, "BEST PRACTICES IN FUTURE IMMIGRANT FAMILY RESEARCH" p28, "WHAT IS RESILIENCE?" p39 |
| Scored far below the threshold | 33 | "REFERENCES" p33 (4 of these: reference lists misread as an index); "High Parental Expectations/Parental Control" p92, "Family Conflict" p93 (italic subheadings: italic did not count as contrast) |
| Just below the threshold | 6 | "SIGNIFICANT GAPS IN DEVELOPMENTAL" p22 (a two-line title in two units), "RECOMMENDATIONS FOR RESEARCHERS" p29, "Canadian-born Chinese, and European" p62 |
| Run-in heading merged into a paragraph by Step 9 | 12 | "Community Mobilization This strategy…" p51, "Acculturation Attitudes In the ICSEY study…" p148, "Study 2: Montreal Participants and Measures…" p147 |

There was also a level problem. The chapter label, title and subtitle formed separate
headings ("Chapter 2" / "Immigrant Children" / "Making a New Life"), which pushed every
heading below them one level down.

### Rules added

All rules are book-relative and multilingual, with no page, font or size constants. Code is
in [structure/](../backend/src/book_core/structure/); tests are in
[test_structure_10b.py](../backend/tests/test_structure_10b.py). All six tests fail on the
committed Step 10 code.

1. **Part-weight lines.** A unit only partly in the heavier weight (bold share between 15% and
   85%) is a lead running into text, not a standalone title.
2. **Reference lists.** A new navigation kind, `bibliography`, for alphabetical entries most of
   which carry a year.
   - Commas before numbers in these entries (volumes, pages) are not index locators.
   - Only the list title heads the list.
   - Inside the body, the list stays part of its chapter.
3. **Isolated titles at body size.** A capitalised title of the running text, set apart by
   space on both sides and not recurring, is a heading, not a label.
4. **Italic titles.** A whole line in italic, single and unterminated, set apart by space
   before and after, counts as style contrast. An italic phrase does not.
5. **Contents depth, made stricter.** In a book whose contents define the outline:
   - a recurring in-section title is protected only when an occurrence of it is
     contents-linked;
   - "more prominent than any contents-linked heading" protects a title only on opener pages
     and in front and rear matter.
   - This follows the outline-depth decision.
6. **Colour-only numbered lines.** A numbered line set like the body, differing only in colour,
   is a list entry.
7. **Section templates.** Small labels of the running text that recur once per section
   together with at least two other such labels in the same sections are the step labels of a
   template (a procedure printed in every activity). They become `label` unless contents-linked.
8. **Chapter labels and subtitles.**
   - "Chapter 2" merges with the title under it, whatever their sizes.
   - A smaller display-size piece right under a title is its subtitle, but only in a style
     that almost never stands alone as a heading in the book.
9. **Recurring section titles.** A recurring title set at least at body size, in a style group
   made mostly of unique titles ("REFERENCES" closing each chapter), is a section title, not a
   feature label.

### Before and after, rules only

Evidence: [book 1 before](../experiments/out/step10b/headings_before_spanish_us_history.json),
[book 1 after](../experiments/out/step10b/headings_after_spanish_us_history.json),
[book 2 before](../experiments/out/step10b/headings_before_immigrant_children.json),
[book 2 after](../experiments/out/step10b/headings_after_immigrant_children.json).

| | Book 1 before | **Book 1 after** | Book 2 before | **Book 2 after** |
|---|---:|---:|---:|---:|
| Reference / our headings | 499 / 1,000 | 499 / 581 | 243 / 160 | 243 / 231 |
| **Precision** | 0.430 | **0.736** | 0.968 | **0.969** |
| **Recall** | 0.856 | **0.852** | 0.617 | **0.926** |
| F1 | 0.573 | **0.790** | 0.754 | **0.947** |
| Levels exact / within one | 0.749 / 0.998 | **0.753 / 1.0** | 0.533 / 1.0 | **0.862 / 1.0** |
| Zones, pages / units | 0.999 / 0.999 | 0.999 / 0.999 | 0.966 / 0.955 | **0.983 / 0.978** |
| Contents links, title and target | 0.944 | 0.944 | outline 0.905 | outline 0.905 |
| Styled non-headings | 1,090 display, 113 labels | 1,259 display, 187 labels | 42 labels | 0 |

Level counts after the fix:

- **Book 1:** L1 62, L2 440, L3 61, L4 18. Declared levels 0.68 exact; nesting levels 0.81.
- **Book 2:** L1 23, L2 89, L3 90, L4 29.

Roles after the fix:

- **Book 1:**
  - reference sidebar titles → ours: sidebar 213, structural 26 (was 195 / 66);
  - structural → structural: 132;
  - front-section titles: 9 of 10;
  - rear-section titles: 3 / 3;
  - letters: subsection 34.
- **Book 2:**
  - structural 220 / 222 (2 counted as rear);
  - front-section titles 3 / 3.

**A rule that helped one book but hurt the other was dropped or narrowed:**

- **Subtitle join.** Unrestricted, it merged book 1 lesson titles with the display title
  under them, and book 1 levels fell to 0.51. Restricting it to "a style that almost never
  stands alone" kept book 2's gain and restored book 1.
- **Template rule.** Counted over every stream, it also caught book 1's lesson template
  ("ESTRATEGIA DE LECTURA" in a box plus "ACTIVIDADES DE LA LECCIÓN"), and recall fell to
  0.61. It now counts main-flow labels only.
- **Recurring-title rule.** Applied to labels set below body size, it moved "PASAR A LA
  ACCIÓN BIEN FUNDADA" into the section stack, and book 1 levels fell. It now applies at body
  size or larger only.
- **Box-subtitle rule.** "A styled line below a box's first line is a display title" gained
  +0.004 precision and lost a true heading. It was not kept.

**Why book 1 precision stays at 0.74.** 152 false headings remain:

- **39 box titles** set as paragraphs, for example "[Preámbulo]" p38 and activity-box titles.
  The reference keeps biography and strategy box titles in the same streams.
- **33 feature labels**, including "RELACIÓN CON LA GEOGRAFÍA" (13), set like "ACTIVIDADES DE LA
  LECCIÓN", which the reference tags 62 times; and "?PREGUNTA DE INDAGACIÓN ¿…?" (19), a label
  and a question that Step 9 merged into one unit.
- **28 front-matter subsections:** consultant names on p6, and skill lists on p23.
- **18 numbered lines:** "Artículo II–VII", and lesson titles reprinted inside sidebars.
- **16 list items, 11 figure texts, 4 table cells.**

Separating these would need book-1 vocabulary or the reference's own choices. The same
visual patterns are tagged as headings elsewhere in the same reference. The contents-depth
outline (decided) is already applied.

## Part C: frozen producers and book 4 through Steps 6–10, once

**Freeze.** The freeze record is [freeze.json](../experiments/out/step10b/freeze.json),
re-verified after the runs (`step10b_freeze.py --verify`: all equal).

| Producer | Digest |
|---|---|
| alignment | `637e78c5…` |
| document | `512500ca…` |
| layout | `3e1aa754…` |
| reading_order | `32dcffa0…` |
| furniture | `dd3ccdbb…` |
| paragraphs | `a8a2cce4…` |
| structure evidence | `58e27666…` |
| structure | `f5a891d1…` |

The freeze also records the dialect profiles and runner digests.

**One logged amendment (runner only, no producer).** The Step 9 runner's hold-out guard
crashed on a log row without a book, and it read the Step 8 summary from a path only books
1–3 have. Both were fixed:

- the guard now counts started against aborted starts;
- the runner falls back to `out/step8/<book>`.

Two aborted starts are logged in [step9/holdout_runs.jsonl](../experiments/out/step9/holdout_runs.jsonl):

1. The first failed before any computation.
2. The second computed and cached the paragraph units, then failed before any metric.

The completed run reused those cached units. Every other stage ran once and is logged in
`step6`–`step10/holdout_runs.jsonl`.

**Disk** ([disk_check.json](../experiments/out/step10b/disk_check.json)):

- Estimate: 314 pages × book 1's per-page caches (27 MB per page) × 1.25 = **10.6 GB**. Free
  space was 17.6 GB, so the run fit within free space minus 5 GB (12.6 GB).
- Superseded entries were deleted only by the Step 9 rules plus the old Step 10 decisions
  (9 MB).
- The book 4 run used about 1.6 GB. 16 GB is free now.

### Book 4 hold-out results per stage

| Stage | Metric | Book 4 |
|---|---|---:|
| 6 Document evidence | retained tokens; body style | 95,957; 10 pt regular |
| 6 | printed contents candidates; outline entries | p11–13 and p306; 16 |
| 7 Reading order | **main flow**, pooled pairwise agreement | **0.934** (Kendall τ 0.867; adjacent 0.927; 87 / 275 pages perfect) |
| 7 | **float anchors** | **0.606**: tables 0.85, callouts 0.74, sidebars 0.68, notes 0.54, figures 0.49 |
| 7 | within floats | 0.930 |
| 8 Furniture and labels | **page labels, body (Arabic)** | **0.996** (252 / 253) |
| 8 | page labels, all scored markers | 0.890 (252 / 283); all 30 misses are front matter |
| 8 | **furniture precision** (proxy) | **0.958**: running heads 0.96, folios 1.0, running feet 0.46 (24 tokens) |
| 9 Paragraphs | **boundary F1, per-page units** | **0.717** (P 0.812, R 0.642) |
| 9 | exact match | 0.301 |
| 9 | **with page chains**: F1 / exact | **0.719 / 0.301** |
| 9 | split / merge errors | 1,046 / 3,796 |
| 10 Headings, rules only | **precision / recall / F1** | **0.619 / 0.731 / 0.670** (648 ours, 535 reference) |
| 10 | **levels** exact / within one | **0.164 / 0.969** (391 found, nesting) |
| 10 | roles (reference → ours) | structural 332 structural, 36 subsection, 13 front, 4 sidebar; front 5 / 5; rear 1 / 1 |
| 10 | **zones**, units / pages | **0.894 / 0.871** |
| 10 | contents links, title and target | 0.889 (88 / 99 resolved; 117 printed entries) |
| Gates | lines ordered once, in one unit; invariants | 20,142 / 20,142; 0; Step 9 units identical on all 314 pages |

**Reading these numbers.** They come from the single run; nothing was tuned. The causes below
are read from the run's own aggregate output, without inspecting pages.

- **Front-matter labels.** The reference names front pages "FM n" in its own numbering. For
  example, FM11 is on PDF page 15, which prints "xv". Six FM markers were also placed by the
  aligner on body pages 99–144. So front-matter labels are not comparable as printed labels.
- **Paragraph merges.** Merges dominate: this reference sets list items as separate
  paragraphs.
- **Heading levels.** Exact level accuracy is low but within-one is 0.97: levels are mostly
  off by one.
- **Zones.** The body was placed from p74 instead of the first Arabic page (p41). Fewer than
  two chapter openers were found by a sectioning word, so the opener fell back to the most
  prominent numbered heading.

### Books 1 and 2 headings with the frozen code

Identical to "after" above:

- **Book 1:** P 0.736 / R 0.852 / F1 0.790; levels 0.753 / 1.0.
- **Book 2:** P 0.969 / R 0.926 / F1 0.947; levels 0.862 / 1.0.

Both have Step 9 units identical on every page and 0 invariant problems. The `out/step10`
summaries of books 1 and 2 now hold these runs; the Step 10 versions are in commit `03e11e7`.
Summaries:
[book 1](../experiments/out/step10/spanish_us_history/summary.json),
[book 2](../experiments/out/step10/immigrant_children/summary.json).

## Limitations

1. **Book 1 precision is 0.74**, below the target. The remaining classes are reference
   conventions or Step 9 merges (Part B).
2. **Book 4 headings are worse than on the development books**: precision 0.62, levels off by
   one. As a hold-out, it was not inspected.
3. **Book 4 zones.** The body start depends on sectioning-word openers. Without them, the
   fallback opener started the body 33 pages late.
4. **Book 4 front-matter labels** cannot be scored against printed folios: the reference uses
   its own FM numbering.
5. **Book 2 run-in headings** merged into paragraphs by Step 9 (12) remain missed. Step 10
   does not split units.
6. **The book 4 dialect entry** treats every `anchor` as a page marker, because the frozen
   reader has no id filter. That is correct for book 4; another DocBook 4 book with non-page
   anchors would need a reader filter (an aligner change, logged).
7. **The new rules' constants** (bold share 15–85%, year share 0.5, template share 0.8,
   subtitle 10%) were chosen on books 1 and 2 only.
8. **Book 1 classifier.** The opt-in classifier was trained on the old rule features. It was
   not re-evaluated with the new rules.

## Decisions for you

1. **Book 1 precision.** Accept 0.74 as rules-only, with the residue documented as reference
   convention? Or ask for a client profile that follows this reference series (box titles and
   labels as paragraphs)?
2. **Book 4 zones.** May the next step use folio-run evidence (the first Arabic run starts the
   body) when fewer than two sectioning-word openers exist? This would be a post-hold-out
   change on development books, logged.
3. **Book 4 levels.** Should the next step look at book 4 levels? That would make book 4
   development, and a new hold-out would be needed.
4. **Front-matter page labels.** For references with their own front-matter numbering (FM n),
   should page-label accuracy be reported on body pages only?
5. **Page-anchor filter.** Approve a logged reader change that takes page markers only from
   anchors whose id matches the dialect's pattern?

## Reproduce

From `experiments/`:

1. Part A:
   - `python step5_run.py --book medical_anatomy --holdout --reason "…"`
   - `python step5_gold.py --book medical_anatomy --holdout`
   - `python step10b_inventory.py`
   - `python step10b_aligner_identity.py --scratch <dir>`
2. Part B: `python step10b_headings.py --label after`; `python step10_run.py --book <book 1 or 2>`.
3. Part C, in this order:
   - `python step10b_housekeeping.py --apply --pages 314`
   - `python step10b_freeze.py`
   - then `step6_run.py`, `step7_layouts.py`, `step7_run.py`, `step8_run.py`, `step9_run.py`
     and `step10_run.py`, each with `--book medical_anatomy --holdout --reason "…"`
   - `python step10b_freeze.py --verify`
4. Gates: `python step10b_gates.py`.

Pytest and Ruff run from `backend/`.

**Step 10b stops here for owner review. Step 11 has not started.**
