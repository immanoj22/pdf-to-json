"""Printed navigation kinds and table-of-contents links (Step 6 evidence, cleaned up).

Step 6 proposed "TOC candidate pages" from repeated title/locator rows; indexes, maps and
tables share that geometry. Here every page gets entry-structure statistics from its text
units and the Step 6 entries, and candidate pages are classified:

- **index**: entries in alphabetical runs (collation key: NFKD without marks, casefolded),
  most entries carry comma-separated locators, sub-entries; typically late in the book;
- **glossary**: alphabetical runs of longer term/definition entries without locator lists;
- **bibliography**: alphabetical runs whose entries mostly carry a year (a reference list);
  commas before numbers in its entries (volumes, pages) are not index locators;
- **table of contents** and **other lists** (lists of maps, sources, features): entries whose
  resolved targets (Step 8 page labels) advance with the list order. Lists are split where the
  target sequence restarts within one label series. The first list that spans most of the book
  is the table of contents; a list whose targets are the pages that immediately follow it is a
  local table of contents (a unit opener); the others are other lists;
- a Step 6 page whose entries sit mostly in figure text, or that has neither alphabetical runs
  nor advancing targets, is rejected as navigation (map labels, numeric tables).

A small multilingual lexicon of list titles (contents, index, glossary) is supporting
evidence only; "índice" is ambiguous in Spanish and decided by structure. Table-of-contents
entries are resolved to their target page through the page labels and to the units on that
page whose text best matches the entry title.

Entries are the text units of the entry streams. A unit that holds several entries (Step 9
may merge a whole index column into one unit) is read line by line: the lines at its column's
base indent open entries (deeper lines are sub-entries and wrapped lines), and the unit is
replaced by those entries when they are themselves in alphabetical order. A run of an index
or glossary also continues onto a neighbouring page whose entries the layout set in a table
region (a ruled glossary page), read with the same entry tests; a table page alone never
starts a run.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict

import regex
from rapidfuzz import fuzz

from book_core.structure.models import REVIEW_BELOW, NavigationPage, TocLink

FIGURE_STREAMS = frozenset({"figure", "table"})
ENTRY_STREAMS = frozenset({"main", "note", "sidebar", "callout", "card"})
RUN_STREAMS = ENTRY_STREAMS | {"table"}  # streams read when a run continues onto a page
_LOCATOR = regex.compile(r"[,;]\s*\p{L}{0,3}\.?\s*\p{N}+")
# A locator list closing an entry, after a comma or a space ("Bone 55", "Body 193, 195",
# "cavities of 46, 186f"): page labels with an optional short letter prefix or suffix
# (figure or table marks) or a range, in any script's digits.
_PAGE = r"\p{L}{0,3}\.?\s*\p{N}+\p{Ll}{0,2}(?:\s*[–—-]\s*\p{N}+\p{Ll}{0,2})?"
_TAIL_LOCATOR = regex.compile(rf"\p{{L}}\p{{Ll}}*[\s,;]\s*{_PAGE}(?:\s*[,;]\s*{_PAGE})*\s*$")
_LETTER = regex.compile(r"\p{L}")
# A year (1500-2099, Arabic digits) standing alone, as reference-list entries carry.
_YEAR = regex.compile(r"(?<![\p{N}\p{L}])(?:1[5-9]|20)\p{N}{2}(?:\p{Ll})?(?![\p{N}\p{L}])")
TITLE_WORDS = {
    "table_of_contents": [
        "contents", "table of contents", "tabla de contenido", "tabla de contenidos",
        "contenido", "contenidos", "sumario", "índice general", "table des matières",
        "sommaire", "inhalt", "inhaltsverzeichnis", "sommario", "inhoud", "spis treści",
        "содержание", "оглавление", "içindekiler", "目次", "目录", "目錄", "المحتويات",
        "תוכן העניינים", "sumário",
    ],
    "index": [
        "index", "índice analítico", "índice alfabético", "índice onomástico", "índice",
        "register", "stichwortverzeichnis", "indice analitico", "indice", "указатель", "索引",
        "dizin", "فهرس", "מפתח",
    ],
    "bibliography": [
        "bibliography", "bibliografía", "bibliographie", "literaturverzeichnis", "references",
        "referencias", "références", "works cited", "obras citadas", "bibliografia",
        "参考文献", "المراجع", "ביבליוגרפיה",
    ],
    "glossary": [
        "glossary", "glosario", "glossaire", "glossar", "glossário", "glossario",
        "глоссарий", "用語集", "词汇表", "مسرد", "מילון מונחים", "sözlük",
    ],
}  # fmt: skip


def sort_key(text):
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    letters = [c for c in decomposed if c.isalpha() and not unicodedata.combining(c)]
    return "".join(letters[:3])


def _title_kind(text):
    key = " ".join(regex.sub(r"[^\p{L}\s]", " ", text.casefold()).split())
    for kind, words in TITLE_WORDS.items():
        if any(key == w or key.startswith(w + " ") or key.endswith(" " + w) for w in words):
            return kind
    return None


def label_pages(pages):
    by_label = defaultdict(list)
    for page in pages:
        if page["label"] is not None:
            by_label[page["label"]].append(page["page"])
    return by_label


def _series(label):
    """(series, value) of a printed label: prefix + Arabic value, or Roman, else None."""
    if label is None:
        return None
    match = regex.fullmatch(r"(\D*?)(\p{N}+)", label)
    if match:
        return match[1].casefold(), int("".join(str(unicodedata.digit(c)) for c in match[2]))
    if regex.fullmatch(r"(?i)[ivxlcdm]+", label):
        from book_core.structure.numbering import _value

        return "roman", _value(label)
    return None


def pairwise_order(values):
    """Share of ordered pairs (i < j) with values[i] <= values[j]; robust to outliers."""
    pairs = ordered = 0
    for i, a in enumerate(values):
        for b in values[i + 1 :]:
            pairs += 1
            ordered += a <= b
    return ordered / pairs if pairs else 0.0


def _columns(entries):
    """Entries grouped into columns (start positions within three font sizes)."""
    columns = []
    for unit in sorted(entries, key=lambda u: u["start"]):
        if columns and unit["start"] - columns[-1][-1]["start"] <= 3 * unit["size"]:
            columns[-1].append(unit)
        else:
            columns.append([unit])
    return columns


def _column_order(entries):
    """(weighted alphabetical order, keys counted) of entries read per column on the
    column's base-indent entries, in reading order."""
    weighted = total = 0
    for column in _columns(entries):
        # Sub-entries (indented within the column) break the order of the entries they
        # belong to; the order is read on the column's base-indent entries.
        base = min(u["start"] for u in column)
        column = [u for u in column if u["start"] - base <= 0.5 * u["size"]]
        ordered = sorted(column, key=lambda u: (u["position"], u["block"]))
        column_keys = [k for k in (sort_key(u["text"]) for u in ordered) if k]
        if len(column_keys) >= 2:
            weighted += pairwise_order(column_keys) * len(column_keys)
            total += len(column_keys)
    return (weighted / total if total else 0.0), total


