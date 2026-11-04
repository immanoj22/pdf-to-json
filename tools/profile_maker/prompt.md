# Profile maker: instructions for a Claude Code session

You are writing a **client profile** for the book adapters: one YAML file that tells the
adapter engine how this client wants its deliveries. You work locally, in this repository.
**No book content leaves this machine**: do not paste book text, deliveries or guidelines
into any web service, search engine or external tool. Read files only.

## Inputs (the person running you gives these)

- `CLIENT`: a short lower-case name (`acme`, `jaypee`).
- `GUIDELINE`: the client's conversion guideline (PDF or text).
- `EXAMPLES`: 2–3 finished deliveries of the client (folders of XML files and images), and,
  for each, the converter's publication of the same book (a folder with `book.json`). They
  go in an examples file (see `examples.template.yaml` next to this file).
- `PARENT` (optional): a profile to extend, default `_base/docbook_base`.

## Read first

1. `profiles/schema/profile.schema.json`: **the only fields you may use.** Every field has a
   type, allowed values, a default and a description. Unknown fields are errors.
2. `profiles/_base/docbook_base.yaml`: the defaults you inherit; set only differences.
3. The guideline, item by item. Number the items as the guideline does.
4. The example deliveries: the main XML file, two chapter files, `page_info.xml` if any,
   the file and image names. Note what the guideline does not say (ids, roles, file layout).
5. `docs/adapter_quickstart.md` for the commands.

## Write

`profiles/<CLIENT>/<CLIENT>_v1.yaml`, starting with:

```yaml
# <Client>: <format> house style.
# Source: <guideline title, version, date>, cited below as "item N". Where the guideline is
# silent, values copy the example deliveries, cited as "delivery".
profile: <CLIENT>_v1
version: 1.0.0
date: "<guideline date, YYYY-MM-DD>"
extends: <PARENT>
client: <client name>
guideline: <guideline title and version>
```

Rules for every setting:

- Use **only schema fields** and their allowed values. Check the description before using
  a field; if no field expresses a rule, do not invent one.
- **Cite the source** at the end of the line: `# item 17`, or `# delivery` when you read it
  from the example deliveries, or `# guess` when neither says it. Put every `delivery` and
  `guess` value whose correctness the client should confirm under `confirm_with_client`
  with a one-line note.
- Patterns (`ids.*`, `labels.*`, `images.name`) use the placeholders the schema documents
  (`{chapter}`, `{level}`, `{n}`, `{num}`, `{page_label}`...). Regexes are Python syntax;
  quote them with single quotes in YAML.
- Rules (`rules:`) are named functions listed in the schema enum. Switch one on only when a
  guideline item asks for what its description says; cite the item.
- Per-book choices the guideline makes conditional ("if colour plates are supplied") are
  `book_options` with the rule they switch, not global rules.
- Never set a value only because the example deliveries do it when the guideline says
  otherwise: the guideline wins, and you note the delivery's difference in a comment.
- Where the guideline conflicts with the DTD (for example an attribute the DTD does not
  declare), the DTD wins (DTD validity is item 1 of every DocBook guideline); say so in a
  comment and list it under `confirm_with_client`.

At the end of the file, add a comment block:

```yaml
# Needs a new rule (the schema cannot express these; adapter work, not profile work):
# - item N: <what the guideline asks> — <why no field or rule fits>
```

## ePub (optional `epub` section)

If the guideline also has an ePub part, add an `epub:` section (fields in the schema, under
`epub`). Set only what the guideline or the finished ePub files state, and say where each
value came from (`# epub item N`, `# sample ePub`, `# guess`); list every guess in
`confirm_with_client`. The fields are: `package` (folder and file names), `css` (style sheet
names; the CSS text itself is a file the team adds under `profiles/css/`, or `text:`),
`link_colour` (match the PDF, never default blue), `cover` (front cover only), `half_title`
(heading text), `title_page`, `copyright`, `guide`, `nav` (contents depth, the `#TOC`
container id, the return link from each heading, page list, landmarks), `landmarks`,
`metadata` (publisher, language), `accessibility` (hazard, conformance claim),
`images` and `math`. A profile with no `epub` section can only make DocBook.

## Other formats (HTML, NIMAS/DTBook, DAISY 3, JATS, BITS)

If the client's specification is for one of the standard formats, extend its base profile
(`extends: _base/html_base`, `_base/dtbook_nimas_base`, `_base/daisy3_base`, `_base/jats_base`
or `_base/bits_base`) and set only the differences. The format's choices are in the section
named like the format: `html`, `dtbook` (with `nimas`), `daisy3`, `jats`, `bits`; list the
formats the profile is for in `formats:` (for example `formats: [bits]`). Fields to read from
the specification:

- `html`: file names, style sheet, contents depth, page list, MathML.
- `dtbook`: `parts` (nested or flat), `headings.max_level`, `sidebar_render`, `metadata`
  (publisher, rights, language), `nimas` (file names, `dc:Format`, the sections whose pages
  make the title/copyright PDF).
- `daisy3`: the same content fields, `files`, `smil.split`, `ncx`, `resource` labels.
- `jats`: `mode` (`single`, or `per_article` for a book made of articles), `article_type`,
  `journal` (id, title, issn, publisher), `contrib_types`, `math`.
- `bits`: `book_type`, `publisher`, `contrib_types`, `math`.

Dates, publisher, rights and identifiers are book facts: they belong in the book settings
(`publisher`, `publication_date`, `rights`, `isbn`), never guessed. Anything the specification
asks that no field covers goes under "Needs a new rule".

## Check and test

```bash
PY=.venv/bin/python; export PYTHONPATH=backend/src
$PY -m book_adapters profiles validate profiles/<CLIENT>/<CLIENT>_v1.yaml
$PY -m book_adapters profile test profiles/<CLIENT>/<CLIENT>_v1.yaml --examples <examples.yaml> --out <tmp folder>
```

`profile test` converts nothing: it exports each example's publication with your profile and
compares it with the client's delivery. It prints, per example, the **differences a profile
can fix** (DTD errors, house-rule findings, file and id naming patterns, attribute values one
side never uses, elements one side never writes, page_info) and counts the Stage 1 / source
differences apart (headings, paragraphs, tables the converter decided; no profile fixes
those). Open `<tmp folder>/<example>/report/compare.html` for the full comparison.

Loop: adjust the YAML → validate → test, until only Stage 1 / source differences remain or
each remaining one is explained in a comment (a guideline item that overrules the delivery,
a delivery slip, a "needs a new rule"). Exit code 0 means none remain.

## Report back

- The file path and `profiles validate` output.
- The last `profile test` summary per example.
- Every `guess` and `confirm_with_client` entry.
- The "needs a new rule" list.
