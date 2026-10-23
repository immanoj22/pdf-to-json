# The book JSON (schema `universal-book` 1.0.0)

This is the output of Stage 1: one JSON document per book that adapters (DTBook/NIMAS,
EPUB, DAISY, HTML, JATS) read without knowing how the converter works. This page explains
the document in plain words. The exact contract is the JSON Schema
[`book.schema.json`](../backend/src/book_core/assembly/book.schema.json) (Draft 2020-12),
generated from the Pydantic model in
[`assembly/schema.py`](../backend/src/book_core/assembly/schema.py). Every published file is
validated against it.

## Promises

- **Nothing is lost in the default complete profile.** Every word of the PDF is in exactly one of three places: a unit of
  `content`, a `furniture` record (running heads, page numbers), or a `suppressed` record
  that says why it is not content (hidden text, text outside the printed page).
- **Nothing is invented.** A unit's `text` is the source text exactly as the PDF holds it
  (Unicode NFKC). It is never corrected or rewritten. Decisions (where a hyphen is
  removed, which words are bold, what is a list marker) are recorded beside the text.
- **Every uncertain item is flagged.** Each unit has a `review_status` (`ok`,
  `needs_review`, `must_check`) and `flags` (reasons). `review` lists them all.
- **Stable and deterministic.** Ids are 16 hexadecimal characters derived from the source;
  the same PDF, settings and run date give the same bytes. `metadata.content_sha256` is the hash
  of everything except `metadata.run` (the run date) and the hash itself.

## Files

A book is published as a folder:

| File | What |
|---|---|
| `book.json` | The document (UTF-8, keys sorted, compact). |
| `images/` | Figure images (named by the client profile) and equation image fallbacks. |
| `review/` | Crop images of review items (per the client profile; by default every item). |
| `manifest.json` | Every file with its SHA-256, the schema version, the content hash and the run date. |

## Top level

| Key | What |
|---|---|
| `schema` | `{"name": "universal-book", "version": "1.0.0"}`. A minor version adds optional fields; a major version changes or removes fields. |
| `metadata` | Title (the book-title heading, if found), content languages with their share of letters, source PDF hash and page count, converter name, version and code digest, client profile id/version/hash, settings hash, content hash, run date. |
| `pages` | One entry per physical page: index, printed label and its source (`printed`, `metadata`, `inferred`, `none`), size in points, rotation, `source` (`native`, `ocr`, `mixed`), zone (`front`, `body`, `rear`), section, review status. |
| `content` | The book in reading order: a list of units (below). |
| `furniture` | Running heads and feet, folios, production marks: kept, never in `content`. |
| `navigation` | `toc` (the printed table of contents, entries resolved to pages and units), `outline` (headings with level and parent), `sections` (front, body and rear sections), `page_list` (page markers). |
| `suppressed` | Text that is not content, with its reason (below). |
| `review` | Every item a person should look at, sorted (below). |
| `styles` | The fonts of the book and what they were learned to be (bold, italic, small caps) with the evidence. |
| `assets` | Every image file with its kind, SHA-256 and the unit that uses it. |

`furniture`, `navigation`, `suppressed`, `review` and `styles` can be left out by the client
profile (`output.sections`); then they are `null`.
The default profile keeps all these sections. The lossless gate applies to that complete
publication; a client that omits furniture or suppression records cannot reconstruct the
whole source ledger from its reduced JSON alone.

## Units

Every unit has:

| Field | What |
|---|---|
| `id` | Stable id (16 hex characters). |
| `type` | The kind of unit (below). |
| `pages`, `boxes` | The physical page(s) and the rectangle(s) on them (PDF points, origin top left). |
| `order` | Position in the book's reading order (depth first through the tree). |
| `source` | `native` (PDF text) or `ocr` (read from a scan). |
| `confidence` | The deciding stage's confidence (a rule score, not a probability). |
| `review_status`, `flags` | `ok`, `needs_review` or `must_check`, and the reasons. |
| `continues_from`, `continues_to` | The previous or next piece of the same paragraph, item, entry, list or table across a page or column break (below). |
| `provenance` | The stages that produced the unit and a short reason. |
| `refs` | Where the text comes from: layout line ids and, for parts of lines, span ranges. |

### Types

