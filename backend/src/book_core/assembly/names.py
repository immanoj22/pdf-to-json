"""Optional personal-name parsing (client profile ``names.split``, off by default).

Index entries and bibliography entries often start with a personal name written family
name first ("Lincoln, Abraham, 45"; "Smith, J. A., & Brown, K. (2001). Title..."). When the
profile asks for it, the printed text is kept unchanged and each recognised name is added as
offsets with ``family`` and ``given`` parts, a rule confidence and ``needs_review`` (always:
names are hard). Nothing is parsed when the shape does not fit; nothing is language- or
script-specific beyond Unicode letter classes (case is used only where the script has it).
"""

from __future__ import annotations

import regex

from book_core.assembly.schema import PersonName

WORD = r"\p{Lu}[\p{L}\p{M}'’\-]*"
GIVEN = rf"(?:{WORD}|\p{{Lu}}\.)(?:\s+(?:{WORD}|\p{{Lu}}\.)|-\p{{Lu}}\.)*"
INDEX_NAME = regex.compile(
    rf"^(?P<family>{WORD}(?:\s+{WORD})?),\s+(?P<given>{GIVEN})(?=,|\s*$|\s+\p{{N}})"
)
AUTHOR = regex.compile(
    rf"(?P<family>{WORD}(?:\s+{WORD})?),\s+(?P<given>(?:\p{{Lu}}\.\s?)+|{GIVEN})"
)
YEAR = regex.compile(r"\(\s*\p{N}{4}[\p{L}]?\s*\)|\b\p{N}{4}\b")


def split_names(text, entry_type, term=None):
    """[PersonName] found at the start of an index or bibliography entry."""
    if entry_type == "index_entry":
        head = text if term is None else text[term[0] : term[1]]
        offset = 0 if term is None else term[0]
        match = INDEX_NAME.match(head)
        if not match:
            return []
        return [
            PersonName(
                start=offset + match.start(),
                end=offset + match.end(),
                family=match["family"],
                given=match["given"],
                confidence=0.6,
            )
        ]
    if entry_type == "bibliography_entry":
        year = YEAR.search(text)
        limit = year.start() if year else min(len(text), 200)
        names, position = [], 0
        while position < limit:
            match = AUTHOR.search(text, position, limit)
            if not match or (names and match.start() - position > 6):
                break
            if not names and match.start() > 2:
                break
            names.append(
                PersonName(
                    start=match.start(),
                    end=match.end(),
                    family=match["family"],
                    given=match["given"].strip(),
                    confidence=0.5,
                )
            )
            position = match.end()
        return names
    return []
