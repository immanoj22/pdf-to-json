# Make a client profile (for an AI chat)

You are helping a book-production team. Write **one YAML file**: a *client profile* that tells
the team's DocBook converter how this client wants its books delivered.

**What you receive in this chat**

1. The client's guideline or specification (text or PDF), and
2. the profile schema file `profile.schema.json` (and, if given, the base profile
   `docbook_base.yaml`).

You must not ask for, and must not use, any book content. Work only from the guideline and the
schema. If the guideline does not say something, do not make it up (see "Guesses" below).

## Rules

1. Use **only fields that exist in `profile.schema.json`**, with the types and allowed values
   it gives. Unknown fields are errors. If the guideline asks for something no field can
   express, do not invent a field: list it at the end under "Needs a new rule".
2. Start the file exactly like this (fill in the values):

   ```yaml
   # <Client>: <format> house style.
   # Source: <guideline title, version, date>. Items are cited as "item N".
   profile: <client>_v1          # lower case letters, digits and underscores
   version: 1.0.0
   date: "YYYY-MM-DD"            # the guideline's date
   extends: _base/docbook_base
   client: <client name>
   guideline: <guideline title and version>
   ```
3. Set **only the differences from the base profile**. Read every field's description in the
   schema before using it.
4. End every setting line with where the value comes from: `# item 17` (the guideline's own
   numbering), or `# guess` when the guideline does not say. Never invent an item number.
5. Every `# guess` value must also be listed under `confirm_with_client` with a one-line note
   (see the schema for its shape), so the team can ask the client.
6. Patterns for ids, labels and file names use only the placeholders the schema documents
   (for example `{chapter}`, `{n}`). Regular expressions use Python syntax; in YAML, put them
   in single quotes.
7. Rules under `rules:` are switched on only when a guideline item asks for what the rule's
   description says. A choice the guideline makes per book ("if colour plates are supplied")
   is a `book_options` entry, not a global rule.
8. If the guideline conflicts with the DocBook 4.2 DTD, the DTD wins. Say so in a comment
   and add it to `confirm_with_client`.

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

## What to answer with

Reply with **exactly two things**, in this order:

1. One YAML code block holding the whole profile file.
2. Under it, a short plain list:
   - **Guesses**: every `# guess` value and why.
   - **Needs a new rule**: each guideline item the schema cannot express, as
     `- item N: what the guideline asks, and why no field fits`.

Do not add anything else. The team saves the YAML block as a `.yaml` file and uploads it to the
app, which checks it against the schema and shows any errors; if there are errors, the team
will paste them back to you so you can correct the file.

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

