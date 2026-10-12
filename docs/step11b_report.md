# Step 11b: book 4 as a development book

Book 4 (the medical textbook) is now a development book, and its Step 11 losses were traced
to general causes. Every rule change was run on books 1–4 and kept only if it helped at least
one book and made no other book worse beyond noise. There is no hold-out in this step.

The following are unchanged, and the old projects were not touched:

- the text ledger;
- the committed gold;
- Steps 4–9;
- the reading order.

**Main findings** (book 4, Step 11 → Step 11b; all rules are general, with no page, font,
size or vocabulary constants)

| Book 4 metric | Step 11 | **Step 11b** |
|---|---:|---:|
| Paragraph boundary F1 | 0.672 | **0.818** |
| Paragraph boundary recall | 0.58 | **0.79** |
| Paragraph exact match | 0.349 | **0.482** |
| List items, exact | 0.530 | **0.743** |
| Index entries, exact | 0.179 | **0.863** |
| Index sub-entry level | 0.884 | 0.963 |
| Heading levels, exact | 0.148 | **0.847** |
| Heading levels, within one | 0.969 | 0.977 |

- **Book 4 list items:** the Step 11 run scored 0 items, because this dialect writes list items
  as paragraphs inside lists; the list-item metric now counts them. 0.530 is the Step 11
  output re-scored with that metric.
- **Book 4 heading precision** fell from 0.619 to 0.598: 23 index letter dividers are now
  headings, which this reference does not tag as headings (decision 1).
- **Book 1:**
  - paragraph boundary F1 0.932 → **0.943**, with 373 fewer split errors;
  - index entries 0.932 → **0.936**;
  - everything else is identical.
- **Book 2** is identical on every metric.
- **Book 3** (anecdotal):
  - index entries 0.454 → **0.628**;
  - zones 0.444 → **0.889**, now that its first index pages are recognised.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | **841 passed**, 0 failed / 0 skipped (828 at Step 11 + 13 new in [test_step11b.py](../backend/tests/test_step11b.py)) | [JUnit](../experiments/out/step11b/pytest.xml), [log](../experiments/out/step11b/pytest.log) |
| 24 measured pages vs original sources | **0 missing / 0 extra** | [cross-check](../experiments/out/step11b/original_source_crosscheck.json) |
| Full book | **495,751** retained tokens; passing | [full_book.json](../experiments/out/step11b/full_book.json) |
| I1–I7 on 24 pages | **0 each** | [invariants.json](../experiments/out/step11b/invariants.json) |
| Every line in exactly one unit and ordered once | All four books: 84,085 / 14,396 / 1,231 / 20,142 lines, 0 problems; 24 one-page fixtures | final summaries; [lists on fixtures](../experiments/out/step11b/lists_on_fixtures.json) |
| Books 1–2 metrics not worse | Book 1 better or equal on every metric; book 2 identical | [compare.json](../experiments/out/step11b/compare.json) |
| Disk | 20 GB free before the first book run (Step 11 book 4 lists cache: 52 MB per run); 15 GB free after all variants (`.cache/step11` 1.5 GB). No cache entry was deleted | `df` |
| Ruff check / format, from backend/ | pass | [ruff.log](../experiments/out/step11b/ruff.log) |

## Part 0: decisions

All are recorded in [decisions.md](decisions.md).

- **Book 4 is promoted to development.**
  - The promotion is logged as `promoted_to_development` in the Step 10 and Step 11
    `holdout_runs.jsonl`; `step10_run.py` treats book 4 as development.
  - Its Step 10b and Step 11 results stay recorded as the honest hold-out numbers.
- **Settled:**
  - keep the Step 7/8 float anchors;
  - lists in table cells wait for the tables step;
  - cross-reference words stay configuration data;
  - the adapter maps contents depth.
- **Your instructions during this step** are recorded too:
  - the repetition evidence for set-off markers;
  - no math operators as markers;
  - the dialogue guard;
  - measuring single-item lists before adding any rule.

**Runs.** [step11b_run.py](../experiments/step11b_run.py) runs the unchanged Step 11 evaluation
and writes each rule variant to `out/step11b/<label>/<book>`. Book 3 runs once per variant,
logged in [runs.jsonl](../experiments/out/step11b/runs.jsonl).
[step11b_compare.py](../experiments/step11b_compare.py) builds the tables below.
`r0_baseline` is the Step 11 code with the new list-item metric. It reproduces every Step 11
number exactly.

## Task 1: book 4 paragraph and list boundaries

