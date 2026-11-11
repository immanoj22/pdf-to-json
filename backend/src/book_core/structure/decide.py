"""Whole-book structure decisions from pass-1 evidence (pure: evidence in, decisions out).

1. Body style and style groups (``styles``).
2. Printed navigation kinds and contents links (``navigation``).
3. Heading detection (``headings``), with contents and outline links as evidence.
4. Book parts (``zones``) from folio runs, top-level headings and navigation.
5. Levels and roles (``hierarchy``), section by section; logical order of inserted blocks.
"""

from __future__ import annotations

from collections import Counter

import regex

from book_core.extraction.fingerprints import stable_id
from book_core.model.common import SpanRef
from book_core.structure import headings as detection
from book_core.structure.classifier import group_statistics, item_features
from book_core.structure.headings import BOX_STREAMS
from book_core.structure.hierarchy import FLOAT_STREAMS, assign, book_role_order
from book_core.structure.models import REVIEW_BELOW, Heading, NavigationPage, RejectedCandidate
from book_core.structure.navigation import _title_kind as title_kind
from book_core.structure.navigation import classify, toc_links
from book_core.structure.numbering import numbering
from book_core.structure.styled import annotate, styled_text
from book_core.structure.styles import body_style, group_of, group_table, prominence
from book_core.structure.zones import OPENER_ROLES, decide_zones, logical_order
from book_core.structure.zones import title_kind as zone_title_kind

# A title in a float stream at least this many size steps above the body is structural
# (a chapter-opener banner); smaller float titles are attached to the section around them.
FLOAT_TITLE_STEP = 3
DEFAULT_CONFIG = {
    "threshold": 0.6,
    "reject_window": 0.3,
    "max_lines": 3,
    "max_tokens": 20,
    "long_tokens": 25,
    "large_ratio": 1.5,
    "larger_ratio": 1.15,
    "smaller_ratio": 0.9,
    "isolation_fonts": 1.6,
    "repeated_pages": 3,
    "artwork_title_ratio": 2.0,
    "merge_gap_fonts": 2.5,
    "run_in_tokens": 8,
    "list_run": 4,
    "feature_share": 0.15,
    "mixed_weight": [0.15, 0.85],
    "template_share": 0.8,
    "subtitle_alone": 0.1,
    "dated_entries": 0.5,
    "glossary_terms": 0.5,
    "outline": "contents",
    "contents_min_links": 5,
    "contents_coverage": 0.5,
    "minimum_entries": 5,
    "alphabetical_entries": 8,
    "alphabetical": 0.8,
    "alphabetical_extend": 0.6,
    "advancing": 0.7,
    "toc_span": 0.4,
    "local_toc_share": 0.2,
    "title_match": 80.0,
    "cover_pages": 2,
    "cover_letters": 400,
}


def _heading_order(item, order, page_units, main_top=None):
    """Book-order key of a heading. A title set in a float (a chapter-opener banner drawn as
    artwork) that outranks every main-flow heading candidate of its page is the page's opening
    title, not text read after the running text: like a Step 7 float anchor, it takes its
    place in the main flow before the first main-flow unit that starts below its centre. A
    float title set like a main-flow title (one piece of a title split over the artwork and
    the text) keeps the stream order.
    """
    page, index = order[item["first_unit"]["unit"]]
    unit = item["first_unit"]
    if unit["stream"] not in FLOAT_STREAMS or item["prominence"][0] < FLOAT_TITLE_STEP:
        return (page, index)
    if main_top is not None and item["prominence"] <= main_top:
        return (page, index)
    centre = (unit["block"] + unit["block_end"]) / 2
    for position, other in enumerate(page_units[page]):
        if other["stream"] == "main" and other["block"] > centre:
            return (page, position - 0.5)
    return (page, index)


