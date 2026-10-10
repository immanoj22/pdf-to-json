# Step 10: headings, levels, roles and book parts

Every Step 9 unit that looks like a title is now a heading candidate with evidence. Candidates
become one of three things: a **heading** (with a neutral level and role), a **display title**
or a **label**. The last two are non-heading roles: the unit keeps its style evidence but is
not a heading. Printed navigation pages are classified (contents, index, glossary, other list).
Contents entries are resolved to pages and units. Every page has a zone (front, body, rear)
and a section kind. Every decision carries confidence and reasons.

Step 10 only reads the Step 9 units and order; it changes neither. The ledger and the gold are
untouched, and old projects were not touched.

**Main finding.** On book 1, rules plus a heading classifier reach precision 0.95 and recall
0.88 in page-block cross-validation. On hold-out book 2 the book-1 classifier fails (recall
0.07), while rules alone reach precision 0.97 and recall 0.62. Which one is the default is a
decision for you (see Decisions).

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | **793 passed**, 0 failed / 0 skipped (774 at Step 9 + 19 new) | [JUnit](../experiments/out/step10/pytest.xml), [log](../experiments/out/step10/pytest.log) |
| 24 measured pages vs original sources | **0 missing / 0 extra** | [cross-check](../experiments/out/step10/original_source_crosscheck.json) |
| Full book | **495,751** retained tokens; passing | [full_book.json](../experiments/out/step10/full_book.json) |
| I1-I7 on 24 pages | **0 each** | [invariants.json](../experiments/out/step10/invariants.json) |
| Every line in exactly one unit and ordered once | 24 pages ([report](../experiments/out/step10/units_every_line_once.json)); all lines of the three books (84,085 / 14,396 / 1,231), 0 problems | per-book summaries |
| Reading-order and paragraph metrics not worse | **Identical.** Every page of all three books has the same units, joins and order as the frozen Step 9 run (758 / 331 / 9 pages, 0 differing). Step 10 writes neither | per-book summaries |
| Structure stage on the 24 one-page fixtures | runs; every heading or styled unit is a unit of its page | [report](../experiments/out/step10/structure_on_fixtures.json) |
| Ruff check / format, from backend/ | pass | [ruff.log](../experiments/out/step10/ruff.log) |

## Part 0: decisions and housekeeping

Recorded in [decisions.md](decisions.md):

- **Float anchors.** The Step 7/8 anchors stay; the paragraph-boundary proposals stay recorded.
- **Page joins.** The NIMAS adapter default splits at the page marker. A client profile may
  join paragraphs instead.
- **Lists step.** Glossary order and "entries never join across pages" are scheduled there.
- **Compounds.** The book's own hyphenated spelling is kept, with the reference spelling as
  an alternative.
- **Backlog.** Per-stage cache keys remain the next infrastructure task.
- **Your mid-step instructions** on heading precision are recorded as well.

Housekeeping ([log](../experiments/out/step10/housekeeping.json)):

- Deleted only superseded Step 10 development entries: 1 evidence file and 3 decision files,
  13 MB. `caching.py` is unchanged.
- Cache use now: step7 27.0 GB, objects 5.2 GB, step6b 3.0 GB, step9 0.40 GB, huggingface
  0.30 GB, step6 0.13 GB, step8 0.11 GB, pip 0.10 GB, step5 26 MB, step10 12 MB. 17 GB free.
- The Step 9 paragraph caches for books 2 and 3 were refilled under the current paragraph
  producer ([log](../experiments/out/step10/paragraph_cache_fill.jsonl)). The producer changed
  only by the logged, comment-only Step 9 edit. The refill ran the unchanged stage code and
  computed no metric. The identity gate above confirms that every page is identical.

## Design (brief)

[structure/](../backend/src/book_core/structure/) has two passes.