**Why recall fell at Step 11 (0.64 → 0.58).** At Step 11, 749 reference boundaries that
Step 9 had were lost, and 314 were gained. By class (evidence:
[book4_missed_boundaries_step11.json](../experiments/out/step11b/book4_missed_boundaries_step11.json)):

| Class | Lost at Step 11 | Missed at Steps 9 and 11 |
|---|---:|---:|
| **Glossary rule applied to the ruled term table, pp. 18–28** | **733** | 134 |
| List items not split: markers not recognised | 6 | **775** |
| Table cells (tables step) | 9 | 1,253 |
| Paragraphs (Step 9 boundary) | 1 | 72 |

Examples:

- **Ruled term table (733 lost).** pp. 18–28 are a three-column ruled table (term / meaning /
  example). Step 10 classed them as a glossary, and the glossary rule then merged whole cells
  and columns:
  - p20 "Gills";
  - p25 "Latissimus dorsi—broadest muscle";
  - p25 "In = 'not' + nominatus = 'name'".

  The navigation fix (Task 2) removes this class.
- **List items not split (775).** Book 4's bullets either sit against the text or extract
  from a symbol font as letters, numbers or control characters, and none was read as a
  marker:
  - p238 "–Penis";
  - p54 "◆In 1858, his first edition…";
  - p242 "◆Thyroid gland" after "◆…".
- **Table cells (1,253):** p16 "Y" | "11"; p263 "ǊPalpable: Femoral triangle…". These wait
  for the tables step (decided).

### Rule: set-off list markers

Code: [lines.py](../backend/src/book_core/lists/lines.py) `set_off_marker`.

- A single glyph alone in its span at the line start is read as a bullet when item text (a
  letter or number) follows it. This covers glued bullets ("◆Thyroid gland") and symbol-font
  glyphs ("Ǌ", "¾", "\x89").
- Its signature is the glyph, the mark font and the following text's font.
- A known bullet glyph counts on its own. Any other glyph needs a second line of the block
  with the same signature at the same start (repetition evidence). Colour is not required.
- **Never markers:**
  - decimal digits;
  - opening brackets and quotes, and other punctuation;
  - math operators (`Sm`), except ∙ ⋅ ∘;
  - a letter set in the same font and colour as its text;
  - a dash line whose text opens with ¿ ¡ « " or carries a dialogue tag.

Variants. Books 1 and 3 were identical across all three variants.

| Variant | Book 2 paragraph F1 | Book 4 paragraph F1 | Book 4 list items exact |
|---|---:|---:|---:|
| Navigation only (r1) | 0.854 | 0.747 | 0.530 |
| First rule: a different font or colour, or any symbol (r2a) | **0.844 (worse)** | 0.819 | 0.747 |
| Your repetition rule, plus "a glyph set like its text is text" (r2b) | 0.854 | 0.786 | 0.616 |
| **Kept: repetition rule; the same-style check only for letters (r2, r3)** | 0.854 | **0.818** | **0.743** |

- **r2a (rejected)** read statistics in book 2 ("p < .001", "F(1, 147)", "α = .77") and "(" as
  markers.
- **r2b (rejected)** also rejected symbols and dashes glued to text in the text's own font:
  1,017 "◆" and 278 "–" item starts were lost.
- **Gap between your repetition rule and the first rule** (book 4, set-off markers dropped by
  the repetition test; [marker_gap](../experiments/out/step11b/marker_gap/medical_anatomy.json)):
  - **(a) signature mismatch: 14.** Same glyph and mark font, different text font. Examples:
    p63 "ǊCells of superficial layer…", p63 "ǊExample: Ducts…" (italic), p66 "» Location:…".
  - **(b) block boundary: 19.** Examples: p62 "–Squamous…", p81 "Dermatoglyphics…", p86
    "–Neck: Fascia colli".
  - **(c) single on the page: 36.** Examples: p50 "–Appendix = appendix", p51 "—Herophilus",
    p51 "—Galen".
  - (a) does not dominate, so the signature keeps the text font. (b) and (c) are left for
    you (decision 3).
- **Dialogue check** ([dash_lists](../experiments/out/step11b/dash_lists/)): dash lists before
  → after.
  - Book 4: 2 → 148, with 392 items, all genuine sub-items ("–Myo = muscle (prefix)").
  - Books 1–3: 0 → 0. No dash item is dialogue in any book.
  - The math and dialogue guard (r3) changed no metric in any book.
