"""Step 11 entry points: lists and entries for a whole book, cached per page and per book.

Pass 1 reads every page once for the book's compound lexicon (hyphen decisions of new joins
use the unchanged Step 9 rule). Pass 2 builds each page (``lists.page``) from its Step 9 units
and order, with Step 10 navigation kinds and headings and Step 8 page labels, and caches it.
The book stage then joins what continues on the next page:

- a marked list whose numbering (or bullet) continues at the start of the next page's main
  flow, and an entry list (index, glossary, bibliography, contents, definitions) continued on
  consecutive pages of the same navigation kind, are one list (``list_aliases``);
- an index or reference entry continued on the next page (its first line indented, with no
  entry open) is linked, not merged (``EntryLink``); entries never join across pages like
  prose, so a Step 9 page join between entries is dropped (recorded);
- a Step 9 page join between other units is kept, mapped to the units holding its lines.

``load_page`` applies the aliases and links to a cached page (the Step 9 pattern).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pydantic import Field

from book_core.extraction.fingerprints import stable_id
from book_core.lists.keys import book_fingerprint, book_key_components, lists_code_digest
from book_core.lists.models import ENTRY_KINDS, BookLists, EntryLink, PageLists, StructuredList
from book_core.lists.page import (
    DEFAULT_CONFIG,
    LISTS_VERSION,
    NAV_MODES,
    PageContext,
    build_page_lists,
)
from book_core.model.common import CoreModel, Provenance
from book_core.objects.analysis import atomic_write, verified_read
from book_core.paragraphs.cache import load_page as load_paragraph_page
from book_core.paragraphs.keys import book_fingerprint as paragraph_fingerprint
from book_core.paragraphs.lexicon import Profile
from book_core.settings import Settings
from book_core.structure.keys import decision_fingerprint

LOADED_DIGEST = lists_code_digest()
ENTRY_MODES = frozenset({"index", "glossary", "bibliography", "contents"})


def assert_unchanged():
    if lists_code_digest() != LOADED_DIGEST:
        raise RuntimeError("lists producer source changed; restart the worker")


class BookListsResult(CoreModel):
    book: BookLists
    page_keys: dict[int, str] = Field(default_factory=dict)
    list_aliases: dict[str, str] = Field(default_factory=dict)  # page list id -> book list id
    page_links: list[dict] = Field(default_factory=list)  # kept Step 9 joins and entry links
    continued_items: dict[str, dict] = Field(default_factory=dict)  # unit -> list id, level


def structure_key(structure):
    inputs = structure.cache_key_inputs
    return decision_fingerprint(inputs["structure_producer_sha256"], inputs["evidence_key"],
                                structure.config, structure.structure_version)  # fmt: skip


def page_contexts(structure, furniture_book, vocabulary, compounds, config):
    navigation = {n.page: n.kind for n in structure.navigation_pages}
    headings = frozenset(u for h in structure.headings if not h.run_in for u in h.unit_ids)
    run_in = frozenset(u for h in structure.headings if h.run_in for u in h.unit_ids)
    label_pages = {}
    for marker in furniture_book.markers:
        if marker.label is not None:
            label_pages.setdefault(marker.label, []).append(marker.page)

    def context(number):
        return PageContext(navigation=navigation.get(number), heading_units=headings,
                           run_in_units=run_in, label_pages=label_pages,
                           vocabulary=vocabulary, compounds=compounds, config=config)  # fmt: skip

    return context


def _summary(number, built, lists, context):
    """What the book stage needs from a page: the main flow's first and last text units."""
    main = built.order.main.id
    text = [
        u
        for u in built.units
        if u.stream_id == main
        and u.kind
        not in {"running_head", "running_foot", "folio", "production_mark", "artifact", "invisible"}
    ]
    by_list = {lst.id: lst for lst in lists}

    def describe(unit):
        if unit is None:
            return None
        lst = by_list.get(unit.list_id)
        return {
            "unit": unit.id, "kind": unit.kind, "list": unit.list_id,
            "list_kind": lst.kind if lst else None,
            "marker_type": unit.marker.type if unit.marker else None,
            "value": unit.marker.value if unit.marker else None,
            "level": unit.level,
            "open_start": "indented line without an open entry" in unit.boundary.reasons,
            "first_line": unit.line_ids[0], "last_line": unit.line_ids[-1],
        }  # fmt: skip

    return {
        "page": number,
        "mode": NAV_MODES.get(context.navigation),
        "first": describe(text[0] if text else None),
        "last": describe(text[-1] if text else None),
        "unit_of_line": {lid: u.id for u in built.units for lid in u.line_ids},
        "kind_of": {u.id: u.kind for u in built.units},
        "item_of": {
            u.id: {"list": u.list_id, "level": u.level}
            for u in built.units
            if u.kind == "list_item"
        },
    }


