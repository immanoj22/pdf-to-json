# Adapter A — profile-driven adapter engine + Jaypee DocBook profile

## Summary

**What works.** A client-neutral adapter engine turns a published `book.json` into a
client delivery, with every client choice in a profile YAML. The Jaypee v3 profile was
written by hand from the guideline (item numbers cited in its comments).

On the ART book (9789372025262), the delivery is laid out like the real one:
- `<ISBN>/<ISBN>.xml`, `page_info.xml`, `Chapters/front.xml`, `ch1–ch17.xml` (a chapter that
  opens a part carries the `<part>`), `images/`, `bigimages/`.
- **DocBook 4.2 DTD: 0 errors** in all 19 files.
- **House rules generated from the profile: 0 violations.**
- **Lossless: 0 missing, 0 extra** of 37,639 tokens; the XML re-read from disk matches the
  ledger token for token.
- Parts (5), chapters (17), bibliographies (17), prefaces (3), page anchors with
  first/last roles, and `page_info.xml` match the delivery exactly.

All 7 books are DTD-valid with lossless 0/0 and no undeclared order exceptions (table
below). There are 53 adapter tests, all passing. The same input, profile and book settings
give byte-identical output, including the ZIP (tested). Copy-paste commands are in
`docs/adapter_quickstart.md`.

**Confirm with Jaypee** (owner decisions of 2026-10-30, implemented as profile values):
- **Image sizes.** `images/` max 500 px wide (`images.max_width`, from the delivery).
  `bigimages/` hold the same image at source size (`images.big_max_width: null`); a cap can
  be set. The delivered big images are 338–672 px wide. Ours are 806–876 px for ART, because
  our crops are rendered at 300 dpi.
- **Alt text.** The placeholder is "(no image)", the delivery's wording. The export **fails**
  (exit 3, no delivery written, report written) while any figure or equation alt text is a
  placeholder. The user can pass `--allow-alt-text-placeholders`; the report then records
  `alt_text.override: true` with the count and an `OVERRIDE` warning. No published book has
  alt text yet (ART: 17 placeholders), so every run below used the recorded override.
- **Text inside figures.** It is not written as XML text by default
  (`figures.embedded_text: omit`): it stays in the image, the alt text describes it, and it
  remains in book.json. The lossless report lists it as "text inside a figure (stays in the
  image)" (ART: 57 tokens). `textobject` and `caption` remain profile choices.

**Other guesses** (marked in `jaypee_v3.yaml`):
- JPEG quality 90.
- Continued figures get `chNfigMcK` ids, because item 13 shows the original id and ids must
  be unique.
- Paragraph roles (noindent after a title, indent after that) and nested bold/italic were
  read from the delivery, not the guideline.

**Guideline rules the schema cannot express yet** (details below):
- Item 2: float placement "close to the paragraph".
- Item 6: colour of table cells.
- Item 23: swapping colour-plate images (only the note removal is expressible).
- Item 25: the label format of set figures ("Figs. 5.5A").
- Items 11/12: subchapter detection.
- Item 31: epigraph detection.
- Copyright-page heads (`legalhead`/`copyrighthead`).
- Exact `page_info.xml` formatting (fixed in the writer).

**Guideline vs DTD conflict:** item 27's `<sidebar label="BOX 1">` is not valid DocBook 4.2
(`sidebar` has no `label`). Item 1 (DTD-valid) wins: the profile writes the id and title role
only. **Delivery defect:** the real delivery's `Chapters/ch8.xml` is not well-formed (it opens
`<part>` and never closes it); its other 18 files are DTD-valid.

**What Stage 1 must improve** (`docs/adapter_requests.md`, R1–R14). Most of the remaining
differences from the delivery are Stage 1's:
- **Headings:** ART has 9 sections where the delivery has 144 (titles arrive as
  `display_title` paragraphs). There are no part/chapter headings in ART; book 4 and IAP
  give only the chapter number as the heading.
- **Zones:** Trichology's articles and Statistics' whole body are in the wrong zone.
- **Figures and tables:** captions not linked or interleaved with body text; tables drawn
  as images or wrapped in callout boxes.
- **Reading order:** two-column text is interleaved inside paragraphs and table cells.
- **Alignment and epigraph roles:** not provided.

The part and chapter starts that the adapter infers for ART are all marked
**adapter-inferred** in the review list. Those fallbacks run only when book.json has no
heading of that kind, so they stop by themselves once Stage 1 supplies the headings.

## Results on the published books

Profile `jaypee_v3` 3.0.0 on every book. ART uses `books/9789372025262.yaml`; the others have
no book settings, so their ISBN is "to supply" and their folder is `ISBN_TO_SUPPLY`. One
worker; times are the full run including checks.

