# Step 9: paragraphs

Ordered lines are now joined into paragraph units in every stream: the main flow and each
float. Each unit carries confidence and reasons, line joins (line, row, column, page),
hyphenation and split-word decisions, inline style runs and language runs. Heading-like and
list-like lines are separate units, kinds `heading_candidate` and `list_item_candidate`. No
heading level, list, figure, table or zone is decided.

Raw spans are never rewritten: joins and dehyphenation are recorded as metadata, and
normalized paragraph text is a derived view. The ledger, Step 4 layouts and the Step 7 builder
are unchanged. Gold changed only by the logged, owner-approved book 2 marker fix. Old projects
were not touched.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | **774 passed**, 0 failed / 0 skipped (744 at Step 8, plus 2 furniture and 28 paragraph tests) | [JUnit](../experiments/out/step9/pytest.xml), [log](../experiments/out/step9/pytest.log) |
| 24 measured pages vs original sources | **0 missing / 0 extra** | [cross-check](../experiments/out/step9/original_source_crosscheck.json) |
| Full book | **495,751** retained tokens; passing | [full_book.json](../experiments/out/step9/full_book.json) |
| I1-I7 on 24 pages | **0 each** | [invariants.json](../experiments/out/step9/invariants.json) |
| Every line in exactly one unit and ordered once | 24 pages ([report](../experiments/out/step9/units_every_line_once.json)) and every line of the three books: 84,085, 14,396 and 1,231; 0 invariant problems | per-book summaries |
| Reading-order metric not worse | Emitted order is **identical** to Step 8 in all three books (book 1: main flow 0.945681, anchors 0.90067). See "Float anchors" | summaries |
| Ruff check / format, from backend/ | pass | [ruff.log](../experiments/out/step9/ruff.log) |

## Part 0: decisions and housekeeping

All Part 0 decisions are recorded in [decisions.md](decisions.md).

- **CONÉCTATE** stays content as a sidebar float read after the main text. It is unchanged
  from Step 8: 141 lines on 141 pages, never in a furniture stream.
- **Front-matter metadata rule (correctness rule, logged).** Trusted PDF page-label metadata
  now labels only front matter: pages before the first printed run that have no fitted
  printed folio, with `source = metadata`. A front-matter edge line that prints exactly that
  label becomes the folio. Inside and after the runs, the sequence infers labels; metadata
  confirms them or flags a disagreement. There was no threshold change.

  Book 2 was re-run once for this rule (logged in
  [step8 holdout_runs.jsonl](../experiments/out/step8/holdout_runs.jsonl)). The two
  "completed" records there were appended afterwards, because the runner's log write failed
  on a relative `--out` path; the outputs were written normally.

  | Book 2 | Step 8 | After the rule |
  |---|---|---|
  | Marker sources | printed 312, metadata 19 | printed 312, metadata 11, inferred 8 |
  | Front-matter folio lines "v", "vii", … | running_foot (3 lines) | **folio** (316 folios) |
  | Label / placement accuracy (old gold) | 0.9898 / 0.9898 | 0.9898 / 0.9898 (unchanged) |
  | Books 1 and 3 | – | identical outputs |

- **Book 2 gold markers 146/147 fixed with evidence**
  ([evidence](../experiments/out/step9/gold_fix/evidence.json), renders
  [p157](../experiments/out/step9/gold_fix/top_strip_157.png),
  [p158](../experiments/out/step9/gold_fix/top_strip_158.png)):
  - PDF pages 157 and 158 print folios 146 and 147, and the PDF label metadata agrees.
  - Bibliography entries 1–15 lie on page 157 and entries 16–30 on page 158.
  - The reference places page break 146 after entry 15, so derived placement (the page holding
    most of the following text) landed one page late.
  - Fix: 146 → p157 and 147 → p158. The manifest digests were updated, gold stays
    `human_approved: false`, and before/after is logged in
    [step5 holdout_runs.jsonl](../experiments/out/step5/holdout_runs.jsonl).
  - Book 2 marker accuracy: **0.9898 → 0.9966 (293/294)**. The one remaining miss is gold "i"
    placed on a blank front page.
- **`repeated_box` requires drawn geometry**
  ([boxes.py](../backend/src/book_core/furniture/boxes.py)). The line must be covered at least
  80% by drawn fills, or sit inside a stroked frame, smaller than 40% of the page. Native
  drawings are read through the Extractor, for candidate pages only.
  - Book 1: CONÉCTATE is boxed on all 141 pages; outputs are unchanged.
  - Book 2: the false repeated box (a citation repeated on 3 pages, 117 lines) is now plain
    content.
