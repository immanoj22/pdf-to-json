"""A vector-heavy page (Step 18: 2.17 million path items on one Spanish page) is read
without holding its whole parse: large cached payloads are validated element by element and
give the same model and the same bytes as the ordinary reader.
"""

import pytest
from pydantic import ValidationError

import book_core.cache_store as store
from book_core.cache_store import read_model, release_free_memory, write_model
from book_core.model.common import BBox, Provenance
from book_core.objects.models import NativeObjectPage, PageObject, PathItem, RenderGlyph
from book_core.objects.models import TextRenderInfo as Info


def vector_page(blank_page, paths=400):
    """A native page with 30 drawings of ``paths`` path items and a glyph each."""
    provenance = Provenance(engine="pymupdf", method="native")
    objects = [
        PageObject(
            id=f"{n:016x}",
            kind="drawing",
            bbox=BBox(x0=n, y0=n, x1=n + 1, y1=n + 2),
            source_page=1,
            stroke=[0.0, 0.0, 0.0],
            path_items=[
                PathItem(operator="l", coordinates=[n, k, n + 0.5, k + 0.25]) for k in range(paths)
            ],
            render_info=[
                Info(
                    seqno=n,
                    render_type=0,
                    font="F",
                    size=9.5,
                    color=[0.0],
                    direction=(1.0, 0.0),
                    writing_mode=0,
                    glyphs=[
                        RenderGlyph(
                            unicode=65,
                            glyph_id=3,
                            origin=(n, 1.5),
                            bbox=None if n % 2 else BBox(x0=0, y0=0, x1=1, y1=1),
                        )
                    ],
                )
            ],
            provenance=provenance,
        )  # fmt: skip
        for n in range(30)
    ]
    return blank_page.model_copy(update={"objects": [*blank_page.objects, *objects]})


@pytest.fixture
def blank_page(tmp_path):
    import pymupdf

    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

    path = tmp_path / "blank.pdf"
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), "Map key", fontsize=9)
        doc.save(path)
    return PyMuPDFExtractor("cpu").extract_object_page(path, 1)


def test_a_large_payload_reads_element_by_element_to_the_same_model(
    tmp_path, monkeypatch, blank_page
):
    page = vector_page(blank_page)
    write_model(tmp_path / "1.json", page, "key")
    ordinary = read_model(tmp_path / "1.json", NativeObjectPage, "key")
    calls = []
    monkeypatch.setattr(store, "LARGE_PAYLOAD_BYTES", 1)
    monkeypatch.setattr(store, "release_free_memory", lambda: calls.append(1))
    by_element = read_model(tmp_path / "1.json", NativeObjectPage, "key")
    assert calls == [1]
    assert by_element == ordinary == page
    assert by_element.model_dump_json(exclude_defaults=True) == page.model_dump_json(
        exclude_defaults=True
    )


def test_a_large_payload_is_still_fully_validated(tmp_path, monkeypatch, blank_page):
    page = vector_page(blank_page, paths=2)
    payload = page.model_dump_json(exclude_defaults=True).replace('"operator":"l"', '"op":"l"', 1)
    store.write_payload(tmp_path / "1.json", payload, "key")
    monkeypatch.setattr(store, "LARGE_PAYLOAD_BYTES", 1)
    with pytest.raises(ValidationError):
        read_model(tmp_path / "1.json", NativeObjectPage, "key")


def test_path_items_and_glyphs_hold_no_attribute_dict():
    item = PathItem(operator="c", coordinates=[1, 2, 3, 4, 5, 6])
    glyph = RenderGlyph(unicode=66, glyph_id=4, origin=(1, 2), bbox=None)
    assert not hasattr(item, "__dict__") and not hasattr(glyph, "__dict__")
    with pytest.raises(ValidationError):
        PathItem(operator="l", coordinates=[1, 2], extra=1)


def test_releasing_free_memory_is_safe_to_call():
    release_free_memory()
    release_free_memory()
