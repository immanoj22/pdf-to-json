"""Book details: a pre-filled draft the user confirms. The ISBN is required, comes only from
the printed book and must pass its check digit; it is never invented."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from book_adapters.engine.settings import isbn13_valid

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def clean_isbn(value: str | None) -> str:
    return re.sub(r"[\s\-‐‑–—]", "", value or "")


def validate_details(details: dict, options: dict) -> list[dict]:
    """Problems in the details, as {field, message}; empty when they can be used."""
    problems = []
    isbn = clean_isbn(details.get("isbn"))
    if not isbn:
        problems.append(
            {"field": "isbn", "message": "The ISBN is required. Copy it from the copyright page."}
        )
    elif not isbn13_valid(isbn):
        problems.append(
            {
                "field": "isbn",
                "message": "This ISBN-13 is not valid (13 digits starting 978 or 979; the last "
                "digit must match the check digit). Check it against the book.",
            }
        )
    if not (details.get("title") or "").strip():
        problems.append({"field": "title", "message": "The title is required."})
    year = str(details.get("year") or "").strip()
    if year and not re.fullmatch(r"(19|20)\d{2}", year):
        problems.append({"field": "year", "message": "The year has four digits, for example 2026."})
    for i, a in enumerate(details.get("authors") or []):
        if not (a.get("surname") or "").strip():
            problems.append(
                {"field": f"authors.{i}.surname", "message": "Each author needs a surname."}
            )
    for name, value in (details.get("options") or {}).items():
        decl = options.get(name)
        if decl is None:
            problems.append(
                {"field": f"options.{name}", "message": "The profile has no such option."}
            )
        elif decl["type"] == "boolean" and not isinstance(value, bool):
            problems.append({"field": f"options.{name}", "message": "Tick or untick this option."})
    return problems


def year_from_edition(edition: str | None) -> str | None:
    m = YEAR_RE.search(edition or "")
    return m.group(0) if m else None


def authors_from_xml(main_xml: Path) -> list[dict]:
    """Authors the adapter read from the title page, from the draft delivery's ``bookinfo``."""
    from lxml import etree

    parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
    root = etree.parse(str(main_xml), parser).getroot()
    out = []
    for author in root.iter("author"):

        def text(tag, a=author):
            return " ".join("".join(e.itertext()).split()) if (e := a.find(tag)) is not None else ""

        degrees = " ".join(
            " ".join("".join(e.itertext()).split())
            for e in author.findall("othername")
            if e.get("role") == "degrees"
        )
        out.append(
            {
                "role": text("contrib"),
                "firstname": text("firstname"),
                "surname": text("surname"),
                "degrees": degrees,
                "source": "title page",
            }
        )
    return out


def settings_yaml(details: dict, profile_ref: str) -> str:
    """The adapter's book-settings file from the confirmed details."""
    groups = []
    for a in details.get("authors") or []:
        person: dict = {}
        if a.get("role"):
            person["contrib"] = a["role"]
        person["firstname"] = a.get("firstname") or ""
        person["surname"] = a.get("surname") or ""
        if a.get("degrees"):
            person["degrees"] = a["degrees"]
        groups.append([person])
    data = {
        "isbn": clean_isbn(details.get("isbn")) or None,
        "title": (details.get("title") or "").strip() or None,
        "edition": (details.get("edition") or "").strip() or None,
        "profile": profile_ref,
        "options": dict(details.get("options") or {}),
    }
    if groups:
        data["authorgroups"] = groups
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