- **Pass 1 (evidence, cached).** Per-unit evidence: style (character-weighted size, weight,
  case, colour), position along the page's own block axis, spacing, sentence cues, navigation
  entries and a leading-run record for run-in headings.
  - Its key ([keys.py](../backend/src/book_core/structure/keys.py)) depends only on the pass-1
    producers, so rule changes never re-read the book.
- **Pass 2 (decision, cached).** The key binds the whole package, the evidence key, the
  configuration and the classifier identity (model digest and threshold).
- **Tests.** Closure tests cover both entry points, and a test proves that a decision edit
  does not re-key the evidence.

**No absolute sizes.** Style is judged against the book's body style. A *coarse style group*
is (size step of about 12% relative to the body, weight, case); colour is separate evidence.

**Navigation** ([navigation.py](../backend/src/book_core/structure/navigation.py)):

- **Index:** alphabetical entry order, measured per column so row-synchronised bilingual
  columns count, plus comma locator lists.
- **Glossary:** the same order with longer entries and no locators. Runs extend to
  neighbouring pages with the same structure.
- **Contents vs other lists:** Step 6 rows whose targets (resolved through Step 8 labels)
  advance with the list.
  - Lists split where a label series restarts.
  - The first list spanning the book is the contents; one whose targets are the following
    pages is a local contents list; the rest are other lists.
- **Rejected:** figure-text pages (maps) and pages whose targets do not advance.
- **Title lexicon:** a small multilingual list-title lexicon is supporting evidence only
  ("índice" is decided by structure).
- **Contents entries** are ordered by reading order and fuzzy-matched to units on their target
  page.

**Heading candidates** ([headings.py](../backend/src/book_core/structure/headings.py)): summed
evidence.

- **For:** style contrast relative to the body, the Step 4 block type, isolation, numbering
  ([numbering.py](../backend/src/book_core/structure/numbering.py): multilingual sectioning
  words, CJK 第N章, decimal, bare numbers, Roman numerals, alphabet letters; dates are not
  numbers) and contents or outline links.
- **Against:** figure and table text, lines of navigation pages, later lines of a box,
  letter-spaced lettering, questions and digits.
- **Whole-book passes:**
  - A label recurring once per section is a feature title; one recurring several times in a
    section is an inline label.
  - Lowercase continuations of large titles join them.
  - Runs of four or more same-style lines are list entries.
- **Merging:** pieces merge into one heading: a label above a title, a bare lesson number, or
  a title split into several blocks.
- **Run-in headings:** a main-flow paragraph that opens with a 2–8-word run in contrasting
  weight or size, ending in a full stop or dash, is a run-in heading. It is a span range; the
  unit stays a paragraph.

**Non-heading roles** ([styled.py](../backend/src/book_core/structure/styled.py)), whole-book
consistency without gold:

- **display_title:** when the book's contents list reliably links its numbered sections (book
  1: 125 links, 71% of numbered body headings), the contents define the outline. A body title
  that is not numbered, not linked, not on an opener page and not a box or feature title is a
  display title of its section's text.
- **label:** a capitalised title no larger than the body, with no once-per-section evidence.
- **Protected:** numbered or linked titles, once-per-section recurring titles, titles more
  prominent than any linked heading (openers), and titles in a style group made mostly of
  numbered or linked headings.
- **Configuration:** `outline = all` keeps every title as a heading.

**HeadingClassifier slot** ([classifier.py](../backend/src/book_core/structure/classifier.py)):

- **Model:** LightGBM, behind the existing `accuracy.interfaces.HeadingClassifier` protocol
  (features in `HeadingInput.features`, likelihood in `HeadingResult`).
- **Features:** 39 gold-free features per candidate, including whole-book style-group
  statistics (group size, numbered/linked share, occurrences per section). The most important
  were group numbered/linked share, occurrences per section, space after, the rule score and
  repetition.
- **Training:** book 1 derived gold only
  ([experiments/step10_classifier.py](../experiments/step10_classifier.py), GroupKFold(5)
  over 20-page blocks). The threshold, 0.2, was chosen out-of-fold as the best F1 with
  recall ≥ 0.85.