- **Cache housekeeping** ([log](../experiments/out/step9/housekeeping.json)).
  - What was deleted: 224 entries whose producer is superseded. For each one, the real key
    function, applied to the same source and configuration, gives a different key.
  - Space freed: **0.94 GiB**, as old extraction namespaces (`step5/native`, `step6/native`),
    old metadata entries, two superseded book-1 reading-order folders, old furniture decisions
    and pages, and 7 alignments replaced by the logged Step 5b run.
  - What was kept: every current key, the newest alignment per book (evaluation evidence),
    the step6 document artifacts, step6b and objects.
  - `caching.py` is unchanged.

  Cache disk use now: step7 26 GB, objects 4.9 GB, step6b 2.9 GB, huggingface 291 MB, step9
  287 MB, step6 123 MB, step8 110 MB, pip 98 MB, pytest 56 MB, step5 26 MB. 15 GB is free.

## Model and rules (brief)

[paragraphs/](../backend/src/book_core/paragraphs/) holds the models, geometry, lexicon,
segment, crosspage, inline, anchors, page, text, keys and cache modules.

- **Model.**
  - `ParagraphUnit`: line ids, kind, `Boundary` (confidence, reasons, evidence), `LineJoin`s,
    `StyleRun`s, language and `LanguageRun`s, and `continues_from` / `continues_to`.
  - `HyphenDecision` and `WordJoin` reference span ranges.
  - `PageParagraphs` holds the units, the order and the `AnchorMove`s. Its validator enforces
    that every ordered line is in exactly one unit.
  - `BookParagraphs` holds the page joins, page-join candidates and the profile.
  - No source text is stored.
- **Measurements.** Everything is measured in the line's own reading frame: the start is the
  right edge for right-to-left text, and vertical writing advances right to left. Gaps are
  measured against the lane run's line pitch, falling back to the book's pitch for that font
  size. Indents and line fill are measured in font sizes.
- **Boundary evidence.** A boundary is placed when the summed evidence reaches 0.45.
  - **Gap:** ignored when a float occupies the gap.
  - **First-line indent:** a local bump over both neighbours, so text wrapped around a shape
    does not count.
  - **Hanging-indent blocks:** detected per lane run and in a local window, from clustered
    indents and line fill.
  - **Short last line:** counts in justified text only.
  - **Text cues:** a sentence terminal, an open end or a break hyphen on the previous line; the
    case of the next line; a colon followed by a gap.
  - **Style change, drop caps and same-row fragments.**
  - **Block types:** Step 4 type changes (heading, caption, figure, table).
  - **Navigation:** Step 6 printed-navigation entries; each entry is a unit.
- **List markers.** Bullets, dashes and numbers always count. A single-letter marker counts
  only with sequence evidence (the adjacent letter appears in the same stream, same case and
  punctuation) or inside a hanging-indent block, so an initial ("W. Bush") never splits a
  paragraph. This was changed at your request; see the table below.
- **Columns.** A column join needs Step 7 continuation evidence ("continues", or "neutral"
  with an open end), no indent, the same style, and a next lane that does not start lower.
  Starting lower means a new row, as in glossary rows.
- **Pages.** A page join links the last main-flow text unit of one page to the first of the
  next. It needs the same running kind and style, Step 7 "continues", and no indent or new
  entry. Furniture, floats and notes are in other streams, so they never break a join.
