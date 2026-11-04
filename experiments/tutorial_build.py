"""Builds the tutorial from the screenshots: docs/tutorial/book_converter_tutorial.html (one
self-contained file), the PDF (Chrome, headless) and an animated walkthrough (GIF).

Usage: python tutorial_build.py"""

from __future__ import annotations

import base64
import html
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "docs/tutorial"
SHOTS = T / "shots"

STEPS = [
    ("01_books", "The Books page",
     "Every book you have worked on is listed here with its state. Press **New book** to start another one, "
     "or open a book to carry on where you stopped. Nothing is lost when you close the browser."),
    ("02_upload", "Step 1: Upload the PDF",
     "Press **New book**. Drag the book's PDF onto the box, or press **choose a file**. "
     "The PDF stays on this computer. A file that is not a PDF, is damaged or has a password is refused, "
     "and the message says why."),
    ("03_profile_list", "Step 2: Choose the profile",
     "A **profile** is the set of rules for one client and one output format. Profiles marked **standard** "
     "are ready-made for a format with no client rules: **html_base** (web pages), **dtbook_nimas_base** "
     "(NIMAS for accessible textbooks), **daisy3_base** (DAISY talking books), **jats_base** (JATS journal XML) "
     "and **bits_base** (BITS book XML). Client profiles such as **jaypee_v4** make DocBook and ePub."),
    ("04_profile_standard_chosen", "Pick the profile, then Continue",
     "Choose one profile and press **Continue**. If the profile does not yet exist for your client, "
     "see \"Make a profile for a new client\" at the end of this guide."),
    ("04b_convert", "Step 3: Convert",
     "The tool reads the PDF and works out the chapters, headings, lists, tables, pictures and page numbers. "
     "Press **Convert** and wait: a long book can take a long time, the progress is shown, and you can close "
     "the browser and come back. If it is stopped, press Convert again: finished pages are not redone. "
     "Scanned pages need text recognition, which is not part of this version."),
    ("05_book_details", "Step 4: Check the book details",
     "The tool reads the title page and copyright page and fills in a draft. **Check every field against the "
     "printed book.** The ISBN is required and must be a real ISBN-13: it is never guessed. Authors are read "
     "from the title page where the profile asks for it, split into role, first name, surname and degrees: fix "
     "any that are wrong, or press **Add an author** if none was found. **Publisher, publication date and "
     "rights** are optional but the NIMAS, DAISY, JATS and BITS packages need them: anything left empty is "
     "listed in the QC report as \"to supply\". Press **Confirm and continue to review**."),
    ("06_review", "Step 5: Review what needs a person",
     "The tool lists everything it was not sure about, **most important first**. For each item you see the "
     "page picture with the spot highlighted. Typical items: a picture needs a description (alt text), "
     "a heading may not be a heading, a table looks wrong. Fix it, or press **Skip**. Every change is saved "
     "with your name and can be undone. Enter your name in the **who** box first."),
    ("07_export_choose_format", "Step 6: Export",
     "Pick the **profile** and the **format**. The format list shows **only what that profile supports**. "
     "\"Every format of this profile\" makes all of them in one go. Press **Export**."),
    ("08_export_blocked", "If the export is blocked",
     "Pictures and equations without a description stop the export, because accessible books need them. "
     "Write the descriptions in the review. If the client agreed to deliver without them, tick "
     "**Export anyway with missing picture descriptions**: the override is written into the QC report."),
    ("09_export_result", "The result: PASS, WARN or FAIL",
     "**PASS**: nothing to report. **WARN**: usable, but read the reasons. **FAIL**: do not deliver. "
     "Use **Download** to get the delivery (a ZIP of the folder) and **Download the QC report**. "
     "The review list is the list of items a person still has to look at."),
    ("10_export_qc", "Reading the QC report",
     "The report shows three checks. **Schema**: the file is valid against the official standard (checked "
     "offline). **Format rules**: links work, images have descriptions, page numbers are complete and in order, "
     "required data is present. **Lossless**: no word of the book was lost or added. Anything marked "
     "\"to supply\" is information the PDF does not contain, for example the publisher."),
    ("11_check_delivery", "Check an edited delivery",
     "If someone edited a delivery by hand, upload the ZIP here to run the same checks on it again."),
    ("12_profile_maker", "Make a profile for a new client",
     "Open **Make a profile from a client spec** on the Profile step. Copy the prompt, download the schema "
     "file, and paste both with the client's guideline into an AI chat (**never book content**). Save the YAML it "
     "returns and upload it under **Upload a profile file**: mistakes are shown with line and field. For "
     "NIMAS, DAISY, JATS or BITS the AI starts from the matching base profile."),
]

FORMATS = [
    ("HTML5", "html_base", "Web pages: one page per chapter, a contents page, accessible (headings, alt text, page numbers)."),
    ("NIMAS / DTBook", "dtbook_nimas_base", "US accessible textbooks (NIMAS 1.1): DTBook XML, package file, images, title/copyright PDF."),
    ("DAISY 3", "daisy3_base", "Digital talking books (text only): DTBook, SMIL, navigation (NCX) and page list."),
    ("JATS", "jats_base", "Journal-article XML (NISO JATS 1.4). One article, or one per chapter for a book made of articles."),
    ("BITS", "bits_base", "Book XML (BITS 2.2): parts, chapters, index, references."),
    ("DocBook / ePub", "client profile, e.g. jaypee_v4", "Client deliveries to the client's own rules."),
]

