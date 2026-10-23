"""The whole book: two passes over a final archive, then links, order, navigation, review.

Pass 1 learns what needs the whole book: the font table (``assembly.fonts``), the content
languages, and the place of every unit (internal link targets resolve to the unit at the
target point). Pass 2 builds each page (``assembly.build.PageBuild``). Then:

- continuity chains become ``continues_from``/``continues_to`` on the units (with the page
  marker and the hyphen decision at the break); table chains also carry the repeated header
  rows and the column map; segments of one list are linked the same way;
- every unit gets its position in the book's reading order (``order``, depth first);
- navigation: the printed table of contents (resolved entries), the heading outline, the
  sections (front, body, rear) and the page list;
- the review list (``assembly.review``) and the metadata with the content hash.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from book_core.assembly import schema as S
from book_core.assembly.build import Context, PageBuild, content_hash, rnd, sid
from book_core.assembly.fonts import FontTable
from book_core.assembly.review import review_list
from book_core.cache_store import read_json


def _units_and_boxes(payload):
    """[(unit id, page box)] of the final view's text units of one page."""
    spans = payload["source"]["store"]["spans"]
    view = payload["table_view"]
    removed = set(view["removed"])
    units = [u for u in payload["units"]["units"] if u["id"] not in removed] + view["added"]
    found = []
    for unit in units:
        boxes = [spans[s]["bbox"] for lid in unit["line_ids"]
                 for s in payload["line_spans"].get(lid, []) if s in spans]  # fmt: skip
        if boxes:
            found.append(
                (
                    unit["id"],
                    min(b["x0"] for b in boxes),
                    min(b["y0"] for b in boxes),
                    max(b["x1"] for b in boxes),
                    max(b["y1"] for b in boxes),
                )
            )
    return found


def _target_unit(units, point):
    """The unit holding ``point``, else the first unit starting at or below it."""
    x, y = point
    inside = [u for u in units if u[1] - 1 <= x <= u[3] + 1 and u[2] - 1 <= y <= u[4] + 1]
    if inside:
        return min(inside, key=lambda u: (u[4] - u[2]) * (u[3] - u[1]))[0]
    below = [u for u in units if u[2] >= y - 2]
    if below:
        return min(below, key=lambda u: (u[2], u[1]))[0]
    return None