| Book | DTD files / errors | House violations | Tokens | Missing / extra | Omitted by profile | Undeclared out-of-order | Adapter-inferred | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ART 9789372025262 | 19 / 0 | 0 | 37,639 | 0 / 0 | 265 | 0 | 22 | 24.8 s |
| Book 4 (anatomy) | 12 / 0 | 36 ¹ | 94,539 | 0 / 0 | 1,422 | 0 | 11 | 97.9 s |
| Art therapy (index) | 4 / 0 | 0 | 4,202 | 0 / 0 | 0 | 0 | 0 | 2.2 s |
| Book 2 (immigrant children) | 17 / 0 | 0 | 121,359 | 0 / 0 | 4 | 0 | 0 | 32.8 s |
| Statistics | 24 / 0 | 466 ² | 300,555 | 0 / 0 | 1,486 | 0 | 0 | 210.3 s |
| IAP MEC (frontend output) | 13 / 0 | 31 ¹ | 123,465 | 0 / 0 | 420 | 0 | 0 | 47.2 s |
| Trichology (frontend output) | 33 / 0 | 0 | 82,179 | 0 / 0 | 3,524 | 0 | 1 | 26.4 s |

Alt-text placeholders (exported with the recorded override): ART 17, book 4 308, art
therapy 0, book 2 1, Statistics 598, IAP MEC 38, Trichology 202.

¹ All are ids with a `_2` suffix: two printed chapters merged into one division (Stage 1 gives
8 of 14 and 10 of ~30 chapter headings), so "Table 1.2" and "Table 2.2" collide. Stage 1, R1.
² Same cause: the whole body is in a `front_other` section, so tables and figures get the
outside-chapter prefix (`ch0tbl1`, `ch0tbl1_2`). Stage 1, R3.
The first commit had one undeclared order exception in book 4: a preface title taken from
figure text. Figure text is now omitted by default, and the exception is gone.

"Omitted by profile" is text the Jaypee delivery does not carry, each with a reason:
- text inside figures (it stays in the image);
- cover;
- printed TOC;
- title page (represented by `bookinfo` from the book settings);
- repeated header rows of continued tables;
- titles repeated on continued table parts.

Furniture and suppressed text are not content. Declared moves (counted separately, never
silent):
- continuations joined across pages;
- captions attached to figures;
- copyright page placed in `bookinfo`;
- bibliography placed at the chapter end;
- title placed at the chapter start.

Run records: `experiments/out/adapter_a/runs.json`, `compare_*.json`, `run.log`.

## Comparison with the real delivery (ART 9789372025262)

| Element | Ours | Delivery | Label |
|---|---:|---:|---|
| part / chapter / partintro | 5 / 17 / 5 | 5 / 17 / 5 | equal (parts and chapters adapter-inferred from opener text) |
| page_info.xml | identical | | equal |
| anchor | 128 | 132 | equal for the PDF we have; the 4 missing are index pages (R14) |
| bibliography / bibliomixed | 17 / 136 | 17 / 132 | close; the 4 extra entries were not inspected |
| preface / dedication / authorgroup | 3 / 1 / 3 | 3 / 1 / 3 | equal (front titles: see R5) |
| section | 9 | 144 | **Stage 1** (R4): titles are `display_title` paragraphs |
| para | 2,035 | 1,720 | **Stage 1**: column interleaving splits paragraphs and lists (R8) |
| emphasis | 1,026 | 854 | **Stage 1**: bold section titles stay as bold paragraphs (R4) |
| ulink | 331 | 970 | **source/Stage 1**: about 600 are index links (no index in our PDF, R14); citation and "Fig./Table N" links are written |
| index / indexentry | 0 / 0 | 1 / 271 | **source**: the PDF ends at page 116 (R14) |
| sidebar | 17 | 5 | **Stage 1**: coloured tables come as callout boxes (R7) |
| informaltable | 15 | 0 | **Stage 1**: untitled tables (titles not linked, R7) |
| itemizedlist | 52 | 30 | **Stage 1**: interleaved column lines as unmarked lists (R8) |
| figure / informalfigure | 10 / 7 | 11 / 2 | **Stage 1**: p94 flowchart caption not linked (R6); p127 table is an image (R7); 3 front banners kept as images, their titles unused (R5) |
| caption (figure notes) | 0 | 4 | **Stage 1**: abbreviation notes are not figure credits/notes |
| legalnotice | 1 | 2 | **adapter**: the delivery puts "Printed in India" in a second legalnotice after `<isbn>`; not fixed (no rule says which lines go after the ISBN) |
| email | 0 | 4 | **Stage 1** (R12): no spans for e-mail addresses |
| para role alignright / aligncenter | 0 / 0 | 11 / 2 | **Stage 1** (R9) |
| emphasis role legalhead / copyrighthead | 0 | 5 | **schema** (cannot be expressed yet) |

