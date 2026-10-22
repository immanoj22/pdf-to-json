"""Step 15 shared helpers: final archives read as token owners, main-flow items and chains.

``book_view(book, capture)`` reads a final archive once, page by page, and keeps per page:

- ``owner``: {retained token ordinal: owner id}: a text-owning table (its id) when a table
  cell holds the token's line, else the final-view unit holding the line (text kinds only);
- ``main``: the page's main-flow items in reading order: (owner id, kind) for every final
  unit or table that holds main-stream lines (furniture kinds left out), consecutive lines
  of one owner collapsed;
- ``kind``/``stream``: kind and stream kind of every final unit (tables: ``table``);
- ``last_line``/``first_line`` of every unit, and the page's tables with their links.

``chains`` gives {unit id: chain root} from the units' ``continues_from`` links (and, when
present, the archive's continuity record); tables chain through ``continues_from``.
"""

# ruff: noqa: E402
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
from step14a_bundles import token_owners

from book_core.cache_store import read_json
from book_core.lists.models import TEXT_KINDS
from book_core.model.spans import ExtractedPage

OUT = ROOT / "experiments/out/step15"
FURNITURE = frozenset({"running_head", "running_foot", "folio", "production_mark", "artifact",
                       "invisible"})  # fmt: skip
FLOATS = frozenset({"table", "caption", "figure_text"})


def capture_run(capture):
    return lambda book: common.read(Path(capture) / "performance" / f"{book}.json")["run"]


def final_units(payload):
    units = payload["units"]["units"]
    view = payload["table_view"]
    removed = set(view["removed"])
    return [u for u in units if u["id"] not in removed] + view["added"]


class PageView:
    def __init__(self, number, payload, layout):
        self.number = number
        page = ExtractedPage.model_validate(payload["source"])
        self.store = page.store
        self.spans_of = {line.id: line.span_ids for line in layout.lines}
        self.layout = {line.id: line for line in layout.lines}
        self.tokens = token_owners(page, layout)
        units = final_units(payload)
        self.units = {u["id"]: u for u in units}
        self.tables = payload["tables"]["tables"]
        self.continuity = payload.get("continuity")
        table_of = {lid: t["id"] for t in self.tables for lid in t["line_ids"]}
        unit_of = {lid: u["id"] for u in units for lid in u["line_ids"]}
        self.kind = {u["id"]: u["kind"] for u in units} | {t["id"]: "table" for t in self.tables}
        self.stream = {u["id"]: u["stream_kind"] for u in units}
        self.owner = {}
        for ordinal, (lid, _) in enumerate(self.tokens):
            if lid in table_of:
                self.owner[ordinal] = table_of[lid]
            elif lid in unit_of and self.kind[unit_of[lid]] in TEXT_KINDS:
                self.owner[ordinal] = unit_of[lid]
        self.main = []
        for stream in payload["units"]["order"]["streams"]:
            if stream["kind"] != "main":
                continue
            for lid in stream["line_ids"]:
                who = table_of.get(lid) or unit_of.get(lid)
                if who is None or self.kind[who] in FURNITURE:
                    continue
                if not self.main or self.main[-1][0] != who:
                    self.main.append((who, self.kind[who]))
        self.links = {u["id"]: (u.get("continues_from"), u.get("continues_to")) for u in units}
        self.line_text = {}

    def text(self, line_id):
        if line_id not in self.line_text:
            spans = self.store.spans
            self.line_text[line_id] = "".join(spans[s].raw_text for s in self.spans_of[line_id])
        return self.line_text[line_id]


@lru_cache(maxsize=2)
def book_view(book, capture):
    run = capture_run(capture)(book)
    root = Path(run["output"])
    pages = {}
    for number in range(1, run["pages"] + 1):
        payload = read_json(root / f"page_{number:06d}.json.gz")
        pages[number] = PageView(number, payload, common.layout_page(book, number))
        del payload
    return pages, read_json(root / "book.json.gz")


def chains(pages, archive):
    """{unit or table id: chain root} over the cross-page links in the archive."""
    previous = {}
    record = archive.get("continuity")
    if record is not None:
        for chain in record["chains"]:
            members = chain["members"]
            for member in members[1:]:
                previous[member] = members[0]
        return previous
    links = {}
    for view in pages.values():
        for uid, (came, _) in view.links.items():
            if came:
                links[uid] = came
        for table in view.tables:
            if table.get("continues_from"):
                links[table["id"]] = table["continues_from"]["table_id"]

    def root(uid, seen=()):
        while uid in links and uid not in seen:
            seen = (*seen, uid)
            uid = links[uid]
        return uid

    return {uid: root(uid) for uid in links}


def neighbours(view, owner):
    """(items after, items before) ``owner`` in the page's main flow, or None outside it."""
    ids = [who for who, _ in view.main]
    if owner not in ids:
        return None
    at = ids.index(owner)
    return view.main[at + 1 :], view.main[:at]


def count(rows, key):
    return dict(Counter(r[key] for r in rows).most_common())
