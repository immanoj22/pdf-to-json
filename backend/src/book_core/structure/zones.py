"""Book parts: front, body and rear matter, and the section kind of every page.

Evidence, combined per page and then grouped into contiguous sections:

- **Section openers**: pages (other than printed navigation) with a heading numbered by a
  sectioning word of part, unit or chapter rank ("Unidad 3", "Chapter 2", "第3章"); without
  at least two of them, pages whose numbered heading has the book's most prominent style among
  numbered headings.
- **Folio runs** (Step 8): the body starts at the first opener (normally where the first
  Arabic run starts); pages before it are front matter. With fewer than two sectioning-word
  openers, the body starts at the first Arabic folio run instead (prominent numbered headings
  still open sections). A separate run in another label series is its own block.
- **End of the body**: after the last numbered heading of the main run, the first printed
  glossary or index page, a page titled as an appendix or bibliography, or a page whose most
  prominent heading is unnumbered and at least as prominent as the numbered section headings
  starts the rear matter.
- **Inserted blocks**: a run in another label series that holds numbered headings is body
  matter; otherwise trailing pages are rear matter.
- **Printed navigation** (``structure.navigation``): table-of-contents and other list pages
  are front-matter sections; glossary and index pages are rear-matter sections. A reference
  list (bibliography) inside the body stays part of its chapter.
- **Page content**: the first pages with little text are the cover; a front page with a
  copyright sign or an ISBN is the copyright page; pages dominated by credit text are credits;
  the page of the book title is the title page.
- **Titles**: a small multilingual lexicon of section titles (preface, introduction,
  dedication, acknowledgements, appendix, bibliography, credits) is supporting evidence.

The logical position of an inserted body block follows the table of contents: when the
contents list its sections before the first body section, the block is ordered before it
(``Section.logical_index``); physical page order is never changed.
"""

from __future__ import annotations

import regex

from book_core.extraction.fingerprints import stable_id
from book_core.structure.models import REVIEW_BELOW, PageZone, Section

TITLE_KINDS = {
    "preface": ["preface", "prefacio", "préface", "vorwort", "prefazione", "foreword",
                "prólogo", "prologo", "prologue", "introduction", "introducción",
                "einleitung", "introduzione", "presentación", "avant-propos"],
    "dedication": ["dedication", "dedicatoria", "dédicace", "widmung", "dedica"],
    "credits": ["credits", "créditos", "crédits", "acknowledgments", "acknowledgements",
                "agradecimientos", "remerciements", "danksagung", "ringraziamenti"],
    "appendix": ["appendix", "apéndice", "appendice", "anhang", "annexe", "anexo",
                 "appendices", "apéndices"],
    "bibliography": ["bibliography", "bibliografía", "bibliographie", "literaturverzeichnis",
                     "references", "referencias", "références", "works cited", "obras citadas",
                     "bibliografia"],
}  # fmt: skip
_ISBN = regex.compile(r"(?i)\bisbn\b|©|\(c\)\s*\p{N}{4}")
OPENER_ROLES = frozenset({"part", "unit", "chapter"})
NAVIGATION_SECTIONS = {"table_of_contents": "table_of_contents", "other_list": "other_list",
                       "glossary": "glossary", "index": "index",
                       "bibliography": "bibliography"}  # fmt: skip


def title_kind(text):
    key = " ".join(regex.sub(r"[^\p{L}\s]", " ", text.casefold()).split())
    for kind, words in TITLE_KINDS.items():
        if any(key == w or key.startswith(w + " ") for w in words):
            return kind
    return None


