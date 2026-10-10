"""Step 10: headings, levels and roles, navigation kinds and book parts (synthetic)."""

import shutil
import unicodedata

import pytest
from test_cache_keys import closure

from book_core.caching import PACKAGE
from book_core.evaluation.derived_harness import DerivedGold
from book_core.evaluation.structure import heading_scores, toc_scores, zone_scores
from book_core.paragraphs.lexicon import TOKEN
from book_core.reading_order.continuation import beginning, ending
from book_core.structure.decide import DEFAULT_CONFIG, decide_book
from book_core.structure.features import repeat_key
from book_core.structure.keys import (
    EVIDENCE_ENTRY_POINTS,
    EVIDENCE_SCOPE,
    STRUCTURE_ENTRY_POINTS,
    evidence_code_digest,
    structure_code_digest,
    structure_scope_files,
)
from book_core.structure.models import BookStructure, Heading
from book_core.structure.numbering import numbering

SOURCE = "a" * 64
BODY = "The river carried boats and goods between the towns along its banks for many years and"


class Book:
    """Pass-1 evidence written by hand: pages of units in stream order."""

    def __init__(self, pages):
        self.pages = [
            {"page": n, "label": None, "label_kind": "none", "label_source": "none",
             "label_run": None, "letters_by_stream": {}, "units": [], "navigation": []}
            for n in range(1, pages + 1)
        ]  # fmt: skip
        self.runs, self.toc_pages, self.count = [], [], 0

    def unit(self, page, text, size=10.0, bold=False, stream="main", kind=None, color=0,
             gap=2.0, lead_run=None, entries=(), rtl=False):  # fmt: skip
        self.count += 1
        letters = [c for c in text if c.isalpha()]
        cased = [c for c in letters if c.isupper() or c.islower()]
        row = {
            "page": page, "unit": f"u{self.count}", "stream": stream,
            "stream_id": f"p{page}-{stream}",
            "kind": kind or ("paragraph" if size <= 10.5 and not bold else "heading_candidate"),
            "region": "main_text", "lines": max(1, len(text) // 80), "text": text,
            "tokens": len(TOKEN.findall(text)), "letters": len(letters), "rtl": rtl,
            "language": "und", "size": size, "bold": 1.0 if bold else 0.0, "italic": 0.0,
            "color": color, "family": "serif",
            "caps": round(sum(c.isupper() for c in cased) / len(cased), 3) if cased else None,
            "block": 0.1, "block_end": 0.1, "start": 0.0, "end": 100.0,
            "gap_before": gap, "gap_after": gap, "previous_kind": None, "next_kind": None,
            "ending": ending(text), "beginning": beginning(text),
            "navigation_entries": list(entries), "repeat_key": repeat_key(text)[:120],
            "boundary_reasons": [], "review": False, "lead_run": lead_run,
            "separator": False, "token_ordinals": [self.count * 100 + i for i in range(3)],
        }  # fmt: skip
        self.pages[page - 1]["units"].append(row)
        return row

    def body(self, page, count=3):
        for _ in range(count):
            self.unit(page, BODY + ".")

    def evidence(self):
        for page in self.pages:
            streams = {}
            for unit in page["units"]:
                streams.setdefault(unit["stream_id"], []).append(unit)
            for units in streams.values():
                for position, unit in enumerate(units):
                    unit["position"], unit["stream_units"] = position, len(units)
                for a, b in zip(units, units[1:], strict=False):
                    a["next_size"], a["next_bold"] = b["size"], b["bold"]
                    b["previous_size"], b["previous_bold"] = a["size"], a["bold"]
            page["letters_by_stream"] = {"main": sum(u["letters"] for u in page["units"])}
        return {"source_sha256": SOURCE, "pages": self.pages, "runs": self.runs,
                "bookmarks": [], "toc_pages": self.toc_pages, "cache_key_inputs": {}}  # fmt: skip


def decide(book, **config):
    return decide_book(book.evidence(), {**DEFAULT_CONFIG, **config})


def headings_by_text(decided, book):
    units = {u["unit"]: u for p in book.pages for u in p["units"]}
    return {" ".join(units[u]["text"] for u in h.unit_ids): h for h in decided["headings"]}


def chapters(book, numbered=True):
    for page, title in ((1, "Chapter 1"), (4, "Chapter 2")):
        book.unit(page, title if numbered else f"The {title.split()[1]} part", size=20, bold=True)
        book.body(page)
        book.unit(page + 1, f"{title[-1]}.1 Background of the valley", size=14, bold=True)
        book.body(page + 1)
        book.unit(page + 2, f"{title[-1]}.2 Later settlements", size=14, bold=True)
        book.body(page + 2)


def test_numbered_headings_levels_and_roles():
    book = Book(6)
    chapters(book)
    decided = decide(book)
    found = headings_by_text(decided, book)
    assert found["Chapter 1"].level == found["Chapter 2"].level == 1
    assert found["Chapter 1"].role == "chapter"
    assert found["1.1 Background of the valley"].level == 2
    assert found["2.2 Later settlements"].level == 2
    assert found["2.2 Later settlements"].role in {"section", "lesson"}
    assert all(z.zone == "body" for z in decided["page_zones"])
    assert not any(u["text"].startswith("The river") for u in [])  # body text is no heading
    assert len(decided["headings"]) == 6


def test_unnumbered_headings_by_style_only():
    book = Book(3)
    book.unit(1, "Origins of the river", size=18, bold=True)
    book.body(1)
    book.unit(2, "Early settlers", size=13, bold=True)
    book.body(2)
    book.unit(3, "Trade on the water", size=13, bold=True)
    book.body(3)
    found = headings_by_text(decide(book), book)
    assert set(found) == {"Origins of the river", "Early settlers", "Trade on the water"}
    assert found["Origins of the river"].level == 1
    assert found["Early settlers"].level == found["Trade on the water"].level == 2


def test_size_alone_is_not_enough():
    book = Book(1)
    book.unit(1, "The river carried boats between the towns along its banks.", size=10.6)
    book.body(1)
    assert decide(book)["headings"] == []


def test_run_in_heading_keeps_the_paragraph():
    book = Book(1)
    lead = {"span_ids": ["s1"], "end": 7, "tokens": 2, "letters": 10, "last": ".", "bold": True,
            "italic": False, "size_ratio": 1.0, "rest_bold": False, "rest_italic": False,
            "color_differs": False, "rest_letters": 200}  # fmt: skip
    book.body(1, 1)
    unit = book.unit(1, "Early causes. " + BODY + ".", lead_run=lead)
    decided = decide(book)
    run_in = [h for h in decided["headings"] if h.run_in]
    assert len(run_in) == 1 and run_in[0].unit_ids == [unit["unit"]]
    assert run_in[0].run_in[0].span_id == "s1" and run_in[0].run_in[0].end == 7


def test_a_one_word_label_is_not_a_run_in_heading():
    book = Book(1)
    lead = {"span_ids": ["s1"], "end": 7, "tokens": 1, "letters": 6, "last": ":", "bold": True,
            "italic": False, "size_ratio": 1.0, "rest_bold": False, "rest_italic": False,
            "color_differs": False, "rest_letters": 200}  # fmt: skip
    book.unit(1, "Source: " + BODY + ".", lead_run=lead)
    assert not [h for h in decide(book)["headings"] if h.run_in]


def toc_book():
    """Page 1: contents with two levels; pages 2-7 the chapters it lists (labels 1-6)."""
    book = Book(7)
    book.unit(1, "Contents", size=24, bold=True)
    entries = [("Chapter 1 Rivers", "1", 2.0, 2), ("1.1 Sources", "2", 4.0, 3),
               ("Chapter 2 Towns", "4", 2.0, 5), ("2.1 Markets", "5", 4.0, 6),
               ("Chapter 3 Trade", "6", 2.0, 7)]  # fmt: skip
    for index, (title, label, indent, _target) in enumerate(entries):
        entry_id = f"e{index}"
        book.unit(1, f"{title} {label}", entries=[entry_id])
        book.pages[0]["navigation"].append({
            "id": entry_id, "title": title, "target_label": label,
            "level_evidence": {"indentation_fonts": indent, "reference_side": "suffix"},
            "reference_side": "suffix", "leaders": True, "font_size": 10.0,
            "geometry_only_ambiguous": False, "confidence": 0.9, "line_ids": [],
        })  # fmt: skip
    for page in range(2, 8):
        book.pages[page - 1]["label"] = str(page - 1)
    for title, _label, indent, target in entries:
        size = 20 if indent == 2.0 else 14
        book.unit(target, title, size=size, bold=True)
        book.body(target)
    book.body(3)
    book.toc_pages = [{"page": 1}]
    book.runs = [{"kind": "arabic", "first_page": 2, "last_page": 7, "inferred_pages": [],
                  "first_label": "1", "last_label": "6", "index": 0, "prefix": "",
                  "offset": 1}]  # fmt: skip
    return book


def test_table_of_contents_with_levels_resolves_entries():
    book = toc_book()
    decided = decide(book)
    assert [(n.page, n.kind) for n in decided["navigation_pages"]] == [(1, "table_of_contents")]
    links = {link.entry_id: link for link in decided["toc_links"]}
    assert [links[f"e{i}"].target_page for i in range(5)] == [2, 3, 5, 6, 7]
    assert all(link.unit_ids for link in links.values())
    assert links["e0"].level == 1 and links["e1"].level == 2
    found = headings_by_text(decided, book)
    assert found["Chapter 1 Rivers"].level == 1 and found["1.1 Sources"].level == 2
    assert "Chapter 1 Rivers 1" not in found  # contents lines are not headings
    assert decided["page_zones"][0].zone == "front"
    assert decided["page_zones"][0].section_kind == "table_of_contents"


def test_roman_then_arabic_zones():
    book = Book(8)
    book.unit(1, "The Book of Rivers", size=30, bold=True)
    book.unit(2, "Preface", size=18, bold=True)
    book.body(2)
    book.body(3)
    book.unit(4, "Chapter 1", size=20, bold=True)
    book.body(4)
    book.body(5)
    book.unit(6, "Chapter 2", size=20, bold=True)
    book.body(6)
    book.body(7)
    book.body(8)
    book.runs = [
        {"kind": "roman", "first_page": 2, "last_page": 3, "inferred_pages": [], "index": 0},
        {"kind": "arabic", "first_page": 4, "last_page": 8, "inferred_pages": [], "index": 1},
    ]
    decided = decide(book)
    zones = [z.zone for z in decided["page_zones"]]
    assert zones == ["front"] * 3 + ["body"] * 5
    kinds = {z.page: z.section_kind for z in decided["page_zones"]}
    assert kinds[2] == "preface" and kinds[4] == "chapter"
    found = headings_by_text(decided, book)
    assert found["Preface"].role == "front_section_title" and found["Preface"].level == 1
    assert found["The Book of Rivers"].role == "book_title"


def test_right_to_left_heading():
    book = Book(4)
    for page, title in ((1, "الفصل 1"), (3, "الفصل 2")):
        book.unit(page, title, size=20, bold=True, rtl=True)
        book.unit(page, "النهر طويل جدا ويمر عبر مدن كثيرة على ضفتيه منذ سنوات طويلة.", rtl=True)
        book.unit(page + 1, "تاريخ المدن", size=14, bold=True, rtl=True)
        book.unit(page + 1, "كانت المدن صغيرة في البداية ثم كبرت مع التجارة على النهر.", rtl=True)
    found = headings_by_text(decide(book), book)
    assert found["الفصل 1"].role == "chapter" and found["الفصل 1"].level == 1
    assert found["تاريخ المدن"].level == 2
    assert numbering("פרק 4 המים")["role_hint"] == "chapter"


def test_bilingual_heading_is_one_heading():
    book = Book(1)
    book.unit(1, "Los ríos", size=18, bold=True)
    book.unit(1, "The rivers", size=18, bold=True, gap=1.2)
    book.body(1)
    decided = decide(book)
    assert len(decided["headings"]) == 1
    assert len(decided["headings"][0].unit_ids) == 2


def test_map_label_is_not_a_heading():
    book = Book(1)
    book.unit(1, "ATLANTIC OCEAN", size=12, bold=True, stream="figure", kind="figure_text")
    book.unit(1, "O C E A N   P A C I F I C O", size=14, bold=True)
    book.body(1)
    assert decide(book)["headings"] == []


def test_numbering_patterns_are_multilingual_and_dates_are_not_numbers():
    assert numbering("Capítulo 3: El río")["role_hint"] == "chapter"
    assert numbering("Unidad IV")["value"] == 4
    assert numbering("第3章 概要")["role_hint"] == "chapter"
    assert numbering("1.2.3 Methods")["depth"] == 3
    assert numbering("02")["kind"] == "number"
    assert numbering("11 DE SEPTIEMBRE DEL 2001") is None
    assert numbering("Article civil") is None


def test_level_never_skips_going_down():
    from book_core.model.common import Provenance

    def heading(i, level):
        return Heading(id=f"h{i}", page=1, unit_ids=[f"u{i}"], level=level,
                       level_method="style_rank", role="section", confidence=0.9,
                       reasons=["t"])  # fmt: skip

    with pytest.raises(ValueError, match="skips"):
        BookStructure(source_sha256=SOURCE, structure_version="t", pages=1,
                      headings=[heading(1, 1), heading(2, 3)],
                      provenance=Provenance(source_sha256=SOURCE))  # fmt: skip


def gold(units, markers=(), book="b"):
    return DerivedGold(book=book, split="development", manifest={"notes": []}, units=units,
                       markers=list(markers), pages=[])  # fmt: skip


def gold_unit(unit, kind, pdf, zone="body", level=None, path="/x/level1/h1"):
    return {"unit": unit, "kind": kind, "pdf": pdf, "zone": zone, "heading_level": level,
            "heading_level_method": "declared" if level else None, "path": path}  # fmt: skip


def test_heading_and_zone_metrics():
    book = Book(6)
    chapters(book)
    decided = decide(book)
    units = {u["unit"]: u for p in book.pages for u in p["units"]}
    tokens = {uid: [(u["page"], o) for o in u["token_ordinals"]] for uid, u in units.items()}
    first = next(u for u in units.values() if u["text"] == "Chapter 1")
    body = next(u for u in units.values() if u["text"].startswith("The river"))
    reference = gold([
        gold_unit(0, "heading", [[1, first["token_ordinals"][0], 3]], level=1),
        gold_unit(1, "paragraph", [[1, body["token_ordinals"][0], 3]]),
    ])  # fmt: skip
    zone_of = {z.page: z.zone for z in decided["page_zones"]}
    scores = heading_scores(reference, decided["headings"], tokens, zone_of)
    assert scores["recall"] == 1.0 and scores["levels"]["all"]["exact"] == 1.0
    zones = zone_scores(reference, decided["page_zones"])
    assert zones["unit_accuracy"] == 1.0 and zones["page_accuracy"] == 1.0
    assert toc_scores(reference, [], tokens) == {}


@pytest.mark.parametrize("entry", [*STRUCTURE_ENTRY_POINTS, *EVIDENCE_ENTRY_POINTS])
def test_structure_scope_covers_the_import_closure(entry):
    scope = structure_scope_files() if entry in STRUCTURE_ENTRY_POINTS else (
        structure_scope_files(scope=EVIDENCE_SCOPE)
    )  # fmt: skip
    missing = closure(entry) - set(scope)
    assert not missing, f"Step 10 cache key ignores {sorted(missing)}"


def test_decision_rules_do_not_rekey_the_evidence(tmp_path):
    copy = tmp_path / "book_core"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    evidence, structure = evidence_code_digest(copy), structure_code_digest(copy)
    target = copy / "structure" / "headings.py"
    target.write_bytes(target.read_bytes() + b"\n# edited\n")
    assert evidence_code_digest(copy) == evidence
    assert structure_code_digest(copy) != structure
    target = copy / "structure" / "features.py"
    target.write_bytes(target.read_bytes() + b"\n# edited\n")
    assert evidence_code_digest(copy) != evidence


def test_editing_any_structure_producer_changes_the_digest(tmp_path):
    copy = tmp_path / "book_core"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    original = structure_code_digest()
    assert structure_code_digest(copy) == original
    for relative in structure_scope_files(copy):
        if not relative.startswith("structure/"):
            continue
        target = copy / relative
        data = target.read_bytes()
        target.write_bytes(data + b"\n# edited\n")
        assert structure_code_digest(copy) != original, relative
        target.write_bytes(data)


def test_heading_classifier_slot():
    lightgbm = pytest.importorskip("lightgbm")
    from book_core.accuracy.interfaces import HeadingClassifier
    from book_core.structure.classifier import (
        FEATURES,
        LightGBMHeadingClassifier,
        heading_request,
        train,
    )

    rows = [{name: float((i + j) % 3) for j, name in enumerate(FEATURES)} for i in range(60)]
    labels = [int(row["rule_score"] > 0) for row in rows]
    booster = train(rows, labels)
    assert lightgbm.__version__
    path = "heading_test_model.txt"
    import pathlib
    import tempfile

    folder = pathlib.Path(tempfile.mkdtemp())
    (folder / path).write_bytes(booster.model_to_string().encode("utf-8"))
    provider = LightGBMHeadingClassifier(folder / path, threshold=0.5)
    assert isinstance(provider, HeadingClassifier)
    assert provider.metadata.model_sha256
    request = heading_request(SOURCE, {"id": "h1", "page": 1}, rows[1])
    result = provider.classify(request)
    assert result.status == "evidence" and result.heading_likelihood is not None
    assert result.label in {"heading", "not_heading"}
    shutil.rmtree(folder)


def test_page_evidence_records_style_and_run_in_lead():
    from test_furniture import PageBuilder
    from test_paragraphs import built

    from book_core.structure.features import page_evidence

    page = PageBuilder(1)
    band = page.band("b", 80, 200, [(60, 550, "column")])
    title = page.line("t", 60, 80, 300, "A river", size=18)
    rows = [page.line(f"c{i}", 60, 110 + 14 * i, 540, BODY) for i in range(3)]
    page.region("t", "heading_candidate", [title], band, 0)
    page.region("c", "main_text", rows, band, 0)
    sid = title.span_ids[0]
    page.spans[sid] = page.spans[sid].model_copy(update={"flags": 16})
    native, layout, result = built(page)
    from test_paragraphs import furnished

    _, _, furniture = furnished(page)
    evidence = page_evidence(native, layout, result, furniture, [], [])
    first = evidence["units"][0]
    assert first["text"] == unicodedata.normalize("NFKC", "A river")
    assert first["bold"] == 1.0 and first["size"] == 18.0
    assert first["next_size"] == 10.0
