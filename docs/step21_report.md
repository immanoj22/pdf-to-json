# Step 21 — correct Jaypee delivery from Stage 1 (headings, front/back matter, parts, question banks, parity)

Status: **complete for review.** One commit. Stage 1 only, plus the adapter fixes listed below.

## Summary (one page)

**What was wrong.** The delivery for the Jaypee books needed hand repair in a few places that
all came from Stage 1: chapter numbers printed beside or above a title, a dedication page
read as a section, folio numbers picked by size-blind sequence fitting, bibliographies split
or mis-ordered, bullet glyphs lost, question banks (NEET) left as separate lists with answers
glued into options, run-to-run differences between development and production and between 1 and
2 workers, and about 2 review items per page of noise.

**What changed (all general; no book, page, font or word rules).**

- **Headings.** A chapter number printed before the title in reading order but after it in
  the text is read first; bare numbers and bold lead-ins are not headings; one heading for a
  two-line title; same label, same level.
- **Folios and pages.** A printed number far from the series' typical size is not a folio. A
  short untitled page before any titled front section is a dedication. Front-matter roman
  numerals stay in order in the page list and anchors.
- **Question banks.** A numbered stem, its options (1 or 2 columns, around a picture, across a
  page break) and its printed answer are one question entry; entries form question sets.
  Schema 1.2.0 adds optional fields only.
- **Book parts.** The person confirms front matter, body and each back-matter part as page
  ranges before export (mandatory, no override).
- **Lists.** Bullet glyphs get a shape (bullet, square, circle, diamond, check) read from the
  drawn glyph; dingbat fonts are recognised from the font descriptor.
- **Parity.** Model threads are fixed (one) and every mapping written to `book.json` is
  sorted, so development and production runs and 1-worker and 2-worker runs give the same
  bytes.

**Results.** All gates pass on the frozen code (table below). Question entries: 92.0% of the
113 sample questions complete (target 90%). Review items per page fell on every book
(ART 2.18 → 2.08, Hypertension 1.59 → 1.35, Dermatology 2.26 → 2.0, IAP 0.74 → 0.65; NEET sample 2.5 on the
36-page development sample against 9,354 items on the full book before). IAP: 39 of 39
printed contents entries linked.

**Running after the commit (owner decision):** the NEET pattern sample (gates, folio check, the
40-question hand check, the question-set export of the 185 pages), the Statistics MathML gate
on the 336 gold pages, one parity confirmation run (production mode, 2 workers, with the parts
file) against `final3`, and the before-and-after timing of the formula-reader change on 20
Statistics pages. The formula reader now runs on a fixed 4-thread scope in its identity
(`FORMULA_THREADS`); the parity pair after that change and the speed gain are measured after
the commit, and the change is reverted and made a Step 22 item if parity breaks or the gain is
under 30%.

**Owner decisions recorded here.**

1. **NEET is measured on a pattern sample** (185 pages chosen from a census of the PDF), not
   the full book. The full book runs in the background after this commit as confirmation.
2. **The Statistics MathML gate is confirmed on the 336 gold pages only,** and after the
   commit. If 87.35% strict / 98.61% symbol do not hold, that is the first item of Step 22.
3. **The apostrophe is written as `&#x2019;` in `jaypee_v5`.** This differs from guideline
   item 18; it is an owner decision recorded in the profile.
4. **IAP bookmarks** with file-style labels (Ch-01, Ch-00Prelims, "Contents") are not counted
   as contents entries (Step 22).

## Gates