def _continues(last, first, previous_mode, mode):
    """Why the list of ``last`` continues with the list of ``first`` on the next page."""
    if last is None or first is None or last["list"] is None or first["list"] is None:
        return None
    if last["list_kind"] != first["list_kind"]:
        return None
    if last["list_kind"] in {"index", "glossary", "bibliography", "contents", "definition"}:
        if previous_mode == mode:
            return f"{last['list_kind']} entries continue on the next page"
        return None
    if last["marker_type"] != first["marker_type"] or last["level"] != first["level"]:
        return None
    if last["value"] is None or first["value"] == last["value"] + 1:
        return "the list's markers continue on the next page"
    return None


def analyze_book_lists(
    pages, inputs, paragraphs, paragraph_cache, structure, furniture, cache_dir,
    settings=None, config=None,
):  # fmt: skip
    """(BookListsResult, cache hit) for ``pages`` (a callable returning a fresh page iterator).

    ``paragraphs``: the Step 9 ``BookParagraphResult``; ``structure``: the Step 10
    ``BookStructure``; ``furniture``: the Step 8 book decisions (page labels).
    """
    assert_unchanged()
    settings = settings or Settings()
    config = {**DEFAULT_CONFIG, **(config or {})}
    components = book_key_components(
        lists=LOADED_DIGEST, structure_key=structure_key(structure),
        paragraph_key=paragraph_fingerprint(paragraphs.book.cache_key_inputs),
        settings=settings, config=config, version=LISTS_VERSION,
    )  # fmt: skip
    key = book_fingerprint(components)
    root = Path(cache_dir) / "lists"
    path = root / "book" / f"{key}.json"
    if path.exists():
        result = verified_read(path, BookListsResult, key)
        if result.book.source_sha256 != inputs.digest:
            raise ValueError("Lists cache belongs to another source")
        return result, True
    profile = Profile()
    for page in pages():
        layout, _ = inputs(page)
        profile.add_page(page, layout, SimpleNamespace(edges=[]))
    compounds = profile.freeze()["compounds"]
    context_of = page_contexts(structure, furniture.book, inputs.vocabulary, compounds, config)
    page_keys, summaries, page_lists = {}, [], []
    for page in pages():
        number = page.geometry.page
        layout, _ = inputs(page)
        step9 = load_paragraph_page(paragraphs, number, paragraph_cache)
        context = context_of(number)
        built, lists = build_page_lists(page, layout, step9, context,
                                        inputs.extractor.device.resolved)  # fmt: skip
        page_key = stable_id(key, "page", number)
        atomic_write(root / "page" / key / f"{number}.json", built, page_key)
        page_keys[number] = page_key
        summaries.append(_summary(number, built, lists, context))
        page_lists.append(lists)
    aliases, links, dropped, continued = _link_pages(summaries, paragraphs)
    book_lists = _book_lists(page_lists, aliases)
    book = BookLists(
        source_sha256=inputs.digest,
        lists_version=LISTS_VERSION,
        pages=len(page_keys),
        lists=book_lists,
        entry_links=[EntryLink(**{k: v for k, v in link.items() if k != "kind"})
                     for link in links if link["kind"] == "entry"],
        dropped_page_joins=dropped,
        profile={"hyphenated_compounds": len(compounds)},
        config=config,
        cache_key_inputs=components,
        provenance=Provenance(
            source_sha256=inputs.digest, engine="book_core.lists", engine_version=LISTS_VERSION,
            method="derived", resolved_device=inputs.extractor.device.resolved,
        ),
    )  # fmt: skip
    result = BookListsResult(book=book, page_keys=page_keys, list_aliases=aliases,
                             page_links=links, continued_items=continued)  # fmt: skip
    assert_unchanged()
    atomic_write(path, result, key)
    return result, False


