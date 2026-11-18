"""Line ends that Stage 1 left without a decision, decided from the book's own words.

Stage 1 writes a join record (``LineJoin``) for the line ends it reads as a word break or a
kept hyphen. A text record it never reads that way (a table cell, a caption, a title, a list
entry built from a column) has none, and a line end without a record reads as a space:
"polysac charides", "CK- MB". This step adds the missing records when the book is loaded, in
memory only (book.json on disk is not touched), with the same three decisions Stage 1 uses:

* ``keep`` for a hard hyphen at a line end: the hyphen stays, the line end vanishes ("CK-MB").
  When the hyphen only breaks a word the book otherwise writes whole and in no other form
  ("pub-" "lic"), the hyphen is dropped (``join``).
* ``soft_join`` for a soft hyphen at a line end, ``word`` for a split with no hyphen at all, only
  when the whole word is a word of the book that stands inside a line elsewhere, and (for the
  split with no hyphen) the first part is not a word of the book. A line end that does not pass
  stays a space: the next line is then not the continuation (text order, columns), and gluing
  the two would make a word the book does not have.

The decisions use only the book's text, never a dictionary, and add no text."""

from __future__ import annotations

import unicodedata
from collections import Counter

import regex

WORD = regex.compile(r"[\p{L}\p{M}]+")
ENDS_IN_WORD = regex.compile(r"[\p{L}\p{M}]+$")
COMPOUND = regex.compile(r"[\p{L}\p{M}]+(?:-[\p{L}\p{M}]+)+")
SOFT = "­"
CONFIDENCE = 0.8


def _key(word: str) -> str:
    return unicodedata.normalize("NFKC", word).casefold()


def text_records(data: dict):
    """Every text record of the content (paragraphs, list items, cells, captions...)."""

    def walk(node):
        if isinstance(node, dict):
            content = node.get("content")
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                yield content
            elif isinstance(content, list):
                for item in content:
                    yield from walk(item)
            for key, value in node.items():
                if key != "content" and isinstance(value, (list, dict)):
                    yield from walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    yield from walk(data.get("content"))


def vocabulary(records) -> tuple[Counter, Counter]:
    """(words, hyphenated compounds) written inside a line: the first word of a line that
    follows a line end and the last word of a line that may be cut are left out, so that the
    halves of a broken word never count as words."""
    words, compounds = Counter(), Counter()
    for content in records:
        lines = content["text"].split("\n")
        for n, line in enumerate(lines):
            tokens = list(WORD.finditer(line))
            if n and tokens and not line[: tokens[0].start()].strip():
                tokens = tokens[1:]
            tail = line.rstrip()
            if n < len(lines) - 1 and tokens and tail and (tail[-1].isalpha() or tail[-1] in "-" + SOFT):
                if tokens[-1].end() >= len(tail.rstrip("-" + SOFT)):
                    tokens = tokens[:-1]
            words.update(_key(t.group()) for t in tokens)
            compounds.update(_key(m.group()) for m in COMPOUND.finditer(line))
    return words, compounds


def infer_joins(records) -> Counter:
    """Add the missing join records to the text records (``content`` dicts) in memory; returns
    what was added. ``records`` is every text record of the book (``LoadedBook.records``)."""
    records = list(records)
    words, compounds = vocabulary(records)
    added = Counter()
    for content in records:
        text = content["text"]
        if "\n" not in text:
            continue
        joins = content.get("joins")
        have = {j["at"] for j in joins or ()}
        new = []
        at = text.find("\n")
        while at != -1:
            if at and at + 1 < len(text) and at not in have:
                part = WORD.match(text, at + 1)
                before = text[at - 1]
                record = None
                if part:
                    if before == SOFT:
                        stem = ENDS_IN_WORD.search(text[: at - 1])
                        if stem and words[_key(stem.group() + part.group())] > 0:
                            record = ("soft_join", at - 1)
                    elif before == "-":
                        stem = ENDS_IN_WORD.search(text[: at - 1])
                        if stem and text[at - 1 - len(stem.group()) : at - 1] == stem.group():
                            whole = _key(stem.group() + part.group())
                            joined = (
                                words[whole] > 0
                                and words[_key(stem.group())] == 0
                                and compounds[_key(stem.group() + "-" + part.group())] == 0
                            )
                            record = ("join", at - 1) if joined else ("keep", None)
                    elif before.isalpha():
                        stem = ENDS_IN_WORD.search(text[:at])
                        if (
                            stem
                            and len(stem.group()) >= 2
                            and len(part.group()) >= 2
                            and words[_key(stem.group())] == 0
                            and words[_key(stem.group() + part.group())] > 0
                        ):
                            record = ("word", None)
                if record:
                    decision, hyphen = record
                    new.append({"at": at, "decision": decision, "hyphen_at": hyphen,
                                "confidence": CONFIDENCE, "review_status": "ok"})  # fmt: skip
                    added[decision] += 1
            at = text.find("\n", at + 1)
        if new:
            content["joins"] = sorted([*(joins or ()), *new], key=lambda j: j["at"])
    return added


__all__ = ["infer_joins", "text_records", "vocabulary"]
