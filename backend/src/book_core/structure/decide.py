"""Whole-book structure decisions from pass-1 evidence (pure: evidence in, decisions out).

1. Body style and style groups (``styles``).
2. Printed navigation kinds and contents links (``navigation``).
3. Heading detection (``headings``), with contents and outline links as evidence.
4. Book parts (``zones``) from folio runs, top-level headings and navigation.
5. Levels and roles (``hierarchy``), section by section; logical order of inserted blocks.
"""

from __future__ import annotations

from collections import Counter

from book_core.extraction.fingerprints import stable_id
from book_core.model.common import SpanRef
from book_core.structure import headings as detection
from book_core.structure.classifier import group_statistics, item_features
from book_core.structure.headings import BOX_STREAMS
from book_core.structure.hierarchy import FLOAT_STREAMS, assign
from book_core.structure.models import REVIEW_BELOW, Heading, RejectedCandidate
from book_core.structure.navigation import _title_kind as title_kind
from book_core.structure.navigation import classify, toc_links
from book_core.structure.numbering import numbering
from book_core.structure.styled import annotate, styled_text
from book_core.structure.styles import body_style, group_of, group_table, prominence
from book_core.structure.zones import decide_zones, logical_order

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


def _detection_confidence(value, threshold):
    return round(min(0.97, 0.55 + 0.35 * (value - threshold)), 4)


def decide_book(evidence, config, classifier=None):
    pages = evidence["pages"]
    source = evidence["source_sha256"]
    body = body_style(pages)
    navigation_pages, statistics, rejected_navigation = classify(
        pages, evidence.get("toc_pages", []), config
    )
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
        group = group_of(max(titles, key=lambda m: (m["letters"], m["size"])), body)
        marker = next((numbering(m["text"]) for m in members if numbering(m["text"])), None)
        link = next((link_of[m["unit"]] for m in members if m["unit"] in link_of), None)
        repeats = max(scores[m["unit"]][2].get("repeated_pages", 0) for m in members)
        items.append({
            "id": stable_id(source, "heading", first["unit"]),
            "page": first["page"],
            "order": order[first["unit"]],
            "units": [m["unit"] for m in members],
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
            or (item["stream"] in FLOAT_STREAMS and item["prominence"][0] < 3)
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
        next(i for i in early if i["page"] == title_page)["book_title"] = True
    zone_headings = [
        {"id": i["id"], "page": i["page"], "text": i["text"], "prominence": i["prominence"],
         "numbered": i["numbered"],
         "keyword_role": i["role_hint"] if (i["numbering"] or {}).get("kind") == "keyword"
         else None,
         "book_title": i.get("book_title", False)}
        for i in items if i["run_in"] is None and not i["attached"]
    ]  # fmt: skip
    sections, page_zones, zone_profile = decide_zones(
        pages, evidence.get("runs", []), navigation_pages, zone_headings, config
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
                          reasons=reasons[:8] or ["below threshold"])
        for unit, value, reasons in near
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
            "rejected_navigation_pages": {str(k): v for k, v in rejected_navigation.items()},
            "zones": zone_profile,
            "styled": styled_profile,
            "logical_order_moves": moved,
            "review_below": REVIEW_BELOW,
        },
        "_candidates": candidates_out,
    }
