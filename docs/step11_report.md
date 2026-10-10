# Step 11: lists, index and glossary entries

Step 9 list-like units are now structured lists and entries. Each item is its own unit and
carries confidence and reasons. Units are split from or merged over Step 9 units at line
boundaries only, so every line still belongs to exactly one unit. The step covers:

- bulleted, numbered, lettered and unmarked lists, with nesting and continuation lines;
- definition runs and bilingual glossaries;
- index entries with sub-entries and locators;
- reference lists and contents entries;
- list roles.

No figure, table or math is decided here. The text ledger and the committed gold are
unchanged, and the old projects were not touched.

**Main findings**

- **Book 1:**
  - Paragraph boundary F1 rose from 0.898 to **0.932** and exact match from 0.753 to
    **0.894**. Merge errors fell from 2,265 to 715.
  - Exact match by reference kind:
    - glossary descriptions: 0.22 → **0.95**;
    - list items: 0.65 → **0.88**;
    - index entries: 0.60 → **0.93**.
  - Main-flow reading order rose from 0.946 to **0.954**, because glossary pages are now read
    entry by entry.
- **Book 2:** reference entries rose from 0.949 to **0.994** exact. Cross-page entry errors fell
  from 2 to 0.
- **Book 4 (hold-out, run once):**
  - Paragraph exact match rose from 0.301 to **0.349**, but boundary F1 fell from 0.717 to
    **0.672** (recall 0.64 → 0.58).
  - Index entries: 0.11 → 0.18 exact; sub-entry levels 0.88.
  - Zones: **0.871 → 0.980** of pages with the new body-start rule.
- **Float anchors at item boundaries (Task 5) are not applied.** Book 1 gets worse
  (0.901 → 0.892–0.895), and book 2 is unchanged.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | **828 passed**, 0 failed / 0 skipped (807 at Step 10b + 21 new) | [JUnit](../experiments/out/step11/pytest.xml), [log](../experiments/out/step11/pytest.log) |
| 24 measured pages vs original sources | **0 missing / 0 extra** | [cross-check](../experiments/out/step11/original_source_crosscheck.json) |
| Full book | **495,751** retained tokens; passing | [full_book.json](../experiments/out/step11/full_book.json) |
| I1–I7 on 24 pages | **0 each** | [invariants.json](../experiments/out/step11/invariants.json) |
| Every line in exactly one unit and ordered once | **All four books** (84,085 / 14,396 / 1,231 / 20,142 lines, 0 problems, order invariants checked on every page); 24 one-page fixtures for Step 9 and for Step 11 | per-book summaries; [lists on fixtures](../experiments/out/step11/lists_on_fixtures.json) |
| Step 9 unchanged | Paragraph producer equals the Step 10b freeze (`a8a2cce4…`) in all four runs | summaries |
| Earlier metrics not worse | Reading order: equal or better in all books. Paragraphs: better on book 1, equal on books 2–3; **book 4 boundary F1 is worse** (exact match is better; see Part C). Headings, page labels, zones of books 1–2: identical to Step 10b | Part C |
| Ruff check / format, from backend/ | pass | [ruff.log](../experiments/out/step11/ruff.log) |

## Part 0: decisions and fixes

All are recorded in [decisions.md](decisions.md).

- **Accepted:** book 1 heading precision 0.74 (rules only). Book 4 stays the hold-out until a
  new reference book arrives.
- **Page labels** are reported for body pages and for all markers. A reference with its own
  front-matter numbering is flagged (`reference_own_front_numbering`); book 4 is flagged. Code:
  `marker_scores` in [furniture.py](../backend/src/book_core/evaluation/furniture.py).
- **Zones.** With fewer than two sectioning-word openers, the body starts at the first Arabic
  folio run ([zones.py](../backend/src/book_core/structure/zones.py)). Books 1–2 have 10 and
  12 openers, so they are unchanged. There is a synthetic test. On book 4 the body now starts
  at p41 instead of p74.
- **Reader (logged aligner change).** An element named as a page marker counts only when its
  id matches the dialect's `page_marker_label` pattern
  ([xml_reader.py](../backend/src/book_core/reference/xml_reader.py),
  [dialects.py](../backend/src/book_core/reference/dialects.py)).
  - Marker labels are unchanged, because the aligner reads them as folio evidence.
  - All four books were re-aligned with the new reader. Their derived gold is
    **byte-identical except the version fields**
    ([reader_identity.json](../experiments/out/step11/reader_identity.json)).
  - Book 2's committed gold carries the logged Step 9 marker fix (146/147). The first
    comparison flagged exactly that fix, so it was re-applied to the re-derived gold before
    comparing.
  - No anchor was rejected in any book. All runs are logged in
    [step5/holdout_runs.jsonl](../experiments/out/step5/holdout_runs.jsonl).