def _line_split(unit, minimum, threshold):
    """The entries a unit of several lines holds, read line by line, or None.

    In each column of the unit's lines, a line at the base indent opens an entry; the deeper
    lines after it (sub-entries, wrapped lines) belong to it. The split is used only when
    there are at least ``minimum`` entries and they are in alphabetical order."""
    rows = unit.get("line_entries") or []
    if len(rows) < minimum:
        return None
    size = unit["size"]
    lines = [{"start": r[0], "size": size, "index": i} for i, r in enumerate(rows)]
    base = {}
    for column in _columns(lines):
        low = min(line["start"] for line in column)
        for line in column:
            base[line["index"]] = line["start"] - low <= 0.5 * size
    entries, current = [], None
    for index, (start, head, tail, letters, tokens) in enumerate(rows):
        if base[index] or current is None:
            current = {
                "start": start, "size": size, "position": unit["position"],
                "block": unit["block"] + index * 1e-6, "text": head, "tail": tail,
                "letters": letters, "tokens": tokens, "lines": 1, "stream": unit["stream"],
                "navigation_entries": [], "lead_run": None, "separator": False,
            }  # fmt: skip
            entries.append(current)
        else:
            current["tail"] = tail
            current["letters"] += letters
            current["tokens"] += tokens
            current["lines"] += 1
    entries = [e for e in entries if e["letters"] >= 2]
    if len(entries) < minimum:
        return None
    order, counted = _column_order(entries)
    if counted < minimum or order < threshold:
        return None
    return entries