- **Model file:** [backend/heading_models/](../backend/heading_models/), with a manifest.
- **Optional:** LightGBM is the optional `classical-ml` extra; without it the rules decide.

**Levels and roles** ([hierarchy.py](../backend/src/book_core/structure/hierarchy.py)): a stack
over book order.

- **Prominence:** a heading closes open sections that are no more prominent. The title piece,
  not a decorative number, sets prominence.
- **Spine:** numbered or contents-linked headings form the spine. An unnumbered heading never
  closes a spine section.
- **Sectioning-word sections:** a part/unit/chapter section closes only at an equal or higher
  word.
- **Contents-level consistency:** headings with the same contents level and style share one
  level.
- **Resets:** each front or rear section and each inserted label run starts a new stack.
- **Attached titles:** box and feature titles take the level of the innermost spine section.
- **Never skips down:** a level never skips going down (a validator enforces it).
- **Roles:** from numbering words per level, else chapter → section → subsection; front/rear
  section titles; sidebar and feature titles; the book title.

**Zones** ([zones.py](../backend/src/book_core/structure/zones.py)):

- The body runs from the first opener (a part/unit/chapter-numbered heading) through the last
  numbered heading of the main folio run.
- Rear matter starts at a glossary or index page, an appendix or bibliography title, or an
  unnumbered top-level title after that.
- Before the body is front matter: cover, title page, copyright (©/ISBN), titled preface or
  dedication, contents and other lists.
- A run in another label series holding numbered sections is body matter. Its *logical* order
  follows the contents list.

## Results per book (no overall score)

Book 1: development. Book 2: hold-out, run once. Book 3: anecdotal hold-out, run once. The
producer was frozen at `5dceeb47…` with model `19d85e77…` before the hold-outs
([log](../experiments/out/step10/holdout_runs.jsonl)).

One aborted book-2 start is logged with its reason: the precondition failed before any Step 10
computation. The runner now logs "started" only after its preconditions pass.

### Headings

| | Book 1, rules only | Book 1, rules + classifier (out-of-fold) | Book 1, emitted (in-sample) | **Book 2, rules only** | Book 2, emitted (rules + classifier) | Book 3 |
|---|---:|---:|---:|---:|---:|---:|
| Reference headings | 499 | 499 | 499 | 243 | 243 | 2 |
| Our headings | 1,000 | 486 | 475 | 160 | 22 | 2 |
| **Precision** | 0.430 | **0.952** | 0.987 | **0.968** | 0.947 | 1.0 |
| **Recall** | 0.856 | **0.878** | 0.900 | **0.617** | **0.074** | 1.0 |
| F1 | 0.573 | 0.913 | 0.942 | 0.754 | 0.137 | 1.0 |
| Level exact / within one | 0.749 / 0.998 | 0.733 / 0.995 | **0.748 / 0.998** | 0.533 / 1.0 | 0.833 / 1.0 (18 found) | 1.0 / 1.0 |

Notes on the table:

- The emitted book-1 run uses the model trained on all of book 1, so it is in-sample. The
  honest book-1 figure is the out-of-fold column.
- Before your instruction, rules alone stood at precision 0.21 and recall 0.94 (2,241
  headings).
- Book 1 levels by reference method (emitted): **declared 0.70 exact / 0.99 within one**
  (187); **nesting 0.78 / 1.0** (262).
- Book 2 levels are all of the nesting method.
- Book 2's emitted levels are reported for the hold-out run itself. Its rules-only levels,
  roles and precision/recall come from the rules-only decision cached in the same single run;
  no new decision was made.

**The book-1 classifier does not transfer.** It learned book 1's conventions: in-lesson titles
and recurring labels are not headings. Book 2 is an academic book whose reference tags every
section level. Its rule decisions are already precise (0.97), and the classifier rejects
most of them. Book 2 has no linked printed contents (its Step 6 candidates are index rows), so
the contents-outline rule did not apply and rules kept every titled section. Book 2's
remaining rule misses were not inspected (hold-out discipline).