## Design (brief)

Code: [lists/](../backend/src/book_core/lists/). Tests:
[test_lists.py](../backend/tests/test_lists.py).

- **Line evidence** ([lines.py](../backend/src/book_core/lists/lines.py)), all read in the
  line's own reading frame (right-to-left aware):
  - **Markers:** any symbol or dash glyph, numbers in any script, letters and Roman numerals.
    Letters and Roman numerals count only with sequence evidence.
  - **Terms:** a heavier lead run ending at a separator.
  - **Locators:** page labels, ranges and letter-prefixed labels.
  - **Page references:** short parenthesised lines like "(p. 12)".
  - **Cross-references:** a small multilingual lexicon decides the locator kind only, never a
    unit boundary.
- **Page segmentation** ([page.py](../backend/src/book_core/lists/page.py)). Blocks of
  consecutive list-capable Step 9 units are segmented by the page's Step 10 navigation kind.
  Step 10 heading units are never split or merged. Figure and table streams are not touched.
  - **Marked lists** carry their marker as span evidence, a normalized type and a start
    value.
    - Nesting comes from marker indent and type.
    - A numbering restart opens a new list.
    - A list continued in the next column is re-anchored there, not nested.
    - Hanging continuation lines join their item.
  - **Definition runs:** two or more term lines ended by a wide separator.
  - **Unmarked lists:** three or more one-line units of one style, start and pitch, none
    ending a sentence. These never change unit boundaries.
  - **Index** (columns found from start positions):
    - a base-indent line starts an entry;
    - an indented line continues it, unless the previous line completed an entry (it ended
      with a locator, or ended clearly short) — then it is a sub-entry, its level from the
      indent rank;
    - locators link to physical pages through the Step 8 labels.
  - **Glossary:** see Part B.
  - **Reference lists:** used only for hanging-indent blocks where most entries carry a year.
  - **Contents:** one entry per printed navigation entry, with its indent level.
- **Roles** ([roles.py](../backend/src/book_core/lists/roles.py)), from structure and
  punctuation only:
  - **questions:** most items end with a question mark, in any script;
  - **question-and-answer:** each question is followed by running text;
  - **activities:** a numbered list in a box, or one whose items open with a lead term;
  - **objectives:** a lead-in ending with a colon, right after a heading.
- **Book stage** ([cache.py](../backend/src/book_core/lists/cache.py)):
  - A list continues on the next page when its markers continue, or for entry lists, when
    the next page has the same navigation kind.
  - An index or reference entry continued on the next page is **linked, never merged**.
  - A Step 9 page join between entries is dropped and recorded.
  - New joins take their hyphen decisions from the unchanged Step 9 rule.
  - Cached per page and per book. The key ([keys.py](../backend/src/book_core/lists/keys.py))
    binds the lists package, the Step 10 decision key (which chains Steps 4–10), the
    paragraph book key, settings and configuration. A closure test, a digest test and a test
    per key component guard it.
- **Evaluation** ([evaluation/lists.py](../backend/src/book_core/evaluation/lists.py)):
  - list items: exact match, item and list boundary F1, kind agreement, nesting;
  - definition term and description exact match;
  - index entry exact match and sub-entry level (levels from
    [entry_levels.json](../backend/reference_dialects/entry_levels.json), evaluation data);
  - reference entries;
  - cross-page entry errors.

  Every metric is also computed on the Step 9 units ("before").

## Part A: lists (books 1 and 2, development)

Book 1 list items: reference list items outside tables and off index pages (2,054 scored).
List items in table cells wait for the tables step.

| Book 1 list items | Step 9 units | **Step 11** |
|---|---:|---:|
| **Exact match** | 0.732 | **0.801** (body 0.819 → **0.927**; front 0.589 → 0.589) |
| Item boundary F1 | 0.868 | **0.896** |
| Kind agreement (tokens in a list-kind unit) | 0.0 | **0.875** |
| **List boundary F1** | 0.516 | **0.686** |
| **Nesting level** (exactly matched items), exact / relative | – | **0.790 / 0.981** (1,483 items; reference depths 1: 1,172, 2: 283, 3: 28) |

