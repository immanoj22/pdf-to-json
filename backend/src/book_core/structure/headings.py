"""Heading detection: which units are headings, from summed, book-relative evidence.

Candidates are the Step 9 heading-candidate units plus any short text unit (at most
``max_lines`` lines and ``max_tokens`` tokens). Style is always judged against the book's body
style (``structure.styles``), never by an absolute size, and never by size alone:

- style contrast: size ratio to the body, weight, capitals, colour, and contrast with the text
  that follows in the same stream;
- layout: the Step 4 block type (heading/title region), isolation (space before and after),
  first unit of its stream, short line count;
- text: short, no sentence terminal at the end, not starting lowercase, letters rather than
  digits; numbering patterns (``structure.numbering``);
- navigation: a table-of-contents entry or a document-outline entry resolved to this unit;
- repetition: the same text in the same style group on several pages (recurring feature
  titles and section labels).

Evidence against: figure or table text (map and diagram labels, table headers) unless it is
set far larger than the body (an opener title on artwork), lines of printed navigation pages
(only the list title and alphabetical dividers head them), later lines of a box set like its
text, letter-spaced lettering, questions and sentences, and labels made of digits.

Whole-book passes then adjust the scores:

- section recurrence: a short label that recurs once per numbered section, regularly, is a
  feature title; one that recurs several times within a section is an inline label;
- continuation: a large line starting lowercase right after a heading piece of similar size
  continues that title;
- list runs: four or more consecutive same-style lines with no text between them are list
  entries (names, terms, dates).

A unit is a heading candidate when the score reaches ``threshold``. Consecutive candidate units
of one stream that are close together and not both numbered form one heading (a title over
several blocks, a label above a title, a bare number before or after it). A main-flow
paragraph whose first line starts with a run of two to ``run_in_tokens`` words in contrasting
weight or size ending in a full stop or dash (no digits) is a run-in heading: the heading
covers that span range and the unit stays a paragraph. Which candidates are headings, display
titles or labels is decided next (``structure.styled``, ``structure.classifier``).
"""

from __future__ import annotations

from collections import Counter, defaultdict

import regex

from book_core.structure.navigation import _title_kind as title_kind
from book_core.structure.numbering import numbering
from book_core.structure.styles import case_of, group_of

_DIGITS = regex.compile(r"\p{N}")
_TERMINAL = regex.compile(r"[.!?。！？؟।]$")
_QUESTION = regex.compile(r"[?？؟]\s*$")
RUN_IN_ENDS = frozenset(".—–")
BOX_STREAMS = frozenset({"sidebar", "callout", "card", "note"})


def repetition_table(pages, body):
    """{(repeat key, style group): number of pages} over short units."""
    pages_of = defaultdict(set)
    for page in pages:
        for unit in page["units"]:
            if unit["tokens"] <= 12 and unit["letters"] >= 3:
                pages_of[(unit["repeat_key"], group_of(unit, body))].add(page["page"])
    return {key: len(value) for key, value in pages_of.items()}


def is_candidate(unit, config):
    if unit["kind"] == "heading_candidate":
        return True
    return unit["lines"] <= config["max_lines"] and unit["tokens"] <= config["max_tokens"]