- **Hyphens** (Step 6 vocabulary first, then the book's own compound lexicon):
  - A soft hyphen always joins.
  - A number at the hyphen keeps it.
  - Otherwise the hyphenated form attested inside lines is compared with the joined
    spelling's count.
  - When neither form is attested: keep if both parts are words of the book, join otherwise.
  - No hyphenation dictionary is used, so no dictionary licence question arises.
  - Split words without a hyphen are joined only on strong vocabulary evidence.
- **Inline.**
  - Style runs: bold, italic, superscript and subscript (flag, or a smaller raised/lowered
    span), small caps (font name), and colour emphasis.
  - Language runs: Lingua, restricted to the Settings languages (spa, eng), with a
    book-relative letter threshold. Its offsets are mapped back to spans.
- **Cache identity** ([keys.py](../backend/src/book_core/paragraphs/keys.py)).
  - The key binds: the paragraph and furniture producers, the furniture decision key (which
    chains the layout and order fingerprints), the Step 6 evidence digest (vocabulary and
    navigation entries), the language detector identity, settings, configuration and version.
  - A closure test, a test that every scope file edit changes the digest, and a test per key
    component guard it.

## Results (per book, no overall score)

Paragraph-like reference units are paragraph, caption, list_item and definition_description.
The headline metric is scored on per-page units, because the book 1 reference splits every
paragraph at a page break. The chained variant counts page joins.

| | Book 1 (development) | Book 2 (hold-out, once) | Book 3 (hold-out, anecdotal, once) |
|---|---:|---:|---:|
| Reference units scored | 15,199 | 757 | 0 (index entries only) |
| **Boundary precision / recall / F1** | 0.917 / 0.880 / **0.898** | 0.785 / 0.937 / **0.854** | – |
| **Exact unit match** | **0.753** | **0.680** | – |
| Split / merge errors | 1,174 / 2,265 | 194 / 57 | – |
| Exact by kind | paragraph 0.896, caption 0.865, list_item 0.647, definition 0.216 | paragraph 0.680 | – |
| With page chains: F1 / exact | 0.897 / 0.742 | **0.932 / 0.857** | – |
| Units | paragraph 10,080, heading cand. 3,566, list cand. 1,018, caption 647, figure text 3,539, table text 233 | paragraph 3,120, heading cand. 210, list cand. 99 | paragraph 115 |
| Low-confidence units (flagged) | 446 | 16 | 0 |

Joins:

| | Book 1 | Book 2 |
|---|---|---|
| Column joins: precision / recall vs reference | 0.702 / 0.807 (470 joins of 1,357 candidates) | 0 of 6 (only 16 candidates) |
| Page joins | 111 of 711 page pairs (62 neutral pairs flagged). Reference precision 0.085 (the reference splits at page breaks). Seeded audit of 20: **15 correct** mid-sentence continuations; 5 wrong, all in glossary/index | **precision 1.000 / recall 0.859** (134 of 156 reference joins) |

Book 3 makes 4 page joins in the index.

Hyphenation:

| | Book 1 | Book 2 | Book 3 |
|---|---|---|---|
| Decisions | keep 51, join 1, soft join 1; split-word join 1 | join 1,345, keep 84 | keep 3 |
| Accuracy vs reference spelling | **0.809** (38/47) | **0.984** (1,400/1,423) | 3/3 |

Book 1's line-end hyphens are mostly real compounds. Its 9 errors are compounds such as
"hispano-/estadounidense" and "complejo militar-/industrial", which the reference writes
joined even though the book writes them hyphenated inside lines elsewhere.

Inline:

| | Book 1 | Book 2 | Book 3 |
|---|---|---|---|
| Style runs | bold 14,909, italic 537, superscript 308, subscript 23, colour 2,732 | bold 296, italic 1,583, superscript 53, subscript 2 | italic 10 |
| Unit languages | es 13,830, en 1,793, und 3,460 | en 2,122, und 1,339, es 14 | en 73, und 42, es 2 |
| Units with language runs (mixed) | 3,214 | 1,052 | 33 |

Language results are model evidence restricted to the configured languages, not calibrated
truth.

### Owner's case: the "Gobernantes estadounidenses…" paragraph (book 1, p26)

| | Result |
|---|---|
| Old project (phase0 audit) | Opening `<p>` truncated after "la estructura"; prose split into several fragments, interleaved with unrelated content |
| Step 9 | **One unit**, 7 lines, from "Gobernantes estadounidenses como Benjamin Franklin…" to "…lo habían hecho los iroqueses:". It **matches reference unit 1586 exactly**. The lines wrap around the circular pull quote (starts at x 398, 394, 404, 412, …); a local-bump indent rule keeps them together. The block quote that follows is its own unit ("colon followed by a gap: a displayed element follows"), as in the reference (1587) |

See the overlay [p26](../experiments/out/step9/overlays/paragraphs_p26.png) (P10).

### List-marker fix (your instruction, before the hold-outs ran)

| Book 1 | Boundary F1 | Exact match | Paragraph exact | List items exact |
|---|---:|---:|---:|---:|
| Any single letter + "." or ")" counts | 0.89746 | 0.75163 | 0.8931 | 0.6472 |
| Interim: uppercase letter markers dropped | 0.89808 | 0.75308 | 0.8956 | 0.6474 |
| **Final: sequence evidence or hanging-indent block** | **0.89811** | **0.75308** | **0.8958** | 0.6470 |

The p590 "George / W. Bush argumentó…" paragraphs are no longer split. Tests: "W. Bush
argumentó…" stays one paragraph; an "A./B./C." list splits into three items; a lettered entry
in a hanging-indent block counts. Books 2 and 3 ran once, after this was re-frozen.

### Float anchors: a decision for you

Paragraph-boundary anchors are computed for every float (book 1: 120 proposals) and recorded
as `AnchorMove` evidence. They are **not applied**: the emitted order keeps the Step 7/8
anchor, because applying them lowers the reading-order metric, and the gate says it must not
get worse.

| Book 1 float anchors | Accuracy |
|---|---:|
| Step 8 (centre anchor; emitted) | **0.9007** |
| Nearest paragraph boundary | 0.8873 |
| End of the paragraph | 0.8909 |
| Guarded variants (strong joins only, at most 1–3 lines away) | 0.8936–0.8995 |

The Step 7 metric already counts an anchor inside the right paragraph as correct, so a move
can only lose. Every loss traced to a merged unit of ours, where the move carries the float
into the next reference paragraph. With exact paragraphs the move would be neutral. The rule
is configurable (`anchor_rule = keep | nearest | end`).

## Overlays

The overlays show units boxed and numbered (`P` paragraph, `H` heading candidate, `L` list
candidate, `C` caption). A unit continued into another column gets one box per column and an
arrow. Page joins are marked `pN->` / `->pN`. Hyphen decisions are marked `J` / `K` / `S`, and
flagged units are red. All were inspected. [Index](../experiments/out/step9/overlays/overlays.json).

| Page | What it shows |
|---|---|
| [p26](../experiments/out/step9/overlays/paragraphs_p26.png) | The Gobernantes paragraph (P10), the quote as its own unit, pull quote in a float |
| [p100](../experiments/out/step9/overlays/paragraphs_p100.png) | Column continuation into the right column |
| [p465](../experiments/out/step9/overlays/paragraphs_p465.png) | Two columns, then cards |
| [p669](../experiments/out/step9/overlays/paragraphs_p669.png) | Bilingual glossary (row order inherited from Step 7) |
| [p590](../experiments/out/step9/overlays/paragraphs_p590.png) | Paragraph continued from p589; column join; "W. Bush" lines no longer split |
| [p306](../experiments/out/step9/overlays/paragraphs_p306.png), [p421](../experiments/out/step9/overlays/paragraphs_p421.png), [p692](../experiments/out/step9/overlays/paragraphs_p692.png) | Unseen pages (seeded draw, seed 9) |

## Low-confidence list

Book 1 has 446 flagged units: 213 paragraph, 206 figure text, 15 heading, 10 table, 2
caption. Flags mean a boundary or join decided within 0.15 of the threshold. The most common
first reasons are a hanging-indent outdent (61) and gaps of 1.5–2 pitches without other
evidence. Examples:
- p2: a table-of-contents line merged across entries.
- p338: map labels.
- p671: glossary rows.

Book 2 has 16 flagged units and book 3 none. Full lists with page, unit, reasons and text are
in `low_confidence.jsonl.gz` per book, for example
[book 1](../experiments/out/step9/spanish_us_history/low_confidence.jsonl.gz).

## Limitations

1. **Glossary units (definition 0.216).** Step 7 reads the bilingual glossary row by row, so
   page references and the two languages interleave. Units cannot match the reference's
   per-language entries without reordering, and Step 9 never reorders.
2. **Back-matter page joins.** Glossary and index entries end without sentence cues, and the
   next page starts lowercase; 5 of the 20 audited joins are wrong for this reason.
3. **Column joins on timeline/table pages** (for example p347) follow the inherited Step 7
   order across columns.
4. **Merges remain the main paragraph error** (book 1: 2,265): table-of-contents and index
   lines without navigation evidence, and Step 4 regions that merge texts.
5. **Book 2 splits** (194) come from short lines in ragged text read as paragraph ends. This
   was found on the hold-out and not tuned.
6. **Post-hold-out comment edit.** The `segment.py` comment "EM SPACE" contained a forbidden
   schema tag word (caught by test_boundaries). It was reworded after the hold-out runs. The
   syntax tree is identical and the edit is logged with both producer digests. Behaviour is
   unchanged, and the hold-outs were not re-run.
7. **Confidence and language.** Confidence values are rule heuristics. Language runs depend on
   Lingua and the configured languages.

## Decisions for you

1. **Float anchors.** Keep the Step 7/8 anchors in the emitted order, with paragraph-boundary
   proposals recorded (current), or apply "end of paragraph" and accept 0.9007 → 0.8909 until
   paragraph merges are reduced?
2. **Page joins vs reference convention.** Book 1's reference splits paragraphs at page
   breaks; book 2's keeps them whole, and we match book 2 with precision 1.0. The model
   records joins as links between per-page units, so an adapter can emit either form. Is
   that the right default?
3. **Glossary order.** Should Step 7 read bilingual glossary rows entry by entry, Spanish then
   English, as the reference does, instead of synchronised rows? That would lift the
   definition units.
4. **Hyphen policy for compounds.** Keep compounds the book itself writes hyphenated inside
   lines (current), or follow the reference's joined spelling ("hispanoestadounidense")?

## Reproduce

From the project root:
1. `python experiments/step9_housekeeping.py [--apply]`
2. `python experiments/step9_gold_fix.py` (runs once)
3. `python experiments/step8_run.py --book <book> [--holdout --correctness-rerun "…"] --out experiments/out/step9/furniture`
4. `python experiments/step9_run.py --book spanish_us_history`
5. Hold-outs, once each: `python experiments/step9_run.py --book <book> --holdout --reason "…"`
6. `python experiments/step9_overlays.py`
7. `python experiments/step9_gates.py`

Pytest and Ruff run from `backend/`.

**Step 9 stops here for owner review. Step 10 has not started.**
