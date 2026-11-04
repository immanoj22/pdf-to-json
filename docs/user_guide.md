# User guide: PDF to Jaypee DocBook and ePub

For the production team. No technical knowledge needed. Everything runs on this computer; the
PDF and the results never leave it.

## Start and stop

1. Open a terminal in the project folder and run `.venv/bin/python -m book_app`.
2. Open **http://127.0.0.1:8777** in Chrome, Edge or Firefox.
3. Stop the app with Ctrl+C in the terminal. Books and decisions are kept; a conversion that was
   running shows "stopped" and can be started again (finished pages are not redone).

Settings (port, who may connect, data folder, how many conversions at once, the biggest PDF) are in
**app_settings.yaml**. Restart the app after changing it. By default only this computer can use
the app. Do not switch the office network on (`allow_lan: true`) without asking the owner: the PDF
reader's licence needs checking first.

## The steps for one book

The strip at the top of a book shows the steps: **1 Upload, 2 Profile, 3 Convert, 4 Book details,
5 Review, 6 Export**. You can go back to any step you have reached.

### 1. Upload the PDF
Press **New book**, then drag the PDF onto the box (or choose it). Up to 2 GB. The app looks
inside the file: a file that is not a PDF, is damaged or has a password is refused with a reason.

### 2. Choose the profile
A profile is the client's rules. The list shows the name, version, **tested / untested** and date.
- **Pick one**, then **Continue**.
- **Upload a profile file (YAML).** It is checked at once. A mistake shows the line, the field,
  what is wrong and a "did you mean" suggestion; nothing is stored until the file is correct. A
  good file is stored as a **new version marked "untested"**. Older versions are never replaced.
- **Make a profile from a client spec** (open the panel): see the next section.

### 3. Convert
Press **Convert**. You see the stage, "Stage 4 of 18" and the time passed. A long book takes many
minutes; you can leave the page. **Cancel** stops it and removes the half-made files. If it
stops by itself, the page tells you the stage, the page and the reason in plain words; press
**Convert again**. Only one book converts at a time (the setting can allow two).

### 4. Book details
The app fills in what the book prints. Check each field against the copyright and title pages.
- **ISBN is required.** It must be a real ISBN-13 (the last digit is a check digit). The app never
  guesses one: if it is red, read the digits again from the book.
- Title, edition, year, and the authors as **first name / surname / degrees**.
- The profile's **options** are tick boxes with their explanation (for example colour plates).

Press **Confirm and continue to review**.

### 5. Review
Type **your name** at the top (it is remembered). Every decision is saved with your name and the
time, in a separate decisions file for this book. The converted book is never edited; the export
applies your decisions to a copy.

**Flagged items.** The list shows **must check** items first, then the rest. On the left is the
PDF page with the item marked in yellow (use ◀ ▶ for other pages, − + to zoom). On the right are
what it is, why it was flagged, what we currently have, and an editor for that kind:

| Kind | What you can do |
|---|---|
| Picture description | write the description, or say the picture is decoration |
| Heading | not a heading / heading level 1–5 / start of a new chapter |
| Text break | join the paragraph with the next one |
| Character | minus sign or en dash |
| Author | correct first name, surname, degrees |
| Table | looks right / needs fixing (a note for the team) |
| Figure | a real figure, or decoration |

Then press **Accept** (it is right), **Fix** (apply what you entered) or **Skip** (leave it for
later). "23 of 41 decided" shows your progress. Filters: kind, page, open / decided. A fix changes
the list only when you press **Refresh the list** (half a minute for a long book).

**Browse pages.** Press **Browse pages** to open any page, flagged or not. For each text on the
page:
- **Make heading** (choose the level), **Set level**, **Not a heading**;
- **Join with next paragraph**, **Split here…** (choose the line where the new paragraph starts);
- tick several bullet paragraphs and press **Make a list from the selected paragraphs** (the
  bullet sign comes from the profile);
- **Start a new chapter here**;
- on a figure: write the description, or mark it decoration.

Everything you change is under **Your changes** at the bottom, each with **Undo**.

### 6. Export
Choose the profile (you can export again with another profile or version) and the **Format**:
**DocBook XML (ZIP)**, **ePub 3**, or **DocBook and ePub** (the same book, both files). For an ePub
use a profile with an ePub part (**jaypee_v4**); an older profile gets neutral defaults and a
warning. Optionally add the **front cover image** (JPEG or PNG): the PDF does not hold the
cover, and without it the ePub has no cover page and the review list asks for one. Press **Export**.
The result page shows the verdict:
- **PASS** nothing to report; **WARN** usable, but read the reasons; **FAIL** do not deliver.
- **DTD**: the DocBook structure check. **Jaypee house rules**: one line per rule with the
  guideline item. **Lossless**: no word lost or added. Element counts and warnings follow.

**Missing picture descriptions block the export.** Write them in the review. If the client agreed to
placeholders, tick **Export anyway with missing picture descriptions**; the override is written into
the QC report.

Then **Download the delivery ZIP** (the exact Jaypee folder layout) and **Download the QC report
(HTML)**. Earlier exports stay listed with their verdicts.

**The ePub result** has its own PASS / WARN / FAIL: **EPUBCheck** (the official checker; "not run"
when Java or its jar is missing, which is a WARN), **our ePub checks** (package, navigation, links,
style sheets, page list and the Jaypee ePub items: front cover only, link colour, "Half Title
Page", guide, two-way contents links), the **lossless** check, and the accessibility metadata.
Buttons: **Download the ePub**, **Download the ePub QC report**, **Open the ePub review list**.
The ePub's "modified" time is the export's time, so the same export always gives the same file.
Several things are marked "confirm with Jaypee" in the report (their CSS and a sample ePub were not
available when the profile was written).

## Books page
Lists every book: profile and version, state, the last export's verdicts (DocBook and ePub) and date. **Open** returns
to the right step, **Re-export** goes to Export, **Delete** asks you to confirm and removes only
that book's files.

## Check an edited delivery
You edited a delivery ZIP in your own XML editor? Open **Check an edited delivery**.
1. Choose the book it was made from (for the house rules and the text comparison), or only a profile
   (then only the DTD is checked).
2. Choose the ZIP and press **Check the delivery**.

You get the DTD result, the house rules, and how many words were **removed or added compared with
the converter's text** (expected if you edited text; look at the examples if you did not). Your
ZIP is only read, never changed. The report can be downloaded.

## Make a profile for a new client with an AI chat
Use this when you have the client's guideline but no profile for them.
1. In step 2, open **Make a profile from a client spec**.
2. Press **Copy the prompt**, and download **the schema file** (and the base profile if you like).
3. Open an AI chat. Paste the prompt, attach the client's **guideline or spec** and the schema file.
4. **Give the AI only the client's guideline/spec, never book content.**
5. The AI answers with one YAML block and a list of guesses. Save the block as `client_v1.yaml`.
6. Upload it under **Upload a profile file**. If it shows problems, paste the error table into the
   same chat and ask for a corrected file, then upload again. Each good upload is a new version.
7. Ask the client to confirm every guess the AI listed. The profile stays **untested** until it has
   been run against finished deliveries by the technical team.

## If something goes wrong
- *"The app is not answering"*: it was stopped. Start it again; your books are still there.
- *Not enough free disk space*: the converter keeps 5 GB free. Delete old books on the Books page.
- *Layout models missing* (top right): ask the technical team to set `models_folder`.
- A conversion that stopped: read the stage and page on the page, press **Convert again**; if it
  stops at the same place, send that sentence to the technical team.