def score(unit, body, context, config):
    """(score, reasons, evidence) for one candidate unit."""
    reasons, evidence = [], {}
    total = 0.0

    def add(weight, why):
        nonlocal total
        total += weight
        reasons.append(f"{why} ({weight:+.2f})")

    ratio = unit["size"] / max(body["size"], 0.1)
    evidence["size_ratio"] = round(ratio, 3)
    bold = unit["bold"] >= 0.5 and not body["bold"]
    upper = case_of(unit) == "upper"
    color = unit["color"] != body["color"]
    evidence.update({"bold": bold, "upper": upper, "color_contrast": color})
    if ratio >= config["large_ratio"]:
        add(0.5, f"set {ratio:.2f}x the body size")
    elif ratio >= config["larger_ratio"]:
        add(0.3, f"set {ratio:.2f}x the body size")
    elif ratio < config["smaller_ratio"]:
        if unit["stream"] in BOX_STREAMS and unit["position"] == 0:
            add(-0.1, "smaller than the body, but opens a box")
        else:
            add(-0.45, "smaller than the body: a label of the running text")
    contrast = 0.0
    if bold:
        contrast += 0.2
    if upper:
        contrast += 0.15
    if color:
        contrast += 0.1
    if contrast:
        add(contrast, "weight/case/colour contrast with the body")
    if not (ratio >= config["larger_ratio"] or bold or upper or color):
        add(-0.7, "no style contrast with the body")
    following = unit.get("next_size")
    if following is not None:
        if unit["size"] >= following * config["larger_ratio"] or (
            unit["bold"] >= 0.5 and (unit.get("next_bold") or 0) < 0.5
        ):
            add(0.15, "stands out from the text that follows")
    if unit["kind"] == "heading_candidate":
        add(0.3, "Step 4 heading/title block")
    if unit["position"] == 0 and unit["stream_units"] > 1:
        add(0.1, "first unit of its stream")
    elif (unit["stream"] in BOX_STREAMS and unit["position"] >= 1
          and ratio < config["larger_ratio"]):  # fmt: skip
        add(-0.5, "a later line of a box, set like its text (list or timeline entry)")
    gap_before, gap_after = unit.get("gap_before"), unit.get("gap_after")
    if gap_before is not None and gap_before >= config["isolation_fonts"]:
        add(0.1, "space before")
    if gap_after is not None and gap_after >= config["isolation_fonts"]:
        add(0.05, "space after")
    tokens, lines = unit["tokens"], unit["lines"]
    evidence.update({"tokens": tokens, "lines": lines})
    if tokens <= 12:
        add(0.1, "short")
    elif tokens > config["long_tokens"]:
        add(-0.6, "long text")
    if lines > 3:
        add(-0.3, "more than three lines")
    if unit["ending"] == "terminal" and not unit["text"].rstrip().endswith(":"):
        if _QUESTION.search(unit["text"]):
            add(-0.45 if tokens > 4 else -0.2, "ends with a question mark")
        elif tokens > 4:
            add(-0.35, "ends with a sentence terminal")
    if unit["beginning"] == "lower":
        add(-0.4, "starts lowercase")
    letters = unit["letters"]
    digits = len(_DIGITS.findall(unit["text"]))
    if letters < 2 or digits > letters:
        add(-0.8, "digits rather than words")
    marker = numbering(unit["text"])
    evidence["numbering"] = marker["kind"] if marker else None
    if marker is not None:
        if marker["kind"] == "letter":
            if ratio >= config["larger_ratio"] and context["alphabetical_page"]:
                add(0.5, "alphabetical divider letter")
        elif tokens <= config["max_tokens"]:
            add(0.25, f"{marker['kind']} numbering")
    styled = ratio >= config["larger_ratio"] or bold or upper or unit["kind"] == "heading_candidate"
    if unit["unit"] in context["toc_units"] and styled:
        add(0.45, "matches a table-of-contents entry")
    if unit["unit"] in context["outline_units"] and styled:
        add(0.35, "matches a document-outline entry")
    repeats = context["repetition"].get((unit["repeat_key"], group_of(unit, body)), 0)
    evidence["repeated_pages"] = repeats
    if repeats >= config["repeated_pages"] and tokens <= 8:
        add(0.1, f"recurring title on {repeats} pages")
    divider = bool(marker and marker["kind"] == "letter" and context["alphabetical_page"])
    if divider:
        pass  # an alphabetical divider stays one, whatever block holds it
    elif unit["stream"] in {"figure", "table"} or unit["kind"] in {"figure_text", "table_text"}:
        if ratio >= config["artwork_title_ratio"] and letters >= 3:
            add(-0.1, "text on artwork, set as a title")
        else:
            add(-0.8, "figure or table text (labels and headers)")
    if unit["kind"] == "caption":
        add(-0.15, "caption block")
    if context["navigation_kind"] in {"index", "glossary"}:
        if not (marker and marker["kind"] == "letter") and title_kind(unit["text"]) is None:
            add(-1.5, "inside an index or glossary: only dividers and the list title head it")
    elif unit["navigation_entries"] and context["navigation_kind"] is not None:
        add(-0.7, "entry of a printed navigation list")
    words = unit["text"].split()
    if len(words) >= 4 and sum(len(w) == 1 for w in words) >= 0.6 * len(words):
        add(-0.8, "letter-spaced label (map or diagram lettering)")
    if context["navigation_kind"] in {"table_of_contents", "other_list"}:
        title = title_kind(unit["text"]) is not None or (
            unit["size"] >= 0.9 * context["page_top_size"] and ratio >= config["large_ratio"]
        )
        if not title:
            add(-1.0, "a line of a printed list (only the list title heads it)")
    return round(total, 4), reasons, evidence


