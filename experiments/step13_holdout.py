"""Step 13 Part 0: seeded draw of the math hold-out, then download and seal the drawn PDF.

Candidates are the two CC BY 4.0 first-edition books the owner named (branch ``1e`` of
osbooks-college-algebra-bundle). The draw happens before any download or pipeline run. The
sealed PDF is checked for edition identity only (title, chapter list, page count); the
pipeline never runs on it until the final benchmark.

    python step13_holdout.py draw            # seeded draw, logged
    python step13_holdout.py seal            # download drawn PDF, edition check, log seal
"""

import datetime
import hashlib
import json
import random
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out" / "step13"
LOG = OUT / "holdout_runs.jsonl"
SEED = 20261014
BUNDLE = ROOT.parent / ".cache" / "external" / "osbooks-college-algebra-bundle-1e"
BUNDLE_COMMIT = "8322d84e2df67cad5ba6616fd306eb22427a50c4"
# Official CMS API values (https://openstax.org/apps/cms/api/v2/pages/?type=books.Book&slug=...),
# read 2026-10-14: both retired first editions, license CC BY 4.0.
CANDIDATES = {
    "algebra-and-trigonometry": {
        "title": "Algebra and Trigonometry",
        "pdf_url": "https://assets.openstax.org/oscms-prodcms/media/documents/"
        "AlgebraAndTrigonometry-OP_1tE6R5r.pdf",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    },
    "college-algebra": {
        "title": "College Algebra",
        "pdf_url": "https://assets.openstax.org/oscms-prodcms/media/documents/CollegeAlgebra-OP.pdf",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    },
}
MDML = "{http://cnx.rice.edu/mdml}"


def letters(text):
    """Edition identity compares letters and digits only (an outline may drop a serial comma)."""
    return "".join(character for character in text.casefold() if character.isalnum())


def log(record):
    OUT.mkdir(parents=True, exist_ok=True)
    record["time"] = datetime.datetime.now().isoformat(timespec="seconds")
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps(record, indent=1))


def drawn():
    for line in LOG.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["action"] == "drawn":
            return row["book"]
    raise SystemExit("no draw logged")


def draw():
    if LOG.exists() and any(
        json.loads(x)["action"] == "drawn" for x in LOG.read_text().splitlines()
    ):
        raise SystemExit("already drawn; a draw is never repeated")
    pool = sorted(CANDIDATES)
    book = random.Random(SEED).choice(pool)
    log(
        {
            "action": "drawn",
            "book": book,
            "pool": pool,
            "seed": SEED,
            "n": 1,
            "category": "math",
            "reason": "owner Step 13 Part 0: math hold-out, seeded draw",
        }
    )


def collection_chapters(slug):
    path = BUNDLE / "collections" / f"{slug}.collection.xml"
    root = ET.parse(path).getroot()
    titles = [e.text for e in root.iter(f"{MDML}title")]
    return titles[0], titles[1:]


def seal(folder):
    book = drawn()
    info = CANDIDATES[book]
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / info["pdf_url"].rsplit("/", 1)[1]
    if not target.exists():
        urllib.request.urlretrieve(info["pdf_url"], target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    with pymupdf.open(target) as document:
        pages = document.page_count
        metadata_title = document.metadata.get("title", "")
        outline = [title for level, title, _page in document.get_toc() if level == 1]
        front = letters(" ".join(document[index].get_text() for index in range(min(6, pages))))
    title, chapters = collection_chapters(book)
    missing = [c for c in chapters if not any(letters(c) in letters(o) for o in outline)]
    check = {
        "collection_title": title,
        "pdf_metadata_title": metadata_title,
        "title_match": letters(title) in letters(metadata_title or "") or letters(title) in front,
        "collection_chapters": len(chapters),
        "chapters_missing_from_pdf_outline": missing,
    }
    status = "sealed" if not missing and check["title_match"] else "edition_mismatch"
    log(
        {
            "action": status,
            "book": book,
            "seed": SEED,
            "pdf_url": info["pdf_url"],
            "pdf_sha256": digest,
            "pdf_pages": pages,
            "license_url": info["license_url"],
            "source_repo": "https://github.com/openstax/osbooks-college-algebra-bundle",
            "source_branch": "1e",
            "source_commit": BUNDLE_COMMIT,
            "edition_check": check,
            "reason": "never run until the final benchmark" if status == "sealed" else "not sealed",
            "note": "edition check compares letters and digits; title from metadata or front pages",
        }
    )


if __name__ == "__main__":
    if sys.argv[1] == "draw":
        draw()
    elif sys.argv[1] == "seal":
        seal(sys.argv[2])