Adapter differences fixed during this step, each found by this comparison:
- bold+italic nested (as delivered), not `bolditalic`;
- paragraph roles (noindent after a title, then indent; none in cells and list items);
- the title-page logo moved into `legalnotice` as `fm-1`;
- `continue_previous` for chapter 17's references, so `page_info` reads 112–116;
- table cell paras without a role;
- `f`/`t` index suffixes inside the link;
- object mentions followed by a superscript citation ("Table 1¹").

The delivery also has its own slips, which are not copied: `role="itlaic"`,
`anchor id="page_118"`, citations in ch2's tables linking to `ch3bib`, and the malformed
`ch8.xml`.

**Book 4** (9789366165769) is the same Jaypee DocBook 4.2 family, but in the **older house
style**: `ch01.xml` file names, `pageXXXI-1.jpg` image names, title role equal to the id,
`label="Table 1.1"`, figures without ids. These are what v3 items 16, 33 and 35 call wrong,
so we follow v3 and the file names differ by design. Its element comparison is in
`compare_medical_anatomy.json`. The biggest differences are Stage 1's: 9 chapters for 14,
`qandaentry` 34 vs 186 (question sets not detected as lists), and `sidebar` 236 vs 83.

## Our ch2.xml next to the delivered one (first 60 lines)

The full text is in `experiments/out/adapter_a/ch2_side_by_side.md`. Same skeleton:

- `<part id="prt2" label="SECTION 2">` with `<anchor id="page9" role="first"/>` in the title;
- `<partintro><sidebar><para><orderedlist numeration="arabic" continuation="restarts" role="…">`
  ending with `<anchor id="page10" role="last"/>`;
- `<chapter id="ch2" label="CHAPTER 2">` with `<anchor id="page11" role="first"/>`;
- `<table id="ch2tbl1" label="Table 1" frame="all">` with `title role="ch2tblt1"`, colspecs,
  `entry colname align valign`, and `&#x0027;`/`&#x03BC;` entities.

The differences are Stage 1's:
- "INTRODUCTION" is a bold `para` instead of `section ch2lev1sec1`.
- The opener list's first entry became the box title, so ours starts at role 3, not 2.
- Two-column lines are interleaved in the first paragraphs and table cells.
- Table 1 sits inside a callout sidebar.

## Design

```
backend/src/book_adapters/
  engine/   load (schema + manifest check), profile (+ store), settings (book settings
            + draft), outline (parts/chapters/sections/blocks), text (joins, tokens),
            ledger, packager (files, images), run
  writers/  base (Writer interface), docbook, serialize (characters, line breaks)
  rules/    characters, structure, links, writer_switches (18 named rules)
  validate/ dtd (pinned OASIS 4.2), house_rules (from the profile), lossless
  compare/  element counts, per chapter, files, labels, page_info
profiles/schema/{profile,book_settings}.schema.json, _base/docbook_base.yaml,
         jaypee/jaypee_v3.yaml, jaypee/examples/examples.yaml, _test/other_client.yaml
books/9789372025262.yaml
```

- **No client values in code.** The engine and writer contain no client values. A second
  profile (`_test/other_client.yaml`) gives the same book `chap1`, `c1_s1_1`,
  `media/img_p7_1.png`, `parts/chap1.xml` and no `page_info`; tested.
- **Profiles.** Profiles are validated against `profile.schema.json` (unknown fields are
  errors) and support `extends`. Errors give file, line, field and a suggestion, e.g.
  `client.yaml:6: ids.chaptr: unknown field … Did you mean 'chapter'?`. Regexes are
  compiled and id placeholders checked. Every field has a type, an enum where one applies,
  a default and a description, so the profile maker can write profiles.
- **Store.** There is no admin role. `book-adapters profiles list | validate | add`, and
  `run --profile FILE.yaml`, which stores the upload. Each upload is a new immutable
  revision (`name@version#rN`, written with exclusive create), marked "untested". The
  report warns about untested profiles and records the profile file, version, file hash,
  resolved hash and parent chain.
- **Book settings.** `books/<isbn>.yaml` is validated, including the ISBN check digit and the
  profile's `book_options`. `settings draft` pre-fills only printed values (ISBN with a
  valid check digit, edition, title) and lists the rest under `to_supply`.
- **Lossless check.** It works at three levels:
  1. Every token (Stage 1 rule, joins applied) is written exactly once as text, as a label
     attribute (`Fig. 1` → `label`), or as list structure, or it is omitted with a reason.
  2. Text outside declared moves is in book.json order.
  3. The XML read back from disk equals the ledger token for token. Alt-text slots are
     excluded.
