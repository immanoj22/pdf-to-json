# Adapter B — close the gaps with Jaypee's delivery, QC report, profile maker

Status: **complete for review.** One commit on `adapter-b`; not merged. No ePub, no frontend,
no Stage 1 (`book_core`) or JSON Schema change. No book was converted.

## Summary

**What changed.** The Jaypee adapter now closes every gap with the ART delivery that the
adapter can close, reports the rest by cause, and a new client profile can be made from a
guideline and a few finished deliveries.

- **Index.** Entries, letter divisions, page links (`f`/`t` inside the link, each end of a
  range linked, en dashes) and `index.xml` are written. ART's PDF has no index, so ART's
  271 entries cannot appear (request R14); the index was measured on the books that have one
  (book 4, IAP, Trichology, Dermatology, cancer biology, RSSDI, Spanish, Statistics).
  Where the converter gave an entry no locator, the adapter reads the page numbers and
  splits merged sub-entries; each is a review entry.
- **Links.** Printed web addresses and e-mail addresses are linked as the delivery does
  (ART: web 0 → 9, e-mail 0 → 5; Jaypee 9 and 4+1). A line end inside an address is not a
  space. "Tables 1 and 2" links each number.
- **Sidebars.** ART 16 → 5 (Jaypee 5): a coloured box that holds only a table is the table.
- **Paragraphs.** ART 1,893 → 1,879 (Jaypee 1,720). The rest is the converter's: 64 pairs
  of our paragraphs are one paragraph in the delivery and book.json has no continuation link.
- **House-rule findings** (Step 20 → now): Spanish 22 → 0, cancer biology 19 → 0, RSSDI
  421 → 74 (and DTD errors 53 → 0), ART 1, book 4 12, IAP 30, Statistics 466. The
  remaining ones are all one cause: the converter merges chapters or puts the body in the
  front zone, so one printed "Table 1" occurs twice in a "chapter" (R15, R19).
- **Characters** (Jaypee profile): soft hyphens removed, broken bullet glyphs mapped,
  apostrophes and minus signs, a line end inside an address joined. Every changed character
  is recorded in the emission ledger; the lossless check re-derives each written text from
  its source plus those records (0 unexplained on all 11 books).
- **Authors** in `bookinfo` are read from the title page (`firstname`, `surname`,
  `othername role="degrees"`, affiliation, address). ART's come out equal to Jaypee's. An
  unclear split is **must check**.
- **QC report** (`qc_report.html/json`) and **review list** (`review_list.html/json`) per
  delivery; **compare** and **profile test** as commands; **profile maker** instructions.

**Gates (11 books: the 8 Step 20 publications + Dermatology, cancer biology, RSSDI Atlas):**
DTD errors 0 on all; lossless missing/extra 0/0 on all; 0 text pieces out of order on all
(Spanish was 4,139, RSSDI 65, cancer biology 23); two full runs byte-identical on all 11
(deliveries and reports, `run.json` aside); 70 adapter tests pass (was 53); Ruff check and
format clean. QC verdict is `warn` on all 11 (alt-text override, must-check items, the
house findings above); none `fail`.

## ART before → after (compare with Jaypee's delivery)

Before = Adapter B's starting point (main at 7d6d8c6a, Step 20 publication). After = final run.
Source of each remaining difference: *S1* Stage 1 (book.json), *src* the PDF.

