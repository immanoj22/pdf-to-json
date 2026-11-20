"""The trained reference parser (AnyStyle, a CRF model; MIT licence), run as a local command.

Nothing leaves the machine: the command is a program on this computer (``BOOK_ANYSTYLE_CMD``, a
command line such as ``tools/anystyle.sh``). When it is not set or fails, ``parse_many`` returns
None and the rules alone read the references (every reference then still passes the validators or
is flagged). A model retrained on staff corrections (``BOOK_ANYSTYLE_MODEL``, see
:mod:`book_adapters.refmodel`) is passed with ``-P``."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from .vancouver import Reference, complete_last_page

COMMAND_ENV = "BOOK_ANYSTYLE_CMD"
MODEL_ENV = "BOOK_ANYSTYLE_MODEL"


def command() -> list[str] | None:
    raw = os.environ.get(COMMAND_ENV, "").strip()
    return shlex.split(raw) if raw else None


def available() -> bool:
    return command() is not None


def parse_many(texts: list[str], model: str | None = None, timeout: int = 600) -> list[dict] | None:
    """AnyStyle's JSON record of each text (same order), or None when it cannot be run."""
    cmd = command()
    if not cmd or not texts:
        return None
    model = model or os.environ.get(MODEL_ENV) or None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "refs.txt"
        src.write_text("\n".join(" ".join(t.split()) for t in texts) + "\n", "utf-8")
        args = [*cmd, "-f", "json", "--stdout"]
        if model and Path(model).is_file():
            args += ["-P", model]
        try:
            done = subprocess.run([*args, "parse", str(src)], capture_output=True, timeout=timeout, check=False)
            data = json.loads(done.stdout.decode("utf-8"))
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
    return data if isinstance(data, list) and len(data) == len(texts) else None


def _first(value) -> str:
    return (value[0] if isinstance(value, list) and value else value or "").strip() if not isinstance(value, dict) else ""


def initials(given: str) -> str | None:
    """``B.J.`` / ``Joseph F.`` / ``D J`` as initials ``B.J.``."""
    parts = re.findall(r"[^\W\d_]+\.?", given or "")
    letters = []
    for p in parts:
        word = p.rstrip(".")
        if len(word) == 1 or (word.isupper() and len(word) <= 3):
            letters += list(word)
        else:
            letters.append(word[0])
    letters = [c.upper() for c in letters if c.isalpha()]
    return "".join(f"{c}." for c in letters) or None


def to_reference(number: int, text: str, rec: dict) -> Reference:
    """AnyStyle's record as our reference: only what the parser found, nothing guessed."""
    ref = Reference(number=number, full=text)
    ref.engine = "anystyle"
    for person in rec.get("author") or []:
        if person.get("others"):
            ref.et_al = True
        elif person.get("family") or person.get("given"):
            family, given = (person.get("family") or "").strip(" .,"), person.get("given", "")
            if not family:  # a name the parser left whole: the last long word is the surname
                words = given.replace(",", " ").split()
                if words and len(words[-1].strip(".")) >= 3 and not words[-1].isupper():
                    family, given = words[-1].strip(" ."), " ".join(words[:-1])
            ref.authors.append((initials(given), family))
    ref.title = _first(rec.get("title")).strip(" ,.\"“”") or None
    kind = rec.get("type") or ""
    container = _first(rec.get("container-title") or rec.get("collection-title")).strip(" ,.") or None
    ref.source = container if kind in ("article-journal", "chapter", "paper-conference", "article") else None
    year = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", _first(rec.get("date")))
    ref.year = year.group(1) if year else None
    ref.volume = _first(rec.get("volume")).strip(" ,.") or None
    volpages = re.fullmatch(r"(\d{1,4})\s*:\s*([A-Za-z]?\d[\w\-–]*)", ref.volume or "")
    if volpages and not _first(rec.get("pages")):  # "99:e23137" is volume 99, page e23137
        ref.volume, rec = volpages.group(1), {**rec, "pages": [volpages.group(2)]}
    ref.issue = _first(rec.get("issue")).strip(" ,.") or None
    pages = _first(rec.get("pages")).strip(" ,.")
    if pages:
        m = re.match(r"^([A-Za-z]?\d+)\s*[–\-]\s*([A-Za-z]?\d+)$", pages)
        first, last = (m.group(1), m.group(2)) if m else (pages, None)
        if not re.fullmatch(r"[A-Za-z]?\d+", first):  # not a page number: not written, flagged
            ref.flags.append(f"pages “{pages}” not read")
            first, last = "", None
        if not first:
            pass
        elif first[:1] in "eE" and first[1:].isdigit():
            ref.article_number = first.lower() + (f"-e{complete_last_page(first[1:], last.lstrip('eE'))}" if last else "")
        else:
            ref.first_page = first
            ref.last_page = complete_last_page(first, last)
    doi = _first(rec.get("doi"))
    url = _first(rec.get("url"))
    ref.url = f"http://dx.doi.org/{doi}" if doi else (url or None)
    ref.pmid = _first(rec.get("pmid")) or None
    ref.publisher = _first(rec.get("publisher")).strip(" ,.") or None
    ref.place = _first(rec.get("location")).strip(" ,.") or None
    ref.edition = _first(rec.get("edition")).strip(" ,.") or None
    ref.kind = kind or None
    return ref