def assemble(archive, *, native_page, evidence_page, profile, converter, settings_sha256,
             run_date=None, progress=None):  # fmt: skip
    """(Book, Context) of one final archive.

    ``native_page(n)``: the native object page (span geometry, drawings) or None (OCR);
    ``evidence_page(n, page)``: {"links": [PageLink], "not_rendered": {span: proof}}."""
    archive = Path(archive)
    book = read_json(archive / "book.json.gz")
    manifest = read_json(archive / "manifest.json.gz")
    total = manifest["pages"]
    from book_core.model.spans import ExtractedPage

    fonts, letters, places, evidence = FontTable(), Counter(), {}, {}
    for number in range(1, total + 1):
        payload = read_json(archive / f"page_{number:06d}.json.gz")
        page = ExtractedPage.model_validate(payload["source"])
        fonts.add(page.store)
        for unit in payload["units"]["units"]:
            if unit["kind"] in {"running_head", "running_foot", "folio", "production_mark",
                                "artifact", "invisible"}:  # fmt: skip
                continue
            text = "".join(page.store.spans[s].text for lid in unit["line_ids"]
                           for s in payload["line_spans"].get(lid, [])
                           if s in page.store.spans)  # fmt: skip
            letters[unit.get("language") or "und"] += sum(c.isalpha() for c in text)
        places[number] = _units_and_boxes(payload)
        evidence[number] = evidence_page(number, page)
        if progress:
            progress("assembly_pass1", number, total)
    fonts.freeze()
    known = Counter({k: v for k, v in letters.items() if k not in {"und", None}})
    language = known.most_common(1)[0][0] if known else None
    structure = book["structure"]
    headings = {h["unit_ids"][0]: h for h in structure["headings"] if not h["run_in"]}
    run_in = {}
    for h in structure["headings"]:
        if h["run_in"]:
            for uid in h["unit_ids"]:
                run_in.setdefault(uid, []).append(h)
    ctx = Context(
        profile=profile,
        fonts=fonts,
        language=language,
        book=book,
        headings=headings,
        run_in=run_in,
        styled={uid: s["role"] for s in structure["styled"] for uid in s["unit_ids"]},
        lists={item["id"]: item for item in book["lists"]["book"]["lists"]},
        navigation={n["page"]: n["kind"] for n in structure["navigation_pages"]},
        markers={m["page"]: m for m in book["furniture"]["markers"]},
        zones={z["page"]: z for z in structure["page_zones"]},
        archive=archive,
    )
    for found in evidence.values():
        for link in found.get("links", []):
            if link.target_page and link.target_point and link.target_page in places:
                target = _target_unit(places[link.target_page], link.target_point)
                ctx.link_targets[(link.target_page, link.target_point)] = (
                    sid(target) if target else None)  # fmt: skip
    content, pages = [], []
    for number in range(1, total + 1):
        payload = read_json(archive / f"page_{number:06d}.json.gz")
        build = PageBuild(ctx, number, payload, native_page(number), evidence[number])
        nodes = build.build()
        marker = ctx.markers.get(number, {})
        geometry = build.page.geometry
        page_source = _page_source(build)
        zone = ctx.zones.get(number, {})
        page_flags = []
        page_status = "ok"
        if build.ocr is not None:
            ocr_status = build.ocr.get("review_status")
            if ocr_status in {"needs_review", "must_check"}:
                page_status = ocr_status
                page_flags.append(f"ocr_page: OCR page review ({ocr_status})")
                ctx.review.append((None, number, "ocr_page", "the page was read by OCR; "
                                   f"page status {ocr_status}", ocr_status, None))  # fmt: skip
        if marker.get("review_required"):
            page_flags.append("page_label: the printed page label is uncertain")
            page_status = "needs_review" if page_status == "ok" else page_status
            ctx.review.append((None, number, "page_label", "the printed page label is uncertain",
                               "needs_review", None))  # fmt: skip
        pages.append(S.PageEntry(
            index=number, label=marker.get("label"), label_source=marker.get("source", "none"),
            width=rnd(geometry.width), height=rnd(geometry.height), rotation=geometry.rotation,
            source=page_source, zone=zone.get("zone"),
            section=sid(zone["section_id"]) if zone.get("section_id") else None,
            review_status=page_status, flags=page_flags))  # fmt: skip
        content.append(S.PageMarker(
            id=sid(f"page-marker:{book['source_sha256']}:{number}"), pages=[number], order=0,
            provenance=S.Provenance(stages=["furniture"], reasons=marker.get("reasons", [])[:3]),
            page=number, label=marker.get("label"), label_source=marker.get("source", "none"),
            confidence=round(marker.get("confidence", 1.0), 4)))  # fmt: skip
        content.extend(nodes)
        if progress:
            progress("assembly_pass2", number, total)
    index = {unit.id: unit for unit in S.iter_units(content)}
    link_chains(book.get("continuity", {}), index, ctx)
    link_segments(content, ctx)
    for position, unit in enumerate(S.iter_units(content)):
        unit.order = position
    navigation = navigation_of(structure, ctx, content)
    review = review_list(content, ctx)
    sections = profile.output.sections
    styles = S.Styles(
        fonts=[S.FontStyle(name=s.name, bold=s.bold, italic=s.italic, small_caps=s.small_caps,
                           characters=s.characters, evidence=s.evidence)
               for s in fonts.styles.values()],
        body_font=fonts.body_font(),
    )  # fmt: skip
    total_letters = sum(known.values()) or 1
    title = next((u.content.text.replace("\n", " ").strip() for u in S.iter_units(content)
                  if isinstance(u, S.Heading) and u.role == "book_title"), None)  # fmt: skip
    assets = [
        S.Asset(file=name, kind=row["kind"], sha256=row["sha256"], bytes=row["bytes"],
                unit=row["unit"])
        for name, row in sorted(ctx.images.items())
    ]  # fmt: skip
    draft = S.Book(
        metadata=S.Metadata(
            title=title,
            languages=[S.Language(code=code, share=round(n / total_letters, 4))
                       for code, n in known.most_common() if n / total_letters >= 0.005],
            source=S.SourceInfo(sha256=book["source_sha256"], pages=total),
            converter=S.Converter(**converter),
            profile=S.ProfileInfo(id=profile.profile.id, version=profile.profile.version,
                                  sha256=profile.sha256),
            settings_sha256=settings_sha256,
            content_sha256="0" * 64,
            run=S.RunInfo(date=run_date),
        ),
        pages=pages,
        content=content,
        furniture=ctx.furniture if "furniture" in sections else None,
        navigation=navigation if "navigation" in sections else None,
        suppressed=sorted(ctx.suppressed, key=lambda s: (s.page, s.id))
        if "suppressed" in sections else None,
        review=review if "review" in sections else None,
        styles=styles if "styles" in sections else None,
        assets=assets,
    )  # fmt: skip
    data = draft.model_dump(mode="json", by_alias=True, exclude_none=False)
    draft.metadata.content_sha256 = content_hash(data)
    return draft, ctx


def _page_source(build):
    methods = {s.provenance.method for s in build.spans.values() if s.raw_text.strip()}
    if methods == {"ocr"}:
        return "ocr"
    if "ocr" in methods:
        return "mixed"
    return "native"


