"""Step 17: the published book JSON (assembly stage), client profiles, styling, review list."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from test_cache_keys import closure
from test_continuity import Detectors, _book, _run

from book_core import caching
from book_core.assembly import schema as S
from book_core.assembly import validate
from book_core.assembly.build import DIVIDER, group_lists, sid
from book_core.assembly.fonts import FontTable, small_caps_span, style_words
from book_core.assembly.lossless import compare, json_tokens
from book_core.assembly.names import split_names
from book_core.assembly.profile import ClientProfile, load_profile, ocr_settings
from book_core.book_run import run_book
from book_core.cache_store import read_json
from book_core.ledger.tokenization import token_counter
from book_core.model.common import BBox, Provenance
from book_core.model.spans import TextSpan
from book_core.tables.settings import TableSettings

# --- schema --------------------------------------------------------------------------------


def test_the_committed_schema_is_the_generated_one():
    committed = validate.SCHEMA_FILE.read_text("utf-8")
    assert committed == validate.schema_text(), "regenerate assembly/book.schema.json"
    schema = json.loads(committed)
    assert schema["title"].endswith(S.SCHEMA_VERSION)
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema)


def _minimal():
    meta = S.Metadata(
        source=S.SourceInfo(sha256="a" * 64, pages=1),
        converter=S.Converter(name="book_core", version="0", producer="b" * 64),
        profile=S.ProfileInfo(id="default", version="1.0.0", sha256="c" * 64),
        settings_sha256="d" * 64,
        content_sha256="e" * 64,
    )
    paragraph = S.Paragraph(
        id="0123456789abcdef", pages=[1], order=1, provenance=S.Provenance(stages=["lists"]),
        content=S.TextContent(text="Hello\nworld", spans=[S.InlineSpan(kind="bold", start=0,
                                                                        end=5)]),
    )  # fmt: skip
    marker = S.PageMarker(
        id="fedcba9876543210",
        pages=[1],
        order=0,
        provenance=S.Provenance(stages=["furniture"]),
        page=1,
        label="1",
    )
    return S.Book(
        metadata=meta,
        pages=[S.PageEntry(index=1, width=400, height=600)],
        content=[marker, paragraph],
    ).model_dump(mode="json", by_alias=True)


def test_a_valid_book_passes_and_round_trips_identically():
    data = _minimal()
    assert validate.errors(data) == []
    text = validate.dumps(data)
    again = S.Book.model_validate(json.loads(text)).model_dump(mode="json", by_alias=True)
    assert validate.dumps(again) == text


@pytest.mark.parametrize(
    ("change", "where"),
    [
        (lambda d: d["content"][1].pop("content"), "content/1"),
        (lambda d: d["content"][1].update(id="not-hex"), "content/1/id"),
        (lambda d: d["content"][1].update(surprise=1), "content/1"),
        (lambda d: d["content"][1]["content"]["spans"][0].update(kind="blink"), "content/1"),
        (lambda d: d["metadata"].pop("source"), "metadata"),
        (lambda d: d["pages"][0].update(index=0), "pages/0/index"),
        (lambda d: d.update(schema={"name": "universal-book", "version": "9.9.9"}), "schema"),
    ],
)
def test_broken_files_fail_clearly(change, where):
    data = _minimal()
    change(data)
    found = validate.errors(data)
    assert found and any(path.startswith(where) for path, _ in found), found
    with pytest.raises(validate.InvalidBook, match="schema error"):
        validate.check(data)


def test_model_rules_refuse_impossible_units():
    with pytest.raises(ValueError, match="ends past"):
        S.TextContent(text="ab", spans=[S.InlineSpan(kind="italic", start=0, end=3)])
    with pytest.raises(ValueError, match="line end"):
        S.TextContent(text="ab", joins=[S.LineJoin(at=1, decision="join", confidence=0.9)])
    with pytest.raises(ValueError, match="alt-text slot"):
        S.Equation(id="0123456789abcdef", pages=[1], order=0,
                   provenance=S.Provenance(stages=["mathml"]), output="image",
                   image=S.Image(file="e.png", format="png", width=1, height=1, dpi=72,
                                 sha256="a" * 64, bytes=1))  # fmt: skip
    with pytest.raises(ValueError, match="external URI or an internal target"):
        S.InlineSpan(kind="link", start=0, end=1)


@pytest.mark.parametrize("end", [0, 100])
def test_file_validation_checks_span_offsets_as_well_as_schema_types(end):
    data = _minimal()
    data["content"][1]["content"]["spans"][0]["end"] = end
    with pytest.raises(validate.InvalidBook, match="content/1"):
        validate.check(data)


# --- client profiles -----------------------------------------------------------------------


def test_the_default_profile_follows_the_reference_conventions(tmp_path):
    profile = load_profile()
    assert profile.profile.id == "default"
    assert profile.captions.placement == "after"
    assert profile.names.split is False and profile.alt_text.mode == "empty"
    assert profile.images.name_pattern == "page_{label}_{n}"
    assert profile.ocr.word_thresholds == {"pp_ocrv5": 0.94, "tesseract": 0.84}
    assert len(profile.sha256) == 64 and profile.sha256 == load_profile().sha256
    as_json = tmp_path / "profile.json"
    as_json.write_text(json.dumps(profile.model_dump(mode="json")), "utf-8")
    assert load_profile(as_json).sha256 == profile.sha256


@pytest.mark.parametrize(
    "text",
    [
        '[profile]\nid="x"\nversion="1.0.0"\nsurprise=1\n',
        '[profile]\nid="x"\nversion="1.0.0"\n[images]\nnaming="a"\n',
        '[profile]\nid="x"\nversion="1.0.0"\n[images]\nname_pattern="page_{n}"\n',
        '[profile]\nid="x"\nversion="1.0.0"\n[ocr]\naccuracy_mode="fastest"\n',
        '[profile]\nid="x"\nversion="1.0.0"\n[ocr.word_thresholds]\nabbyy=0.5\n',
        '[profile]\nid="x"\nversion="one"\n',
        '[profile]\nid="x"\nversion="1.0.0"\n[output]\nsections=["furniture","colophon"]\n',
    ],
)
def test_unknown_keys_and_bad_values_are_errors(tmp_path, text):
    path = tmp_path / "bad.toml"
    path.write_text(text, "utf-8")
    with pytest.raises(ValueError):
        load_profile(path)


def test_profile_ocr_settings_and_hash_change_with_a_setting(tmp_path):
    from book_core.ocr.settings import OcrSettings

    base = load_profile()
    changed = ClientProfile.model_validate(
        {
            **base.model_dump(mode="json"),
            "ocr": {"accuracy_mode": "tesseract_only", "word_thresholds": {"tesseract": 0.8}},
        }
    )
    assert changed.sha256 != base.sha256
    settings = OcrSettings(
        executable=tmp_path / "t.exe",
        tessdata=tmp_path,
        asset_manifest=tmp_path / "m.json",
        second_reader="off",
    )
    mapped = ocr_settings(changed, settings)
    assert mapped.accuracy_mode == "tesseract_only"
    assert mapped.calibration("tesseract").word_threshold == 0.8
    assert mapped.calibration("pp_ocrv5").word_threshold == 0.94  # the measured default


# --- fonts, small caps, names, dividers ----------------------------------------------------


def _span(sid_, text, font="Times-Roman", size=10.0, flags=0, color=0, x=0.0, method="native"):
    return TextSpan(id=sid_, line_id="l1", page=1, raw_text=text, text=text,
                    bbox=BBox(x0=x, y0=0, x1=x + 5 * len(text), y1=size), font=font, size=size,
                    color=color, flags=flags,
                    provenance=Provenance(source_sha256="a" * 64, method=method))  # fmt: skip


def test_tied_script_and_direction_use_the_first_text_evidence():
    from book_core.assembly.text import build_text

    first = _span("a", "a").model_copy(update={"script": "Latin", "text_direction": "ltr"})
    second = _span("b", "b").model_copy(update={"script": "Hebrew", "text_direction": "rtl"})
    spans = {s.id: s for s in (first, second)}
    for order in ((first, second), (second, first)):
        content = build_text(
            [("line", [(s.id, None, None) for s in order])], spans
        ).content
        assert (content.script, content.direction) == (order[0].script, order[0].text_direction)


def test_suppression_preserves_tokens_split_across_source_spans():
    from book_core.assembly.text import Segment, build_text, source_runs

    spans = {s.id: s for s in (_span("a", "r"), _span("b", "t"))}
    visible = build_text([("line", [("a", None, None), ("b", None, None)])], spans,
                         frozenset({"b"})).content
    hidden = spans["b"]
    suppressed = {"text": "t", "retained_by_ledger": True,
                  "source_runs": [r.model_dump() for r in source_runs(
                      [Segment(0, 1, hidden, 0, 1, "line")], spans)]}
    data = {"content": [{"type": "paragraph", "content": visible.model_dump()}],
            "furniture": [], "suppressed": [suppressed]}
    assert visible.text == "r" and suppressed["text"] == "t"
    result = compare(data, Counter({"rt": 1}))
    assert (result["missing"], result["extra"]) == (0, 0)


def test_source_slices_follow_line_sequence_after_cache_key_sorting():
    from book_core.assembly.text import Segment, ordered_spans, source_runs
    from book_core.model.spans import SourceLine, SpanStore

    # The cache serializes object keys alphabetically. The space must stay between
    # the label and its number when independently suppressed spans are reconstructed.
    spans = {s.id: s for s in (_span("z", "CHAPTER"), _span("a", " "), _span("m", "3"))}
    store = SpanStore(spans=spans, lines=[SourceLine(
        id="l1", page=1, bbox=spans["z"].bbox, span_ids=["z", "a", "m"])])
    cached = SpanStore.model_validate_json(json.dumps(store.model_dump(), sort_keys=True))
    ordered = ordered_spans(cached)
    suppressed = []
    for span in ordered.values():
        runs = source_runs([Segment(0, len(span.text), span, 0, len(span.raw_text), "line")],
                           ordered)
        suppressed.append({"text": span.text, "retained_by_ledger": True,
                           "source_runs": [run.model_dump() for run in runs]})
    data = {"content": [], "furniture": [], "suppressed": suppressed}
    result = compare(data, Counter({"CHAPTER": 1, "3": 1}))
    assert (result["missing"], result["extra"]) == (0, 0)


def test_font_styles_are_learned_per_book_from_names_and_flags():
    assert style_words("ABCDEF+MinionPro-SemiboldIt") == ["semibold", "it"]
    assert style_words("TimesNewRomanPS-BoldItalicMT") == ["bold", "italic", "mt"]
    assert style_words("Arial,Bold") == ["bold"]
    table = FontTable()
    store = SimpleNamespace(spans={s.id: s for s in [
        _span("a", "plain", "Body-Regular"),
        _span("b", "flagged", "Display", flags=1 << 4),
        _span("c", "slanted", "Text-Itali"),
        _span("d", "both", "Sans-BoldOblique"),
        _span("e", "code", "Code-Semibold-SC700", flags=1 << 4),
        _span("f", "ocr word", "unknown", method="ocr"),
    ]})  # fmt: skip
    table.add(store)
    table.freeze()
    assert (table.style("Body-Regular").bold, table.style("Body-Regular").italic) == (False, False)
    assert table.style("Display").bold  # flags alone, no name word
    assert table.style("Text-Itali").italic and not table.disagreements  # truncated name word
    assert table.style("Sans-BoldOblique").bold and table.style("Sans-BoldOblique").italic
    assert not table.style("Code-Semibold-SC700").small_caps  # a code, not small capitals
    assert table.style("unknown") is None  # OCR spans carry no font evidence


def test_small_caps_need_capitals_set_smaller_than_the_line():
    assert small_caps_span("HISTORY", 7.5, 10)
    assert not small_caps_span("History", 7.5, 10)
    assert not small_caps_span("HISTORY", 10, 10)


def test_index_dividers_are_one_to_three_letters_of_any_script():
    for text in ("A", "Ch", "Ж", "X–Z", "Ω"):
        assert DIVIDER.match(text)
    for text in ("A1", "Abraham", "12", "A, B, C"):
        assert not DIVIDER.match(text)


def test_name_splitting_keeps_the_printed_text_and_flags_every_name():
    (name,) = split_names("Lincoln, Abraham, 45, 112", "index_entry", (0, 16))
    assert (name.family, name.given, name.start, name.end) == ("Lincoln", "Abraham", 0, 16)
    assert name.review_status == "needs_review"
    found = split_names("Smith, J. A., & Brown, K. (2001). Children of immigrants.",
                        "bibliography_entry")  # fmt: skip
    assert [n.family for n in found] == ["Smith", "Brown"]
    assert split_names("ancient world, 12", "index_entry", (0, 13)) == []


def test_list_items_group_into_segments_and_nested_lists_into_their_parent():
    def item(uid, list_id):
        node = S.ListItem(id=sid(uid), pages=[1], order=0, provenance=S.Provenance(
            stages=["lists"]), content=S.TextContent(text=uid))  # fmt: skip
        node._list = (list_id, 1)
        return node

    a, b = "a" * 64, "b" * 64
    ctx = SimpleNamespace(counts=Counter(), lists={
        "L1": {"kind": "bulleted", "level": 1, "confidence": 0.9, "reasons": ["r"]},
        "L2": {"kind": "numbered", "level": 2, "parent_item_id": b, "confidence": 0.9,
               "reasons": ["r"]}})  # fmt: skip
    paragraph = S.Paragraph(id="0" * 16, pages=[1], order=0,
                            provenance=S.Provenance(stages=["lists"]),
                            content=S.TextContent(text="p"))  # fmt: skip
    out = group_lists([item(a, "L1"), item(b, "L1"), item("c" * 64, "L2"), paragraph,
                       item("d" * 64, "L1")], ctx)  # fmt: skip
    first, para, second = out
    assert [i.id for i in first.items] == [sid(a), sid(b)]
    (nested,) = first.items[1].children
    assert nested.list_type == "numbered" and nested.items[0].id == sid("c" * 64)
    assert isinstance(para, S.Paragraph) and second.segment == 1 and second.list_id == first.list_id


# --- end to end: a small book --------------------------------------------------------------


def _book_json(result):
    return json.loads((Path(result["book_json"]) / "book.json").read_text("utf-8"))


def _ledger(archive):
    from book_core.model.spans import ExtractedPage

    retained, discarded = Counter(), Counter()
    for path in sorted(Path(archive).glob("page_*.json.gz")):
        page = ExtractedPage.model_validate(read_json(path)["source"])
        for line in page.store.lines:
            tokens = token_counter(page.store.raw_line_text(line))
            (retained if page.geometry.content_bbox.contains_center(line.bbox)
             else discarded).update(tokens)  # fmt: skip
    return retained, discarded


def test_an_entry_keeps_its_own_level_inside_a_flat_index_list(tmp_path):
    from book_core.assembly.build import Context, PageBuild
    from book_core.model.spans import ExtractedPage

    result = _run(_book(tmp_path / "entries.pdf"), tmp_path / "out", tmp_path / "cache", 1)
    payload = read_json(Path(result["output"]) / "page_000001.json.gz")
    fonts = FontTable()
    fonts.add(ExtractedPage.model_validate(payload["source"]).store)
    fonts.freeze()
    list_id = "f" * 64
    ctx = Context(profile=load_profile(), fonts=fonts, language=None, book={}, headings={},
                  run_in={}, styled={}, lists={list_id: {"kind": "index", "level": 1}},
                  navigation={}, markers={}, zones={})
    page = PageBuild(ctx, 1, payload, None, {})
    source = next(u for u in page.units.values() if u.kind == "paragraph")
    for level in (1, 2, 3, None):
        entry = source.model_copy(update={"kind": "index_entry", "list_id": list_id,
                                          "level": level, "item_role": "sub_entry"})
        node = page.unit_node(entry)
        assert node.level == level
        (group,) = group_lists([node], ctx)
        assert group.level == 1
        restored = S.ListNode.model_validate(json.loads(group.model_dump_json()))
        assert restored.items[0].level == level


def test_a_small_book_is_published_valid_lossless_and_identical_with_two_workers(tmp_path):
    pdf = _book(tmp_path / "continued.pdf")
    serial = _run(pdf, tmp_path / "a_out", tmp_path / "a", 1)
    data = _book_json(serial)
    assert validate.errors(data) == []
    assert data["metadata"]["profile"]["id"] == "default"
    assert data["metadata"]["run"]["date"] is None
    # Lossless: every retained token is in content, furniture or suppressed text.
    retained, discarded = _ledger(serial["output"])
    result = compare(data, retained, discarded)
    assert (result["missing"], result["extra"]) == (0, 0), result
    # The paragraph continued across the page carries the break, its marker and the hyphen.
    units = {u.id: u for u in S.iter_units(S.Book.model_validate(data).content)}
    (first,) = [u for u in units.values() if u.continues_to and u.continues_to.kind == "page"
                and u.type == "paragraph"]  # fmt: skip
    assert first.continues_to.hyphen == "join" and first.continues_to.page_marker.page == 2
    assert units[first.continues_to.unit].continues_from.unit == first.id
    assert first.content.text.rstrip().endswith("develop-")
    # The continued table names its repeated header row.
    tables = [u for u in units.values() if u.type == "table"]
    assert [t.continuation.repeated_header_rows for t in tables if t.continuation] == [1]
    # Page markers open every page, in order; ids are unique; order is the traversal.
    markers = [u for u in data["content"] if u["type"] == "page_marker"]
    assert [m["page"] for m in markers] == [1, 2, 3, 4]
    orders = [u.order for u in S.iter_units(S.Book.model_validate(data).content)]
    assert orders == list(range(len(orders))) and len(units) == len(orders)
    # Two workers: byte-identical output folder.
    parallel = _run(pdf, tmp_path / "b_out", tmp_path / "b", 2)

    def files(result):
        base = Path(result["book_json"])
        return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in base.rglob("*") if p.is_file()}  # fmt: skip

    assert files(serial) == files(parallel)
    # The run date is outside the content hash.
    dated = run_book(pdf, tmp_path / "c_out", tmp_path / "a", workers=1, device="cpu",
                     table_settings=TableSettings(model_evidence="on"),
                     table_evidence=Detectors(), run_date="2026-10-23")  # fmt: skip
    other = _book_json(dated)
    assert other["metadata"]["run"]["date"] == "2026-10-23"
    assert other["metadata"]["content_sha256"] == data["metadata"]["content_sha256"]


def _styled(path):
    with pymupdf.open() as document:
        page = document.new_page(width=420, height=600)
        y, x = 80, 40
        for text, font, size, dy in (("Plain text with ", "helv", 10, 0),
                                     ("strong", "hebo", 10, 0), (" and ", "helv", 10, 0),
                                     ("slanted", "heit", 10, 0), (" words, area m", "helv", 10, 0),
                                     ("2", "helv", 6, -4),
                                     (" and a link here.", "helv", 10, 0),
                                     ("12", "helv", 6, -4)):  # fmt: skip
            page.insert_text((x, y + dy), text, fontsize=size, fontname=font)
            width = pymupdf.get_text_length(text, fontname=font, fontsize=size)
            if text == " and a link here.":
                start = x + pymupdf.get_text_length(" and a ", fontname=font, fontsize=size)
                end = start + pymupdf.get_text_length("link", fontname=font, fontsize=size)
                page.insert_link(
                    {
                        "kind": pymupdf.LINK_URI,
                        "uri": "https://example.org/a",
                        "from": pymupdf.Rect(start, y - 9, end, y + 2),
                    }
                )
            x += width
        page.insert_text((40, y + 40), "The next line has an underlined word in it.",
                         fontsize=10)  # fmt: skip
        start = 40 + pymupdf.get_text_length("The next line has an ", fontsize=10)
        end = start + pymupdf.get_text_length("underlined", fontsize=10)
        page.draw_line((start, y + 42), (end, y + 42), width=0.6)
        page.insert_text((40, y + 80), "Hidden words printed white on white paper.",
                         fontsize=10, color=(1, 1, 1))  # fmt: skip
        page.insert_text((40, y + 120), "Visible closing sentence of the page.", fontsize=10)
        # Synthetic italic: an upright font drawn with a sheared matrix.
        point = pymupdf.Point(40, y + 160)
        page.insert_text(point, "Upright then", fontsize=10)
        start = pymupdf.Point(40 + pymupdf.get_text_length("Upright then ", fontsize=10), y + 160)
        page.insert_text(start, "sheared", fontsize=10,
                         morph=(start, pymupdf.Matrix(1, 0, -0.25, 1, 0, 0)))  # fmt: skip
        page.insert_text((205, 580), "7", fontsize=8)
        document.save(path)
    return path


def test_styles_links_underline_and_white_on_white_text(tmp_path):
    pdf = _styled(tmp_path / "styled.pdf")
    result = run_book(pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    data = _book_json(result)
    assert validate.errors(data) == []
    spans = []
    for unit in S.iter_units(S.Book.model_validate(data).content):
        content = getattr(unit, "content", None)
        if isinstance(content, S.TextContent):
            spans += [(s.kind, content.text[s.start : s.end], s.href) for s in content.spans]
    assert ("bold", "strong", None) in spans
    assert ("italic", "slanted", None) in spans
    assert ("superscript", "12", None) in spans  # a footnote marker: the baseline rule
    assert ("math", "m2", None) in spans  # math keeps its own record, never sup/sub twice
    assert not any(kind == "superscript" and text == "2" for kind, text, _ in spans)
    assert ("link", "link", "https://example.org/a") in spans
    assert ("underline", "underlined", None) in spans
    assert ("italic", "sheared", None) in spans  # slanted glyphs, an upright font
    assert not any(kind == "italic" and "Upright" in text for kind, text, _ in spans)
    # White text on white paper: render-proven hidden, dropped from content, listed.
    (hidden,) = [s for s in data["suppressed"] if s["reason"] == "not_rendered"]
    assert "white on white" in hidden["text"] and hidden["retained_by_ledger"]
    tokens = json_tokens(data)
    assert tokens["content"]["white"] == 0 and tokens["suppressed_retained"]["white"] == 2
    retained, discarded = _ledger(result["output"])
    assert compare(data, retained, discarded)["missing"] == 0
    kinds = {i["kind"] for i in data["review"]["items"]}
    assert "hidden_text" in kinds
    hidden_reviews = [i for i in data["review"]["items"] if i["kind"] == "hidden_text"]
    assert hidden_reviews and all(i["unit"] == hidden["id"] for i in hidden_reviews)


def test_cache_closure_covers_the_assembly_stages():
    assert closure("assembly/cache.py") <= set(caching.coverage_files("assembly"))
    assert closure("assembly/hidden.py") <= set(caching.coverage_files("assembly_evidence"))
    assert closure("assembly/links.py") <= set(caching.coverage_files("assembly_evidence"))
    assert "assembly" in caching.DEPENDENCIES["final"]
    assert closure("book_run.py") <= set(caching.coverage_files("final"))


def test_a_marker_glued_to_its_word_stays_in_the_text():
    from book_core.assembly.build import _glued
    from book_core.lists.models import Marker
    from book_core.model.common import SpanRef
    from book_core.model.spans import SourceLine

    spans = {s.id: s for s in [_span("a", "Inspection of the area"), _span("b", "1. Next")]}
    store = SimpleNamespace(
        spans=spans, lines=[SourceLine(id="l1", page=1, bbox=spans["a"].bbox, span_ids=["a", "b"])]
    )
    store.raw_line_text = lambda line: "".join(spans[s].raw_text for s in line.span_ids)
    glued = Marker(refs=[SpanRef(span_id="a", start=0, end=1)], type="upper_roman", value=1)
    real = Marker(refs=[SpanRef(span_id="b", start=0, end=2)], type="decimal", value=1)
    assert _glued(glued, store) and not _glued(real, store)


def test_the_page_flag_is_the_share_of_flagged_words_per_reader():
    from book_core.ocr.settings import default_calibrations
    from book_core.ocr.tokens import page_status

    tess, pp = default_calibrations()["tesseract"], default_calibrations()["pp_ocrv5"]
    assert (tess.word_threshold, pp.word_threshold) == (0.84, 0.94)
    assert page_status([], tess) == "must_check"
    assert page_status([0.95] * 95 + [0.5] * 5, tess) is None  # 5% flagged
    assert page_status([0.95] * 90 + [0.5] * 10, tess) == "must_check"  # 10% >= 9.2%
    assert page_status([0.9] * 10, pp) == "must_check"  # below PP-OCRv5's own threshold
    assert page_status([0.9] * 10, None) == "needs_review"


def test_only_a_disagreeing_second_reading_flags_a_word_and_pp_reads_first_where_measured():
    from book_core.ocr.cache import pp_first
    from book_core.ocr.engines import OcrAlternative, OcrWord
    from book_core.ocr.tokens import disagrees

    word = OcrWord("café", (0, 0, 1, 1), 0.9, (1,))
    same = word.__class__(**{**word.__dict__, "alternatives": (
        OcrAlternative("pp", "café", 0.9, (0, 0, 1, 1)),)})  # fmt: skip
    other = word.__class__(**{**word.__dict__, "alternatives": (
        OcrAlternative("pp", "cafe", 0.9, (0, 0, 1, 1)),)})  # fmt: skip
    assert not disagrees(same) and disagrees(other) and not disagrees(word)
    settings = SimpleNamespace(accuracy_mode="best_measured", pp_primary=("chi_sim", "chi_tra"))
    horizontal = SimpleNamespace(words=(OcrWord(
        "中文", (0, 0, 40, 10), 0.9, (1,), script="Hani", text_direction="ltr"),))
    vertical = SimpleNamespace(words=(OcrWord(
        "中文", (0, 0, 10, 40), 0.9, (1,), script="Hani"),))
    assert pp_first(settings, ("chi_sim", "osd"), horizontal, horizontal)
    assert not pp_first(settings, ("chi_sim", "eng"), horizontal, horizontal)
    assert not pp_first(settings, ("chi_sim",), vertical, horizontal)
    assert not pp_first(settings, ("chi_sim",), horizontal, vertical)
    assert not pp_first(settings, ("chi_sim",), horizontal, SimpleNamespace(words=()))
    assert not pp_first(settings, ("chi_sim",), SimpleNamespace(words=()), horizontal)
    assert not pp_first(settings, ("chi_sim",), horizontal)
    assert not pp_first(settings, ("chi_sim",))
    assert not pp_first(SimpleNamespace(accuracy_mode="tesseract_only", pp_primary=("chi_sim",)),
                        ("chi_sim",), horizontal, horizontal)  # fmt: skip


@pytest.mark.parametrize("runs", [[(0, 0)], [(0, 4)], [(0, 2), (1, 3)]])
@pytest.mark.parametrize("suppressed", [False, True])
def test_source_slices_are_bounded_and_non_overlapping(runs, suppressed):
    slices = [S.SourceRun(page=1, line="a" * 16, span="b" * 16,
                          position=0, start=a, end=b) for a, b in runs]
    with pytest.raises(ValueError, match="source run|Source runs"):
        if suppressed:
            S.Suppressed(id="c" * 16, reason="not_rendered", page=1,
                         refs=S.SourceRefs(), text="abc", source_runs=slices,
                         retained_by_ledger=True)
        else:
            S.TextContent(text="abc", source_runs=slices)


def test_figure_whitespace_between_suppressed_words_keeps_the_source_boundary():
    from book_core.assembly.build import PageBuild

    builder = object.__new__(PageBuild)
    builder.units = {"unit": SimpleNamespace(id="unit", line_ids=["line"])}
    builder.table_owned_units = lambda: set()
    builder.table_owned_lines = lambda: set()
    run = dict(page=1, line="a" * 16, span="b" * 16, source_start=0)
    space = S.TextContent(text=" ", source_runs=[S.SourceRun(**run, position=1, start=0, end=1)])
    builder.text = lambda *args, **kwargs: (SimpleNamespace(lines=["line"]), space)
    figure_text = builder.figure_text(SimpleNamespace(unit_id="unit"), False)
    assert figure_text is not None and figure_text.content.text == " "
    suppressed = [dict(text=text, retained_by_ledger=True,
                       source_runs=[dict(**run, position=position, start=0, end=len(text))])
                  for position, text in [(0, "CHAPTER"), (2, "3")]]
    book = {"content": [{"type": "figure", "text": [figure_text.model_dump()]}],
            "suppressed": suppressed}
    tokens = json_tokens(book)
    assert sum(tokens.values(), Counter()) == Counter({"CHAPTER": 1, "3": 1})


@pytest.mark.parametrize("mode", ["empty", "model_draft"])
def test_explicit_profile_controls_alt_text_drafts(tmp_path, mode):
    from test_figures import _figure_book, _figures

    from book_core.figures.models import AltText
    from book_core.figures.settings import FigureSettings

    source = tmp_path / "figure.pdf"
    _figure_book(source, 1, True)
    calls = []

    class Stub:
        def describe(self, rgb):
            calls.append(rgb.shape)
            return AltText(text="A draft.", source="model_draft", model="stub")

    profile = ClientProfile.model_validate(
        {**load_profile().model_dump(), "alt_text": {"mode": mode}})
    result = run_book(source, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu",
                      profile=profile,
                      figure_settings=FigureSettings(alt_text_drafts=mode == "empty"),
                      alt_text_generator=Stub())
    figures = [f for f in _figures(result) if f["image"]]
    assert figures
    assert bool(calls) == (mode == "model_draft")
    assert all(f["alt_text"]["source"] == ("model_draft" if calls else "none") for f in figures)