| `type` | What | Notes |
|---|---|---|
| `page_marker` | The start of a physical page | `page`, printed `label`, `label_source`. Every page starts with one. |
| `paragraph` | Running text | `role`: `body`, `display_title` (a styled title that is not a heading), `label`, `credit`, `figure_text` (text of a figure region not linked to a figure), `table_text`, `heading_candidate`, `list_item_candidate`. |
| `heading` | A heading | `level` (1 = outermost), `role` (`chapter`, `section`, `sidebar_title`, ...), `level_method`, `section`. |
| `list` | One run of a list on a page (a *segment*) | `list_id` (shared by all segments of the list), `segment`, `list_type` (`bulleted`, `numbered`, `lettered`, `unmarked`, `definition`, `glossary`, `index`, `bibliography`, `contents`), `marker_type`, `start`, `level`, `items`. Segments of one list are linked with `continues_from`/`continues_to`. |
| `list_item`, `index_entry`, `glossary_entry`, `definition_entry`, `bibliography_entry`, `contents_entry` | An item or entry | `marker` (`text`, `type`, `value`, `punctuation`): the printed marker as structure, not part of `text`; `term` (offsets of a defined term), `locators` (index page references with offsets and resolved target pages), `names` (parsed personal names, only when the profile asks), `children` (nested lists that follow the item). |
| `table` | A table | `rows`, `columns`, `header_rows`, `row_header_columns`, `rotation`, `title`, `notes`, `cells`. Each cell: `row`, `column`, spans, `role` (`column_header`, `row_header`, `section`, `data`), `headers` (ids of the cells labelling it), `box`, `content` (units, or `text` fragments for text that is not a whole unit). A continued table carries `continuation.repeated_header_rows` (leading rows that repeat the first part's header; keep them out of a joined table) and `column_map`. |
| `figure` | A figure | `kind` (`photo`, `drawing`), `image` (file, format, size, dpi, SHA-256), `name`, printed `label`, `small` (icons, bullets: an adapter may skip them), `captions`, `credits`, `text` (text inside the figure), `alt_text` (empty, `needs_review`, unless a person supplies it), `spread_with`, `equations` drawn inside it. |
| `equation` | A display equation | `presentation`, `mathml`, `latex`, `output` (what to render: `mathml`, `mathml_parts`, `image`, `text`), `parts`, `image` (fallback) and `alt_text` (always present with an image fallback; prefilled with the LaTeX by default, still `needs_review`). |
| `box` | A sidebar, coloured callout box or card | `box_kind`, `children` (its own units in order). |
| `footnote` | A note set apart from the text (footnote area) | The marker in the text is a `superscript` span; the link between them is not decided (flagged). |
| `caption` | A caption not linked to a figure or table | Flagged for review. |
| `index_divider` | A letter heading inside an index or glossary ("A", "B"...) | Neither a heading nor an entry. |

Floats (boxes, figures, tables, equations, footnotes, credits) appear in `content` where they
are read: after the unit holding their anchor. Figures, tables and equations anchored inside a
box are inside it; a figure or equation a table cell holds is in that cell.

Items and entries also carry their original `level` (or `null` when unknown). This can
differ from the enclosing list's level: a flat index list can contain entries at several
depths. Consumers should use the entry's own level for index indentation and retain the
printed `item_role`; the list's level describes the list segment itself.

## Text

Text-bearing units have `content`:

| Field | What |
|---|---|
| `text` | The exact source text (NFKC). `"\n"` marks the end of a source line. Read a `"\n"` as a space unless a `joins` entry says otherwise. |
| `raw` | The text before NFKC normalization, only when it differs (ligatures, compatibility characters). |
| `joins` | Decisions at line ends: `at` (offset of the `"\n"`), `decision`: `join` or `soft_join` (a break hyphen: drop the hyphen at `hyphen_at` and the line end), `keep` (a real hyphen: keep it, drop the line end), `word` (a word split without a hyphen: drop the line end). |
| `spans` | Inline meaning over `text[start:end]` (below). |
| `source_runs` | References to slices of this text on source lines split by hidden-text suppression. Each records `page`, `line`, `span`, extraction `position`, `source_start`, and local `start`/`end` offsets. Group by source page and line and sort by position and source offset to reconstruct the ledger's original token boundaries. This does not restore hidden characters to rendered content. |
| `language`, `script`, `direction` | Set when the unit differs from the book (BCP 47 language), and the script and direction of its characters (`ltr`, `rtl`, `ttb`). |

Inline spans (`spans[].kind`): `italic`, `bold`, `bold_italic`, `superscript`, `subscript`,
`small_caps` (from font names), `underline` (only where a rule is drawn under the text), `link`
(`href` for an external link, `target` `{page, unit}` for an internal one), `language`
(`language`; only when the profile turns language spans on, always `needs_review`), `math` (an inline equation: `equation`, `mathml`, `latex`; `start == end`
for drawn math read at that place), `run_in_heading`. Spans may overlap (a bold link).
Spans on OCR text are only made where the reader gives reliable evidence (none today).

## Continuations

`continues_to` on a unit names the next piece: `unit`, `kind` (`page` or `column`),
`page_marker` (`{page, label}` of the page that begins at the break), `hyphen`
(`join`/`soft_join`/`keep` when a hyphen ends the first piece), `word_join`, `skipped`
(floats read between the pieces), `confidence`, `review_status`. `continues_from` mirrors
it. An adapter may join the pieces into one element (with the page marker inside it) or keep
them apart.

## Suppressed text

`reason` is one of:

| Reason | What | Ledger |
|---|---|---|
| `outside_trimbox` | Text outside the printed page (slug lines, crop marks) | the ledger's explicit discard |
| `invisible_render_mode` | Text drawn invisible (render mode 3) over visible text | retained |
| `covered_by_paint` | Text fully covered by later paint (zero changed pixels when removed) | retained |
| `not_rendered` | Text that changes no pixel when removed (white on white, zero size) | retained |

Each record has the page, boxes, the source refs, the text and the evidence. Text that is only
small or light is never suppressed.

A hidden glyph can be part of the same source token as visible glyphs. Such records and
the remaining visible text carry `source_runs`, so a lossless check reconstructs the
original source line from existing text slices before tokenizing. A mixed line's tokens
are counted under its visible section; section counts therefore describe this ledger
view rather than independent tokenization of the rendered fragments.

## Review list

`review.items` lists every item a person should check, sorted by severity (`must_check`
first), page and reading order. Each item: `id`, `unit`, `page`, `kind` (`ocr_word`, `ocr_line`,
`ocr_page`, `table`, `mathml`, `figure`, `alt_text`, `caption`, `credit`, `footnote`,
`join`, `hidden_text`, `structure`, `heading`, `character`, `language`, `style`,
`furniture`, `page_label`, `names`, `order`), `reason`, `severity`, a suggested `action`,
`box`, and `crop` (a file in `review/` when written). `review.counts` counts items by
`severity:kind`.

`unit` resolves to the affected content, furniture or suppression record. Reviews of
removed hidden spans point to their retained suppression record rather than an absent
content unit.

## Client profile

The profile (TOML or JSON; unknown keys are errors) sets: image naming pattern and formats,
alt-text mode, caption placement for adapters, OCR accuracy mode and thresholds, review
crops and language thresholds, which inline styling an adapter writes (`styling.emit`, and
`styling.in_headings`: the references style heading text by its element, so by default an
adapter does not write bold or italic inside headings), name splitting (off by default),
and the output sections. The JSON itself always records the styling that is printed; the
profile only says what an adapter writes. Its
id, version and hash are in `metadata.profile`. The default profile follows the company's
reference XML conventions (for example the caption after its image, as in the DTBook
reference). See [`profiles/default.toml`](../backend/src/book_core/assembly/profiles/default.toml).

An explicitly supplied profile controls figure alt-text generation, overriding the legacy
figure setting. With no explicit profile, existing callers may still request drafts through
`FigureSettings.alt_text_drafts`. Drafts use pinned local model assets and always need review.
OCR segment evidence preserves `word` or `line` granularity. A line score has no measured
word calibration: its page is `must_check` and its text gets an `ocr_line` review item.

## For adapter authors

- Read `content` in order; open a new page at each `page_marker`.
- Render `text` with its `joins` (hyphens) and `spans`; never alter the text itself.
- Use `continues_to` to join pieces across pages if the target format keeps paragraphs whole.
- For tables, drop `continuation.repeated_header_rows` when joining parts.
- Equations: use `output`; an `image` output needs the `alt_text`.
- Check `review_status` before trusting a unit; `must_check` units keep their original evidence.
