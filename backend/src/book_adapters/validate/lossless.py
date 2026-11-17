"""Lossless check.

1. Coverage: every token of every book.json content text record (rendered with its line-end
   joins; Stage 1 token rule) is written exactly once: as text, in a label attribute, or as
   list structure; or it is listed as omitted with a reason (profile omissions). Missing
   and duplicated tokens are counted. Furniture and suppressed text are not content.
2. Order: text written outside a declared move appears in book.json order.
3. Output: the XML re-read from disk holds exactly the ledger's text, token by token
   (alt-text slots excluded), so nothing was written that the ledger does not explain.
4. Character changes: every written text equals its source text rendered with exactly the
   character changes the ledger records (soft hyphens removed, apostrophes, dashes...), so
   an output rule can change characters but never lose or add text unrecorded. Coverage
   (1) counts source tokens by their source offsets, so a removed soft hyphen that joins
   "photo" and "copying" still proves both written once.
"""

from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import regex
from lxml import etree

from ..engine.text import DELETE, TOKEN_RE, render, render_tokens

INLINE = frozenset({"emphasis", "superscript", "subscript", "ulink", "anchor", "email", "phrase"})


def coverage(doc, ledger) -> dict:
    counts: dict[str, Counter] = defaultdict(Counter)
    kinds: dict[str, Counter] = defaultdict(Counter)
    for entry in ledger.entries:
        if not entry.addr:
            continue
        for s, e in entry.ranges:
            for i in range(s, e):
                counts[entry.addr][i] += 1
                kinds[entry.addr][(i, entry.kind)] += 1
    omitted: dict[str, list] = defaultdict(list)
    for om in doc.omissions:
        omitted[om.addr].append(om)
    result = Counter()
    by_reason = Counter()
    represented = Counter()
    missing_examples, duplicate_examples = [], []
    for addr in sorted(doc.records, key=lambda a: doc.order[a]):
        content = doc.records[addr]
        for token, chars in render_tokens(content):
            result["tokens"] += 1
            times = min(counts[addr][i] for i in chars)
            if times == 1:
                result["written_once"] += 1
                first = min(chars)
                for (i, kind), _ in kinds[addr].items():
                    if i == first:
                        represented[kind] += 1
                        break
            elif times == 0:
                reason = next(
                    (
                        om.reason
                        for om in omitted.get(addr, ())
                        if all(any(s <= i < e for s, e in om.ranges) for i in chars)
                    ),
                    None,
                )
                if reason:
                    by_reason[reason] += 1
                    result["omitted"] += 1
                else:
                    result["missing"] += 1
                    if len(missing_examples) < 20:
                        missing_examples.append(
                            {
                                "addr": addr,
                                "token": token,
                                "context": content["text"][
                                    max(0, min(chars) - 30) : max(chars) + 30
                                ],
                            }
                        )
            else:
                result["duplicated"] += times - 1
                if len(duplicate_examples) < 20:
                    duplicate_examples.append({"addr": addr, "token": token, "times": times})
    return {
        "tokens": result["tokens"],
        "written_once": result["written_once"],
        "missing": result["missing"],
        "extra": result["duplicated"],
        "omitted": result["omitted"],
        "omitted_by_reason": dict(sorted(by_reason.items())),
        "written_as": dict(sorted(represented.items())),
        "missing_examples": missing_examples,
        "duplicate_examples": duplicate_examples,
    }


def order(ledger) -> dict:
    moved = Counter()
    violations = []
    high = (-1, -1)
    for entry in ledger.entries:
        if entry.kind not in ("text", "marker") or entry.addr is None or not entry.ranges:
            continue
        if entry.move:
            moved[entry.move] += 1
            continue
        key = (entry.order, entry.ranges[0][0])
        if key < high:
            if len(violations) < 20:
                violations.append({"addr": entry.addr, "text": entry.rendered[:60]})
            moved["(undeclared)"] += 1
        else:
            high = key
    return {
        "undeclared_out_of_order": moved.pop("(undeclared)", 0),
        "declared_moves": dict(sorted(moved.items())),
        "examples": violations,
    }