def link_chains(continuity, index, ctx):
    """Continuity breaks → ``continues_from``/``continues_to`` (and table continuations)."""
    missing = 0
    for chain in continuity.get("chains", []):
        for brk in chain["breaks"]:
            a, b = index.get(sid(brk["from_id"])), index.get(sid(brk["to_id"]))
            if a is None or b is None:
                missing += 1
                continue
            join = brk.get("join") or {}
            hyphen = (join.get("hyphen") or {}).get("choice")
            review = "needs_review" if brk["review_required"] else "ok"
            marker = (S.PageMarkerRef(page=brk["to_page"], label=brk.get("page_label"))
                      if brk["kind"] == "page" else None)  # fmt: skip
            common = dict(
                kind=brk["kind"],
                page_marker=marker,
                hyphen=hyphen,
                word_join=bool(join.get("word")),
                skipped=[sid(x) for x in brk["skipped_ids"]],
                confidence=round(brk["confidence"], 4),
                review_status=review,
            )
            a.continues_to = S.Continuation(unit=b.id, **common)
            b.continues_from = S.Continuation(unit=a.id, **common)
            if chain["kind"] == "table" and isinstance(b, S.Table):
                b.continuation = S.TableContinuation(
                    repeated_header_rows=brk["repeated_header_rows"],
                    column_map=list(brk["column_map"]))  # fmt: skip
            if brk["review_required"]:
                ctx.review.append((a.id, brk["from_page"], "join",
                                   "continuation across the break is uncertain",
                                   "needs_review", None))  # fmt: skip
    for candidate in continuity.get("candidates", []):
        if candidate.get("review_required") and candidate.get("from_id"):
            ctx.review.append((sid(candidate["from_id"]), candidate["from_page"], "join",
                               "a possible continuation was not joined: "
                               + candidate["reasons"][0], "needs_review", None))  # fmt: skip
    for dropped in continuity.get("dropped_links", []):
        ctx.review.append((sid(dropped["from_unit_id"]) if dropped.get("from_unit_id")
                           else None, dropped.get("from_page", 1), "join",
                           "continuation withdrawn: " + str(dropped.get("reason")),
                           "needs_review", None))  # fmt: skip
    ctx.counts["continuity_members_not_in_content"] = missing


def link_segments(content, ctx):
    """Consecutive segments of one list are linked like other continued units."""
    last = {}
    for unit in S.iter_units(content):
        if not isinstance(unit, S.ListNode):
            continue
        previous = last.get(unit.list_id)
        if previous is not None and previous.continues_to is None and unit.continues_from is None:
            kind = "column" if previous.pages[-1] == unit.pages[0] else "page"
            marker = S.PageMarkerRef(page=unit.pages[0]) if kind == "page" else None
            previous.continues_to = S.Continuation(unit=unit.id, kind=kind, page_marker=marker,
                                                   confidence=1.0)  # fmt: skip
            unit.continues_from = S.Continuation(
                unit=previous.id, kind=kind, page_marker=marker, confidence=1.0
            )
        last[unit.list_id] = unit


def navigation_of(structure, ctx, content):
    published = {u.id for u in S.iter_units(content)}
    toc = []
    for link in structure["toc_links"]:
        toc.append(S.TocEntry(
            entry=sid(link["entry_id"]) if sid(link["entry_id"]) in published else None,
            target_page=link.get("target_page"), target_label=link.get("target_label"),
            target_units=[sid(u) for u in link.get("unit_ids", []) if sid(u) in published],
            level=link.get("level"), confidence=round(link["confidence"], 4)))  # fmt: skip
    outline, stack = [], []
    for heading in structure["headings"]:
        if heading["run_in"]:
            continue
        hid = sid(heading["unit_ids"][0])
        if hid not in published:
            continue
        while stack and stack[-1][0] >= heading["level"]:
            stack.pop()
        outline.append(S.OutlineEntry(heading=hid, level=heading["level"], role=heading["role"],
                                      page=heading["page"],
                                      parent=stack[-1][1] if stack else None))  # fmt: skip
        stack.append((heading["level"], hid))
    sections = [S.Section(id=sid(s["id"]), zone=s["zone"], kind=s["kind"],
                          first_page=s["first_page"], last_page=s["last_page"],
                          heading=sid(s["heading_id"]) if s.get("heading_id")
                          and sid(s["heading_id"]) in published else None)
                for s in structure["sections"]]  # fmt: skip
    page_list = [S.PageListEntry(page=u.page, label=u.label, marker=u.id) for u in content
                 if isinstance(u, S.PageMarker)]  # fmt: skip
    return S.Navigation(toc=toc, outline=outline, sections=sections, page_list=page_list)