def decide_zones(pages, runs, navigation_pages, headings, config):
    """(sections, page zones, profile).

    ``headings``: dicts with id, page, text, prominence, numbered (decimal or keyword
    numbering), keyword_role (role hint of a sectioning word) and book_title.
    """
    total = len(pages)
    nav = {n.page: n.kind for n in navigation_pages}
    by_number = {p["page"]: p for p in pages}
    content = [h for h in headings if h["page"] not in nav]
    by_page = {}
    for heading in content:
        by_page.setdefault(heading["page"], []).append(heading)
    openers = sorted({h["page"] for h in content if h["keyword_role"] in OPENER_ROLES})
    keyword_openers = len(openers)
    numbered = [h for h in content if h["numbered"]]
    opener_reason = "numbered by a part/unit/chapter word"
    if len(openers) < 2 and numbered:
        top = max(h["prominence"] for h in numbered)
        openers = sorted({h["page"] for h in numbered if h["prominence"] == top})
        opener_reason = "most prominent numbered heading"
    run_of = {}
    for index, run in enumerate(runs):
        for number in range(run["first_page"], run["last_page"] + 1):
            run_of[number] = index
        for number in run.get("inferred_pages", []):
            run_of.setdefault(number, index)
    arabic = [r["first_page"] for r in runs if r["kind"] == "arabic"]
    first_body = openers[0] if openers else (min(arabic) if arabic else 1)
    body_rule = "first section opener"
    if keyword_openers < 2 and arabic:
        # Fewer than two sectioning-word openers: a most prominent numbered heading is weak
        # evidence for where the body starts; the first Arabic folio run is stronger.
        first_body, body_rule = min(arabic), "first Arabic folio run (fewer than two openers)"
    main_run = run_of.get(first_body)
    numbered_pages = sorted({h["page"] for h in numbered})
    main_numbered = [p for p in numbered_pages
                     if p >= first_body and run_of.get(p) == main_run]  # fmt: skip
    last_numbered = max(main_numbered, default=first_body)
    section_prominence = sorted(h["prominence"] for h in numbered if h["page"] >= first_body)
    threshold = section_prominence[len(section_prominence) // 2] if section_prominence else None
    rear_start, rear_reason = None, None
    for number in range(last_numbered + 1, total + 1):
        if main_run is not None and run_of.get(number) not in (main_run, None):
            break
        top = max(by_page.get(number, []), key=lambda h: h["prominence"], default=None)
        if nav.get(number) in {"glossary", "index"}:
            rear_start, rear_reason = number, f"printed {nav[number]}"
        elif top is not None and title_kind(top["text"]) in {"appendix", "bibliography"}:
            rear_start, rear_reason = number, f"titled {title_kind(top['text'])}"
        elif (top is not None and not top["numbered"] and threshold is not None
              and top["prominence"] >= threshold):  # fmt: skip
            rear_start, rear_reason = number, "unnumbered top heading after the numbered sections"
        if rear_start is not None:
            break
    main_end = max((n for n, r in run_of.items() if r == main_run), default=total)
    zones, reasons = {}, {}
    for number in range(1, total + 1):
        run = run_of.get(number)
        if number < first_body:
            zone, why = "front", f"before the body start ({body_rule})"
        elif run == main_run or (run is None and number <= main_end):
            if rear_start is not None and number >= rear_start:
                zone, why = "rear", f"rear matter from p{rear_start}: {rear_reason}"
            else:
                zone, why = "body", f"between section openers ({opener_reason})"
        elif run is not None and any(run_of.get(p) == run for p in numbered_pages):
            zone, why = "body", "own label series holding numbered sections"
        else:
            zone, why = "rear", "after the main page run"
        zones[number] = zone
        reasons[number] = [why]
    kinds = {n: _kind(by_number[n], zones[n], nav, by_page, config) for n in zones}
    sections = _sections(pages, zones, kinds, set(openers), by_page, run_of)
    page_zones = []
    for section in sections:
        for number in range(section.first_page, section.last_page + 1):
            page_zones.append(
                PageZone(
                    page=number, zone=section.zone, section_id=section.id,
                    section_kind=section.kind, confidence=section.confidence,
                    reasons=reasons[number] + [kinds[number][1]],
                    review_required=section.review_required,
                )
            )  # fmt: skip
    profile = {
        "openers": openers,
        "opener_rule": opener_reason,
        "first_body_page": first_body,
        "body_start_rule": body_rule,
        "last_numbered_page": last_numbered,
        "rear_start_page": rear_start,
        "rear_reason": rear_reason,
    }
    return sections, sorted(page_zones, key=lambda z: z.page), profile


def _kind(page, zone, nav, by_page, config):
    """(section kind, why) for one page."""
    number = page["page"]
    letters = sum(u["letters"] for u in page["units"])
    text = " ".join(u["text"] for u in page["units"])
    heads = by_page.get(number, [])
    top = max(heads, key=lambda h: h["prominence"], default=None)
    named = title_kind(top["text"]) if top else None
    credit_letters = page["letters_by_stream"].get("credit", 0)
    if number in nav and (nav[number] != "bibliography" or zone == "rear"):
        return NAVIGATION_SECTIONS[nav[number]], f"printed navigation: {nav[number]}"
    if zone == "front":
        if named in {"preface", "dedication"}:
            return named, f"titled {named}"
        if number <= config["cover_pages"] and letters < config["cover_letters"]:
            return "cover", "little text at the start of the book"
        if any(h.get("book_title") for h in heads):
            return "title_page", "the book title"
        if _ISBN.search(text):
            return "copyright", "copyright sign or ISBN"
        return "front_other", "front matter page"
    if zone == "rear":
        if named in {"appendix", "bibliography"}:
            return named, f"titled {named}"
        if named == "credits" or (letters and credit_letters / letters >= 0.5):
            return "credits", "credit text"
        return "rear_other", "rear matter page"
    role = next((h["keyword_role"] for h in heads if h["keyword_role"] in OPENER_ROLES), None)
    return role or "chapter", "section opener" if role else "body page"


def _sections(pages, zones, kinds, openers, by_page, run_of):
    rows, current = [], None
    for page in pages:
        number = page["page"]
        zone, (kind, _) = zones[number], kinds[number]
        if current is not None and current["zone"] == zone and run_of.get(number) == current["run"]:
            if zone == "body" and number not in openers:
                current["last"] = number
                continue
            if zone != "body" and kind == current["kind"]:
                current["last"] = number
                continue
        top = max(by_page.get(number, []), key=lambda h: h["prominence"], default=None)
        current = {"zone": zone, "kind": kind, "first": number, "last": number,
                   "run": run_of.get(number), "heading": top["id"] if top else None,
                   "opener": number in openers}  # fmt: skip
        rows.append(current)
    result = []
    for index, row in enumerate(rows):
        confidence = 0.9 if row["opener"] or row["zone"] != "body" else 0.7
        if row["kind"] in {"front_other", "rear_other"}:
            confidence = 0.65
        result.append(
            Section(
                id=stable_id("section", row["zone"], row["kind"], row["first"]),
                zone=row["zone"], kind=row["kind"], first_page=row["first"],
                last_page=row["last"], heading_id=row["heading"], logical_index=index,
                confidence=confidence, reasons=[f"{row['zone']} matter: {row['kind']}"],
                review_required=confidence < REVIEW_BELOW,
                evidence={"label_run": row["run"], "opener": row["opener"]},
            )
        )  # fmt: skip
    return result


def logical_order(sections, toc_links):
    """Reorder ``logical_index`` by the table of contents: a body block in another label run
    whose sections the contents list before the first main body section moves ahead of it."""
    targets = [link.target_page for link in toc_links
               if link.source_page is not None and link.target_page is not None]  # fmt: skip
    body = [s for s in sections if s.zone == "body"]
    if not targets or not body:
        return sections, None
    main_run = body[0].evidence.get("label_run")
    listed = []
    for target in targets:
        section = next((s for s in body if s.first_page <= target <= s.last_page), None)
        if section is not None and (not listed or listed[-1] is not section):
            listed.append(section)
    if not listed:
        return sections, None
    run = listed[0].evidence.get("label_run")
    if run == main_run:
        return sections, None
    moved = [s for s in body if s.evidence.get("label_run") == run]
    rest = [s for s in sections if s not in moved]
    insert_at = rest.index(body[0])
    reordered = rest[:insert_at] + moved + rest[insert_at:]
    result = []
    for index, section in enumerate(reordered):
        update = {"logical_index": index}
        if section in moved:
            update["reasons"] = [
                *section.reasons,
                "the table of contents lists this block before the first body section",
            ]
        result.append(section.model_copy(update=update))
    return sorted(result, key=lambda s: s.first_page), {
        "moved_first_page": moved[0].first_page,
        "moved_last_page": moved[-1].last_page,
        "placed_before_page": body[0].first_page,
    }