**Book 1 false headings, rules before the non-heading roles** (1,764, your item 1):

| Class | Count | Examples |
|---|---:|---|
| Display titles the reference tags as paragraphs | 1,244 | "Avance" p726, "La Rama Legislativa" p51, "Mayor intervención de EE. UU." p497 |
| Callout/feature labels (caps, body size or smaller) | 302 | "FUENTE PRIMARIA: ORDEN EJECUTIVA" p532, "FUENTE PRIMARIA: DISCURSO" p646, "FUENTE PRIMARIA: CARTA" p81 |
| Other (box subtitles, mixed blocks) | 128 | "Analizar ideas y detalles clave" p305, "Proyección de Robinson" p746, "FRelaciones con la actualidad" p757 |
| List items | 33 | "1. Escritura argumentativa…" p400, "05 El primer Nuevo Trato" p257, "2. Utilizar recursos multimedia…" p90 |
| Figure/map labels, timeline entries | 27 | "ABRIL DE 1993" p544, "ABRIL DE 1961" p356, "igual salario por igual trabajo" p535 |
| Contents/list lines | 25 | "LECCIÓN DE REPASO Y APLICACIÓN" p8, "LECCIÓN INTRODUCTORIA" p11, "05 Estados Unidos se prepara para la guerra" p299 |
| Table headers/cells | 4 | "SCLC", "CORE", "NAACP" p465 |
| Bold quotation | 1 | p300 |

- **Glossary terms:** none. Glossary pages are classified, so only dividers and the list title
  can head them.
- **Emitted book 1:** 6 false headings remain. 1,429 display titles and 299 labels are kept as
  styled non-headings.
- **Rules only:** 1,090 display titles and 113 labels.

**Reference conventions (documented, not tuned to):**

- The book 1 reference sets in-lesson subsection titles as paragraphs (about 900 units in the
  15 pt bold group alone). The owner's example "LA CONFEDERACIÓN IROQUESA" (p26) is one; it is
  now a display title.
- Sidebar titles take their lesson's level.
- The rear matter sits under an empty level-1 wrapper, so Atlas, Glossary and Index are
  level 2 and the letters level 3. We emit 1 and 2, which is within one.
- The harness reports a convention class: a cell (style group × role) of at least 20 headings
  that the reference never tags as a heading and sets as paragraphs at least 80% of the time.
  It reports precision with and without such classes. With display titles, book 1 (emitted)
  has none left.

**Role confusion, book 1 emitted** (reference class → ours):

| Reference class | Ours |
|---|---|
| Structural | structural 134 |
| Sidebar title | sidebar/feature 195, structural 66 |
| Front section title | front 9, subsection 1 |
| Rear section title | rear 3 |
| Rear subsection (letters) | subsection 34, sidebar 6 |
| Book title | subsection 1 |

The reference's book title is "Tiempos modernos"; ours is "HISTORIA".

Book 2, rules only: structural 122 (+23 as sidebar, 2 as rear), front 3/3.

### Hierarchy summary (book 1, emitted)

| | |
|---|---|
| Levels | L1 42, L2 348, L3 58, L4 27 |
| Roles | unit 18, chapter 118, section 56, subsection 63, sidebar 86, feature 120, front 10, rear 3, book title 1 |
| Level methods | attached 206, style rank 175, contents 80, zone 14 |

The spine is TEMA *n* (unit, L1), then lessons "01 …" (chapter, L2), then "Aplica lo que has
aprendido" and similar (L3). Box and feature titles sit at the lesson level.

### Owner's case: "Authors" / "Mapas" / "Biografías"

| | Result |
|---|---|
| Old project (phase0) | Exact labels emitted as paragraphs |
| Step 9 | `heading_candidate` units with no level or role |
| **Step 10** | **Headings, level 1, role `front_section_title`**: Authors p5 (0.87), Biografías p20 (0.85), Mapas p21 (0.85). Also Fuentes primarias, Análisis de casos, Tablas y gráficas, Actividades del tema and Tabla de contenido. Front-section titles: 9 of 10 reference titles found with the right role |