def page_entries(page, streams=ENTRY_STREAMS, config=None):
    """Entry units of a page; units holding several ordered entries are read line by line
    (only with ``config``: its entry count and order thresholds)."""
    entries = []
    for unit in page["units"]:
        if unit["stream"] not in streams or unit["letters"] < 2:
            continue
        split = None
        if config is not None:
            split = _line_split(unit, config["alphabetical_entries"], config["alphabetical"])
        entries += split or [unit]
    return entries


def _entry_text(unit):
    """An entry's text for locator and year tests: its head and, when read line by line,
    the tail of its last line (where locators close)."""
    tail = unit.get("tail")
    return f"{unit['text']} {tail}" if tail and tail not in unit["text"] else unit["text"]


def page_statistics(page, total_pages, streams=ENTRY_STREAMS, config=None):
    entries = page_entries(page, streams, config)
    # Alphabetical order is measured per column of entries (start positions within three
    # font sizes), so side-by-side or bilingual columns read row by row still count.
    alphabetical, total = _column_order(entries)
    keys = [k for k in (sort_key(u["text"]) for u in entries) if k]
    figure_entries = sum(
        bool(u["navigation_entries"]) for u in page["units"] if u["stream"] in FIGURE_STREAMS
    )
    listed = sum(bool(u["navigation_entries"]) for u in page["units"])
    titles = [
        _title_kind(u["text"]) for u in page["units"]
        if u["tokens"] <= 6 and u["letters"] >= 4
    ]  # fmt: skip
    return {
        "entries": len(entries),
        "alphabetical": round(alphabetical, 3) if total else 0.0,
        "alphabetical_page_order": round(pairwise_order(keys), 3) if len(keys) >= 2 else 0.0,
        "locators": round(sum(_has_locators(_entry_text(u)) for u in entries)
                          / max(len(entries), 1), 3),
        "entry_lines": sum(u["lines"] for u in entries),
        "terms": round(sum(_term_entry(u) for u in entries) / max(len(entries), 1), 3),
        "mean_tokens": round(sum(u["tokens"] for u in entries) / max(len(entries), 1), 2),
        "dated": round(sum(bool(_YEAR.search(_entry_text(u))) for u in entries)
                       / max(len(entries), 1), 3),
        "figure_entry_share": round(figure_entries / listed, 3) if listed else 0.0,
        "position": round(page["page"] / max(total_pages, 1), 3),
        "title_kind": next((t for t in titles if t), None),
        "step6_entries": len(page["navigation"]),
        "leaders": sum(bool(e.get("leaders")) for e in page["navigation"]),
    }  # fmt: skip


def _has_locators(text):
    return bool(_LOCATOR.search(text) or _TAIL_LOCATOR.search(text.strip()))


def _term_entry(unit):
    """A term/definition entry: it opens with a run set apart in its own style (weight,
    slant, size or colour) followed by definition text, or with a wide separator."""
    lead = unit.get("lead_run")
    styled = bool(lead) and lead["letters"] >= 2 and lead["rest_letters"] >= 2
    return styled or bool(unit.get("separator"))


def _alphabetical_kind(stats, config):
    if stats["entries"] < config["alphabetical_entries"]:
        return None
    if stats["alphabetical"] < config["alphabetical"]:
        return None
    if stats["dated"] >= config["dated_entries"]:
        return "bibliography"
    if stats["locators"] >= 0.35:
        return "index"
    # A glossary's entries open with a set-off term; alphabetical rows of plain cells (a
    # ruled table of terms) are not a glossary.
    if stats["mean_tokens"] >= 5 and stats["terms"] >= config["glossary_terms"]:
        return "glossary"
    return None