PROBLEMS = [
    ("The ISBN is refused.", "Check the digits against the copyright page. The last digit must match the check digit. The tool never invents an ISBN."),
    ("Export is blocked: picture descriptions missing.", "Write them in the review (step 5), or tick the override if the client agreed. The override is recorded."),
    ("The result says WARN.", "Open the QC report and read the reasons. WARN is usable; items marked must check need a person."),
    ("The result says FAIL.", "Do not deliver. The reason is at the top of the QC report; fix the item in the review and export again."),
    ("A required value shows \"to supply\".", "Add it in Book details (publisher, publication date, rights, ISBN) and export again."),
    ("The conversion stopped.", "Open the book and press Convert again: finished pages are not redone."),
    ("The profile I need is not in the list.", "Upload it, or make one from the client's guideline (last section of this guide)."),
]


def md(text: str) -> str:
    out, parts = "", text.split("**")
    for i, part in enumerate(parts):
        out += f"<b>{html.escape(part)}</b>" if i % 2 else html.escape(part)
    return out


def img(name: str) -> str:
    path = SHOTS / f"{name}.png"
    if not path.is_file():
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img alt="{name}" src="data:image/png;base64,{data}">'


def page() -> str:
    steps = "".join(
        f"<section class='step'><h2>{html.escape(title)}</h2><p>{md(text)}</p>{img(name)}</section>"
        for name, title, text in STEPS
    )
    formats = "".join(
        f"<tr><td><b>{html.escape(a)}</b></td><td><code>{html.escape(b)}</code></td><td>{html.escape(c)}</td></tr>"
        for a, b, c in FORMATS
    )
    problems = "".join(
        f"<tr><td><b>{html.escape(a)}</b></td><td>{html.escape(b)}</td></tr>" for a, b in PROBLEMS
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Book Converter: tutorial</title>
<style>
@page {{ size: A4; margin: 16mm 14mm; }}
body {{ font-family: Arial, Helvetica, sans-serif; color: #1c2024; line-height: 1.45; font-size: 11pt; }}
h1 {{ font-size: 26pt; margin: 0 0 4pt; }} h2 {{ font-size: 15pt; margin: 0 0 6pt; color: #14366b; }}
.sub {{ color: #5b6470; margin-bottom: 14pt; }}
.step {{ break-inside: avoid; margin: 0 0 18pt; padding-top: 4pt; border-top: 2px solid #d6dae0; }}
img {{ width: 100%; border: 1px solid #c3c8cf; border-radius: 4px; margin-top: 6pt; }}
table {{ border-collapse: collapse; width: 100%; margin: 6pt 0 14pt; }}
td, th {{ border: 1px solid #c3c8cf; padding: 5pt 7pt; vertical-align: top; text-align: left; }}
th {{ background: #eef1f5; }} code {{ background: #eef1f5; padding: 1pt 4pt; border-radius: 3px; }}
.box {{ background: #eef5ff; border-left: 4px solid #14366b; padding: 8pt 10pt; margin: 8pt 0 14pt; }}
.new {{ break-before: page; }}
</style></head><body>
<h1>Book Converter</h1>
<div class="sub">Tutorial for the production team: from a PDF to a checked delivery, in plain steps.</div>
<div class="box"><b>What it does.</b> You give it a book's PDF. It reads the book, you check what it was unsure
about, and it writes the delivery in the format the client needs (HTML, NIMAS, DAISY, JATS, BITS, DocBook or
ePub), with a quality report. Everything runs on this computer; the PDF and the results never leave it.</div>
<h2>Start the tool</h2>
<ol><li>Open a terminal in the project folder and run <code>.venv/bin/python -m book_app</code>.</li>
<li>Open <b>http://127.0.0.1:8777</b> in Chrome, Edge or Firefox. (Stop with Ctrl+C in the terminal.)</li></ol>
<h2>The six steps</h2>
<p><b>1 Upload</b> &rarr; <b>2 Profile</b> &rarr; <b>3 Convert</b> &rarr; <b>4 Book details</b> &rarr;
<b>5 Review</b> &rarr; <b>6 Export</b>. The strip at the top of a book shows where you are; you can go back
to any step you have reached.</p>
<h2>Which format and profile?</h2>
<table><tr><th>Format</th><th>Profile</th><th>Use it for</th></tr>{formats}</table>
<div class="new"></div>
{steps}
<h2>If something goes wrong</h2>
<table><tr><th>Problem</th><th>What to do</th></tr>{problems}</table>
<p class="sub">Questions about a client's rules: ask the technical team. More detail: docs/user_guide.md,
docs/formats_report.md.</p>
</body></html>"""


def pdf(src: Path, dst: Path) -> None:
    subprocess.run(
        ["/usr/bin/google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
         f"--print-to-pdf={dst}", "--no-pdf-header-footer", src.as_uri()],
        check=True, capture_output=True, timeout=180,
    )  # fmt: skip


def gif(dst: Path) -> None:
    font = ImageFont.load_default(size=22)
    frames = []
    for name, title, _ in STEPS:
        path = SHOTS / f"{name}.png"
        if not path.is_file():
            continue
        im = Image.open(path).convert("RGB")
        im = im.resize((960, round(im.height * 960 / im.width)))
        bar = Image.new("RGB", (960, 56), (20, 54, 107))
        ImageDraw.Draw(bar).text((16, 14), title, fill=(255, 255, 255), font=font)
        canvas = Image.new("RGB", (960, im.height + 56), (255, 255, 255))
        canvas.paste(bar, (0, 0))
        canvas.paste(im, (0, 56))
        frames.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
    frames[0].save(dst, save_all=True, append_images=frames[1:], duration=3200, loop=0, optimize=True)


if __name__ == "__main__":
    out = T / "book_converter_tutorial.html"
    out.write_text(page(), "utf-8")
    pdf(out, T / "book_converter_tutorial.pdf")
    gif(T / "book_converter_walkthrough.gif")
    print("written:", *sorted(p.name for p in T.iterdir() if p.is_file()))