| Gate | Result |
|---|---|
| Full test suite (`tests`, `tests_adapters`, `tests_app`) | **All pass:** `tests` 1,341 passed / 7 skipped; `tests_adapters` 130 passed; `tests_app` 43 passed / 1 skipped. The 7 skips are caches or fixtures missing on this machine (Step 7 furniture vocabulary, the oversized Spanish map); the app skip needs the layout models. The formula-reader change landed after the full run started, so the formula, math, cache, closure and parity tests (266) and the lint (clean) were run again on the final tree. |
| 30 source sample pages, 0 missing / 0 extra | **Pass** (in the suite) |
| Book 1 ledger 495,751 | **Pass** (`test_full_book.py` in the suite) |
| I1–I7 = 0, every line owned once | **yes** on ART, Hypertension, Dermatology, IAP; NEET sample running after the commit |
| Lossless | 0 missing / 0 extra on ART, Hypertension, Dermatology, IAP; NEET sample running after the commit |
| Development vs production | **Identical.** Hypertension, fresh caches: development mode with 2 workers vs production mode with 1 worker: all 373 published files byte-identical, so this one comparison covers both gates. |
| 1 vs 2 workers | **Identical** (same comparison; also identical on the earlier freeze: 1 worker with caches vs fresh 2 workers vs fresh production, same `book.json` hash). The `final3` Hypertension run had the confirmed parts file and the parity runs did not (a setup slip); their `book.json` differs from `final3` only in `metadata.book_parts` and the content hash that covers it. One confirmation run with the parts file follows the commit. |
| Adapter: DTD-valid, 0 errors | **0 on ART, Hypertension, Dermatology, IAP**; NEET sample running after the commit |
| Adapter: house-rule findings | **0 on ART, Hypertension, Dermatology, IAP** (Dermatology had 1; fixed); NEET sample running after the commit |
| Statistics MathML 87.35% / 98.61% | running after the commit on the 336 gold pages (owner decision) |

## Before → after per book (Stage 1 `book.json`)

| Book | Pages | Headings | Paragraphs | Lists / items | Captions | Review items (per page) | Folio furniture | Unlabelled pages |
|---|---|---|---|---|---|---|---|---|
| ART | 130 | 190 → 183 | 326 → 297 | 90 → 76 / 268 → 236 | 10 → 3 | 284 → 270 (2.18 → 2.08) | 85 → 84 | 0 → 0 |
| Hypertension | 88 | 106 → 104 | 303 → 306 | 93 → 99 / 368 → 383 | 20 → 0 | 140 → 119 (1.59 → 1.35) | 56 → 58 | 16 → 1 |
| Dermatology | 292 | 694 → 687 | 1,245 → 1,109 | 631 → 816 / 2,402 → 3,094 | 82 → 10 | 660 → 583 (2.26 → 2.00) | 253 → 252 | 16 → 16 |
| IAP | 330 | 847 → 797 | 1,727 → 1,559 | 678 → 628 / 2,424 → 2,198 | 16 → 3 | 244 → 214 (0.74 → 0.65) | 270 → 269 | 0 → 0 |
| NEET (pattern sample) | 185 | running after the commit | | | | running after the commit | | |

Notes: "before" is the code at the start of Step 21 (the owner's app job for Dermatology and
IAP). Dermatology's 16 unlabelled pages print no folio. Captions fell because they are now
linked to their figures. IAP also has one question entry after the change (0 before); see known limits (a false one).

## Contents links (IAP, item 15)

| | Entries | Linked |
|---|---|---|
| Before Step 21 | 69 | 28 |
| After the first freeze | 81 | 17 |
| Final | 81 | 40 |

Of the 81, **39 are printed contents entries and all 39 are linked.** The other 42 are PDF
bookmarks with file-style labels (`Ch-01`…, `Ch-00Prelims`, "Contents"); they carry no title,
so no title comparison can link them. Step 22: when a book has printed contents, do not
create contents entries from such bookmarks; if bookmarks are used, link them by their
target page. The fix that brought 17 → 40: a contents entry's target is mapped through the
heading group it was merged into (`assembly/assemble.py`, `link_targets`).

## Item 7 — question entries (NEET)

36-page development sample (113 questions): 104 complete (92.0%). The 9 not complete are
listed in the "known limits" section with their cause. running after the commit: the pattern sample
result and the 40-question hand check.

## Hand checks

- **Page joins (40, seeded across ART, Hypertension, Dermatology, IAP):** 40 of 40 are one
  paragraph continued across the page break (precision 1.00; target 0.95). Recall by a text
  heuristic (no end punctuation and a lowercase start): 104 of 112 candidates linked, about 93%.
- **Chapter starts (20, seeded across four books):** the title words of all 20 are on the
  opener page; **16 are clean.** Four are wrong, see known limits (3 with the number inside the
  title, 1 contents line on a section opener read as a chapter).
- **Bullet lists: 14 of the 20 checked** (7 ART, 7 Dermatology, seeded; read in the extracted
  text). Items are complete, no marker glyph is left in an item's text, and each list has a
  marker shape. Single-item lists: ART 9 of 40 (4 continue across a break), Dermatology 91 of 718
  (21 continue). The 6 cancer-biology lists were **not checked** (owner decision: that book was
  not re-run on the final code); the lists were not compared with page images.