- **Fallbacks.** Part and chapter starts from opener artwork or the printed TOC, and
  front-matter titles from banner text, run only when book.json has no heading of that
  kind. Each is a review entry of kind `adapter-inferred`. Tested both ways.
- **Inputs and isolation.**
  - Worktree `../pdf_book_converter_adapter`, branch `adapter-a`.
  - The Jaypee guideline, the delivery and the ART PDF were read from `~/Downloads` (not
    `external_references/jaypee/`, which does not exist) through new reference keys.
  - The Step 17b publications are not on this PC, so the Step 19 `before` set was copied
    once, read-only and manifest-verified (`experiments/out/adapter_a/README.md`).
  - Nothing in the main tree, `.cache/s19/`, `experiments/out/step19/`,
    `backend/src/book_core/` or the JSON Schema was changed.
  - No conversions were run, and not the backend suite: only the 53 adapter tests.
- **Dependencies.** A new `adapters` extra (PyYAML 6.0.3 MIT, Pillow 12.3.0 MIT-CMU).
  The DocBook DTD licence is recorded in `docs/dependencies.md`. No GPL/AGPL code.

## Guideline coverage (XML items)

| Item | Where |
|---|---|
| 1 DTD | `validate/dtd.py`, pinned OASIS 4.2 (the owner gave no DTD; the delivery names V4.2) |
| 2 float placement | Stage 1 reading order; floats between joined paragraph pieces follow the paragraph (declared) — **not expressible** |
| 3 no italic H3 | `inline.in_titles`, rule `no_italic_heading_level3` |
| 4 small caps | `inline.small_caps: from_source` |
| 5.1/5.2 labels | `labels.*`, figure kinds; sections never get a label (checked) |
| 6 coloured tables | tables stay tables; cell colour **not expressible** (no colour in book.json) |
| 7 list marks | `lists.marks` glyph map; unknown glyph → default + review |
| 8, 32 anchors | `anchors.titles`, `anchors.standalone: previous_para`; checked |
| 9, 10 en dash / minus | rules `index_range_en_dash`, `minus_sign_by_context` (unclear → review) |
| 11, 12 subchapters | `paragraphs.subchapter_role` exists; detection **needs Stage 1** |
| 13 continued figures | rule `continued_figure`, `ids.continued_figure` |
| 14–17 folders, page_info, file = id, bigimages | `delivery.*`, `images.big_include`; checked |
| 18–20 entities | `characters.escape`, `non_ascii: hex4`, rule `apostrophe_straight`; checked |
| 21 empty entries | `tables.empty_entry: self_close`; checked |
| 22 qandadiv | rule `qanda_sets` (book option `qanda`) |
| 23 colour plates | rule `color_plate_note_removal` (book option); image swap **not expressible** |
| 24, 33 image names | `images.name`, `images.front_name`; sequence checked |
| 25 set figures | one image per figure; part-letter labels go to review — **not expressible** |
| 26, 27, 29 sidebar/list/para | rules `sidebar_not_in_list`, `sidebar_children_in_para`, `nested_list_in_para`, `list_in_entry_in_para`; checked. Item 27's sidebar `label` conflicts with the DTD |
| 28 figure vs informalfigure | `figures.titled_unnumbered`, `untitled`, `small`; checked |
| 30 bibliography id | `ids.bibliography`; checked |
| 31 epigraph | rule `epigraph_as_paras` (needs a Stage 1 role) |
| 34, 35 ids/roles | `ids.*`, figure kinds (flowchart `chNflM`); checked |
| 36 index links | `index.link`, `index.suffix_in_link` |
| 37 Suggested Reading | rule `suggested_reading_as_chapter` (book option) |
| 38 no frame="none" | `tables.frame` enum excludes `none`; checked |
| 39 figure alone in table | rule `numbered_figure_alone_in_table` |

ePub items are out of scope (Adapter B / ePub later).

## Open points for review

1. **Banner titles vs wrong headings: decided, keep strict until Step 20.** ART's
   Foreword/Preface/Acknowledgments are titled with the signature names that Stage 1 types
   as `front_section_title`. Recorded as item 1 of the Step 20 list in
   `docs/adapter_requests.md`.
2. **Confirm with Jaypee:** image sizes, the alt-text placeholder and fail-on-placeholder
   rule, and text inside figures not emitted (see the summary).
3. **Sidebar label.** Item 27's `label` on `sidebar` cannot be DTD-valid in 4.2. Ask whether
   Jaypee's DTD differs from OASIS 4.2.
