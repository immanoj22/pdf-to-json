"""One review item per target and cause: an aggregate flag never repeats its causes."""

from pathlib import Path

from test_continuity import _book, _run

from book_core.assembly.build import Context, PageBuild
from book_core.assembly.fonts import FontTable
from book_core.assembly.profile import load_profile
from book_core.cache_store import read_json
from book_core.model.spans import ExtractedPage
from book_core.structure.decide import DEFAULT_CONFIG
from book_core.structure.headings import likely_miss


def test_an_uncertain_boundary_is_one_structure_item(tmp_path):
    result = _run(_book(tmp_path / "book.pdf"), tmp_path / "out", tmp_path / "cache", 1)
    payload = read_json(Path(result["output"]) / "page_000001.json.gz")
    fonts = FontTable()
    fonts.add(ExtractedPage.model_validate(payload["source"]).store)
    fonts.freeze()
    ctx = Context(profile=load_profile(), fonts=fonts, language=None, book={}, headings={},
                  run_in={}, styled={}, lists={}, navigation={}, markers={}, zones={})  # fmt: skip
    page = PageBuild(ctx, 1, payload, None, {})
    source = next(u for u in page.units.values() if u.kind == "paragraph")
    uncertain = source.model_copy(update={
        "review_required": True,
        "boundary": source.boundary.model_copy(update={"review_required": True}),
    })  # fmt: skip
    node = page.unit_node(uncertain)
    structure = [reason for _, kind, reason in ctx.flag_rows[node.id] if kind == "structure"]
    assert structure == ["unit boundary below confidence"]
    # Without a specific cause the aggregate decision is still flagged.
    alone = source.model_copy(update={"review_required": True})
    node = page.unit_node(alone)
    structure = [reason for _, kind, reason in ctx.flag_rows[node.id] if kind == "structure"]
    assert structure == ["list or entry decision below confidence"]


def test_a_near_miss_heading_candidate_is_flagged_for_review(tmp_path):
    """Missed headings were mostly unflagged (Step 18: 1 of 35): a unit scored just below
    the heading decision is published as text with a heading review item."""
    result = _run(_book(tmp_path / "book.pdf"), tmp_path / "out", tmp_path / "cache", 1)
    payload = read_json(Path(result["output"]) / "page_000001.json.gz")
    fonts = FontTable()
    fonts.add(ExtractedPage.model_validate(payload["source"]).store)
    fonts.freeze()
    page = PageBuild(None, 1, payload, None, {})
    source = next(u for u in page.units.values() if u.kind == "paragraph")
    rows = {}
    for near in ({}, {source.id: 0.45}):
        ctx = Context(profile=load_profile(), fonts=fonts, language=None, book={}, headings={},
                      run_in={}, styled={}, lists={}, navigation={}, markers={}, zones={},
                      near_headings=near)  # fmt: skip
        node = PageBuild(ctx, 1, payload, None, {}).unit_node(source)
        rows[bool(near)] = [r for _, k, r in ctx.flag_rows[node.id] if k == "heading"]
    assert rows == {False: [], True: ["heading-like text not marked as a heading"]}


def _candidate(gap_before, reasons, value, **evidence):
    config = {**DEFAULT_CONFIG}
    unit = {"gap_before": gap_before}
    return likely_miss(unit, value, reasons, {"repeated_pages": 0, **evidence}, config)


def test_only_an_unopposed_isolated_one_off_near_miss_is_a_likely_miss():
    """Every near miss flagged gave a review list mostly of body text (Step 19 first run:
    flag precision 0.33): a likely miss has nothing against it, space before it, and does
    not recur."""
    plain = ["weight/slant/case/colour contrast with the body (+0.20)", "short (+0.10)",
             "space before (+0.10)"]  # fmt: skip
    assert _candidate(2.0, plain, 0.4)
    assert not _candidate(0.5, plain, 0.4)  # no space before it
    assert not _candidate(2.0, [*plain, "starts lowercase (-0.40)"], 0.0)  # counter-evidence
    assert not _candidate(2.0, plain, 0.3)  # a rule lowered its score
    assert not _candidate(2.0, plain, 0.4, mixed_weight=True)  # a lead running into text
    assert not _candidate(2.0, plain, 0.4, list_run=5)  # one of a run of list entries
    assert not _candidate(2.0, plain, 0.4, repeated_pages=6)  # a recurring title
    assert not _candidate(2.0, plain, 0.4, label_sections=4)  # a label once per section
