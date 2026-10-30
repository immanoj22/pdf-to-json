"""Lossless check.

1. Coverage: every token of every book.json content text record (rendered with its line-end
   joins; Stage 1 token rule) is written exactly once: as text, in a label attribute, or as
   list structure; or it is listed as omitted with a reason (profile omissions). Missing
   and duplicated tokens are counted. Furniture and suppressed text are not content.
2. Order: text written outside a declared move appears in book.json order.
3. Output: the XML re-read from disk holds exactly the ledger's text, token by token
   (alt-text slots excluded), so nothing was written that the ledger does not explain.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

from ..engine.text import TOKEN_RE, render_tokens

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


def output_matches(main_file: Path, ledger) -> dict:
    expected = _ledger_tokens(ledger)
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


def check(main_file: Path, doc, ledger) -> dict:
    cov = coverage(doc, ledger)
    out = output_matches(main_file, ledger)
    return {
        "missing": cov["missing"] + out.get("xml_missing", 0),
        "extra": cov["extra"] + out.get("xml_extra", 0),
        "coverage": cov,
        "order": order(ledger),
        "output": out,
        "generated_text": Counter(e.note for e in ledger.entries if e.kind == "generated"),
        "settings_text": sorted({e.note for e in ledger.entries if e.kind == "settings"}),
    }