Lists found:

| | Count | By kind and role |
|---|---:|---|
| **Book 1** | 936 | numbered: questions 275, activities 182, general 41; bulleted: general 62, questions 14, objectives 1; lettered 17; unmarked 13; definition 227; glossary 21; index 29; contents 54 |
| **Book 2** | 37 | numbered 16; bulleted 5; bibliography 13; index 2; definition 1 |

- No question-and-answer set was found in either book.
- Book 2's reference has no list items, so book 2's list metrics are its reference entries
  (Part B).

## Part B: glossary and index, before and after

**Glossary reading order (decision recorded with evidence).** Book 1's bilingual glossary
(pp. 664–683) sets each entry as a row: the Spanish entry, a page reference, then the English
entry. Step 7 read these pages line by line across the row, so the languages interleaved. Now:

- on row-synchronised pages, lines are read entry by entry, as the reference does;
- the first column's entry (term, then definition) comes first, its page reference attached,
  then the next column's entry;
- the change is recorded as an order decision.

24 glossary blocks were reordered (some pages hold two blocks).
[Overlay p669](../experiments/out/step11/overlays/lists_spanish_us_history_p669.png).

| Book 1 | Step 9 units | **Step 11** |
|---|---:|---:|
| Glossary descriptions, exact (paragraph metric) | 0.216 | **0.952** |
| Definition terms, exact (term spans) | 0.0 | **0.834** |
| Definition descriptions, exact (unit minus term) | 0.0 | **0.818** |
| **Index entries, exact** (3,157 reference entries on index pages) | 0.600 | **0.932** |
| Index sub-entry level | – | 1.0 (this index sets sub-entries inline, so all reference entries are level 1) |
| Cross-page entry errors (missed / false joins) | 40 (13 / 27) | **11** (10 / 1) |

- The reference's 17 cross-page entries are mostly glossary entries, which now never join.
- Main-flow reading order: 0.9457 → **0.9545**.

| Book 2 | Step 9 units | **Step 11** |
|---|---:|---:|
| **Reference entries, exact** (891) | 0.949 | **0.994** |
| Reference entry splits / merges | 35 / 5 | **5 / 0** |
| Cross-page entry errors | 2 | **0** (3 entry links, all correct) |

## Part C: frozen producers, book 3 once, book 4 once

**Freeze.** The record is [freeze.json](../experiments/out/step11/freeze.json), re-verified
after the runs (all equal).

| Producer | Digest |
|---|---|
| alignment | `4d5f0e41…` |
| paragraphs | `a8a2cce4…` (unchanged since Step 10b) |
| structure | `a2b079a1…` |
| lists | `87c9a4b5…` |

The other producers are unchanged since Step 10b.

**One logged amendment.** It adds `lists/__init__.py`, a docstring-only module. `setuptools`
`find()` installs only packages that have one, so it is a packaging fix with no code. It was
added after the book 3 and 4 runs, which were not re-run. Books 1–2 were re-run and give
identical results ([evidence](../experiments/out/step11/amendment_identity.json)). The
amendment is recorded in the freeze file.

**Runs and disk.**

- Each run is logged in [holdout_runs.jsonl](../experiments/out/step11/holdout_runs.jsonl).
- Step 9 for book 4 is its cached Step 10b run, unchanged. Step 10 used the cached evidence
  with the new decision. Step 11 ran once.
- Disk ([housekeeping.json](../experiments/out/step11/housekeeping.json)):
  - only superseded Step 11 development entries were deleted;
  - the book 4 estimate was 52 MB, with 15.9 GB free.

### Results per book (no overall score)

