# Step 22 — chapter editing in the app, and the Ultrasound-guided Regional Blocks book

Status: **complete for review.** One commit. The converter's Stage 1 gets one change (page numbers
set beside a running head); the rest is the app's Browse editor and two adapter fixes.

## Summary

**The book.** "Ultrasound-guided Regional Blocks" (72 pages, 14 chapters in 5 sections) came out of
the converter with the Contents page read as a part, the printed chapter lists on the section
openers read as headings, chapter 1 read as a section, "PART I/II/III" and REFERENCES read as
chapters or parts, and no page numbers at all (its running head carries the page number beside
the head text, so the number was never read). The export then had extra chapters and lost parts.

**What changed.**

- **Browse editor (app).** On a heading: set its kind (part, chapter, section, front matter, back
  matter), set its number, "belongs to the chapter before" (REFERENCES), and edit the title text
  (it can only lose a stray number; the old title and the new one are kept in the audit log). On a
  paragraph: "Start a new chapter here" with a number. A **Chapters and parts** panel lists every
  part and chapter with number, title and page, refreshed after each change, so the team checks
  the whole structure on one screen. Every change is an audit-log edit, as before.
- **Export follows the edits (adapter).** A heading set as part, chapter, section or front matter
  is exported as that. REFERENCES and other attached titles (feature, sidebar, subsection) never
  open a part or a chapter whatever level they carry (this was the "level 2 PART exported as a
  chapter" and "SECTION disappeared" bug). The number a person sets is the chapter or part number.
  A part or chapter the person sets pulls the headings printed inside it one level below it;
  the converter's own headings are left alone.
- **Stage 1.** A page number set beside a running head ("12" next to "SECTION 2: Upper Limb
  Blocks") extracts as one run with no space and was never read as a page number. The label
  finder now reads the gap between the two pieces of text; the text itself is untouched.
- **Schema 1.3.0.** One optional field: a heading's `number` (the number a person set).

## Result on the Ultrasound book

Using only the Browse operations (16 kind edits, one "not a heading", 19 title edits):

| | Result |
|---|---|
| Chapter list in the app | **5 parts, 14 chapters**, numbered 1–14, clean titles |
| DocBook | 5 parts, 14 chapter files; DTD 0 errors; lossless 0 missing / 0 extra; house-rule findings 0 |
| ePub | EPUBCheck 5.4.0: 0 errors, 0 warnings; lossless 0 missing / 0 extra |
| Figure ids | follow the chapter numbers (`ch1fig1`, `ch2fig1A`, …); 235 internal links, 0 broken (13 to figures) |
| Page labels | none → 62 of 72 pages (printed 12–62, the rest inferred; the 10 front pages have none) |

**The converter's raw output for this book (no edits) is not better yet:** with the page numbers
read, its Contents page is recognised as a contents list (good), but the section openers are read
as chapters (this book's "SECTION" and "CHAPTER" opener labels are rotated, letter-spaced text
that is not read as a sectioning word). The raw export is 3 parts, 20 chapter files and 2 DTD
errors (a chapter that is only a title and a bibliography), against 5 / 18 / 0 before, which
only looked better because the five contents entries were read as headings. The Browse editor is
the repair path (above). The root fix is Step 23 item 1.

## Gates

| Gate | Result |
|---|---|
| Tests | **All pass:** main suite 1,344 passed, 0 failed, 7 skipped; adapter suite 132 passed; app suite 52 passed, 1 skipped (it needs the layout models), including the browser test of the new Browse controls with the ePub lossless check at 0 missing / 0 extra. One main-suite test failed once while the suites ran side by side (they shared one temporary folder); it passes alone and its file passes in full (50 passed). The 7 main-suite skips are caches or fixtures not on this machine. |
| Hypertension, ART, IAP (chapter-start books), before → after | **0 tokens lost, 0 gained, 0 moved** between content and furniture; **0 page labels changed**; I1–I7 = 0 and every line owned once; DTD 0; lossless 0/0; house-rule findings 0 on all three |
| Ultrasound raw conversion | tokens 18,459 → 18,473 (14 gained: the numerals `1.`–`14.` of the contents entries, now one list; none lost) |
| Dermatology, NEET sample, Statistics gold pages | run after this commit (owner decision) |

Owner decisions: Dermatology, the NEET pattern sample and the Statistics gold-page run were moved
to after the commit; the Statistics and NEET runs from Step 21 were paused and restart tonight.

## What was tried and removed (so Step 23 does not repeat it)

- **"A contents title is front matter" (Stage 1).** Matching a heading to a contents word is not
  safe: IAP has a table label "Contents" inside a lesson-plan template (page 125); the rule dropped
  the headings around it and reset the levels after it, and IAP's export went from 43 to 63
  divisions with 2 DTD errors. Removed. The page number fix lets the real contents page be
  recognised the normal way.
- **"A section level that holds chapters is a part" (role rule).** IAP uses the word "section"
  both for its openers and inside chapters; the rule renamed every heading at that level.
  Removed. A softer rule (a level that holds chapters cannot share the chapter role) had no
  effect on this book (sections and chapters sat at one level) and was removed too.

## Step 23 — first items

1. **Section and chapter opener labels** drawn as rotated, letter-spaced text ("S E C T I O N",
   "C H A P T E R") are not read as sectioning words in this book; read them, and the part and
   chapter levels follow.
2. A chapter with only a title and a bibliography (REFERENCES) must join the chapter before it.
3. The delivery's page-info file for a book whose pages carry no printed number.
4. The Browse title editor could also set the number (it keeps the removed number as the number
   today).
