"""One reading per reference from two readers: the trained parser (:mod:`anystyle`) and our rules
(:mod:`vancouver`). Neither is trusted alone:

* each reading must pass the **validators** (a real year, real surnames, a title, no one-letter or
  year-like source, a journal with a volume or pages);
* only one passes: it is used; both pass and agree on authors, year and title: the rules' reading
  is used (the client's tag conventions); both pass but disagree, or neither passes: the closest
  reading is used and the reference is **flagged** for a person (never silently).

A reference with no flag was read the same way by both readers or passed alone."""

from __future__ import annotations

import re
import sys
import unicodedata

from . import anystyle, vancouver
from .vancouver import Reference


def fold(text: str | None) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)).lower())


def problems(ref: Reference) -> list[str]:
    """Why a reading cannot be trusted (empty: it passes)."""
    out = []
    if not ref.year or not re.fullmatch(r"(?:1[5-9]|20)\d\d", ref.year):
        out.append("no valid year")
    if not ref.authors and not ref.et_al:
        out.append("no authors")
    for ini, sur in ref.authors:
        letters = re.sub(r"[^\w]", "", sur)
        if len(letters) < 2 or any(c.isdigit() for c in sur) or "." in sur and len(sur) < 4 or (sur.isupper() and len(letters) <= 3):
            out.append(f"author name “{sur}” is not a surname")
            break
    if not ref.title or len(fold(ref.title)) < 6:
        if ref.engine == "anystyle" or ref.kind in ("journal",) or ref.source and ref.volume:
            out.append("no title")
    for label, value in (("source", ref.source), ("title", ref.title)):
        if value and re.search(r"\b(?:PMID|PMC\d*|ISBN|doi)\b", value, re.I):
            out.append(f"{label} holds an identifier (“{value[:30]}”)")
    if ref.source is not None:
        src = fold(ref.source)
        if len(src) < 3 or re.fullmatch(r"\d+", src) or re.search(r"\b(1[5-9]|20)\d\d\b", ref.source):
            out.append(f"source “{ref.source}” is not a title")
        if ref.title and src == fold(ref.title):
            out.append("source equals the title")
    if ref.kind == "article-journal" and not (ref.volume or ref.first_page or ref.article_number):
        out.append("journal article without volume or pages")
    if ref.volume and (len(ref.volume) > 8 or not re.search(r"\d", ref.volume)):
        out.append(f"volume “{ref.volume}” is not a volume")
    if ref.last_page and ref.first_page and ref.last_page.isdigit() and ref.first_page.isdigit() and int(ref.last_page) < int(ref.first_page):
        out.append("last page before the first")
    return out


def _same_name(x: str, y: str) -> bool:
    x, y = fold(x), fold(y)
    return x == y or (min(len(x), len(y)) >= 4 and (x.endswith(y) or y.endswith(x)))  # "Di Angelantonio" = "Angelantonio"


def organisation(ref: Reference) -> Reference:
    """A reference by an organisation ("National Institute for Health and Care Excellence. Title.
    (2019)") has no person: the words before the title are the author, when they look like a name."""
    if ref.authors or not ref.title:
        return ref
    at = ref.full.find(ref.title[:30])
    if at <= 0 and ". " in ref.title:  # the parser put "Organisation. Title" together
        head, _, rest = ref.title.partition(". ")
        if 2 <= len(head.split()) <= 14 and not re.search(r"\d|\b[A-Z]\.", head) and len(fold(rest)) >= 6:
            ref.authors, ref.title = [(None, head.strip(" .,"))], rest.strip(" .")
            return ref
    head = re.sub(r"\(\s*(?:1[5-9]|20)\d\d[a-z]?\s*\)", "", ref.full[:at] if at > 0 else "").strip(" .,;:")
    words = head.split()
    if 2 <= len(words) <= 14 and not re.search(r"\d", re.sub(r"\([A-Z]+\)", "", head)) and not re.search(r"\b[A-Z]\.", head):
        ref.authors = [(None, head)]
    return ref


def _same(a: Reference, b: Reference) -> list[str]:
    """What the two readings disagree on."""
    diff = []
    if len(a.authors) != len(b.authors) or not all(_same_name(x, y) for (_, x), (_, y) in zip(a.authors, b.authors, strict=False)):
        diff.append("authors")
    if a.year != b.year:
        diff.append("year")
    ta, tb = fold(a.title or a.source), fold(b.title or b.source)  # a book read by the rules has its title as source
    if ta != tb:
        diff.append("title" if not (ta and tb and (ta.startswith(tb) or tb.startswith(ta) or ta.endswith(tb) or tb.endswith(ta))) else "title (one is longer)")
    return diff


def _flag(ref: Reference, *notes: str) -> Reference:
    ref.flags = [*notes]
    return ref


def resolve(number: int, text: str, trained: dict | None) -> Reference:
    rules = vancouver.parse(number, text)
    rules_problems = problems(rules)
    if trained is None:  # the trained parser is not available: the rules alone, as before
        if rules_problems:
            rules.flags = [*rules.flags, *(f"not confident: {p}" for p in rules_problems)]
        return rules
    any_ref = anystyle.to_reference(number, text, trained)
    any_problems = problems(any_ref)
    if any_problems == ["no authors"]:
        any_problems = problems(organisation(any_ref))
    if not rules_problems and not any_problems:
        diff = _same(rules, any_ref)
        if not diff:  # both readers agree: what the rules were unsure of is confirmed
            rules.flags = [f for f in rules.flags if "please check" not in f and "inner full stop" not in f]
            return rules
        hard = [d for d in diff if "longer" not in d]
        if hard:
            return _flag(rules, f"the two readers disagree on {', '.join(hard)} (rules: "
                                f"{rules.title or '-'}; trained: {any_ref.title or '-'})")
        # one title holds the other: the longer is the whole title, unless the rules' title was
        # cut at an abbreviation ("... Sempervivum tectorum L.") where the client's tool cuts too
        mine, theirs = fold(rules.title or rules.source), fold(any_ref.title)
        if len(theirs) > len(mine) and not re.search(r"(?:^|\s)\w{1,3}$", (rules.title or "").strip()):
            return any_ref
        if len(mine) >= len(theirs):
            return rules
        rules.flags = list(dict.fromkeys([*rules.flags, "title: the readers cut it differently - check it"]))
        return rules
    if not any_problems:
        return any_ref
    if not rules_problems:
        return rules
    # neither passes: the closer reading, and the person is told what is wrong with it
    rules_usable = not any("source" in p for p in rules_problems)  # a one-letter source is never written
    best, mine = (any_ref, any_problems) if len(any_problems) < len(rules_problems) or not rules_usable else (rules, rules_problems)
    if best.source and any("source" in p for p in mine):
        best.source = None
    return _flag(best, *(f"not confident: {p}" for p in mine))


def resolve_all(items: list[tuple[int, str]]) -> list[Reference]:
    records = anystyle.parse_many([t for _, t in items])
    refs = [resolve(n, t, records[i] if records else None) for i, (n, t) in enumerate(items)]
    if len(items) > 1:  # one line per list (the journal of the service shows which readers were used)
        used = sum(r.engine == "anystyle" for r in refs)
        state = "trained parser (AnyStyle) used" if records else "trained parser NOT available: rules only"
        print(f"references: {state}; {len(refs)} read, {used} by the trained parser, "
              f"{sum(bool(r.flags) for r in refs)} flagged", file=sys.stderr, flush=True)
    return refs