def _link_pages(summaries, paragraphs):
    aliases, links, dropped, continued = {}, [], [], {}
    by_page = {s["page"]: s for s in summaries}
    for previous, current in zip(summaries, summaries[1:], strict=False):
        if current["page"] != previous["page"] + 1:
            continue
        last, first = previous["last"], current["first"]
        why = _continues(last, first, previous["mode"], current["mode"])
        if why:
            root = aliases.get(last["list"], last["list"])
            aliases[first["list"]] = root
        if (last and first and last["kind"] in {"index_entry", "bibliography_entry"}
                and first["kind"] == last["kind"] and first["open_start"]):  # fmt: skip
            links.append({"kind": "entry", "from_page": previous["page"],
                          "from_unit_id": last["unit"], "to_page": current["page"],
                          "to_unit_id": first["unit"], "confidence": 0.75,
                          "reasons": ["the next page opens with an indented line: the entry "
                                      "continues (linked, not merged)"]})  # fmt: skip
    for join in paragraphs.book.page_joins:
        before, after = by_page.get(join.from_page), by_page.get(join.to_page)
        if before is None or after is None:
            continue
        source = before["unit_of_line"].get(join.join.previous_line_id)
        target = after["unit_of_line"].get(join.join.next_line_id)
        kinds = (before["kind_of"].get(source), after["kind_of"].get(target))
        entry = kinds[0] in ENTRY_KINDS - {"list_item"} or kinds[1] in ENTRY_KINDS - {"list_item"}
        if source is None or target is None or entry:
            dropped.append({"from_page": join.from_page, "to_page": join.to_page,
                            "from_unit_id": source, "to_unit_id": target,
                            "reason": "entries never join across pages like prose"})  # fmt: skip
            continue
        links.append({"kind": "paragraph", "from_page": join.from_page, "from_unit_id": source,
                      "to_page": join.to_page, "to_unit_id": target})  # fmt: skip
        if (
            kinds == ("list_item", "paragraph")
            and after["first"]
            and after["first"]["unit"] == target
        ):
            # The item goes on at the top of the next page: its continuation is that item's text.
            item = before["item_of"][source]
            continued[target] = {"list_id": aliases.get(item["list"], item["list"]),
                                 "level": item["level"]}  # fmt: skip
    return aliases, links, dropped, continued


def _book_lists(page_lists, aliases):
    merged = {}
    for lists in page_lists:
        for lst in lists:
            root = aliases.get(lst.id, lst.id)
            if root not in merged:
                merged[root] = lst.model_copy(update={"id": root})
                continue
            head = merged[root]
            merged[root] = head.model_copy(update={
                "item_ids": [*head.item_ids, *lst.item_ids],
                "last_page": lst.last_page,
                "evidence": {**head.evidence,
                             "items": len(head.item_ids) + len(lst.item_ids),
                             "pages": head.evidence.get("pages", 1) + 1},
            })  # fmt: skip
    return [StructuredList.model_validate(m.model_dump()) for m in merged.values()]


def load_page(result, number, cache_dir):
    """The cached PageLists of one page with book list ids and cross-page links applied."""
    key = result.page_keys[number]
    book_key = book_fingerprint(result.book.cache_key_inputs)
    path = Path(cache_dir) / "lists" / "page" / book_key / f"{number}.json"
    page = verified_read(path, PageLists, key)
    to = {link["from_unit_id"]: link["to_unit_id"] for link in result.page_links
          if link["from_page"] == number}  # fmt: skip
    came = {link["to_unit_id"]: link["from_unit_id"] for link in result.page_links
            if link["to_page"] == number}  # fmt: skip
    units = []
    for unit in page.units:
        update = {}
        if unit.list_id in result.list_aliases:
            update["list_id"] = result.list_aliases[unit.list_id]
        if unit.id in to:
            update["continues_to"] = to[unit.id]
        if unit.id in came:
            update["continues_from"] = came[unit.id]
        if unit.id in result.continued_items:
            item = result.continued_items[unit.id]
            update.update(kind="list_item", list_id=item["list_id"], level=item["level"],
                          item_role="item")  # fmt: skip
        units.append(unit.model_copy(update=update) if update else unit)
    return page.model_copy(update={"units": units})


def chains(result):
    """{unit id: first unit of its cross-page chain} (kept paragraph joins and entry links)."""
    root = {}
    for link in sorted(result.page_links, key=lambda link: link["from_page"]):
        root[link["to_unit_id"]] = root.get(link["from_unit_id"], link["from_unit_id"])
    return root
