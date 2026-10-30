"""Book settings (books/<isbn>.yaml): ISBN, title, edition, authors, chosen profile and
book options. A draft pre-fills only what the book prints; nothing is guessed."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .profile import Problem, ProfileError, _line_map, _schema_problems, apply_defaults, load_schema

ISBN_RE = re.compile(r"(?i)ISBN(?:-13)?[^0-9]{0,12}(97[89](?:[\s‐-―-]?\d){10})")
EDITION_RE = re.compile(
    r"(?i)\b((?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"\d+(?:st|nd|rd|th))\s+edition\b[^\n]{0,20})"
)


@dataclass
class BookSettings:
    data: dict[str, Any]
    file: Path | None
    to_supply: list[str] = field(default_factory=list)

    @property
    def isbn(self) -> str | None:
        return self.data.get("isbn")

    def option(self, name: str, profile) -> Any:
        declared = profile.get("book_options", {}).get(name)
        if name in self.data.get("options", {}):
            return self.data["options"][name]
        return declared["default"] if declared else None


def isbn13_valid(digits: str) -> bool:
    if not re.fullmatch(r"97[89]\d{10}", digits):
        return False
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:12]))
    return (10 - total % 10) % 10 == int(digits[12])


def load_settings(path: Path | str, profile=None) -> BookSettings:
    path = Path(path)
    text = path.read_text("utf-8")
    data, lines, problems = _line_map(text, path.name)
    if not isinstance(data, dict):
        raise ProfileError([Problem(path.name, 1, "", "book settings are a mapping of fields")])
    schema = load_schema("book_settings.schema.json")
    problems += _schema_problems(data, schema, path.name, lines, partial=False)
    if data.get("isbn") and not isbn13_valid(str(data["isbn"])):
        problems.append(
            Problem(path.name, lines.get(("isbn",)), "isbn", "ISBN-13 check digit does not match")
        )
    if profile is not None:
        problems += option_problems(data.get("options") or {}, profile, path.name, lines)
    if problems:
        raise ProfileError(problems)
    data = apply_defaults(data, schema, schema)
    return BookSettings(data, path, missing_fields(data))


def option_problems(options: dict, profile, file: str, lines: dict) -> list[Problem]:
    import difflib

    declared = profile.get("book_options", {}) or {}
    problems = []
    for name, value in options.items():
        line = lines.get(("options", name))
        if name not in declared:
            close = difflib.get_close_matches(name, sorted(declared), n=1)
            problems.append(
                Problem(
                    file,
                    line,
                    f"options.{name}",
                    f"profile {profile.name} declares no such book option "
                    f"(declared: {', '.join(sorted(declared)) or 'none'})",
                    close[0] if close else None,
                )
            )
            continue
        kind = declared[name]["type"]
        ok = {
            "boolean": isinstance(value, bool),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
        }[kind]
        if not ok:
            problems.append(Problem(file, line, f"options.{name}", f"must be {kind}"))
        elif declared[name].get("enum") and value not in declared[name]["enum"]:
            problems.append(
                Problem(file, line, f"options.{name}", f"must be one of {declared[name]['enum']}")
            )
    return problems


def missing_fields(data: dict) -> list[str]:
    missing = [k for k in ("isbn", "title", "edition") if not data.get(k)]
    if not data.get("authorgroups"):
        missing.append("authorgroups")
    return missing


def settings_from_profile_only(profile_ref: str) -> BookSettings:
    schema = load_schema("book_settings.schema.json")
    data = apply_defaults({"profile": profile_ref}, schema, schema)
    return BookSettings(data, None, missing_fields(data))


# --------------------------------------------------------------------------- draft


def draft_settings(book: dict, profile_ref: str) -> tuple[dict, list[str]]:
    """Pre-fill settings from printed front matter. Returns the data and the fields still
    to supply. Only text the book prints is used; an ISBN must pass its check digit."""
    sections = (book.get("navigation") or {}).get("sections") or []
    kind_of_page = {}
    for s in sections:
        for p in range(s["first_page"], s["last_page"] + 1):
            kind_of_page[p] = s["kind"]
    data: dict[str, Any] = {
        "isbn": None,
        "title": None,
        "edition": None,
        "authorgroups": [],
        "profile": profile_ref,
        "options": {},
        "sources": {},
    }

    def texts(kinds):
        for unit in _walk(book.get("content") or []):
            content = unit.get("content")
            if content and kind_of_page.get(unit["pages"][0]) in kinds:
                yield unit["pages"][0], content["text"]

    for page, text in texts({"copyright", "title_page", "front_other"}):
        if data["isbn"] is None:
            for m in ISBN_RE.finditer(text):
                digits = re.sub(r"\D", "", m.group(1))
                if isbn13_valid(digits):
                    data["isbn"] = digits
                    data["sources"]["isbn"] = f"printed on page {page}: {m.group(0)!r}"
                    break
        if data["edition"] is None:
            m = EDITION_RE.search(text)
            if m:
                data["edition"] = " ".join(m.group(1).split())
                data["sources"]["edition"] = f"printed on page {page}"
    title = (book.get("metadata") or {}).get("title")
    if title:
        data["title"] = " ".join(title.split())
        data["sources"]["title"] = "book.json metadata.title (book-title heading)"
    missing = missing_fields(data)
    data["to_supply"] = missing
    return data, missing


def _walk(units):
    for u in units:
        yield u
        for key in ("items", "children"):
            yield from _walk(u.get(key) or [])


def dump_settings(data: dict) -> str:
    head = (
        "# Book settings. Fill every field listed under to_supply; never guess an ISBN.\n"
        "# sources: where each pre-filled value was read.\n"
    )
    return head + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