def run_in(unit, body, config):
    """Span range of a run-in heading at the start of a paragraph, or None."""
    lead = unit.get("lead_run")
    if lead is None or unit["kind"] != "paragraph":
        return None
    if lead["last"] not in RUN_IN_ENDS or not 2 <= lead["tokens"] <= config["run_in_tokens"]:
        return None  # a one-word lead ("Source:", a speaker's name) is a label
    if unit["stream"] != "main" or regex.search(r"\p{N}", unit["text"][: lead["letters"] + 8]):
        return None  # dates and numbered items lead lists, not paragraphs
    if lead["rest_letters"] < 2 * max(lead["letters"], 1):
        return None
    contrast = (
        (lead["bold"] and not lead["rest_bold"])
        or lead["size_ratio"] >= 1.1
        or (lead["italic"] and not lead["rest_italic"] and lead["color_differs"])
    )
    if not contrast or unit["beginning"] == "lower":
        return None
    return lead


def _label(unit):
    """A short label piece: a bare number, a short capitalised word group, "TEMA 1"."""
    marker = numbering(unit["text"])
    return (
        unit["letters"] < 3
        or (unit["tokens"] <= 3 and case_of(unit) == "upper")
        or (marker is not None and marker["kind"] != "letter" and unit["tokens"] <= 2)
    )


def group_headings(accepted, units_by_stream, body, config):
    """Merge consecutive accepted units of one stream into headings: [[unit, ...], ...].

    Pieces join when they are close on the same page, not both numbered, and either continue
    the same style group (a title over several blocks), or a label piece precedes a clearly
    larger title ("TEMA 1" above the unit title), or a bare number follows the title.
    """
    groups = []
    for units in units_by_stream.values():
        open_group = None
        for unit in units:
            if unit["unit"] not in accepted:
                open_group = None
                continue
            if open_group is not None:
                previous = open_group[-1]
                gap = unit.get("gap_before")
                close = gap is None or gap <= config["merge_gap_fonts"]
                numbered = [numbering(u["text"]) for u in (previous, unit)]
                both_numbered = all(m and m["kind"] != "letter" for m in numbered)
                has_title = any(not _label(u) for u in open_group)
                joins = (
                    group_of(previous, body) == group_of(unit, body)
                    or (not has_title and unit["size"] >= previous["size"] * config["larger_ratio"])
                    or (not has_title and previous["letters"] < 3 and unit["letters"] >= 3)
                    or (has_title and unit["letters"] < 3)
                )
                if close and previous["page"] == unit["page"] and not both_numbered and joins:
                    open_group.append(unit)
                    continue
            open_group = [unit]
            groups.append(open_group)
    return groups


def detect(pages, body, navigation_kinds, toc_units, outline_units, config):
    """(groups of heading units in book order, scores, rejected) for the whole book."""
    repetition = repetition_table(pages, body)
    scores, accepted, rejected, run_ins = {}, set(), [], {}
    alphabetical = {n for n, kind in navigation_kinds.items() if kind in {"index", "glossary"}}
    for page in pages:
        context = {
            "repetition": repetition,
            "toc_units": toc_units,
            "outline_units": outline_units,
            "navigation_kind": navigation_kinds.get(page["page"]),
            "alphabetical_page": page["page"] in alphabetical,
            "page_top_size": max((u["size"] for u in page["units"]), default=0.0),
        }
        for unit in page["units"]:
            lead = run_in(unit, body, config)
            if lead is not None and context["navigation_kind"] is None:
                run_ins[unit["unit"]] = lead
            if not is_candidate(unit, config):
                continue
            scores[unit["unit"]] = score(unit, body, context, config)
    _section_recurrence(pages, body, scores, config)
    _continuations(pages, body, scores, config)
    _list_runs(pages, body, scores, config)
    candidates = {u["unit"]: u for page in pages for u in page["units"]}
    for unit_id, (value, reasons, _) in scores.items():
        if value >= config["threshold"]:
            accepted.add(unit_id)
        elif value >= config["threshold"] - config["reject_window"]:
            rejected.append((candidates[unit_id], value, reasons))
    by_stream = defaultdict(list)
    for page in pages:
        for unit in page["units"]:
            by_stream[(page["page"], unit["stream_id"])].append(unit)
    for units in by_stream.values():
        units.sort(key=lambda u: u["position"])
    groups = group_headings(accepted, by_stream, body, config)
    return groups, scores, rejected, run_ins


def _list_runs(pages, body, scores, config):
    """Consecutive accepted lines of one stream in one style group with no text between them
    (at least ``list_run`` of them: names, terms, dates) are list entries, not headings."""
    for page in pages:
        streams = defaultdict(list)
        for unit in page["units"]:
            streams[unit["stream_id"]].append(unit)
        for units in streams.values():
            units.sort(key=lambda u: u["position"])
            run = []
            for unit in [*units, None]:
                accepted = (
                    unit is not None and unit["unit"] in scores
                    and scores[unit["unit"]][0] >= config["threshold"]
                )  # fmt: skip
                if accepted and (not run or group_of(run[-1], body) == group_of(unit, body)):
                    run.append(unit)
                    continue
                if len(run) >= config["list_run"]:
                    for member in run:
                        if (numbering(member["text"]) or {}).get("kind") == "letter":
                            continue
                        value, reasons, evidence = scores[member["unit"]]
                        scores[member["unit"]] = (
                            min(value, config["threshold"] - 0.01),
                            [*reasons, f"one of {len(run)} same-style lines with no text "
                                       "between them: list entries"],
                            {**evidence, "list_run": len(run)},
                        )  # fmt: skip
                run = [unit] if accepted else []