def _confirmed_navigation(navigation_pages, parts):
    """Printed-navigation pages under confirmed book parts: a confirmed bibliography, glossary
    or index range is parsed as that kind of page, and a page of one of those kinds outside
    its confirmed range is no such page (the person said where each part is)."""
    from book_core.structure import parts as book_parts

    plan = book_parts.navigation_plan(parts)
    kept = [n for n in navigation_pages
            if n.page not in plan and n.kind not in book_parts.NAVIGATION.values()]  # fmt: skip
    kept += [n for n in navigation_pages if n.page in plan and n.kind == plan[n.page]]
    have = {n.page for n in kept}
    for page, kind in sorted(plan.items()):
        if page not in have:
            kept.append(NavigationPage(
                page=page, kind=kind, entries=0, confidence=1.0,
                reasons=[f"confirmed book part: {kind}"]))  # fmt: skip
    return sorted(kept, key=lambda n: n.page)


def _merge_navigation_numbers(items, order):
    """A bare number heading on the page of a heading numbered from its contents entry, with
    the entry's number, is that heading's printed number (set apart from its title, often in
    another block): one heading, not two."""
    by_page = {}
    for item in items:
        by_page.setdefault(item["page"], []).append(item)
    dropped = set()
    for item in items:
        marker = item["numbering"] or {}
        if marker.get("source") != "navigation" or marker.get("value") is None:
            continue
        for other in by_page[item["page"]]:
            mark = other["numbering"] or {}
            same = mark.get("kind") == "number" and mark.get("value") == marker["value"]
            if other is item or id(other) in dropped or other["run_in"] is not None or not same:
                continue
            pieces = sorted([other, item], key=lambda i: order[i["units"][0]])
            item["units"] = [u for piece in pieces for u in piece["units"]]
            item["text"] = " ".join(piece["text"] for piece in pieces)
            item["first_unit"], item["last_unit"] = pieces[0]["first_unit"], pieces[-1]["last_unit"]
            item["tokens"] += other["tokens"]
            item["score"] = max(item["score"], other["score"])
            dropped.add(id(other))
            break
    return [item for item in items if id(item) not in dropped]


def _bare_number(item):
    """A heading made only of a number (no title words): "2", "IV"."""
    marker = item["numbering"] or {}
    letters = sum(m["letters"] for m in item["members"])
    return (letters < 2 or marker.get("kind") == "roman") and bool(marker) and all(
        numbering(m["text"]) is not None or m["letters"] < 2 for m in item["members"]
    )


def _merge_opener_numbers(items):
    """A bare chapter number on an opener page (beside a sectioning label, often set apart
    from its title in another block or on the artwork) is the printed number of that page's
    opener title: one heading, the number first. The title is the most prominent heading of
    the page with title words; its own number, when it has one, must agree."""
    by_page = {}
    for item in items:
        by_page.setdefault(item["page"], []).append(item)
    dropped = set()
    for item in items:
        if id(item) in dropped or item["run_in"] is not None or not item["opener_number"]:
            continue
        if not _bare_number(item):
            continue
        value = (item["numbering"] or {}).get("value")
        titles = [o for o in by_page[item["page"]]
                  if o is not item and id(o) not in dropped and o["run_in"] is None
                  and not _bare_number(o)]  # fmt: skip
        if not titles:
            continue
        title = max(titles, key=lambda o: o["prominence"])
        own = (title["numbering"] or {}).get("value")
        if own is not None and value is not None and own != value:
            continue
        if title["prominence"][0] < FLOAT_TITLE_STEP or title["stream"] in BOX_STREAMS:
            continue  # not an opener title (a box title stays attached to its box): a section heading of the page
        title["units"] = [*item["units"], *title["units"]]
        title["members"] = [*item["members"], *title["members"]]
        title["text"] = f"{item['text']} {title['text']}"
        title["first_unit"] = item["first_unit"]
        title["tokens"] += item["tokens"]
        title["score"] = max(title["score"], item["score"])
        if title["numbering"] is None or title["numbering"].get("value") is None:
            title["numbering"] = item["numbering"]
        title["reasons"] = [*title["reasons"], "the bare number on this opener page is its "
                            "printed number (merged)"]  # fmt: skip
        dropped.add(id(item))
    return [item for item in items if id(item) not in dropped]