- **Single-item lists** ([single_items](../experiments/out/step11b/single_items/)):
  - **Book 1:** 45 reference lists with one item, of 2,054 list items. 42 are not list items
    of ours, but only **5 carry a marker** (0.24%):
    - four Roman outline items "I." (p49, p161, p197, p397), which have no sequence evidence;
    - one line that merges several bullets across columns at extraction (p347).

    The other 37 are contents entries (29 held exactly, typed `contents_entry`) and unmarked
    lines ("Escribir un monólogo . . .").
  - **Book 4:** 17 lists, 7 missed, **4 with a marker** (0.12%): p75 "–Epithelial cells…",
    p81 "–Arrectores pilorum:", p176 "–Examples:", p46 "◆Region-wise…".
  - **Book 2:** no reference list items outside tables.
  - Below the 1% threshold, so no single-item rule was added (limitation 3).

## Task 2: book 4 navigation pages, index and glossary

**Why only one page was an index (p305).** Book 4's index (pp. 305–314) prints locators after
a space ("Bone 55", "Body 193, 195"). The locator test required a comma, so only 18% of the
entries on p306 had locators. Two more causes:

- indented sub-entries ("cavities of 46") broke the alphabetical measure (0.66);
- on pp. 307–314, Step 9 had merged each index column into a few units, so those pages had
  fewer than 8 entries.

**Why pp. 18–28 were a glossary.** They are alphabetical, and their units are long with no
locators. A glossary needed nothing more. But in a glossary the entries open with a set-off
term: 87% of book 1's glossary entries do, against 17% on these pages.

Rules (code: [navigation.py](../backend/src/book_core/structure/navigation.py)):

1. **Locators** may follow a space and carry a short letter suffix ("186f", "62t").
2. **Alphabetical order** is measured on the base-indent entries of each column (sub-entries
   are indented).
3. **Glossary** needs set-off terms on at least half of the entries: a lead run in its own
   style, or a wide separator.
4. **Contents guard:** a page whose printed entries resolve to targets that advance with the
   list is contents, never an alphabetical list. Rule 1 alone had turned book 4's contents
   pages 11–13 into index pages.
5. **Run extension** counts a neighbour's entries from its lines too, because Step 9 may hold
   several entries in one unit.

Effects:

| Book | Change (r1) | Metrics |
|---|---|---|
| 1 | identical | identical |
| 2 | 6 chapter-end reference pages (p37, 60, 108, 159, 222, 265) now `bibliography` | identical |
| 3 | pp. 1–2 now `index` | index 0.454 → **0.628**; sub-entry level 0.990 → 1.0; zones 0.444 → **0.889** |
| 4 | index pp. 305–314 (was p305 only); no glossary pages (was 11) | index **0.179 → 0.863**; sub-entry level 0.884 → **0.964**; paragraph F1 0.672 → **0.747** |

**Book 4 index entries:** 0.863 exact (1,421 reference entries); sub-entry levels **0.963**.

Book 4 heading precision fell from 0.619 to 0.598. The index letter dividers ("C", "D", …) are
headings by the existing divider rule:

- book 1's reference tags its dividers as `h3` headings;
- book 4's reference sets them as `indexdiv/title`, which its dialect labels "other";
- book 3's reference tags them as headings.

So this is a reference convention (decision 1).

## Task 3: book 4 heading levels

**Systematic cause.** On a chapter opener, the chapter title is set in the banner artwork, so
it sits in a figure stream. Figure streams come after the main flow in page order. The
chapter title therefore entered the heading hierarchy after that page's section titles:

1. The sections took level 1.
2. The contents-level consistency rule then kept every later section linked at the same
   contents level at level 1.
3. Everything below was one level too shallow: reference 2 → ours 1, 3 → 2, 4 → 3.

**Rule** ([decide.py](../backend/src/book_core/structure/decide.py) `_heading_order`).

- A structural title in a float stream that outranks every main-flow heading candidate of its
  page is the page's opening title. Like a Step 7 float anchor, it takes its place in the
  main flow before the first main-flow unit that starts below its centre.
- A float title set like a main-flow title keeps the stream order. Example: book 1's TEMA
  banner "La Primera Guerra Mundial" next to the main-flow piece "y la expansión
  estadounidense", both at 31 pt, are one title split over the two streams.

Variants:

| | Book 1 levels exact | Book 4 levels exact / within one |
|---|---:|---:|
| Before | 0.753 | 0.151 / 0.969 |
| Unrestricted anchoring (r4a, rejected) | **0.748 (worse)** | 0.867 / 0.980 |
| **Kept: only titles that outrank the page's main-flow headings (r4)** | 0.753 | **0.847 / 0.977** |

- The unrestricted version nested the split TEMA titles of book 1 (pp. 175, 215, 257).
- Books 2 and 3: identical.

Headings P / R and levels, all books (final):

