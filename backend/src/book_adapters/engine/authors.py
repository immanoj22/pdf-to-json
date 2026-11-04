"""Author names and affiliations read from the title page, for <bookinfo> when the book
settings give no author groups.

The title page is read line by line after the book title: a role label ("Editors",
"Foreword") opens a role; a name line ("Chandan Vijay Salunke  PhD") opens a person; lines
after it are degrees, job titles, an organisation, departments and an address
("Panjim, Goa, India"). The word lists and patterns come from the profile (``authors.*``);
no font, size or position is used. Nothing is guessed silently: every person is a review
entry showing the split, and a split the rules cannot settle is ``must_check``.
Text is never copied: every part is a slice of a title-page record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import TextRef, strip_ranges


@dataclass
class Person:
    contrib: TextRef | None = None
    firstname: TextRef | None = None
    surname: TextRef | None = None
    degrees: list[TextRef] = field(default_factory=list)
    jobtitle: list[TextRef] = field(default_factory=list)
    orgname: list[TextRef] = field(default_factory=list)
    orgdiv: list[TextRef] = field(default_factory=list)
    otheraddr: list[TextRef] = field(default_factory=list)
    city: TextRef | None = None
    state: TextRef | None = None
    country: TextRef | None = None
    uncertain: list[str] = field(default_factory=list)
    unit: str | None = None
    page: int | None = None

    def summary(self) -> str:
        def t(ref):
            return ref.plain().strip() if ref is not None else ""

        parts = [
            f"contrib={t(self.contrib)!r}" if self.contrib else "",
            f"firstname={t(self.firstname)!r}",
            f"surname={t(self.surname)!r}",
            f"degrees={' '.join(t(r) for r in self.degrees)!r}" if self.degrees else "",
            f"jobtitle={' '.join(t(r) for r in self.jobtitle)!r}" if self.jobtitle else "",
            f"orgname={' '.join(t(r) for r in self.orgname)!r}" if self.orgname else "",
            f"orgdiv={' | '.join(t(r) for r in self.orgdiv)!r}" if self.orgdiv else "",
            "address=" + repr(", ".join(t(r) for r in (self.city, self.state, self.country) if r))
            if self.city or self.country
            else "",
        ]
        return "; ".join(p for p in parts if p)


@dataclass
class _Line:
    ref: TextRef  # the line, trimmed (one source range)
    text: str  # as read (white space collapsed)
    unit: dict
    opens_unit: bool = False  # first line of its paragraph/heading

    @property
    def raw(self) -> tuple[int, str]:
        s, e = self.ref.ranges[0]
        return s, self.ref.text[s:e]


class _Any:
    """Several profile patterns (each may carry its own flags) used as one."""

    def __init__(self, patterns: list[str]):
        self.patterns = [re.compile(p) for p in patterns]

    def search(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns)

    def fullmatch(self, text: str) -> bool:
        return any(p.fullmatch(text) for p in self.patterns)


def _words(patterns: list[str]) -> _Any | None:
    return _Any(patterns) if patterns else None


class TitlePageReader:
    def __init__(self, profile, make_ref):
        cfg = profile.get("authors") or {}
        self.role = _words(cfg.get("role_labels") or [])
        self.stop = _words(cfg.get("stop_lines") or [])
        self.degree = re.compile(cfg.get("degree_token") or r"^$")
        self.known = {d.casefold() for d in cfg.get("known_degrees") or []}
        self.org = _words(cfg.get("org_words") or [])
        self.orgdiv = _words(cfg.get("orgdiv_words") or [])
        self.job = _words(cfg.get("job_words") or [])
        self.per_role = cfg.get("group") == "per_role"
        self.make_ref = make_ref

    # ------------------------------------------------------------------ lines

    def lines(self, units: list[dict]) -> list[_Line]:
        out = []
        for unit in _text_units(units):
            if unit["type"] == "heading" and unit.get("role") == "book_title":
                out = []  # authors follow the book title
                continue
            ref = self.make_ref(unit["id"])
            pos = 0
            first = True
            for raw in ref.text.split("\n"):
                start, end = pos, pos + len(raw)
                pos = end + 1
                if not raw.strip():
                    continue
                piece = strip_ranges(ref.slice(start, end))
                out.append(_Line(piece, " ".join(piece.plain().split()), unit, first))
                first = False
        return out

    def is_role(self, text: str) -> bool:
        return bool(self.role and self.role.fullmatch(text.strip().rstrip(":").strip()))

    def is_stop(self, text: str) -> bool:
        return bool(self.stop and self.stop.search(text))

    def degree_token(self, token: str) -> bool:
        return bool(self.degree.match(token))

    def name_like(self, text: str) -> bool:
        """2-8 capitalised words or initials, no digits or commas, no job/org words."""
        tokens = text.split()
        if not 1 < len(tokens) <= 8 or re.search(r"[\d,;:|]", text):
            return False
        for words in (self.job, self.org, self.orgdiv):
            if words and words.search(text):
                return False
        if self.degrees_only(text):
            return False
        return all(t[0].isupper() or t[0] == "(" for t in tokens)

    def degrees_only(self, text: str) -> bool:
        """A line of degrees ("MD FIAP", "MD PhD FRCPCH (UK)"), or one starting with a
        degree the profile lists."""
        tokens = [t for _, _, t in _tokens(text) if not t.startswith("(")]
        if not tokens:
            return False
        first = re.sub(r"\(.*\)$", "", tokens[0]).strip(",.").casefold()
        return first in self.known or all(self.degree_token(t) for t in tokens)

    def name_with_degrees(self, text: str) -> bool:
        tokens = [t for _, _, t in _tokens(text)]
        return (
            len(tokens) >= 2
            and self.degree_token(tokens[-1])
            and not self.degree_token(tokens[0])
            and not (self.job and self.job.search(text))
        )

    def address_like(self, text: str) -> bool:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) < 2 or not all(parts) or re.search(r"\d", text):
            return False
        for words in (self.job, self.org, self.orgdiv):
            if words and words.search(text):
                return False
        return all(len(p.split()) <= 4 and p[0].isupper() for p in parts)

    # ------------------------------------------------------------------ reading

    def read(self, units: list[dict]) -> list[list[Person]]:
        lines = self.lines(units)
        start = next(
            (
                i
                for i, ln in enumerate(lines)
                if self.is_role(ln.text) or self.name_with_degrees(ln.text)
            ),
            None,
        )
        if start is None:
            return []
        groups: list[list[Person]] = []
        role: TextRef | None = None
        role_used = False
        person: Person | None = None
        state = "name"
        degree_open = False
        field_open: list[TextRef] | None = None  # affiliation field a line ending in "," continues
        for ln in lines[start:]:
            text = ln.text
            if self.is_stop(text):
                break
            if self.is_role(text):
                role, role_used, state, person = ln.ref, False, "name", None
                continue
            empty = person is not None and not (
                person.degrees or person.jobtitle or person.orgname or person.orgdiv
            )
            named = self.name_like(text) or self.name_with_degrees(text)
            new_person = (
                state == "name"
                or (state == "after_address" and named)
                or (empty and self.name_like(text))
                or (ln.opens_unit and state != "after_name" and named)
            )  # a name opening its own paragraph or heading starts a person
            if new_person:
                person = self._person(ln, None if role_used else role)
                if self.per_role and role_used and groups:
                    groups[-1].append(person)
                else:
                    groups.append([person])
                role_used = role is not None
                state, degree_open, field_open = "after_name", False, None
                continue
            assert person is not None
            first = _tokens(text)[0][2]
            if state == "after_name" and (self.degree_token(first) or degree_open):
                person.degrees.append(ln.ref)
                self._check_degrees(person, text)
                degree_open = bool(re.search(r"(?i)\b(and|in|of|&)$|[,(]$", text))
                continue
            degree_open = False
            if self.address_like(text):
                if person.city or person.country:  # the earlier address line was not the last
                    person.otheraddr += [
                        r for r in (person.city, person.state, person.country) if r
                    ]
                    person.city = person.state = person.country = None
                self._address(person, ln)
                state, field_open = "after_address", None
                continue
            if state == "after_address":
                person.uncertain.append(f"line after the address: {text!r}")
            state = "affiliation"
            if field_open is not None:
                field_open.append(ln.ref)  # the previous line ended in "," or "and"
            elif self.orgdiv and self.orgdiv.search(text):
                person.orgdiv.append(ln.ref)
                field_open = person.orgdiv
            elif self.org and self.org.search(text) and not person.orgname:
                person.orgname.append(ln.ref)
                field_open = person.orgname
            elif person.orgname:
                person.orgname.append(ln.ref)
                person.uncertain.append(f"organisation over several lines: {text!r}")
                field_open = person.orgname
            else:
                person.jobtitle.append(ln.ref)
                field_open = person.jobtitle
            if not re.search(r"(?i)(,|\band|\bof|&)$", text):
                field_open = None
        for group in groups:
            for p in group:
                if p.surname is None:
                    p.uncertain.append("no surname")
                if p.otheraddr:
                    p.uncertain.append("more than one address line")
        return groups

    def _person(self, ln: _Line, role: TextRef | None) -> Person:
        person = Person(contrib=role, unit=ln.unit["id"], page=ln.unit["pages"][0])
        base, raw = ln.raw
        tokens = _tokens(raw)
        k = len(tokens)  # degrees: tokens from the end that look like degrees ("MD", "PhD")
        while k > 1 and self.degree_token(tokens[k - 1][2]):
            k -= 1
        name_tokens = tokens[:k]
        if k < len(tokens):
            person.degrees.append(ln.ref.slice(base + tokens[k][0], base + tokens[-1][1]))
            self._check_degrees(person, " ".join(t[2] for t in tokens[k:]))
        if not name_tokens:
            person.uncertain.append("no name before the degrees")
            return person
        last = name_tokens[-1]
        person.surname = ln.ref.slice(base + last[0], base + last[1])
        if len(name_tokens) > 1:
            person.firstname = ln.ref.slice(base + name_tokens[0][0], base + name_tokens[-2][1])
        else:
            person.uncertain.append("one-word name: first name and surname cannot be split")
        if len(name_tokens) > 4:
            person.uncertain.append("name of more than four words")
        if any(t[2][:1].islower() for t in name_tokens):
            person.uncertain.append("lower-case name part (particle?)")
        if re.fullmatch(r"[A-Z]{1,3}\.?", last[2]):
            person.uncertain.append(f"surname {last[2]!r} looks like initials")
        return person

    def _check_degrees(self, person: Person, text: str):
        if not self.known:
            return
        for _, _, token in _tokens(text):
            core = re.sub(r"\(.*\)$", "", token).strip(",.").casefold()
            if self.degree_token(token) and core not in self.known:
                person.uncertain.append(f"degree {token!r} is not in the profile's list")

    def _address(self, person: Person, ln: _Line):
        """ "City, State, Country" / "City, Country"; leading extra parts are other address
        lines."""
        base, raw = ln.raw
        pieces, pos = [], 0
        for part in raw.split(","):
            a = pos + len(part) - len(part.lstrip())
            b = pos + len(part.rstrip())
            if b > a:
                pieces.append(ln.ref.slice(base + a, base + b))
            pos += len(part) + 1
        if len(pieces) >= 3:
            *other, person.city, person.state, person.country = pieces
            person.otheraddr += other
        elif len(pieces) == 2:
            person.city, person.country = pieces
        elif pieces:
            person.country = pieces[0]


def _text_units(units: list[dict]):
    for unit in units:
        if unit["type"] in ("heading", "paragraph", "caption") and unit.get("content"):
            yield unit
        elif unit["type"] in ("list", "list_item"):
            for item in unit.get("items") or [unit]:
                if item.get("content"):
                    yield item


def _tokens(text: str) -> list[tuple[int, int, str]]:
    """Whitespace tokens of a line; a parenthesised group stays with the token before it
    ("MD(Skin and VD)")."""
    out: list[tuple[int, int, str]] = []
    for m in re.finditer(r"\S+", text):
        if out and "(" in out[-1][2] and ")" not in out[-1][2]:
            s, _, t = out[-1]
            out[-1] = (s, m.end(), text[s : m.end()])
        else:
            out.append((m.start(), m.end(), m.group()))
    return out