| | Book 1 (dev) | Book 2 (dev) | Book 3 (anecdotal, once) | **Book 4 (hold-out, once)** |
|---|---:|---:|---:|---:|
| **Paragraph boundary F1**, Step 9 → 11 | 0.898 → **0.932** | 0.854 → 0.854 | – (no paragraphs) | 0.717 → **0.672** |
| **Paragraph exact**, Step 9 → 11 | 0.753 → **0.894** | 0.680 → 0.680 | – | 0.301 → **0.349** |
| Merges / splits, Step 9 → 11 | 2,265 / 1,174 → 715 / 1,635 | 57 / 194 → same | – | 3,796 / 1,046 → 3,654 / 1,035 |
| With page chains, F1 | 0.897 → 0.932 | 0.932 → 0.932 | – | 0.719 → 0.674 |
| **Index entries exact**, Step 9 → 11 | 0.600 → **0.932** | – (no reference index) | 0.066 → **0.454** | 0.106 → **0.179** |
| **Sub-entry level** | 1.0 | – | 0.990 | **0.884** |
| Reference entries exact | – | 0.949 → **0.994** | – | – |
| Cross-page entry errors, Step 9 → 11 | 40 → 11 | 2 → 0 | 8 → 8 | 0 → 0 |
| **Main flow**, Step 9 → 11 | 0.946 → **0.954** | 0.973 → 0.973 | 0.991 → 0.991 | 0.934 → 0.934 |
| Float anchors (emitted, unchanged) | 0.901 | 0.375 | – | 0.606 |
| Anchors at item boundaries: nearest / end | 0.892 / 0.895 | 0.375 / 0.375 | – | 0.602 / 0.598 |
| **Zones, pages** (Step 10b → 11) | 0.999 → 0.999 | 0.983 → 0.983 | 0.444 → 0.444 | **0.871 → 0.980** (units 0.894 → 0.992) |
| Headings P / R | 0.736 / 0.852 (same) | 0.969 / 0.926 (same) | 1.0 / 1.0 | 0.619 / 0.731 (same) |
| Heading levels exact / within one | 0.753 / 1.0 (same) | 0.862 / 1.0 (same) | 1.0 | 0.148 / 0.969 (was 0.164 / 0.969) |
| **Page labels, all / body** | 1.0 / 1.0 | 0.997 / 1.0 | – | **0.890 / 0.996** (own front numbering flagged) |
| Lists | 936 | 37 | 2 | 399 |

Book 1 split errors (pieces) rose, while reference units split fell from 1,002 to 806. A few
reference units are now cut into more pieces. List-item and glossary units split fell from 424
and 150 to 340 and 24; paragraphs went from 380 to 394.

**Reading these numbers.** They come from single runs; nothing was tuned on books 3–4. Book 4
causes are read from aggregate output only.

- **Book 4 paragraph boundary F1 fell.**
  - Recall fell from 0.64 to 0.58 and precision from 0.81 to 0.80, while exact matches and
    merges improved.
  - Step 11 found 975 list items and 122 lettered lists in book 4. The Step 10b report noted
    that this reference sets list items as separate paragraphs.
  - Pages 18–28 are classed as glossary but are not row-synchronised, so they were not
    reordered. Their entries follow the term rule.
  - Which rule loses the boundaries was not inspected (hold-out).
- **Book 4 index.** Step 10 classed only one page as an index page. Most of the reference's
  1,421 index entries were therefore segmented by the general rules, not the index rule.
- **Book 4 zones.** The body now starts at p41, the first Arabic run. Front-matter units and
  pages now match.
- **Book 4 heading levels.** Exact level accuracy fell from 0.164 to 0.148 with the new zones;
  within one is unchanged at 0.969.
- **Task 5.** Anchors at paragraph or item boundaries lower book 1 and leave book 2 unchanged.
  Not both books improve, so the Step 7/8 anchors stay. The proposals remain recorded.

## Overlays

What is drawn:

- items are boxed in their list's colour and labelled `<kind><n> L<level>`;
- markers are underlined black and terms in the list colour;
- resolved index locators are shown as `>p<n>`;
- glossary pages show entry order as numbered arrows;
- other text units are thin grey.

All were inspected. [Index](../experiments/out/step11/overlays/overlays.json).

| Page | What it shows |
|---|---|
| [book 1 p30](../experiments/out/step11/overlays/lists_spanish_us_history_p30.png) | Bullet lists: a lead-in list (12 items) and a question list; each bullet glyph sits on its own visual line |
| [book 1 p305](../experiments/out/step11/overlays/lists_spanish_us_history_p305.png) | Nested list: Roman items with lettered sub-items (L1/L2) in a sidebar outline |
| [book 1 p8](../experiments/out/step11/overlays/lists_spanish_us_history_p8.png) | Nested contents list: entries with indent levels |
| [book 1 p669](../experiments/out/step11/overlays/lists_spanish_us_history_p669.png) | Glossary: entry by entry, page reference inside the Spanish entry, terms underlined |
| [book 1 p687](../experiments/out/step11/overlays/lists_spanish_us_history_p687.png) | Index: 105 entries, continuations, resolved locators |
| [book 1 p35](../experiments/out/step11/overlays/lists_spanish_us_history_p35.png) | Questions page: numbered question items with lead terms, hanging continuation merged (no question-and-answer set exists in books 1–2) |
| [book 2 p34](../experiments/out/step11/overlays/lists_immigrant_children_p34.png) | Reference list: hanging-indent entries |
| [book 1 p472](../experiments/out/step11/overlays/lists_spanish_us_history_p472.png), [p583](../experiments/out/step11/overlays/lists_spanish_us_history_p583.png) | Unseen pages (seeded draw, seed 11): no lists, all units left as paragraphs |