### Navigation and contents links

| | Book 1 | Book 2 | Book 3 |
|---|---|---|---|
| Contents pages | 7–13 | none | none |
| Other lists | 15–19, 21–22 (sources, biographies, maps, tables) | – | – |
| Glossary pages | 664–683 (bilingual) | 33–34 (false; hold-out, not tuned) | – |
| Index pages | 685–719 | 61 pages (Step 6 confusion resolved, but also some body pages) | 6–9 |
| Rejected Step 6 candidates | 14 (figure text), 20, 23, 25, 104, 111, 175, 257, 299, 409, 486, 539, 589, 628, 645 | 9 | – |
| Printed entries → target page / → unit / title + target correct | 163/164 / 126 / **0.944** | – | – |
| Outline (bookmark) entries resolved to a unit / correct | 2 of 764 (production file IDs) / – | 21/21, **0.905** | – |

Two Step 6 problems are resolved: the index pages are no longer contents pages, and the map
pages (104, 409, …) are no longer navigation at all.

### Zones (book parts)

| | Book 1 | Book 2 | Book 3 |
|---|---:|---:|---:|
| **Unit accuracy** | **0.999** | 0.955 (metadata as front: same) | 0.443 |
| **Page accuracy** | **0.999** (753/754) | 0.966 (0.973 with metadata as front) | 0.444 |

Zone maps:

- **Book 1.**
  - Front: cover 1; front 2; title page 3; copyright 4; front 5–6; contents 7–13; front 14;
    other lists 15–19 and 21–22; front 20 and 23–24.
  - Body: units at 25, 111, 175, 215, 257, 299, 351, 429, 469 and 581 (through 650).
  - Rear: atlas and gazetteer 651–663, glossary 664–683, 684, index 685–719, 720–722.
  - HT block: body chapter 723–758.
  - The only page miss is p2, which the reference puts in rear matter (inside cover).
- **Book 2.**
  - Front: cover 1–2, front 3, title page 4, copyright 5, dedication 6, front 7–11.
  - Body: 14 chapters 12–301.
  - Rear: index 302–304 and 308–327, rear 305–307 and 328–331.
  - Misses: 302–306 and 328–330, which the reference has as body. The index detection fired
    early, on the pages just before the real index.
- **Book 3.** Body 1–5, index 6–9. The reference tags all 9 pages rear: they are index
  fragments with no opener, so pages 1–5 default to body. Anecdotal.

**The moved HT block (book 1, pp. 723–758) lands where the reference puts it:**

- Its pages run in their own label series (HT1–HT36) and hold numbered lessons, so the zone
  is body.
- Physical order is kept.
- The contents list (p7), read in reading order, lists the HT lessons first (left column). The
  HT section therefore gets `logical_index` 11, before TEMA 1 (index 12), with the reason
  "the table of contents lists this block before the first body section". This is the
  reference's order.

## Overlays

Headings are boxed with `L<level> <role>`. Display titles are thin grey `D` boxes and labels
grey `L` boxes. The top band shows zone and section kind. Red means low confidence. All eight
were inspected. [Index](../experiments/out/step10/overlays/overlays.json).

| Page | What it shows |
|---|---|
| [p25](../experiments/out/step10/overlays/structure_p25.png) | Unit opener: TEMA 1 L1 unit; the title split by Step 9 (L2); lesson-list labels |
| [p31](../experiments/out/step10/overlays/structure_p31.png) | Lesson title "02 La guerra de Independencia" L2; reading-strategy box L2 sidebar; in-lesson titles as display titles |
| [p26](../experiments/out/step10/overlays/structure_p26.png) | Lesson 01; "LA CONFEDERACIÓN IROQUESA" as a display title |
| [p119](../experiments/out/step10/overlays/structure_p119.png) | Sidebar page: biography box |
| [p7](../experiments/out/step10/overlays/structure_p7.png) | Contents page: only the list title is a heading |
| [p690](../experiments/out/step10/overlays/structure_p690.png) | Index page: no false headings |
| [p146](../experiments/out/step10/overlays/structure_p146.png), [p566](../experiments/out/step10/overlays/structure_p566.png) | Unseen pages (seeded draw, seed 10) |