- **NEET questions (40):** running after the commit (owner decision): the sample was
  restarted on the committed code and the hand check follows its result.

## Adapter changes (Stage 2, no converter change)

- **Question banks (R15).** A question entry with lettered options is written as DocBook
  `qandaset / qandadiv / qandaentry` (the printed number as `role`) with a `question` (the stem
  as a `para`, then an `orderedlist numeration="loweralpha"` directly inside it) and an `answer`
  (the key line and the explanation, tables and pictures included). The ePub has the same
  structure: `section.qandaentry` with `div.question` (`ol type="a"`) and `aside.answer`. An
  entry with no lettered options stays as plain text. Two questions from the NEET development
  sample's DocBook (DTD valid, lossless 0/0; the 185-page sample follows the commit):

```xml
<qandaentry role="20">
<question><para><emphasis role="bold">A mediterrangean person didn&#x2019;t receive primaquine. Which pathway is affected by G6PD enzyme deficiency? </emphasis><emphasis role="italic">(NEET 2022)</emphasis></para><orderedlist numeration="loweralpha">
<listitem><para>HMP pathway</para></listitem>
<listitem><para>Glycolysis</para></listitem>
<listitem><para>Gluconeogenesis</para></listitem>
<listitem><para>Krebs cycle</para></listitem>
</orderedlist></question>
<answer><para role="noindent"><emphasis role="bold">Ans. is &#x2018;a&#x2019; HMP pathway</emphasis></para></answer>
</qandaentry>
<qandaentry role="23">
<question><para><emphasis role="bold">A woman on anti-depressants presents with bleeding. ...</emphasis> <emphasis role="italic">(NEET 2022)</emphasis></para><orderedlist numeration="loweralpha">
<listitem><para>Vitamin A</para></listitem> <listitem><para>Vitamin D</para></listitem>
<listitem><para>Vitamin E</para></listitem> <listitem><para>Vitamin K</para></listitem>
</orderedlist></question>
<answer><para role="noindent"><emphasis role="bold">Ans. is &#x2018;d&#x2019; Vitamin K</emphasis></para>
<itemizedlist mark="bullet"><listitem><para>The patient presents with steatorrhea and bleeding.</para></listitem> ...</itemizedlist>
<para><informalfigure> ... </informalfigure></para></answer>
</qandaentry>
```


- A blank front-matter page after a roman-numbered page continues the roman series in the
  ePub page list and anchors (Hypertension page 16 → xvi). Anchors stay `pageFM{number}`
  (arabic), as in Jaypee's own ART delivery; the page list starts at iii there too.
- A figure caption ending in a separator and "Continued" marks a continued figure; a continued
  figure has a blank label and no big image (Dermatology Fig. 24A).

## Known limits and the first items of Step 22

1. **Labeller (`furniture/sequence.py`):** a blank page after an inferred front-matter run
   continues it (the adapter does this now; the labeller should).
2. **Visual check on image-only pages** is serial and took up to 21 minutes per page; it must
   run in parallel and much faster. It, and a slow assembly of the question grouping, made the
   full NEET book take more than a day.
3. **Math gate (owner decision):** confirmed after the commit on the 336 gold pages; if
   87.35% / 98.61% do not hold, that is the first item of Step 22.
4. **Chapter openers:** a number placed between two lines of the title ("Competency-based
   Medical 3 Education", "Professionalism and 21 Ethics: Assessment") is read in the middle of
   the title; one contents line on a section opener (IAP page 229, "38. Using Artificial
   Intelligence…") is read as a chapter heading.
5. **Question entries not complete (36-page sample):** two with no entry (pages with "For
   colour version see Plate"), seven with no options (options nested under the stem, or the
   stem classed as a heading). The subject banner "PSM" is kept as a figure the model did not
   find (8 flags, all one banner).
6. **One false question entry in IAP** (page 35): a sentence with inline numbers
   "(5) … (6) … funding and (10) quality assurance." is read as a stem, its options and an
   answer line with key 10. The adapter opens it back into plain text, so the delivery is
   unchanged; the answer-line rule should not accept a line that continues running text.
7. **Hypertension bibliography:** printed pages 61–68 (physical 77–84); the owner's note says
   61–64.
8. **Session C ran a full Statistics run** (`math18`) outside the rule that only the main
   session runs full books.
9. **Cache lesson:** `COMMON` includes the whole `model/`, so a field added to the model
   re-keys every cache. Plan model changes at the start of a step.