Seen on the overlays:

- **p687:** the top of index column 3 continues column 2's last entry but became a separate
  entry. The block is broken between the columns.
- **p687 and p700:** some extracted lines merge text across columns, and their boxes overlap.

## Low-confidence list

Items flagged for review (confidence below 0.6) or of confidence 0.65 or less are listed with
page, kind, reasons and text in `low_confidence.jsonl.gz` per book, for example
[book 1](../experiments/out/step11/spanish_us_history/low_confidence.jsonl.gz). No item falls
below 0.6.

- **Book 1:** 75 items. 60 are unmarked-list items, for example the activity table on p23
  ("Crea un diagrama de Venn . . ."). 15 are index lines indented with no open entry.
- **Book 2:** 3 reference entries whose first line is indented.
- **Book 3:** 4 unmarked items.
- **Book 4:** 50 unmarked items.

## Limitations

1. **Book 4 paragraph boundary F1 is lower** (0.717 → 0.672) although exact matches rose. As a
   hold-out, it was not inspected.
2. **Lists inside tables** (book 1 checks-and-balances charts) wait for the tables step and
   are excluded from the list metric.
3. **Front-matter lists stay at 0.589.** Book 1's contents and source lists keep Step 9's
   per-entry units. Contents nesting is indent-based; relative nesting is right, but absolute
   depth differs from the reference's.
4. **Index:**
   - an entry continued at the top of the next column breaks when the stream order breaks
     the block (p687);
   - lines merged across columns at extraction stay merged;
   - sub-entry levels are developed on synthetic data only (book 1 sets sub-entries inline).
5. **Cross-references** are recognised by a small multilingual lexicon. This affects the
   locator kind only, never unit boundaries.
6. **Question-and-answer sets and objective lists** have no reference labels. Their roles are
   reported as counts and are not scored.
7. **Unmarked lists** are conservative (three or more uniform one-line units) and low
   confidence.
8. **Constants** (indent 0.8, continuation gap 1.9 font sizes, row sync 0.6, year share 0.5,
   question share 0.6, column gap 4 font sizes) were chosen on books 1–2 only.
9. **Right-to-left, other scripts and bilingual glossary rows** are covered by synthetic tests
   only.

## Decisions for you

1. **Book 4 paragraphs.** Its reference sets list items as separate paragraphs, and boundary
   F1 fell while exact matches rose. Should the next step inspect book 4? That would promote
   it to development, as already decided for when a new hold-out book arrives.
2. **Float anchors (Task 5).** Keep the Step 7/8 anchors (current), since no boundary rule
   improves both books?
3. **Lists in table cells.** Defer them to the tables step (current), or handle cell bullets
   now?
4. **Cross-reference lexicon.** Keep it as configuration data for the locator kind, or
   require a typographic cue (italic) as well?
5. **Contents nesting.** Should an adapter map our indent levels onto the reference's depth
   convention (title row at depth 1)? Relative nesting is already 0.98.

## Reproduce

From `experiments/`:

1. Part 0: `python step11_reader_identity.py --scratch <dir>`
2. Development:
   - `python step11_run.py --book spanish_us_history`
   - `python step11_run.py --book immigrant_children`
   - `python step11_overlays.py`
3. Part C, in this order:
   - `python step11_housekeeping.py --apply`
   - `python step11_freeze.py`
   - `python step11_run.py --book art_therapy_index --holdout --reason "…"`
   - `python step11_run.py --book medical_anatomy --holdout --reason "…"`
   - `python step11_freeze.py --verify`
4. Gates: `python step11_gates.py`.

Pytest and Ruff run from `backend/`.

**Step 11 stops here for owner review. Step 12 has not started.**