| | Book 1 | Book 2 | Book 3 | Book 4 |
|---|---:|---:|---:|---:|
| Precision / recall | 0.736 / 0.852 | 0.969 / 0.926 | 1.0 / 1.0 | 0.598 / 0.733 |
| Levels exact / within one | 0.753 / 1.0 | 0.862 / 1.0 | 1.0 / 1.0 | **0.847 / 0.977** |

## Task 4: index entry continued at the top of the next column

- **p687 (book 1)** is already right with the current code. Both column continuations are
  joined:
  - "armas nucleares y guerra" from column 2 into column 3;
  - "Artículos de la Confederación" from column 3 into column 4.

  The Step 11 overlay labels a unit at the top-left of its bounding box. A unit that spans two
  columns therefore shows its label at the top of the next column, which looked like a
  separate entry.
- **The real class:** book 1 index entries split at a column top (27 of 867 split points).
  Two causes:
  1. **Indent base (p685).** In a column of long wrapped entries, more than 90% of the lines
     are indented continuations. The base indent (a 10% quantile) then landed on the
     continuation indent, so every line started an entry. **Rule:** the base indent is the
     leftmost start that at least two lines share
     ([page.py](../backend/src/book_core/lists/page.py) `indent_ranks`).
  2. **Reading order (p686).** Step 7 reads a top band across all four columns first, so a
     continuation comes before the entry it continues. This is not fixable without changing
     reading order (limitation 4).
- **Effect (r5):**
  - **Book 1:** paragraph F1 0.932 → **0.943** (precision 0.898 → 0.919); split errors
    1,635 → 1,262; index entries 0.932 → **0.936**.
  - **Book 4:** sub-entry level 0.964 → 0.963 (one entry; noise).
  - **Books 2 and 3:** identical.

## Task 5: results per book (Step 11 → Step 11b final)

Final runs: `out/step11b/final/<book>/summary.json`. They were re-run after code formatting and give
metrics identical to r5 in all four books.

| | Book 1 | Book 2 | Book 3 (anecdotal) | Book 4 |
|---|---:|---:|---:|---:|
| **Paragraph boundary F1** | 0.932 → **0.943** | 0.854 → 0.854 | – | 0.672 → **0.818** |
| Paragraph exact | 0.894 → 0.895 | 0.680 → 0.680 | – | 0.349 → **0.482** |
| Merges / splits | 715 / 1,635 → 720 / 1,262 | 57 / 194 (same) | – | 3,654 / 1,035 → 2,762 / 1,039 |
| **List items exact** (scored) | 0.801 → 0.801 (2,054) | – | – | 0.530 → **0.743** (3,382) |
| List item boundary F1 / list boundary F1 | 0.896 / 0.686 (same) | – | – | 0.789 / 0.409 → **0.888 / 0.517** |
| **Index entries exact** | 0.932 → **0.936** | – | 0.454 → **0.628** | 0.179 → **0.863** |
| Sub-entry level | 1.0 | – | 0.990 → 1.0 | 0.884 → **0.963** |
| Reference entries (book 2) | – | 0.994 (same) | – | – |
| **Headings P / R** | 0.736 / 0.852 (same) | 0.969 / 0.926 (same) | 1.0 / 1.0 | 0.619 / 0.731 → 0.598 / 0.733 |
| **Heading levels exact / within one** | 0.753 / 1.0 (same) | 0.862 / 1.0 (same) | 1.0 | 0.148 / 0.969 → **0.847 / 0.977** |
| **Zones, pages** | 0.999 (same) | 0.983 (same) | 0.444 → **0.889** | 0.980 (same) |
| **Reading order, main flow** | 0.954 (same) | 0.973 (same) | 0.991 (same) | 0.934 (same) |
| Navigation pages: index / glossary | 35 / 20 (same) | 20 / 0 (+6 bibliography) | 4 → 6 / 0 | 1 → 10 / 11 → 0 |
| Lists | 936 | 37 | 2 → 3 | 399 → 1,364 |

Rule by rule, the number that moved in each book (evidence:
[compare.json](../experiments/out/step11b/compare.json)):

| Rule | Book 1 | Book 2 | Book 3 | Book 4 |
|---|---|---|---|---|
| r1 Navigation (Task 2) | = | = (6 bibliography pages) | index +0.17, zones +0.44 | index +0.68, paragraph F1 +0.075, heading precision −0.02 (dividers) |
| r2 Set-off markers (Task 1) | = | = | = | paragraph F1 +0.071, list items +0.21 |
| r3 Math / dialogue guard | = | = | = | = |
| r4 Float titles (Task 3) | = | = | = | levels +0.70 |
| r5 Index indent base (Task 4) | paragraph F1 +0.011, index +0.004 | = | = | sub-entry level −0.002 (1 entry) |

