# Adapter quickstart

Copy-paste commands for the client adapters (Stage 2). They turn a **converted book folder**
(the converter's output: `book.json`, `manifest.json`, `images/`) into a client delivery,
using a **profile** (the client's rules, YAML) and a **book settings** file (ISBN, title,
authors, options).

## 0. Once per terminal

Run from the adapter checkout. Use the project's Python environment; nothing needs installing
(PyYAML, Pillow, lxml and jsonschema are already in it). After a merge into `main`, use the
main folder instead.

```bash
cd ~/Documents/manoj/Projects/Coeik/pdf_book_converter/pdf_book_converter_adapter_b
PY=~/Documents/manoj/Projects/Coeik/pdf_book_converter/pdf_book_converter/.venv/bin/python
export PYTHONPATH=backend/src
```

Every command below is `$PY -m book_adapters …`. Add `--help` to any command for its
options.

## 1. List profiles

```bash
$PY -m book_adapters profiles list
```

Each line shows the reference (`name@version`, plus `#rN` for uploads), the status, the
start of the file's SHA-256, and the file:

- `builtin`: shipped in `profiles/` (for example `jaypee_v3@3.1.0`).
- `untested`: uploaded by a user and not yet run against example deliveries.

## 2. Validate a profile YAML

```bash
$PY -m book_adapters profiles validate profiles/jaypee/jaypee_v3.yaml
```

A good file prints `OK: jaypee_v3 3.1.0 (2026-11-03); sha256 …`. A bad file prints one line
per problem with file, line, field and a suggestion, and exits with code 1:

```
client.yaml:6: ids.chaptr: unknown field (allowed here: …) Did you mean 'chapter'?
```

Every allowed field is described in `profiles/schema/profile.schema.json`.

## 3. Add a profile YAML to the store

```bash
$PY -m book_adapters profiles add my_client.yaml
```

The file is validated first; a bad file is not stored. A good file is stored as a **new
version** in `profiles/_store/` and nothing existing is ever overwritten. It is marked
`untested`, and the export report warns about this. Adding the same bytes twice returns the
same entry. Store elsewhere with `--profiles-store DIR`, placed before `profiles`.

## 4. Export a converted book

### 4a. Book settings (once per book)

Draft one from the book: only printed values are filled in (ISBN only with a valid check
digit), and the rest is listed under `to_supply`. It never overwrites an existing file.

```bash
$PY -m book_adapters settings draft BOOK_FOLDER --profile jaypee_v3 --out books/ISBN.yaml
```

Then edit `books/ISBN.yaml`: fill the `to_supply` fields (title, edition) and the profile's
book options (Jaypee: `suggested_reading_as_chapter`, `colour_plates`, `qanda`,
`small_caps`).

**Authors.** Leave `authorgroups` out and the Jaypee profile reads the authors from the title
page (role label, first name, surname, degrees, job title, organisation, department,
address). Every person read is an item of the review list; an unclear split (a one-word
name, a degree the profile does not list, an extra address line) is **must check**. To
override, write `authorgroups` in the settings file: the settings always win.

### 4b. Export

```bash
$PY -m book_adapters run BOOK_FOLDER --settings books/ISBN.yaml --out OUT_FOLDER
```

- The profile comes from the settings file (`profile: jaypee_v3`). Give
  `--profile NAME[@VERSION]` to choose another, or `--profile FILE.yaml` to use an uploaded
  YAML. That file is stored as a new untested version, and its exact hash goes in the report.
- **Alt text:** the export **fails** (exit code 3, no delivery written, report written) while
  any figure or equation still has an alt-text placeholder. To export anyway, add
  `--allow-alt-text-placeholders`; the report records the override and its count.
- The command prints a summary: delivery folder, profile and status, DTD errors, house-rule
  violations, lossless missing/extra, warnings, time.

### 4c. Export an ePub

```bash
$PY -m book_adapters run BOOK_FOLDER --settings books/ISBN.yaml --profile jaypee_v4 --format epub \
    --out OUT_FOLDER_EPUB [--modified 2026-11-04T09:00:00Z] [--epubcheck-jar PATH]
```

Writes `OUT_FOLDER_EPUB/<ISBN>.epub` and `OUT_FOLDER_EPUB/report/` (`qc_report.html`, review
list). Same alt-text rule (exit code 3 unless `--allow-alt-text-placeholders`). A front cover
image goes in the settings file as `epub: {cover_image: path}`. `--modified` fixes the
`dcterms:modified` time (default: the profile's date), so reruns are byte-identical.

## 5. Open the results

Everything is inside `OUT_FOLDER`:

| Path | What |
|---|---|
| `OUT_FOLDER/<ISBN>/` | The delivery folder (Jaypee: `<ISBN>.xml`, `page_info.xml`, `Chapters/…`, `Chapters/images/`, `Chapters/bigimages/`) |
| `OUT_FOLDER/<ISBN>.zip` | The same folder as a ZIP (when the profile asks for one; Jaypee does) |
| `OUT_FOLDER/report/qc_report.html` | **Start here.** Verdict (pass / warn / fail) and why; DTD; house-rule findings by rule with the guideline item; lossless result (missing/extra, text not delivered by profile, declared moves, character changes by rule); overrides used; settings to confirm with the client; element counts. Same data in `qc_report.json` |
| `OUT_FOLDER/report/review_list.html` | Every item a person must check, **must check first**, with page, reason and a crop from the publication (alt text, author splits, inferred chapters and index locators, broken bullet glyphs, Stage 1's uncertain headings and flagged tables, unclear minus/en-dash cases). Same data in `review_list.json`; crops in `review_crops/` |
| `OUT_FOLDER/report/delivery_report.json` | Status, profile (name, version, file and resolved SHA-256, built-in or untested), book settings, alt-text override, and the full **validation results** under `checks`: `dtd`, `house_rules`, `lossless` |
| `OUT_FOLDER/report/review.json` | The adapter's own review entries (raw) |
| `OUT_FOLDER/report/run.json` | Run time (the only file that differs between two identical runs) |

The verdict is **fail** when the delivery was not written, the DTD has errors, text was lost
or added, or a written text differs from its source by anything but the recorded character
changes. It is **warn** for house-rule findings, text out of book order, an override, an
untested profile, settings to supply, or must-check items.

**Character changes.** The Jaypee profile removes soft hyphens inside lines, straightens
apostrophes, sets minus signs and index en dashes, and joins a line end inside a web
address. Each changed character is recorded; the lossless check re-derives every written
text from its source plus these changes, so nothing else can change.

Quick look at the verdict:

```bash
$PY -c "import json,sys; q=json.load(open(sys.argv[1])); print(q['verdict'], *q['reasons'], sep='\n  ')" OUT_FOLDER/report/qc_report.json
```

Open the folder in the file manager: `xdg-open OUT_FOLDER`.

Optionally, compare with a real delivery of the same book:

```bash
$PY -m book_adapters compare OUT_FOLDER/<ISBN> REFERENCE_DELIVERY_FOLDER --book BOOK_FOLDER --out OUT_FOLDER/report/compare.json
```

It prints the biggest element-count differences, each labelled **adapter** (a profile or
adapter mapping decides it), **Stage 1** (book.json decides it), **source** (the PDF lacks
it) or **check** (no rule explains it), and writes `compare.json` and `compare.html` (counts,
links by kind, boxes, paragraph splits, files, well-formedness). `--book` (the converted
book folder) lets it tell an unjoined paragraph continuation (adapter) from a missing one
(Stage 1). A reference file that is not well-formed is reported and read anyway.

## 6. Test a profile against example deliveries

`profile test` converts nothing. It exports each example book's existing publication with a
profile YAML and compares it with the client's delivery of that book:

```bash
$PY -m book_adapters profile test MY_PROFILE.yaml --examples EXAMPLES.yaml --out /tmp/ptest
```

The examples file lists, per book, the publication folder, the delivery folder and optional
book settings (template: `tools/profile_maker/examples.template.yaml`; Jaypee:
`profiles/jaypee/examples/profile_test.yaml`, paths from environment variables). The output
has three groups per book: **fix in the profile** (DTD errors, house rules, file and id
naming patterns, attribute values only we write, adapter-labelled counts), **check** (a
person decides: a value only the client uses, an element we never write) and **Stage 1 /
source** (counted, not listed: no profile fixes them). A difference a person has accepted
(a delivery slip, a rule the schema cannot express) goes under `accept:` in the examples
file with a reason. Exit code 0 means nothing is left to fix or check. Full comparisons:
`/tmp/ptest/<book>/report/compare.html`.

## 7. Make a profile for a new client

Open a Claude Code session in this repository and give it `tools/profile_maker/prompt.md`
with the client's guideline and 2–3 finished deliveries (plus the converted books, in an
examples file). It writes `profiles/<client>/<client>_v1.yaml` with only schema fields, a
source for every value (`# item N`, `# delivery`, `# guess`), `confirm_with_client` for the
guesses and a "needs a new rule" list, and loops `profiles validate` → `profile test` until
nothing is left to fix. No book content is sent anywhere. Then add the file to the store
(section 3).

## Worked example: the ART book (9789372025262)

The ART book was converted in the desktop app (job of 3 November 2026). Its converted folder
is the job output below (the folder holding `book.json`; the app also writes a `.zip` next
to it, which is not the input). Its settings file, `books/9789372025262.yaml`, is already
filled in (title, edition, three author groups, profile `jaypee_v3`).

```bash
cd ~/Documents/manoj/Projects/Coeik/pdf_book_converter/pdf_book_converter_adapter_b
PY=~/Documents/manoj/Projects/Coeik/pdf_book_converter/pdf_book_converter/.venv/bin/python
export PYTHONPATH=backend/src
BOOK=$(realpath $(dirname ../pdf_book_converter/frontend_temp/runtime/jobs/7d68b3309eb1cf6c4d6fe41b3c36168c/output/book-*/book.json))
OUT=~/adapter_out/art

# 1-2. Profiles available, and the Jaypee profile is valid
$PY -m book_adapters profiles list
$PY -m book_adapters profiles validate profiles/jaypee/jaypee_v3.yaml

# 4. Export. The converted book has no alt text yet, so this first run fails on purpose
#    (exit code 3) and writes only the report:
$PY -m book_adapters run "$BOOK" --settings books/9789372025262.yaml --out "$OUT"; echo "exit $?"

# ...after alt text is supplied the same command succeeds. To export now anyway,
#    with the override recorded in the report:
$PY -m book_adapters run "$BOOK" --settings books/9789372025262.yaml --out "$OUT" --allow-alt-text-placeholders

# 5. Results
ls "$OUT" "$OUT/9789372025262" "$OUT/9789372025262/Chapters"
$PY -c "import json,sys; q=json.load(open(sys.argv[1])); print(q['verdict'], *q['reasons'], sep='\n  ')" "$OUT/report/qc_report.json"
xdg-open "$OUT/report/qc_report.html"
```

Expected (about 20 seconds per run):

- The first run prints `Export failed: 15 figure/equation alt text(s) are placeholders …`
  and `exit 3`.
- The second run prints a summary with `"profile": "jaypee_v3@3.1.0"`, `"dtd_errors": 0`,
  `"house_rule_violations": 1`, `"lossless_missing": 0`, `"lossless_extra": 0`, and an
  `OVERRIDE` warning. The one house-rule finding is `ch3tbl1_2`: the converter gives chapter
  4 no heading, so chapters 3 and 4 share one "Table 1" (`docs/adapter_requests.md`, R15).
- `$OUT` holds `9789372025262/`, `9789372025262.zip` and `report/`. The delivery has
  `9789372025262.xml`, `page_info.xml` and `Chapters/` with `front.xml`, `ch1.xml`–`ch17.xml`,
  `images/` and `bigimages/`.
- The verdict reads `warn` with three reasons: the `ids.table` finding, the alt-text
  override, and 15 items a person must check (the alt texts) in `review_list.html`.

To compare with the real Jaypee delivery (path on this PC):

```bash
$PY -m book_adapters compare "$OUT/9789372025262" ../external_references/jaypee/9789372025262/delivery --book "$BOOK" --out "$OUT/report/compare.json"
```

To test the Jaypee profile against that delivery (exit code 0 expected):

```bash
export JAYPEE_ART_PUBLICATION="$BOOK" JAYPEE_ART_DELIVERY=$(realpath ../external_references/jaypee/9789372025262/delivery)
$PY -m book_adapters profile test profiles/jaypee/jaypee_v3.yaml --examples profiles/jaypee/examples/profile_test.yaml --out /tmp/ptest
```