def _label_key(text):
    """Printed label for comparing levels: case, punctuation and spacing ignored."""
    return " ".join(regex.sub(r"[^\p{L}\p{N}]+", " ", text).casefold().split())


def flag_level_conflicts(items, zone_of):
    """Review flag (levels are not changed): the same printed label ("INTRODUCTION") held at
    different levels in the body of one book. The headings at a level other than the label's
    most common one are flagged; when levels tie, every one of them is."""
    by_label = {}
    for item in items:
        if item["run_in"] is not None or item.get("book_title") or item["tokens"] > 8:
            continue
        if zone_of.get(item["page"], "body") != "body":
            continue
        key = _label_key(item["text"])
        if sum(c.isalpha() for c in key) >= 3 and not item["numbered"]:
            by_label.setdefault(key, []).append(item)
    flagged = 0
    for members in by_label.values():
        counts = Counter(i["level"] for i in members)
        if len(counts) < 2:
            continue
        top = max(counts.values())
        common = [lv for lv, n in counts.items() if n == top]
        for item in members:
            if len(common) > 1 or item["level"] not in common:
                item["review_required"] = True
                item["level_conflict"] = True
                item["level_reasons"] = [*item["level_reasons"],
                    f"the same printed label is at levels {sorted(counts)} in this book"]  # fmt: skip
                flagged += 1
    return flagged


def _detection_confidence(value, threshold):
    return round(min(0.97, 0.55 + 0.35 * (value - threshold)), 4)