def _ledger_tokens(ledger) -> list[str]:
    out: list[str] = []
    group, current = [], None
    for entry in ledger.entries:
        if entry.kind in ("attr", "structure"):
            continue
        if entry.block != current and group:
            out += TOKEN_RE.findall("".join(group))
            group = []
        current = entry.block
        group.append(entry.rendered)
    if group:
        out += TOKEN_RE.findall("".join(group))
    return out


def xml_tokens(path: Path) -> list[str]:
    parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
    root = etree.parse(str(path), parser).getroot()
    segments: list[tuple[int, str]] = []

    def block_of(el):
        while el is not None and el.tag in INLINE:
            el = el.getparent()
        return id(el)

    def walk(el, excluded: bool):
        if not isinstance(el.tag, str):
            return
        skip = (
            excluded
            or (el.tag == "textobject" and el.get("role") != "figuretext")
            or el.tag == "page-info"
        )
        if el.text and not skip:
            segments.append((block_of(el), el.text))
        for child in el:
            walk(child, skip)
            if child.tail and not skip:
                segments.append((block_of(el), child.tail))

    walk(root, False)
    out: list[str] = []
    group, current = [], None
    for key, text in segments:
        if key != current and group:
            out += TOKEN_RE.findall("".join(group))
            group = []
        current = key
        group.append(text)
    if group:
        out += TOKEN_RE.findall("".join(group))
    return out


_SOFT = "\u00ad"
_ENDS_IN_WORD = regex.compile(r"[\p{L}\p{M}\p{N}]+$")
_STARTS_WITH_WORD = regex.compile(r"^[\p{L}\p{M}\p{N}]+")


def split_words(doc, actual: list[str]) -> dict:
    """Words the source breaks at a line end (a soft hyphen, then the line end), against the
    words that were written. The converter's join record says the two parts are one word; the
    ledger only knows what the writer wrote, so a word the writer left in two parts matches
    its own ledger and the other checks pass. This one compares with the source text itself:

    * ``split``: the source joined the parts, but the written words do not hold the whole word
      (it was written in two parts, or not at all): an error.
    * ``unjoined_known_word``: no join record, yet the whole word is a word of the book that the
      join records do not need: probably one word written in two parts: a warning.
    * ``unjoined_other``: no join record and the whole word is not a word of the book. Usually
      the next line is not the continuation (text order, columns): listed, not an error.
    """
    written = Counter(actual)
    pairs = []
    for addr, content in doc.records.items():
        text = content.get("text") or ""
        at = text.find(_SOFT + "\n")
        if at < 0:
            continue
        joins = {j["at"]: j["decision"] for j in content.get("joins") or ()}
        while at >= 0:
            stem = _ENDS_IN_WORD.search(text[max(0, at - 60) : at])
            part = _STARTS_WITH_WORD.match(text[at + 2 : at + 62])
            if stem and part:
                word = unicodedata.normalize("NFKC", stem.group() + part.group())
                pairs.append((word, stem.group(), part.group(), joins.get(at + 1), addr))
            at = text.find(_SOFT + "\n", at + 2)
    need = Counter(w for w, _, _, decision, _ in pairs if decision in ("join", "soft_join"))
    missing = need - written
    spare = written - need
    result = Counter()
    examples = {"split": [], "unjoined_known_word": [], "unjoined_other": []}
    for word, stem, part, decision, addr in pairs:
        if decision in ("join", "soft_join"):
            result["joined"] += 1
            if missing[word] > 0:
                missing[word] -= 1
                result["split"] += 1
                if len(examples["split"]) < 10:
                    examples["split"].append({"word": word, "parts": [stem, part], "at": addr})
        elif spare[word] > 0:
            spare[word] -= 1
            result["unjoined_known_word"] += 1
            if len(examples["unjoined_known_word"]) < 10:
                examples["unjoined_known_word"].append({"word": word, "parts": [stem, part], "at": addr})
        else:
            result["unjoined_other"] += 1
            if len(examples["unjoined_other"]) < 10:
                examples["unjoined_other"].append({"word": word, "parts": [stem, part], "at": addr})
    return {
        "soft_hyphen_line_ends": len(pairs),
        **{k: result[k] for k in ("joined", "split", "unjoined_known_word", "unjoined_other")},
        "examples": examples,
    }