def _continues(row, kind, config):
    """A neighbouring page's entries continue a run of ``kind``: the same entry structure
    with a weaker alphabetical order."""
    dated = row["dated"] >= config["dated_entries"]
    same = dated == (kind == "bibliography") and (
        dated or (row["locators"] >= 0.35) == (kind == "index")
    )
    # Step 9 may hold several entries in one unit on a page it did not see as navigation,
    # so the entry count of a neighbour is read from its lines too.
    enough = max(row["entries"], row["entry_lines"]) >= config["alphabetical_entries"]
    glossary_ok = row["mean_tokens"] >= 5 and row["terms"] >= config["glossary_terms"]
    return (
        enough
        and row["alphabetical"] >= config["alphabetical_extend"]
        and same
        and (kind != "glossary" or glossary_ok)
    )


def _advancing(page, labels, config):
    """Printed entries whose resolved targets advance with the list: contents, whose entries
    also end with a page number, never an alphabetical list (index locators do not advance
    with the entry order)."""
    resolved = [t for _, t in _targets(page, labels) if t is not None]
    return (
        len(resolved) >= config["minimum_entries"]
        and pairwise_order(resolved) >= config["advancing"]
    )


def _targets(page, labels):
    targets = []
    for entry in page["navigation"]:
        resolved = labels.get(entry.get("target_label"), [])
        targets.append((_series(entry.get("target_label")),
                        resolved[0] if len(resolved) == 1 else None))  # fmt: skip
    return targets


