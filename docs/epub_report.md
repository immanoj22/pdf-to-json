# ePub 3 adapter: Jaypee ePub from the same book

Status: complete for review (one commit). No Docker, no converter (Stage 1) change, no book converted.

## Summary

- **What it does.** The adapter engine has a second writer, `book_adapters/writers/epub3.py`. It
  reuses the outline, ids and numbering, characters pass, links, the review-decisions overlay and
  the emission ledger of the DocBook writer, and writes `<ISBN>.epub` (ePub 3). A new profile,
  `jaypee_v4`, extends v3 (DocBook output byte-identical, tested) and adds an `epub` section.
- **Result on the 11 books:** our checks 0 findings, **EPUBCheck 5.4.0 0 errors / 0 warnings**,
  **lossless 0 missing / 0 extra**, every `.epub` **byte-identical on a second run**. QC verdict is
  `warn` on all 11 (alt-text override, must-check items such as the missing cover image).
- **App.** Export has a format choice (DocBook / ePub / both), an optional cover-image upload, the
  ePub QC (pass / warn / fail), downloads of the `.epub` and its QC report; the Books page shows
  both verdicts. User guide updated.
- **What is missing from Jaypee (so a "confirm with Jaypee" list exists).** The folder
  `external_references/jaypee/epub/` was **not there**: no Jaypee Global CSS and no finished Jaypee
  ePub. So the stylesheet follows the PDF's design, the folder and file names follow common
  practice, and **no sample comparison could be made**. Please send the CSS and 1-2 finished ePubs
  (ideally the ART book's); the compare step will then be added.
- **Java.** Java 22 was already on the machine; nothing was installed. EPUBCheck (BSD) was
  downloaded as a jar into `.cache/tools/` (git-ignored). Where Java or the jar is missing the QC
  says "EPUBCheck not run" and the verdict is `warn`.

## Results on the 11 publications

| Book | Pages (XHTML in spine) | Images | Contents entries | Page list | Internal links | Lossless missing/extra | EPUBCheck err/warn | Verdict |
|---|---:|---:|---:|---:|---:|---|---|---|
| art_lab | 30 | 15 | 164 | 128 | 959 | 0/0 | 0/0 | warn |
| immigrant_children | 25 | 1 | 186 | 329 | 3853 | 0/0 | 0/0 | warn |
| statistics | 47 | 631 | 821 | 869 | 5860 | 0/0 | 0/0 | warn |
| trichology | 144 | 189 | 495 | 270 | 2644 | 0/0 | 0/0 | warn |
| iap_mec | 25 | 38 | 383 | 328 | 3323 | 0/0 | 0/0 | warn |
| art_therapy_index | 4 | 0 | 1 | 9 | 17 | 0/0 | 0/0 | warn |
| dermatology | 27 | 163 | 196 | 290 | 2268 | 0/0 | 0/0 | warn |
| cancer_biology | 24 | 443 | 396 | 271 | 4334 | 0/0 | 0/0 | warn |
| rssdi_atlas | 31 | 156 | 344 | 216 | 3923 | 0/0 | 0/0 | warn |
| medical_anatomy | 28 | 299 | 152 | 313 | 2631 | 0/0 | 0/0 | warn |
| spanish_us_history | 154 | 488 | 394 | 757 | 8728 | 0/0 | 0/0 | warn |

Second run: every `.epub` byte-identical (`dcterms:modified` is passed in; the default is the
profile's date). Reports: `.cache/epub/<run>/<book>/report/`.

## Jaypee ePub rules

| Item | How it is done | Checked by |
|---|---|---|
| 1 Front cover only | One cover page and one `cover-image` from the book settings / app upload. No inside or back cover is ever written. The PDF has no cover; without an image there is no cover page and a **must-check** item. | `cover` check |
| 2 Link colour | CSS `a { color: #231F20 }`: the PDF sets links in body text colour, never blue. | `link_colour` check (no blue, no inline colour) |
| 3 Half title | `halftitle.xhtml`, `<title>` and heading "Half Title Page"; landmark label the same. | `half_title` check |
| 4 guide | `<guide>` in `package.opf` plus ePub 3 landmarks in `nav.xhtml`. | `guide`, `navigation` checks |
| 5 Two-way TOC | Each listed heading wraps its text in a link back to its contents entry in `toc.xhtml` (or the `#TOC` container with `toc_return: container`). | `toc_two_way` check |

ePub 3: `mimetype` first and stored, `container.xml`, `package.opf` (ISBN identifier, title,
authors, publisher, language, `dcterms:modified`), `nav.xhtml` (contents, page list from page
anchors, landmarks), one XHTML per division, images, CSS; headings h1-h6; figures with `alt`
and `figcaption`; tables with `caption` / `thead` / `th`; lists; boxes as `aside`; footnotes as
`epub:type="footnote"`; page breaks as `span epub:type="pagebreak"` with the printed label;
index with links; MathML with `alttext` when Stage 1 gives MathML (unit-tested path; none of the 11
books has any); `lang` attributes. Accessibility metadata (accessMode, accessModeSufficient,
accessibilityFeature, accessibilityHazard, accessibilitySummary) from what the book contains
(`alternativeText` is not claimed while placeholders remain).

## Confirm with Jaypee

Listed in every ePub QC report (profile `confirm_with_client`): the CSS (sizes, weights, colours
taken from the ART PDF; H3 italic), link colour, folder and file names (`OEBPS/Text`, `Images`,
`Styles`, `package.opf`, `nav.xhtml`, `toc.xhtml`), cover source, the half title page being
generated from the book title, return link to the entry vs the `#TOC` container, the legacy
`<guide>`, accessibility hazard `none` and no conformance claim, `dc:publisher`.

## Sample comparison

Not made: no sample ePub and no Jaypee CSS were provided. Nothing is claimed about differences
from Jaypee's real files. Once provided, a compare (file counts, nav entries, page list, element
counts, CSS classes, labelled adapter / Stage 1) can be added.

## Limits

- One XHTML per division (chapter, part, front and back section), not per section.
- Footnote markers are not linked to their notes: Stage 1 does not decide the pairing.
- Per-span languages other than the book's are not marked; the paragraph's language is, when it
  differs from the book's.
- Text inside figures stays in the image (profile choice, as in DocBook).
- DocBook-driven choices (for example moving a bibliography to the chapter end) also
  shape the ePub order; they are declared moves in the lossless report.

## Tests

`backend/tests_adapters/test_epub.py` (21): own checks and lossless, package layout, cover rule,
link colour, half title, guide and landmarks, two-way TOC links (entry and container), page list,
content elements, accessibility metadata, alt-text block and override, determinism, lossless
detects loss, DocBook byte-identical v3 vs v4, schema extension (v3, generated, base and other
profiles still valid; an `epub` typo is rejected with a suggestion), profile without `epub`,
EPUBCheck "not run". App API (`test_api.py`): format choice, blocked / override, both formats,
downloads, cover upload. Browser test (cached ART publication) extended with the ePub export.