def _continuations(pages, body, scores, config):
    """A large line starting lowercase right after a heading piece of similar size continues
    that title (a title broken over blocks); it is accepted with the heading's evidence."""
    for page in pages:
        streams = defaultdict(list)
        for unit in page["units"]:
            streams[unit["stream_id"]].append(unit)
        for units in streams.values():
            units.sort(key=lambda u: u["position"])
            for previous, unit in zip(units, units[1:], strict=False):
                if unit["unit"] not in scores or previous["unit"] not in scores:
                    continue
                value, reasons, evidence = scores[unit["unit"]]
                before = scores[previous["unit"]][0]
                similar = max(unit["size"], previous["size"]) <= 1.3 * min(
                    unit["size"], previous["size"]
                )
                if (value < config["threshold"] <= before and unit["beginning"] == "lower"
                        and similar and unit["size"] >= body["size"] * config["large_ratio"]
                        and unit["lines"] <= 2):  # fmt: skip
                    scores[unit["unit"]] = (
                        config["threshold"],
                        [*reasons, "continues the title above it (lowercase, same size)"],
                        {**evidence, "continuation": True},
                    )


def _section_recurrence(pages, body, scores, config):
    """Small recurring labels: once per numbered section (a feature title) or several times
    within one section (an inline label of the running text).

    Sections here are the spans between prominent numbered candidates (a number or a
    sectioning word set larger than the body) in book order. Scores are adjusted in place.
    """
    segment, current, sequence = {}, 0, []
    for page in pages:
        for unit in page["units"]:
            if unit["unit"] not in scores:
                continue
            marker = numbering(unit["text"])
            prominent = unit["size"] >= body["size"] * config["larger_ratio"]
            if (marker and marker["kind"] in {"keyword", "decimal", "number"} and prominent
                    and scores[unit["unit"]][0] >= config["threshold"]):  # fmt: skip
                current += 1
            segment[unit["unit"]] = current
            sequence.append(unit)
    occurrences = defaultdict(Counter)
    for unit in sequence:
        if unit["tokens"] <= 8 and unit["letters"] >= 3:
            occurrences[(unit["repeat_key"], group_of(unit, body))][segment[unit["unit"]]] += 1
    verdict = {}
    for key, per_segment in occurrences.items():
        if len(per_segment) < config["repeated_pages"]:
            continue
        spanned = max(per_segment) - min(per_segment) + 1
        density = len(per_segment) / spanned
        sample = next(u for u in sequence
                      if (u["repeat_key"], group_of(u, body)) == key)  # fmt: skip
        larger = sample["size"] >= body["size"] * config["larger_ratio"]
        if (not larger and density < config["feature_share"]
                and all(c < 2 for c in per_segment.values())):  # fmt: skip
            continue  # once per section, but only in a few of them: no feature evidence
        repeated = sum(count >= 2 for count in per_segment.values()) / len(per_segment)
        verdict[key] = ("inline" if repeated >= 0.5 else "section", len(per_segment), repeated)
    for unit in sequence:
        key = (unit["repeat_key"], group_of(unit, body))
        if key not in verdict:
            continue
        kind, sections, repeated = verdict[key]
        value, reasons, evidence = scores[unit["unit"]]
        if unit["size"] >= body["size"] * config["larger_ratio"]:
            # A larger title: once per section is a recurring section title (evidence only);
            # several times per section changes nothing (display titles are decided later).
            if kind == "section":
                scores[unit["unit"]] = (value, [*reasons, f"title once per section in "
                                                f"{sections} sections"],
                                        {**evidence, "recurring_title": True})  # fmt: skip
            continue
        evidence = {**evidence, "label_sections": sections,
                    "label_repeat_share": round(repeated, 3)}  # fmt: skip
        if kind == "inline":
            value -= 0.7
            reasons = [*reasons, "label recurs within one section: an inline label (-0.70)"]
        else:
            value += 0.35
            reasons = [*reasons, f"label once per section in {sections} sections (+0.35)"]
            evidence["feature_title"] = True
        scores[unit["unit"]] = (round(value, 4), reasons, evidence)


def style_group_counts(groups, body):
    return Counter(group_of(g[0], body) for g in groups)