def output_matches(main_file: Path, ledger, actual: list[str] | None = None) -> dict:
    expected = _ledger_tokens(ledger)
    if actual is None:
        actual = xml_tokens(main_file)
    if expected == actual:
        return {"xml_tokens": len(actual), "matches_ledger": True, "differences": 0}
    import difflib

    sm = difflib.SequenceMatcher(a=expected, b=actual, autojunk=False)
    diffs = [op for op in sm.get_opcodes() if op[0] != "equal"]
    examples = [
        {"op": op, "ledger": expected[i1 : min(i2, i1 + 8)], "xml": actual[j1 : min(j2, j1 + 8)]}
        for op, i1, i2, j1, j2 in diffs[:10]
    ]
    return {
        "xml_tokens": len(actual),
        "ledger_tokens": len(expected),
        "matches_ledger": False,
        "differences": len(diffs),
        "xml_extra": sum(j2 - j1 for op, i1, i2, j1, j2 in diffs if op in ("insert", "replace")),
        "xml_missing": sum(i2 - i1 for op, i1, i2, j1, j2 in diffs if op in ("delete", "replace")),
        "examples": examples,
    }


def character_changes(doc, ledger) -> dict:
    """Re-render every written text from its source with the recorded changes only and
    compare it with what was written."""
    by_addr: dict[str, dict[int, str]] = defaultdict(dict)
    by_rule = Counter()
    examples: dict[str, list] = defaultdict(list)
    for change in ledger.changes.values():
        by_addr[change.addr][change.offset] = change.new
        by_rule[change.rule] += 1
        if len(examples[change.rule]) < 5:
            text = doc.records[change.addr]["text"]
            examples[change.rule].append(
                {
                    "addr": change.addr,
                    "offset": change.offset,
                    "old": change.old,
                    "new": change.new,
                    "context": text[max(0, change.offset - 20) : change.offset + 20],
                }
            )
    unexplained = []
    checked = 0
    for entry in ledger.entries:
        if entry.kind not in ("text", "marker") or entry.addr not in doc.records:
            continue
        checked += 1
        content = doc.records[entry.addr]
        text = content["text"]
        changes = by_addr.get(entry.addr)
        if changes:
            chars = list(text)
            for offset, new in changes.items():
                chars[offset] = new or DELETE
            text = "".join(chars)
        expected = "".join(ch for ch, _ in render(content, entry.ranges, text=text))
        if expected.strip() != entry.rendered.strip():
            if len(unexplained) < 10:
                unexplained.append(
                    {"addr": entry.addr, "expected": expected[:80], "written": entry.rendered[:80]}
                )
            else:
                unexplained.append(None)
    return {
        "changes": sum(by_rule.values()),
        "by_rule": dict(sorted(by_rule.items())),
        "examples": dict(sorted(examples.items())),
        "texts_checked": checked,
        "unexplained": len(unexplained),
        "unexplained_examples": [u for u in unexplained if u][:10],
    }


def check(main_file: Path, doc, ledger) -> dict:
    cov = coverage(doc, ledger)
    actual = xml_tokens(main_file)
    out = output_matches(main_file, ledger, actual)
    chars = character_changes(doc, ledger)
    return {
        "missing": cov["missing"] + out.get("xml_missing", 0),
        "extra": cov["extra"] + out.get("xml_extra", 0),
        "coverage": cov,
        "order": order(ledger),
        "output": out,
        "split_words": split_words(doc, actual),
        "character_changes": chars,
        "generated_text": Counter(e.note for e in ledger.entries if e.kind == "generated"),
        "settings_text": sorted({e.note for e in ledger.entries if e.kind == "settings"}),
    }
