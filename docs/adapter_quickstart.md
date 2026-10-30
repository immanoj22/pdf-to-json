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
cd ~/Documents/manoj/Projects/Coeik/pdf_book_converter/pdf_book_converter_adapter
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

- `builtin`: shipped in `profiles/` (for example `jaypee_v3@3.0.0`).
- `untested`: uploaded by a user and not yet run against example deliveries.

## 2. Validate a profile YAML

```bash
$PY -m book_adapters profiles validate profiles/jaypee/jaypee_v3.yaml
```

A good file prints `OK: jaypee_v3 3.0.0 (2026-10-23); sha256 …`. A bad file prints one line
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

Then edit `books/ISBN.yaml`: fill the `to_supply` fields (title, edition, authors) and
the profile's book options (Jaypee: `suggested_reading_as_chapter`, `colour_plates`,
`qanda`, `small_caps`).

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

## 5. Open the results

Everything is inside `OUT_FOLDER`:

| Path | What |
|---|---|
| `OUT_FOLDER/<ISBN>/` | The delivery folder (Jaypee: `<ISBN>.xml`, `page_info.xml`, `Chapters/…`, `Chapters/images/`, `Chapters/bigimages/`) |
| `OUT_FOLDER/<ISBN>.zip` | The same folder as a ZIP (when the profile asks for one; Jaypee does) |
| `OUT_FOLDER/report/delivery_report.json` | Status, profile (name, version, file and resolved SHA-256, built-in or untested), book settings, alt-text override, and the **validation results** under `checks`: `dtd`, `house_rules`, `lossless` |
| `OUT_FOLDER/report/review.json` | Every item a person should check (alt text, adapter-inferred chapters, unclear characters…) |
| `OUT_FOLDER/report/run.json` | Run time |

Quick look at the validation results:

```bash
$PY -c "import json,sys; r=json.load(open(sys.argv[1])); c=r.get('checks',{}); print(r['status'], '| DTD errors:', c.get('dtd',{}).get('errors'), '| house violations:', c.get('house_rules',{}).get('violations'), '| lossless missing/extra:', c.get('lossless',{}).get('missing'), c.get('lossless',{}).get('extra'), '| alt text:', r['alt_text'])" OUT_FOLDER/report/delivery_report.json
```

Open the folder in the file manager: `xdg-open OUT_FOLDER`.

Optionally, compare with a real delivery (element counts, files, page_info):

```bash
$PY -m book_adapters compare OUT_FOLDER/<ISBN> REFERENCE_DELIVERY_FOLDER --out OUT_FOLDER/report/compare.json
```

## Worked example: the ART book (9789372025262)

The ART book was converted in the desktop app. Its converted folder is the job output
below (the folder holding `book.json`; the app also writes a `.zip` next to it, which is
not the input). Its settings file, `books/9789372025262.yaml`, is already filled in (title, edition,
three author groups, profile `jaypee_v3`).

```bash
cd ~/Documents/manoj/Projects/Coeik/pdf_book_converter/pdf_book_converter_adapter
PY=~/Documents/manoj/Projects/Coeik/pdf_book_converter/pdf_book_converter/.venv/bin/python
export PYTHONPATH=backend/src
BOOK=$(dirname ../pdf_book_converter/frontend_temp/runtime/jobs/89ae63f992d266ad201a69986fcb4622/output/book-*/book.json)
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
$PY -c "import json,sys; r=json.load(open(sys.argv[1])); c=r['checks']; print(r['status'], '| DTD errors:', c['dtd']['errors'], '| house violations:', c['house_rules']['violations'], '| lossless missing/extra:', c['lossless']['missing'], c['lossless']['extra'], '| alt text:', r['alt_text']['placeholders'], 'placeholders, override', r['alt_text']['override'])" "$OUT/report/delivery_report.json"
xdg-open "$OUT"
```

Expected (about 25 seconds):

- The first run prints `Export failed: 17 figure/equation alt text(s) are placeholders …`
  and `exit 3`.
- The second run prints a summary with `"dtd_errors": 0`, `"house_rule_violations": 0`,
  `"lossless_missing": 0`, `"lossless_extra": 0`, and an `OVERRIDE` warning.
- `$OUT` holds `9789372025262/`, `9789372025262.zip` and `report/`. The delivery has
  `9789372025262.xml`, `page_info.xml` and `Chapters/` with `front.xml`, `ch1.xml`–`ch17.xml`,
  `images/` and `bigimages/`.
- The results line reads
  `written | DTD errors: 0 | house violations: 0 | lossless missing/extra: 0 0 | alt text: 17 placeholders, override True`.

To compare with the real Jaypee delivery (path on this PC):

```bash
$PY -m book_adapters compare "$OUT/9789372025262" ~/Downloads/"9789372025262 8" --out "$OUT/report/compare.json"
```