def classify(pages, toc_pages, config):
    """(NavigationPage list, per-page statistics, rejected Step 6 pages with reasons)."""
    total = len(pages)
    by_number = {p["page"]: p for p in pages}
    labels = label_pages(pages)
    step6 = {row["page"] for row in toc_pages}
    stats = {p["page"]: page_statistics(p, total, config=config) for p in pages}
    run_stats = {}  # rows read with table-region entries: only to continue a run

    def continuing(number):
        if number not in run_stats:
            run_stats[number] = page_statistics(by_number[number], total, RUN_STREAMS, config)
        return run_stats[number]

    decided, rejected = {}, {}
    alphabetical = {n: k for n, row in stats.items()
                    if (k := _alphabetical_kind(row, config)) is not None
                    and not _advancing(by_number[n], labels, config)}  # fmt: skip
    for number, kind in alphabetical.items():
        row = stats[number]
        neighbours = sum(alphabetical.get(number + d) == kind for d in (-1, 1))
        titled = row["title_kind"] == kind
        if not neighbours and not titled:
            continue  # an isolated page in alphabetical order by chance
        confidence = min(0.97, 0.45 + 0.3 * row["alphabetical"] + 0.1 * neighbours
                         + 0.1 * titled)  # fmt: skip
        decided[number] = (kind, confidence, [
            f"alphabetical entry order ({row['alphabetical']:.2f})",
            f"locator lists on {row['locators']:.0%} of entries" if kind == "index"
            else f"years on {row['dated']:.0%} of entries" if kind == "bibliography"
            else "term/definition entries without locator lists",
            *(["neighbouring pages of the same list"] if neighbours else []),
        ])  # fmt: skip
    # A run extends to neighbouring pages with the same entry structure and a weaker order
    # (bilingual or merged entries), page by page outward.
    changed = True
    while changed:
        changed = False
        for number in sorted(decided):
            kind = decided[number][0]
            for neighbour in (number - 1, number + 1):
                if neighbour not in stats or neighbour in decided:
                    continue
                for row, table in ((stats[neighbour], False), (continuing(neighbour), True)):
                    if not _continues(row, kind, config):
                        continue
                    decided[neighbour] = (kind, 0.65, [
                        f"continues the {kind} on the neighbouring page",
                        f"alphabetical entry order ({row['alphabetical']:.2f})",
                        *(["entries set in a table region"] if table else []),
                    ])  # fmt: skip
                    if table:
                        stats[neighbour] = {**row, "table_entries": True}
                    changed = True
                    break
    # A run absorbs short pages between two of its pages (letter-divider pages, list ends).
    for number in sorted(stats):
        if number in decided:
            continue
        before, after = decided.get(number - 1), decided.get(number + 1)
        if before and after and before[0] == after[0] and stats[number]["entries"] >= 1:
            decided[number] = (before[0], 0.6, ["between two pages of the same list"])
    toc_like, figure_pages = [], {}
    for number in sorted(step6):
        if number in decided:
            continue
        row, page = stats[number], by_number[number]
        targets = _targets(page, labels)
        resolved = [t for _, t in targets if t is not None]
        advance = pairwise_order(resolved)
        row["advancing_targets"] = round(advance, 3)
        row["resolved_targets"] = len(resolved)
        if row["figure_entry_share"] >= 0.5:
            figure_pages[number] = targets
            rejected[number] = ["entries are figure text (map or diagram labels)"]
            continue
        if len(resolved) < config["minimum_entries"] or advance < config["advancing"]:
            rejected[number] = [
                f"targets do not advance with the list ({advance:.2f}, {len(resolved)} resolved)"
            ]
            continue
        toc_like.append((number, targets))
    lists = _split_lists(toc_like)
    # A figure-text page right after a list whose targets continue it belongs to the list
    # (entries drawn inside artwork).
    for members in lists:
        last_page = members[-1][0]
        previous = [t for _, ts in members for _, t in ts if t is not None]
        follow = figure_pages.get(last_page + 1)
        if follow and previous:
            resolved = [t for _, t in follow if t is not None]
            if resolved and min(resolved) >= max(previous) and pairwise_order(resolved) >= 0.9:
                members.append((last_page + 1, follow))
                rejected.pop(last_page + 1, None)
                stats[last_page + 1]["advancing_targets"] = 1.0
                stats[last_page + 1]["resolved_targets"] = len(resolved)
    main = None
    for members in lists:
        targets = [t for _, ts in members for _, t in ts if t is not None]
        span = (max(targets) - min(targets)) / max(total, 1) if targets else 0
        if main is None and span >= config["toc_span"]:
            main = members
    for members in lists:
        targets = [t for _, ts in members for _, t in ts if t is not None]
        first_page, last_page = members[0][0], members[-1][0]
        local = (
            members is not main
            and bool(targets)
            and pairwise_order([first_page, *targets]) >= config["advancing"]
            and max(targets) - last_page <= config["local_toc_share"] * total
        )
        if members is main:
            kind, why = "table_of_contents", "first list whose targets span the book"
        elif local:
            kind, why = "table_of_contents", "local contents: targets are the pages that follow"
        else:
            kind, why = "other_list", "a further list with advancing targets"
        for number, _ in members:
            row = stats[number]
            title = row["title_kind"]
            confidence = 0.5 + 0.3 * row["advancing_targets"] + 0.1 * (row["leaders"] > 0)
            if title is not None:
                confidence += 0.1 if title == kind else -0.1
            decided[number] = (kind, min(0.95, confidence), [
                f"targets advance with the list ({row['advancing_targets']:.2f})", why,
            ])  # fmt: skip
            row["list_first_page"], row["list_last_page"] = first_page, last_page
            row["local"] = bool(local)
    pages_out = []
    for number in sorted(decided):
        kind, confidence, reasons = decided[number]
        row = stats[number]
        if row["title_kind"] == kind:
            reasons = [*reasons, "list title names this kind"]
        pages_out.append(
            NavigationPage(
                page=number, kind=kind, entries=row["entries"], confidence=round(confidence, 4),
                reasons=reasons, evidence={k: v for k, v in row.items() if not isinstance(v, list)},
                review_required=confidence < REVIEW_BELOW,
            )
        )  # fmt: skip
    return pages_out, stats, rejected


def _median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else None


def _split_lists(toc_like):
    """Consecutive TOC-like pages, split at a skipped page or where a list restarts: most of
    a page's targets in one label series lie before the previous page's median target."""
    lists, current, previous = [], [], None
    for number, targets in toc_like:
        restart = previous is not None and number - previous[0] > 1
        if not restart and previous is not None:
            by_series = defaultdict(list)
            for series, page in targets:
                if series is not None and page is not None:
                    by_series[series[0]].append(page)
            for name, pages in by_series.items():
                median = previous[1].get(name)
                if median is not None and len(pages) >= 2:
                    earlier = sum(p < median for p in pages)
                    if earlier * 2 > len(pages):
                        restart = True
        if restart and current:
            lists.append(current)
            current = []
        current.append((number, targets))
        medians = defaultdict(list)
        for series, page in targets:
            if series is not None and page is not None:
                medians[series[0]].append(page)
        previous = (number, {k: _median(v) for k, v in medians.items()})
    if current:
        lists.append(current)
    return lists