### Overlays (book 4)

[Index](../experiments/out/step11b/overlays/overlays.json). Drawing conventions:

- list items are boxed in the list colour and labelled `<kind><n> L<level>`;
- markers are underlined;
- index locators are shown as `>p<n>`.

| Page | What it shows |
|---|---|
| [p242](../experiments/out/step11b/overlays/lists_medical_anatomy_p242.png) | List page: glued "◆" bullets and symbol-font bullets as list items |
| [p306](../experiments/out/step11b/overlays/lists_medical_anatomy_p306.png) | Index: space-separated locators, sub-entries, four columns |
| [p41](../experiments/out/step11b/overlays/lists_medical_anatomy_p41.png) | Chapter opener: banner title, learning-objective items, sections |
| [p56](../experiments/out/step11b/overlays/lists_medical_anatomy_p56.png) | Review and multiple-choice questions |

All four were inspected. Seen on them:

- **p242:** the glued "◆" bullets and the numbered hormone list are items with their
  continuation lines. A bulleted paragraph that runs on at the top of the next column stays
  one item, so its box spans both columns.
- **p306:** entries, indented sub-entries (L2) and resolved locators are right.
- **p41:**
  - the learning objectives are list items;
  - the banner title is a heading (Step 10; not drawn by the list overlay);
  - the section headings are kept units.
- **p56:**
  - The review questions and the lettered options are lists.
  - The bold question numbers of the multiple-choice questions ("1.", "2.") are items of
    their own, apart from the question text, which is a separate bold unit.
  - The options of question 3 nest at level 2, while those of questions 1–2 are level 1.

  See limitation 8.

## Limitations

1. **Table cells** hold the largest share of book 4's missed boundaries (1,253). They wait
   for the tables step.
2. **Set-off markers** without repetition evidence stay text:
   - (b) items of one visual list split into separate blocks: 19 lines;
   - (c) a lone dash or symbol-font item on its page: 36 lines.
3. **Single-item lists** with a marker are missed: 5 in book 1 (0.24% of list items) and 4
   in book 4 (0.12%).
4. **Index continuations** that the Step 7 band order puts before their entry (book 1 p686)
   stay split.
5. **Book 4 heading precision 0.598.** The index dividers are a reference convention. The
   other false headings were not re-analysed in this step.
6. **Book 4 heading levels.** 0.847 exact; 15% are still off, mostly by one level, from
   section titles at the same style in different depths.
8. **Multiple-choice questions (book 4, p56).** A question number set as its own bold
   span stays apart from its question text, and the nesting of the options is inconsistent.
   This was seen on the overlay only; it is not measured, and no rule was added.
7. **Constants** were chosen on books 1, 2 and 4 (book 3 is anecdotal):
   - glossary term share 0.5;
   - float-title step 3 (unchanged from Step 10);
   - base-indent pair tolerance 0.4 font sizes.

## Decisions for you

1. **Index letter dividers.** Book 4's reference sets them as `indexdiv/title`, not
   headings, while book 1's reference tags them as headings. Score them as a reference
   convention, or treat book 4's dialect `indexdiv` titles as headings in the evaluation?
2. **Book 1 levels on p215.** These lesson-box labels are not changed by the kept rule. Under
   the unrestricted float anchoring they would nest under the TEMA title. No action is needed
   unless you prefer that nesting.
3. **Set-off markers without repetition** ((b) 19 block-boundary lines, (c) 36 single lines
   in book 4). Either:
   - accept them as text;
   - allow repetition across neighbouring blocks of the same stream, for (b);
   - add book-level evidence, for (c).
4. **Next hold-out.** Book 4 is development now. Which reference book should be the next
   hold-out?

## Reproduce

From `experiments/`:

1. Variants, per book:
   - `python step11b_run.py --book <book> --label <label>`
   - `python step11b_compare.py r0_baseline r1_navigation r2_markers r3_math r4_float_titles r5_index_base final`
2. Diagnostics:
   - `python step11b_tokens.py --book <book> --out <file>`
   - `python step11b_single_items.py --book <book> --tokens <file>`
   - `python step11b_marker_gap.py --book medical_anatomy --scratch <dir>`
   - `python step11b_dash_lists.py --book <book> --scratch <dir>`
   - `python step11b_page_dump.py --book <book> --pages <n…>`
3. `python step11b_overlays.py`
4. Gates: `python step11b_gates.py`.

Pytest and Ruff run from `backend/`.

**Step 11b stops here for owner review. Step 12 has not started.**
