# Adapter requests for Stage 1 (Step 20, Adapter B)

What the adapters need from `book.json` that it does not give today. Each request names the
book, a page (physical page index) or unit id, and why the adapter needs it. Unit ids refer
to the publications listed in `experiments/out/adapter_a/README.md`.

The adapter fills requests R1 and R2 with **adapter-inferred** fallbacks, and since
Adapter B also R17 (index locators) and the R12 web/e-mail links. Every inference is a review
entry of kind `adapter-inferred`. A part/chapter fallback runs only when book.json has no
heading of that kind, so it stops by itself once Stage 1 supplies the headings.

## Adapter B list (2026-11-03, measured on the Step 20 publications)

What the Adapter B compare with Jaypee's ART delivery and the 11-book gate traced to
book.json. The adapter now does its own part of each (noted); the rest needs Stage 1.
Pages are physical pages.

1. **R15 ART chapter starts.** Chapter 4 has no heading (p37, "Sperm Retrieval and
   Handling"), so chapters 3 and 4 merge: `ch3tbl1_2`, page_info 18–23 for 18–22, and every
   later per-chapter compare is shifted by one. On p89 the part opener's contents lines
   ("11. Culture Systems", "12. Cryopreservation", "13. Embryo Transfer") are `chapter`
   headings, so a one-page chapter "11. Culture Systems" appears and part 4 loses its
   partintro. The chapter 8 heading (p65) has no number. The adapter's opener fallback stays
   off when chapter headings exist (owner decision of Adapter A).
2. **R16 Paragraph continuations.** 64 pairs of our consecutive ART paragraphs are one
   paragraph in the delivery, and book.json has no continuation link between them (compare
   `paragraph_splits`; e.g. p30 "…standards such as ISO" / "14644 for cleanroom…" / "for
   laboratory calibration."). 9 pairs go the other way. This is most of the para +162.
3. **R17 Index locators and sub-entries.** Stage 1 gives no locators for entries whose last
   number has a suffix ("Achondroplasia  72, 73f"): book 4 181 of 1,312 entries, IAP 32. It
   merges several printed sub-entries into one item ("four quadrants of 227f, 227t\nnine
   regions of 226f…"): book 4 72, IAP 21, Trichology 3. *Adapter:* `index.infer_locators`
   reads them (each an `adapter-inferred` review entry); Stage 1 should give them.
4. **R18 Lists from bullet paragraphs; broken bullet glyphs.** Paragraphs that start with a
   bullet glyph are not lists: Dermatology 189, Cancer biology 91, Spanish 42, Statistics 11.
   Bullet markers from symbol fonts arrive as letters or control characters (`y`, `NJ`,
   `3⁄4`, `\x83`, `\x89`, `\x8c`) with no glyph name. *Adapter:* `lists.marks` maps the ones a
   delivery shows (`y` bullet, `NJ` and `\x89` square); the others get the default mark and
   a must-check entry.
5. **R19 Zones.** RSSDI Atlas: the case chapters (p22–64) are `front_other` in the front
   zone, so they become prefaces and their figures collide (`ch0fig1_2`: 74 house-rule
   findings). Statistics: Step 21 item 1 (466 findings).
6. **R20 Crops for adapter review entries.** The publication has crops only for Stage 1
   review items. An adapter entry about a unit Stage 1 did not review (an author split, an
   inferred index locator) has no crop in the review list. A page thumbnail per page, or a
   crop per unit on request, would cover them.
7. **R21 Line-end hyphen inside a web address.** "code-of-practice-annexes-\noctober-2021.pdf"
   (ART p130) has a `join` decision that drops the hyphen, so the address reads
   "annexesoctober". *Adapter:* a line end inside an address is joined (recorded); the
   dropped hyphen is Stage 1's decision.
8. **R22 Copyright page.** ART p4's two-column address block is interleaved in two
   paragraphs ("Headquarters … Corporate Office …"); the delivery has one para per printed
   line (39 vs 14). Copyright-page heads (`legalhead`, `copyrighthead`) need a role.
9. **R23 Table inside a box read as paragraphs.** ART p34 "TABLE 2: Troubleshooting guide for
   semen analysis…" is a callout box of 19 paragraphs, so it stays a sidebar of paras.
   *Adapter:* a box holding only a table is now the table (`sidebars.table_only`), which
   fixes the other 11 boxed tables of ART (sidebars 16 → 5, as delivered).
10. **R24 Floats out of their page.** RSSDI p65: a figure of page 65 comes after the page 66
    marker in reading order. *Adapter:* a unit belongs to the section of its place in the
    reading order (it had made a back-matter preface and pushed the body after it).

## Step 20 list

The owner decisions on the Adapter A gate (2026-10-30) and the requests, in priority order.

1. **R5 front-matter titles: signature names typed as headings.** In the ART Foreword,
   Preface and Acknowledgments, the signature names ("Ameet A Naik", "Chandan Vijay
   Salunke Shravani Kanakdas Parker") have role `front_section_title`. The real titles
   ("Foreword", "Preface", "Acknowledgments") are text inside banner figures. *Owner decision:
   the adapter's banner-title fallback stays strict (off when Stage 1 gives title headings)
   until Stage 1 fixes this.*
2. R1 part and chapter headings (with label word and number); R2 TOC entry links.
3. R3 zones and section kinds (Trichology articles, Statistics body).
4. R4 section headings instead of `display_title` paragraphs.
5. R6 caption linking, R7 tables (images, callout boxes, notes), R8 two-column order.
6. R9 alignment/epigraph roles, R10 decorative flag, R11 part numbers, R12 e-mail/URL spans,
   R13 index levels.
7. Alt text: Jaypee exports now fail while any figure/equation alt text is a placeholder
   (override recorded). Converted books need the alt-text workflow (drafts and review) to
   feed `alt_text`.

## R1. Part and chapter headings (role `part` / `chapter`), with label and number

**What:** a heading unit for every part and chapter opener, with role `part`/`chapter`. Also
the printed label word ("SECTION", "CHAPTER") and the number as structured fields, not loose
text.

**Why:** a DocBook delivery is organised by `<part>`/`<chapter>`, with `label="CHAPTER n"`,
ids, chapter files and `page_info.xml`. Without these headings, nothing structural is right.

**Examples:**
- ART 9789372025262: 0 part/chapter headings. The adapter found all 5 parts and 17
  chapters from opener artwork text (adapter-inferred; e.g. part p15 from figure
  `3012936fc6d6a5ff` text "Foundations of Troubleshooting in Assisted Reproductive
  Technology" + "SEC TION"; chapter p25 from figure text "2 / Quality Control … / C H A P T E
  R"). The opener text sits inside banner figures as `figure.text`.
- Book 4 (anatomy): 8 chapter headings for 14 printed chapters. Each heading's text is only
  the number (`70e0deb990dde9ff`, p74: "3"); the word "C H A P T E R" is a separate
  `heading_candidate` paragraph and the title another. Because headings exist, the adapter's
  fallback stays off (by design): 6 chapters are merged into neighbours, so ids collide
  (`ch1tbl2_2`) and chapter titles read "3".
- IAP MEC: 10 chapter headings for 67 level-1 TOC entries; `5018c4c30ce97721` (p25) is "1",
  with "C H A P T E R" as a body paragraph before it.
- Trichology: 34 chapter headings, but pages 77–264 are zoned `rear` (see R3).

## R2. Chapter titles when the opener is a picture

**What:** when a chapter opener is raster artwork (no text), link the chapter to its
printed TOC entry (`navigation.toc[].entry` is `null` today for ART), so the title can be
taken from the TOC.

**Why:** the title must not be invented. For a chapter start that only the TOC supports,
the adapter takes the title from the TOC contents entry with the same number
(adapter-inferred, review entry `outline.toc_title`). In the ART book every opener banner
carries native text, so this path was not needed (22 opener inferences, 0 TOC
inferences). It is covered by the outline code and the review list, ready for books whose
openers are pictures.

## R3. Front/body/rear zones and section kinds

**What:** `pages[].zone` and `navigation.sections[].kind` that follow the book's structure.

**Examples:**
- Trichology: 196 of 272 pages are `rear` (`rear_other`/`glossary` sections from p77). These
  are the yearbook's articles, which the adapter therefore writes as appendices.
- Statistics: pages 14–754 (the whole teaching body) are one `front_other` section in the
  `front` zone; the 32 chapter headings sit inside it. The adapter therefore writes 29
  prefaces, and their tables and figures get the outside-chapter id prefix (`ch0tbl1`,
  `ch0tbl1_2`…: 466 house-rule hits).
- ART: p129–130 (chapter 17's references) are a `bibliography` and a `rear_other` section.
  The Jaypee profile maps them to `continue_previous`, so they rejoin chapter 17 and
  `page_info` matches the delivery (112–116).

## R4. Section headings instead of styled title paragraphs

**What:** headings with levels for in-chapter titles now published as
`paragraph role=display_title`.

**Why:** Jaypee needs `<section id="chNlevXsecY">` with `<title role=…>` (items 34, 35).
ART has 146 `display_title` paragraphs and 27 headings; the delivery has 144 sections. The
adapter writes `display_title` as `<para role="noindent">` and does not promote it: deciding
headings is Stage 1's job.

## R5. Front-matter titles

**What:** front-matter titles (Foreword, Preface, Acknowledgments) as headings with role
`front_section_title`.

**Examples:** ART p7/p9/p11: the titles "Foreword", "Preface", "Acknowledgments" are text
inside banner figures (`c80e849717573f08` "Foreword"). Meanwhile the signatures
("Ameet A Naik", "Chandan Vijay Salunke Shravani Kanakdas Parker") are headings with role
`front_section_title`, and "Acknowledgments" is a level-2 `subsection`. Because the section
has Stage 1 title headings, the banner fallback stays off (by design; owner decision:
keep it strict until Step 20). The delivered
prefaces are therefore split at the signatures and titled with the names. The banner text
stays in book.json (figure text is not written as XML text by default). With an earlier,
ungated version of the fallback, the three titles came out right.

## R6. Captions linked to their figure; continued captions

**What:** every printed "Fig./Flowchart N:" caption in its figure's `captions`, whole (not
split across columns), without running text mixed in.

**Examples (ART):**
- p19 figure `5fe445d0b87493b2`: its caption mixes "Flowchart 1: Troubleshooting workflow:
  Root cause" with body text.
- p17 "Fig. 1:" is split into two `caption` units, one of them interleaved with the other
  column.
- The p94 flowchart has no linked caption, so `bigimages/94-1.jpg` is missing compared with
  the delivery.

The adapter attaches a following `caption` unit that starts with a figure label (declared
move) and nothing more.

## R7. Tables detected as tables (not images, not callout boxes)

**Examples (ART):**
- p127 "TABLE 2: Gamete donation and anonymity" is a figure; the delivery has a table.
- 13 coloured table backgrounds are `box callout` around the table, so the adapter writes a
  sidebar holding the table. The delivery has 5 sidebars; ours has 17.
- Table abbreviation notes ("(HVAC: …)") are not `notes` (delivery: 47
  `para role="small"` rows; ours 7).

## R8. Two-column reading order inside paragraphs and table cells

**Example:** ART p18 paragraph "regulations like the ART Act (India, 2021), have
\ncontamination, or residual detergent…": lines of two columns are interleaved, and so are
cell lines in table 1 (p26). This is visible in `ch2.xml`.

## R9. Paragraph alignment and epigraphs

**What:** alignment (`right`/`center`) for signature lines and centred notes, and roles
`epigraph`/`attribution` for epigraphs.

**Why:** Jaypee codes them as `para role="alignright"` / `aligncenter` (ART delivery: 11
and 2) and item 31 epigraph paras. The adapter rule `epigraph_as_paras` is ready but has no
input.

## R10. Decorative artwork flag

**What:** a flag for decorative images (rules, banners, ornaments).

**Why:** today the adapter can only drop caption-less, text-less artwork at the top of a
part/chapter opener page.

## R11. Part numbers

**Example:** ART p15's big "1" next to "SEC TION" is published as a `folio` furniture record,
not as part of the opener. The adapter numbers parts in order (label "SECTION 1"); the
printed number is lost from the opener.

## R12. Inline e-mail and URLs; copyright-page heads

**What:** link spans for e-mail addresses and URLs printed without a PDF link annotation.
Optionally, a role for copyright-page heads.

**Why:** the ART delivery has 4 `<email>` and legal `emphasis role="legalhead"`. The schema
can map spans, but these are not spans in book.json.

## R13. Index entry levels

**Example:** book 4 index: a level-3 entry follows a level-1 entry with no level-2 entry
between them. DocBook does not allow this, so the adapter writes it as level 2 and adds a
review entry.

## R14. Index in the ART PDF

The ART source PDF (130 pages) ends at printed page 116. The delivery's index (pages
117–120, 271 entries) is not in the PDF we have, so nothing can be compared. This needs the
full PDF, not a Stage 1 change.