| Element | Before | After | Jaypee | Remaining difference |
|---|---:|---:|---:|---|
| part / chapter | 5 / 17 | 5 / 17 | 5 / 17 | equal |
| partintro | 4 | 4 | 5 | S1 (R15: part 4's opener) |
| section | 139 | 139 | 144 | S1 (R15) |
| para | 1,893 | 1,879 | 1,720 | S1 (R16: 64 splits, R22 copyright page) |
| emphasis | 883 | 883 | 854 | S1 (styles from spans) |
| listitem / itemizedlist | 146 / 46 | 146 / 46 | 125 / 30 | S1 (R18: lists read from columns) |
| orderedlist | 6 | 6 | 6 | equal |
| figure / informalfigure | 10 / 5 | 10 / 5 | 11 / 2 | S1 (captions not linked) |
| **sidebar** | **16** | **5** | 5 | **equal** (adapter) |
| table / informaltable | 65 / 15 | 65 / 15 | 67 / 0 | S1 (untitled tables; merged chapters) |
| entry | 1,369 | 1,369 | 1,349 | S1 |
| index / indexentry | 0 / 0 | 0 / 0 | 1 / 271 | src (R14: the PDF ends at page 116) |
| **ulink** | **333** | **343** | 970 | 619 index links = src; web links equal (9 = 9) |
| **email** | **0** | **5** | 4 (+1 mailto) | **equal** (adapter) |
| anchor | 128 | 128 | 132 | src (4 are index pages) |
| bibliomixed | 136 | 136 | 132 | S1 |
| legalnotice | 1 | 1 | 2 | adapter: no rule says which lines follow the ISBN |
| **preface** | **6** | **3** | 3 | **equal** (adapter); front anchors equal |
| page_info.xml | differs | differs | | S1 (R15: chapters 3–4 merged) |

Links by kind (ours / Jaypee): citation 262 / 266, object mentions 71 → 72 / 75, web 9 / 9, e-mail 5 / 5, index page links 0 / 619.
Full table with labels: `experiments/out/adapter_b/final/compare_art_lab.json` and
`.cache/adapter_b/final/art_lab/` (run `book-adapters compare … --book …` for the HTML).

## Per-book before → after (Step 20 → Adapter B)

| Book | Index entries / sub-entries | Index page links | Web / e-mail links | Sidebars | Soft hyphens left | House findings | Out of order |
|---|---|---|---|---|---|---|---|
| Spanish | — / 8 → 9 | 6,170 → 6,783 | 0 → 4 / 0 | 462 → 457 | 1 → 0 | 22 → 0 | 4,139 → 0 |
| Book 2 | — | 2,779 → 2,876 | 0 → 32 / 0 → 1 | same | 0 | 0 | 0 |
| Art therapy | 616 → 660 / 194 → 235 | — | — | 1 → 0 | 0 | 0 | 0 |
| Book 4 | 944 → 943 / 353 → 439 | 1,240 → 1,683 | 0 → 2 / 0 → 5 | same | 52 → 0 | 12 | 0 |
| Statistics | — | — | 289 → 287 | 5 → 3 | 0 | 466 | 0 |
| ART | — | — | 0 → 9 / 0 → 5 | 16 → 5 | 9 → 0 | 1 | 0 |
| IAP MEC | 510 → 509 / 346 → 361 | 939 → 1,014 | 0 → 66 / 0 → 5 | 22 → 13 | 10 → 0 | 30 | 0 |
| Trichology | — | 866 → 883 | 0 → 2 / 0 → 5 | same | 7 → 0 | 0 | 0 |
| Dermatology* | 576 → 575 / 274 → 330 | 731 → 1,069 | 0 → 4 / 0 → 5 | 10 → 9 | 9 → 0 | 23 | 0 |
| Cancer biology* | 792 → 791 / 347 → 358 | 2,446 → 2,824 | 0 → 34 | 86 → 93 | 52 → 0 | 19 → 0 | 23 → 0 |
| RSSDI Atlas* | — / 176 → 194 | 812 → 1,007 | 0 → 19 / 0 → 5 | 27 → 24 | 13 → 0 | 421 → 74 | 65 → 0 |

\* frontend outputs of 3 November 2026; "before" is the unchanged adapter run once on them
(`experiments/out/adapter_b/before/`). The e-mail counts of 5 are the publisher's own
address block on the copyright page. One entry fewer in book 4, IAP, Dermatology and cancer
biology is the index note, now a para before the first letter (as delivered); the added
sub-entries are merged printed lines the adapter now splits (`index.split_lines`).
Per-book numbers: `experiments/out/adapter_b/final/metrics.json`.

## 1. The six gaps

1. **Index.** Writer unchanged in structure; new: range locators linked at both ends
   (`index.range_links`), locators and sub-entries the converter missed
   (`index.infer_locators`, every one an `adapter-inferred` review entry), the index note as
   `para role="aligncenter"`, a second index (art therapy "Author Index") as its own group,
   an index that Stage 1 splits over two zones stays one, link/emphasis nesting
   (`73<emphasis>f</emphasis>` inside the link), letter divisions keep each group's own text.
   Book 4: 181 entries had no locator; 268 locator readings and 70 line splits are reviewed.
2. **Links.** Rule `link_urls_emails` (web `http://` added for `www.`, `<email>` for
   addresses; profile `links.*`); "Tables 1 and 2". ART counts above. Citation links
   (266 vs 262) and object mentions depend on the converter's chapter and superscript spans.
3. **Sidebars and paragraphs.** Sidebars: adapter (11 boxed tables), fixed. Paragraphs:
   64 Stage 1 splits (compare: `paragraph_splits`; every one has no continuation link),
   copyright page (R22). The page 34 "TABLE 2" box is 19 paragraphs (R23).
4. **House-rule findings.** Grouped above. The adapter's own violations were: a section kind
   (`other_list`) missing from the profile, a part without chapters written as a `part`,
   chapter numbers off after such a part, back-matter pages placed before later body pages
   (RSSDI, Spanish), ids repeated across front-matter divisions. The rest is Stage 1's.
5. **Character output.** `soft_hyphen_removal` (inline only; line-end ones are Stage 1 join
   decisions), broken bullet glyphs in `lists.marks` (`y` bullet, `NJ` and U+0089 square, from
   the ART and book 4 deliveries; any other letter/digit/control glyph is a **must check**
   with the default mark). Entities per items 18–20 were already written. Changes by rule,
   ART: apostrophes 43, soft hyphens 9, address line ends 7, minus 1.
6. **Authors.** `engine/authors.py`, profile `authors.*` (role labels, degree token, known
   degrees, job / organisation / department words). No font or position is used. Tested on
   7 title pages: ART exact. IAP, RSSDI, Dermatology and Trichology are right for the clear
   people and produce must-check entries for the rest (a degree not in the list such as
   "PT" or "PG diploma…", two organisation lines, a line after the address).
   Book settings `authorgroups` always win.

## 2. QC report, review list, compare

- `qc_report.json/html`: verdict (fail: not written, DTD errors, text lost or added,
  unexplained character change; warn: house findings, order exceptions, override, untested
  profile, settings to supply, must-check items), house rules by rule with the guideline
  item, lossless, character changes by rule, element counts, profile name/version/hash,
  overrides, `confirm_with_client` settings (9 for Jaypee), review counts.
- `review_list.json/html`: adapter entries + Stage 1 review items, must check first, page
  (and printed label), reason, crop (copied to `review_crops/`; the Stage 1 crop of the
  unit, else the figure image). ART: 268 items, 15 must check, 267 with a crop. Adapter
  entries about units Stage 1 did not review have no crop (R20).
- `compare OURS REF [--book B] [--out F]` → counts table + biggest differences labelled
  adapter / Stage 1 / source / check, as JSON and HTML; links by kind, boxes, paragraph
  splits, well-formedness. A reference file that is not well-formed (ART `ch8.xml`) is
  reported and read with a recovering parser.

## 3. Profile maker

Local procedure, no API: `tools/profile_maker/prompt.md` (+ `examples.template.yaml`).
`book-adapters profile test FILE.yaml --examples EX.yaml` exports the example books'
existing publications and compares them with the deliveries; it separates differences a
**profile** fixes, ones a **person** decides, accepted ones (with a reason in the examples
file) and **Stage 1 / source** ones. Exit 0 = nothing left.

**Proof: `jaypee_generated.yaml`** was written from the guideline alone (no delivery read),
schema fields only, each value cited to an item or marked guess, plus a "needs a new rule"
list (items 2, 6, 7 partly, 11, 12, 23, 25, 31).

| Profile | `profile test` on ART | Result |
|---|---|---|
| `jaypee_v3` (hand-written) | fix 0, check 0, accepted 10, Stage 1/source 45 | exit 0 |
| `jaypee_generated` (guideline only) | fix 2, check 4, accepted 9, Stage 1/source 47 | exit 1 |

The generated profile exports DTD-valid with lossless 0/0 (after one adapter fix: a
book-level `bibliography` that holds text is an appendix). Its 6 open differences are exactly
what the guideline does not say: the folder name `bigimages` (guideline says "big_images"),
`para role` for captions / `indent` / `small`, and `<ulink>` / `<email>` (link rules are a
delivery convention). 51 fields differ from `jaypee_v3` (`generated_vs_v3.json`):

| Group | Fields | Why they differ |
|---|---|---|
| Values only a delivery shows | `images.max_width` 500, `delivery.zip`, `main_doctype: commented`, `part_files`, `labels.part/chapter` ("SECTION n", "CHAPTER n"), `paragraphs.roles.*` (noindent/indent/small), `paragraphs.first_after_title_role`, `outline.part_intro_wrapper: sidebar`, `inline.bold_italic: nested`, `inline.in_titles`, `anchors.titles` (preface…), `figures.decorative: omit`, `alt_text_placeholder` | the guideline is silent; v3 copies the delivery |
| Link and character rules | `rules` (+ `link_citations`, `link_object_mentions`, `link_urls_emails`, `soft_hyphen_removal`), `links.email`, `characters.escape."` | delivery conventions; item 19 says quotes are entities, the generated one stops at what the items list |
| Index | `index.range_links`, `infer_locators`, `suffix_in_link` (`fc`), `paragraphs.roles.index_note` | item 36 gives only `f`/`t`; the rest is the delivery |
| Zones and authors | `front_matter.sections.*` (`continue_previous`, `other_list`, `dedication.default_title`), `outline.part_label_words`, `authors.*` (v3 only) | delivery layout; the author word lists come from reading title pages |
| Guideline vs delivery | `delivery.bigimages_folder`, `figures.*` | guideline text vs delivery (`bigimages`); the guideline says `big_images` |
| Opposite choice | `double_quotes_curly` (generated only) | item 19 asks for U+201C/U+201D; v3 leaves quotes as extracted |

Conclusion: the guideline gives the structure rules (ids, labels, roles, entities, lists,
tables, figures: most of them identical); a delivery gives layout and style. A real client
profile therefore needs the 2–3 deliveries, as planned.

## Profile change

`jaypee_v3` is now **3.1.0** (2026-11-03): new fields `sidebars.table_only`, `index.*`,
`authors.*`, `links.*`, `confirm_with_client`, `other_list` mapping, `index_note` role, three
bullet-glyph marks, rules `soft_hyphen_removal`, `link_urls_emails`. Schema: 7 new field
groups, all with defaults, so older profiles still validate.

## Skips and limits

- **ART index** cannot be written (not in the PDF). The index code is tested on synthetic
  data and measured on 8 books, not against Jaypee's `index.xml`; its details (e.g. `tertiaryie`
  with no secondary) follow the delivery's note only.
- **Stage 1 requests** R15–R24 in `docs/adapter_requests.md`. Not fixed here: merged chapters,
  paragraph continuations, bullet-paragraph lists, zones, crops for adapter entries.
- **Authors** are read from one title page; real titles with unusual layouts will land in
  must check. Alt text is still a placeholder everywhere (override recorded).
- **Not done:** `legalnotice` after the ISBN, copyright-page heads, float placement (item 2),
  cell colours (item 6), set-figure labels (item 25), subchapters and epigraphs (items 11, 12,
  31, no converter role). No unit test for the `bibliography`-as-appendix path beyond the
  generated-profile run.
- The science book, sealed books and hold-outs were not read or run.

## Evidence

| What | Where |
|---|---|
| Run records, hashes, determinism | `experiments/out/adapter_b/{before,final,final_rerun}/` |
| Before → after per book | `experiments/out/adapter_b/final/metrics.json` |
| ART compare | `experiments/out/adapter_b/final/compare_art_lab.json` |
| Profile maker proof | `experiments/out/adapter_b/profile_maker/` |
| Tools | `experiments/adapter_b_{run,metrics,profile_diff}.py` |
| Tests | `backend/tests_adapters/test_adapter_b.py` (16) + 1 changed, 1 extended |