## Low-confidence list

- **Book 1:** 19 low-confidence headings, mostly Constitution clause titles ("SECCIÓN 3,
  CLÁUSULA 1", p61–69, confidence 0.57) and amendment titles. The full list with page, role,
  confidence, reasons and text is in
  [low_confidence.jsonl.gz](../experiments/out/step10/spanish_us_history/low_confidence.jsonl.gz).
- **Book 2:** 0 low-confidence headings (emitted).
- **Styled non-headings** carry their own confidence (classifier likelihood distance).

## Limitations

1. **Classifier transfer.** Trained on one book, it encodes that reference's outline
   convention and fails on book 2 (recall 0.07). Page-block CV inside one book does not
   measure transfer.
2. **Book 2 rules recall is 0.62** (hold-out, not inspected or tuned).
3. **Step 4/9 merges are inherited.** Opener titles merged with caption text ("TEMA8 raíces a
   promover…", "TEMA11 Más voces…"), titles split in two, and glossary letters merged with
   entries cannot be headings without reordering or splitting units, which Step 10 never does.
4. **Labels vs feature titles** share styles. "LO QUE PUDO HABER SIDO" (a reference heading)
   recurs within one section and is classed as an inline label.
5. **Book title** differs from the reference choice (the "HISTORIA" cover word vs "Tiempos
   modernos").
6. **Zones.** Book 2's index start is early by 5 pages, and its trailing pages are tagged
   rear. Book 3 (fragments) has no openers, so its pages default to body.
7. **Level conventions.** Rear-matter levels are one less than the reference's, which has an
   empty wrapper.
8. **Coverage.** Right-to-left, CJK and bilingual headings are covered by synthetic tests
   only.
9. **Confidences** are rule heuristics or model likelihoods, not calibrated probabilities.

## Decisions for you

1. **Default heading decision.** Options:
   - (a) Rules + book-1 classifier (current emitted default): book 1 out-of-fold P 0.95 / R
     0.88, but book 2 R 0.07.
   - (b) Rules only: book 1 P 0.43 / R 0.86; book 2 P 0.97 / R 0.62.
   - (c) Use the classifier only for books whose profile matches its training (same publisher
     or series), and rules elsewhere.

   I recommend (b) as the default and (c) as a client-profile option. Changing the default is
   one configuration line, not a producer change.
2. **Outline depth.** Book 1's reference omits in-section titles (display titles). Should the
   adapter default follow the contents depth (current `outline = contents`), or emit every
   visual title as a heading (`outline = all`) for richer navigation?
3. **Training data for transfer.** Should a later step train the classifier on more books,
   with leave-one-book-out evaluation, before it is used beyond its own series?
4. **Rear-matter wrapper.** Should the adapter add an empty rear-matter level so the
   reference's levels match, or keep our levels?

## Reproduce

From the project root:

1. `python experiments/step10_housekeeping.py [--apply]`
2. `python experiments/step10_run.py --book spanish_us_history` (pass 1 and pass 2,
   evaluation)
3. `python experiments/step10_classifier.py` (book 1 CV; writes the model and manifest)
4. `python experiments/step10_fill_paragraphs.py --book <book>` (cache fill only, if needed)
5. Hold-outs, once each:
   `python experiments/step10_run.py --book <book> --holdout --reason "…"`
6. `python experiments/step10_overlays.py`
7. `python experiments/step10_gates.py`

Pytest and Ruff run from `backend/`.

**Step 10 stops here for owner review. Step 11 has not started.**