def _match(title, unit_text):
    a = " ".join(regex.sub(r"[^\p{L}\p{N}\s]", " ", title.casefold()).split())
    b = " ".join(regex.sub(r"[^\p{L}\p{N}\s]", " ", unit_text.casefold()).split())
    if not a or not b:
        return 0.0
    # A partial match counts only for a unit not much longer than the title (a title split
    # over units, or a numbered title); a long paragraph that mentions it does not.
    partial = fuzz.partial_ratio(a, b) if 4 <= len(b) <= 2 * len(a) + 8 else 0.0
    return max(fuzz.ratio(a, b), partial)


def toc_links(pages, navigation_pages, bookmarks, config):
    """Links for every entry on table-of-contents pages and for every bookmark."""
    by_number = {p["page"]: p for p in pages}
    labels = label_pages(pages)
    toc = {n.page for n in navigation_pages if n.kind == "table_of_contents"}
    links = []
    for number in sorted(toc):
        # Entries in the page's reading order (the order of the units holding them).
        position = {}
        for index, unit in enumerate(by_number[number]["units"]):
            for entry_id in unit["navigation_entries"]:
                position.setdefault(entry_id, index)
        entries = sorted(by_number[number]["navigation"],
                         key=lambda e: position.get(e["id"], len(position)))  # fmt: skip
        indents = sorted({round(e["level_evidence"].get("indentation_fonts", 0.0), 1)
                          for e in entries if e.get("level_evidence")})  # fmt: skip
        for entry in entries:
            label = entry.get("target_label")
            targets = labels.get(label, [])
            target = targets[0] if len(targets) == 1 else None
            indent = round((entry.get("level_evidence") or {}).get("indentation_fonts", 0.0), 1)
            level = _indent_level(indent, indents)
            links.append(_link(entry["id"], number, entry.get("title") or "", label, target,
                               by_number, level, config,
                               ["printed table-of-contents entry"]))  # fmt: skip
    for mark in bookmarks:
        target = mark.get("target_page")
        depth = (mark.get("level_evidence") or {}).get("outline_depth")
        links.append(_link(mark["id"], None, mark.get("title") or "", None, target, by_number,
                           depth, config, ["document outline entry"]))  # fmt: skip
    return links


def _indent_level(indent, indents):
    """Level from indentation clusters of one page (within 1 font size = same level)."""
    clusters = []
    for value in indents:
        if not clusters or value - clusters[-1][-1] > 1.0:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    for index, cluster in enumerate(clusters):
        if cluster[0] <= indent <= cluster[-1]:
            return index + 1
    return None


def _link(entry_id, source, title, label, target, by_number, level, config, reasons):
    units, score = [], None
    if target is not None and target in by_number and title:
        scored = sorted(
            (
                (_match(title, u["text"]), -u["size"], u["unit"], u)
                for u in by_number[target]["units"]
                if u["letters"] >= 2
            ),
            key=lambda x: (-x[0], x[1]),
        )
        if scored and scored[0][0] >= config["title_match"]:
            score = round(scored[0][0], 1)
            units = [scored[0][2]]
    if target is None:
        confidence, why = 0.3, "target label resolves to no single page"
    elif not units:
        confidence, why = 0.5, "target page resolved; no unit matches the title"
    else:
        confidence, why = min(0.97, 0.5 + score / 200), f"title matches a unit ({score})"
    return TocLink(
        entry_id=entry_id, source_page=source, target_label=label, target_page=target,
        unit_ids=units, match_score=score, level=level, confidence=round(confidence, 4),
        reasons=[*reasons, why], review_required=confidence < REVIEW_BELOW,
    )  # fmt: skip