def decide_book(evidence, config, classifier=None):
    pages = evidence["pages"]
    source = evidence["source_sha256"]
    body = body_style(pages)
    navigation_pages, statistics, rejected_navigation = classify(
        pages, evidence.get("toc_pages", []), config
    )
    book_parts = config.get("book_parts")
    if book_parts:
        navigation_pages = _confirmed_navigation(navigation_pages, book_parts)
    links = toc_links(pages, navigation_pages, evidence.get("bookmarks", []), config)
    toc_units = {u for link in links if link.source_page is not None for u in link.unit_ids}
    outline_units = {u for link in links if link.source_page is None for u in link.unit_ids}
    link_of = {u: link for link in links for u in link.unit_ids}
    kinds = {n.page: n.kind for n in navigation_pages}
    groups, scores, near, run_ins = detection.detect(
        pages, body, kinds, toc_units, outline_units, config
    )
    units = {u["unit"]: u for page in pages for u in page["units"]}
    page_units = {page["page"]: page["units"] for page in pages}
    order = {u["unit"]: (page["page"], i) for page in pages
             for i, u in enumerate(page["units"])}  # fmt: skip
    items = []
    for members in groups:
        first = members[0]
        value = max(scores[m["unit"]][0] for m in members)
        # The title piece (not a label or bare number) sets the group's style.
        titles = [m for m in members if not detection._label(m)] or members
        # A piece that starts lowercase continues the title above it; it never sets the style.
        titles = [m for m in titles if m["beginning"] != "lower"] or [
            m for m in members if m["beginning"] != "lower"] or titles
        group = group_of(max(titles, key=lambda m: (m["letters"], m["size"])), body)
        marker = next((numbering(m["text"]) for m in members if numbering(m["text"])), None)
        opener = next((scores[m["unit"]][2].get("opener_role") for m in members
                       if scores[m["unit"]][2].get("opener_role")), None)  # fmt: skip
        if opener is not None and (marker is None or (
                marker["kind"] in {"number", "decimal"} and marker["depth"] == 1)):  # fmt: skip
            # A title on opener art beside a sectioning label ("SECTION", "C H A P T E R")
            # opens a section of the label's role; a one-level number is that section's.
            marker = {"kind": "keyword", "role_hint": opener, "depth": 1,
                      "value": (marker or {}).get("value"), "position": "start"}  # fmt: skip
        link = next((link_of[m["unit"]] for m in members if m["unit"] in link_of), None)
        entry = numbering(link.title) if link is not None and link.title else None
        if entry is not None and entry["kind"] == "keyword" and (
                marker is None or marker["kind"] != "keyword"):  # fmt: skip
            # The contents or outline entry this heading opens prints its sectioning word
            # and number ("Chapter 1 Sampling and Data" for a page titled "SAMPLING AND
            # DATA"): the heading opens a section of that role.
            marker = {**entry, "source": "navigation"}
        repeats = max(scores[m["unit"]][2].get("repeated_pages", 0) for m in members)
        items.append({
            "id": stable_id(source, "heading", first["unit"]),
            "page": first["page"],
            "order": order[first["unit"]],
            "units": [m["unit"] for m in members],
            "members": list(members),
            "opener_number": opener is not None,
            "stream": first["stream"],
            "position": first["position"],
            "tokens": sum(m["tokens"] for m in members),
            "text": " ".join(m["text"] for m in members),
            "score": value,
            "reasons": scores[first["unit"]][1],
            "evidence": {**scores[first["unit"]][2], "units": len(members)},
            "style_group": group,
            "prominence": prominence(group),
            "numbering": marker,
            "toc_level": link.level if link is not None and link.source_page else None,
            "links": [link.entry_id] if link is not None else [],
            "entry_kind": zone_title_kind(link.title) if link is not None and link.title
            else None,
            "toc_linked": link is not None and link.source_page is not None,
            "repeated": repeats,
            "feature": any(scores[m["unit"]][2].get("feature_title") for m in members),
            "template_step": any(scores[m["unit"]][2].get("template_step") for m in members),
            "recurring_title": any(scores[m["unit"]][2].get("recurring_title") for m in members),
            "first_unit": first,
            "last_unit": members[-1],
            "list_title": any(title_kind(m["text"]) for m in members) or (
                first["size"] >= body["size"] * config["large_ratio"]
                and first["page"] in kinds
                and first["size"] >= max(u["size"] for u in page_units[first["page"]]) * 0.9
            ),
            "run_in": None,
        })  # fmt: skip
    for unit_id, lead in run_ins.items():
        unit = units[unit_id]
        if any(unit_id in item["units"] for item in items):
            continue
        ratio = lead["size_ratio"]
        step_group = f"{0 if ratio < 1.12 else 1}:{'bold' if lead['bold'] else 'regular'}:mixed"
        items.append({
            "id": stable_id(source, "heading", unit_id, "run-in"),
            "page": unit["page"],
            "order": order[unit_id],
            "units": [unit_id],
            "members": [unit],
            "opener_number": False,
            "stream": unit["stream"],
            "position": unit["position"],
            "tokens": lead["tokens"],
            "text": unit["text"],
            "score": config["threshold"],
            "reasons": ["run-in: leading run in contrasting style ending in punctuation"],
            "evidence": {"run_in_tokens": lead["tokens"]},
            "style_group": step_group,
            "prominence": prominence(step_group),
            "numbering": None,
            "toc_level": None,
            "links": [],
            "repeated": 0,
            "run_in": lead,
            "first_unit": unit,
            "last_unit": unit,
        })  # fmt: skip
    items = _merge_navigation_numbers(items, order)
    items = _merge_opener_numbers(items)
    main_top = {}
    for item in items:
        if item["stream"] == "main":
            page = item["page"]
            main_top[page] = max(main_top.get(page, item["prominence"]), item["prominence"])
    for item in items:
        item["order"] = _heading_order(item, order, page_units, main_top.get(item["page"]))
    items.sort(key=lambda item: item["order"])
    # A recurring title set at least at body size in a style group made mostly of unique
    # titles is a recurring section title of that heading style ("References" closing every
    # chapter), not a feature label; labels set smaller than the body stay feature labels.
    unique, sizes = Counter(), Counter()
    for item in items:
        sizes[item["style_group"]] += 1
        unique[item["style_group"]] += item["repeated"] < config["repeated_pages"]
    for item in items:
        if (item.get("feature") and item["prominence"][0] >= 0
                and unique[item["style_group"]] * 2 > sizes[item["style_group"]]):  # fmt: skip
            item["feature"] = False
            item["section_title"] = True
            item["reasons"] = [
                *item["reasons"],
                "recurring title of a heading style made "
                "mostly of unique titles: a section title, not a feature label",
            ]
    for item in items:
        item["numbered"] = bool(item["numbering"]) and item["numbering"]["kind"] != "letter"
        item["role_hint"] = (item["numbering"] or {}).get("role_hint")
        item["attached"] = (
            item["stream"] in BOX_STREAMS
            or (item["stream"] in FLOAT_STREAMS and item["prominence"][0] < FLOAT_TITLE_STEP)
        ) or bool(item.get("feature"))
        item["spine"] = item["numbered"] or item["toc_level"] is not None
        item["detection_confidence"] = _detection_confidence(item["score"], config["threshold"])
    # The book title: the first heading of the page holding the most prominent heading
    # among the pages before the first printed list and the first numbered section.
    first_list = min((n.page for n in navigation_pages), default=len(pages) + 1)
    covers = {p["page"] for p in pages[: config["cover_pages"]]
              if sum(u["letters"] for u in p["units"]) < config["cover_letters"]}  # fmt: skip
    first_numbered = min((i["page"] for i in items if i["numbered"]), default=len(pages) + 1)
    early = [i for i in items if i["page"] < min(first_list, first_numbered)
             and not i["attached"] and i["run_in"] is None]  # fmt: skip
    if early and min(first_list, first_numbered) <= len(pages):  # front matter is bounded
        # The most prominent early title; a title page that repeats it wins over the cover.
        top = max(i["prominence"] for i in early)
        pages_with_top = sorted({i["page"] for i in early if i["prominence"] == top})
        inner = [n for n in pages_with_top if n not in covers]
        title_page = (inner or pages_with_top)[0]
        title_item = next(i for i in early if i["page"] == title_page)
        title_item["book_title"] = True
        # The title page's other lines set at hardly more than body size (an editor's name,
        # "Foreword by ...", the publisher) are credits; its only heading is the title.
        credits = [i for i in items
                   if i["page"] == title_page and i is not title_item and not i["attached"]
                   and i["run_in"] is None
                   and i["first_unit"]["size"] < body["size"] * config["large_ratio"]]  # fmt: skip
        if credits:
            items = [i for i in items if all(i is not c for c in credits)]
    zone_headings = [
        {"id": i["id"], "page": i["page"], "text": i["text"], "prominence": i["prominence"],
         "numbered": i["numbered"],
         "keyword_role": i["role_hint"] if (i["numbering"] or {}).get("kind") == "keyword"
         else None,
         "book_title": i.get("book_title", False), "entry_kind": i.get("entry_kind"),
         "toc_linked": i.get("toc_linked", False)}
        for i in items if i["run_in"] is None and not i["attached"]
    ]  # fmt: skip
    # Sectioning words in the book's own order: a section word enclosing chapters opens
    # sections too (its opener pages are body pages).
    roles = OPENER_ROLES | set(book_role_order(items, {}))
    sections, page_zones, zone_profile = decide_zones(
        pages, evidence.get("runs", []), navigation_pages, zone_headings, config, roles,
        book_parts=book_parts,
    )
    sections, moved = logical_order(sections, links)
    section_of = {z.page: z.section_id for z in page_zones}
    zone_of = {z.page: z.zone for z in page_zones}
    openers = set(zone_profile["openers"])
    styled_profile, top_linked = annotate(items, zone_of, openers, set(kinds), config)
    stats = group_statistics(items)
    by_page = {}
    for item in items:
        by_page.setdefault(item["page"], []).append(item)
    for page_items in by_page.values():
        ranked = sorted(page_items, key=lambda i: i["prominence"], reverse=True)
        for rank, item in enumerate(ranked):
            item["features"] = item_features(
                item, body, zone_of, openers, set(kinds), stats, top_linked, rank
            )
    if classifier is not None:
        likelihoods = classifier.likelihoods([item["features"] for item in items])
        for item, likelihood in zip(items, likelihoods, strict=True):
            item["classifier_likelihood"] = round(likelihood, 6)
    kept, styled = [], []

    def styled_id(heading_id):
        return stable_id(source, "styled", heading_id)

    for item in items:
        fixed = item.get("book_title") or item["run_in"] is not None
        if classifier is None or fixed:
            heading, role, why = item["rule_role"] is None, item["rule_role"], item["rule_why"]
        else:
            likelihood = item["classifier_likelihood"]
            heading = likelihood >= classifier.threshold
            role = item["rule_role"] or (
                "label" if item["prominence"][0] <= 0 and item["prominence"][2] else "display_title"
            )
            why = f"heading classifier likelihood {likelihood:.2f}"
            if item["rule_why"]:
                why += "; rules: " + item["rule_why"]
            item["reasons"] = [*item["reasons"], why]
        if heading:
            kept.append(item)
        else:
            styled.append(styled_text(item, role, why, styled_id))
    styled_profile.update({
        "display_titles": sum(s.role == "display_title" for s in styled),
        "labels": sum(s.role == "label" for s in styled),
        "classifier": classifier.identity() if classifier is not None else None,
    })  # fmt: skip
    candidates_out = items
    items = kept
    assign(items, section_of, zone_of, config)
    level_conflicts = flag_level_conflicts(items, zone_of)
    section_by_id = {s.id: s for s in sections}
    headings = []
    for item in items:
        run = item["run_in"]
        refs = []
        if run is not None:
            refs = [SpanRef(span_id=s) for s in run["span_ids"][:-1]]
            refs.append(SpanRef(span_id=run["span_ids"][-1], start=0, end=run["end"]))
        evidence_row = {k: v for k, v in item["evidence"].items()
                        if isinstance(v, (int, float, str, bool)) or v is None}  # fmt: skip
        evidence_row.update({
            "score": item["score"], "prominence": ":".join(map(str, item["prominence"])),
            "numbering": (item["numbering"] or {}).get("kind"),
            "numbering_depth": (item["numbering"] or {}).get("depth"),
            "toc_level": item["toc_level"], "attached": item["attached"],
            "level_conflict": bool(item.get("level_conflict")),
        })  # fmt: skip
        headings.append(
            Heading(
                id=item["id"], page=item["page"], unit_ids=item["units"], run_in=refs,
                level=item["level"], level_method=item["level_method"], role=item["role"],
                style_group=item["style_group"], navigation_entry_ids=item["links"],
                section_id=section_of.get(item["page"]),
                confidence=item["confidence"],
                reasons=[*item["reasons"][:8], *item["level_reasons"]],
                evidence=evidence_row, review_required=item["review_required"],
            )
        )  # fmt: skip
    for heading in headings:
        if heading.section_id not in section_by_id:
            raise ValueError("Heading section is unknown")
    rejected = [
        RejectedCandidate(unit_id=unit["unit"], page=unit["page"], score=value,
                          reasons=reasons[:8] or ["below threshold"], likely_miss=miss)
        for unit, value, reasons, miss in near
    ]  # fmt: skip
    candidates = [units[u] for u in scores]
    style_rows = group_table(candidates, body)
    accepted_groups = Counter(h.style_group for h in headings)
    return {
        "body_style": body,
        "style_groups": [
            {"group": g, **row, "headings": accepted_groups.get(g, 0)}
            for g, row in sorted(style_rows.items(), key=lambda x: prominence(x[0]), reverse=True)
        ],  # fmt: skip
        "navigation_pages": navigation_pages,
        "toc_links": links,
        "headings": headings,
        "styled": styled,
        "rejected": rejected,
        "sections": sections,
        "page_zones": page_zones,
        "profile": {
            "candidates": len(scores),
            "headings": len(headings),
            "run_in_headings": sum(bool(h.run_in) for h in headings),
            "low_confidence_headings": sum(h.review_required for h in headings),
            "level_conflict_headings": level_conflicts,
            "rejected_navigation_pages": {str(k): v for k, v in rejected_navigation.items()},
            "zones": zone_profile,
            "styled": styled_profile,
            "logical_order_moves": moved,
            "review_below": REVIEW_BELOW,
        },
        "_candidates": candidates_out,
    }
