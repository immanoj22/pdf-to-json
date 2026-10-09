"""Synthetic reference pairs: the aligner's required behaviours, on real span-store pages."""

import unicodedata

import pytest

from book_core.model.common import BBox, Provenance
from book_core.model.spans import (
    ExtractedPage,
    ExtractorIdentity,
    PageGeometry,
    SourceLine,
    SpanStore,
    TextSpan,
)
from book_core.reference.aligner import PDF_CAUSES, XML_CAUSES, align
from book_core.reference.dialects import load_dialects
from book_core.reference.pdf_tokens import page_tokens
from book_core.reference.xml_reader import ReferenceRejected, repair_header_quotes
from book_core.reference.xml_reader import read_reference as read_with
from book_core.settings import Settings

SHA = "b" * 64
DIALECTS = load_dialects(Settings().reference_dialects)


def read_reference(data: bytes):
    return read_with(data, DIALECTS)


def extracted_page(number: int, lines: list[str]) -> ExtractedPage:
    spans, source_lines = {}, []
    for index, text in enumerate(lines):
        lid, sid = f"p{number}-l{index}", f"p{number}-s{index}"
        bbox = BBox(x0=10, y0=10 + 12 * index, x1=190, y1=20 + 12 * index)
        spans[sid] = TextSpan(
            id=sid,
            line_id=lid,
            page=number,
            raw_text=text,
            text=unicodedata.normalize("NFKC", text),
            bbox=bbox,
            font="test",
            size=10,
            color=0,
            flags=0,
            provenance=Provenance(source_sha256=SHA),
        )
        source_lines.append(SourceLine(id=lid, page=number, bbox=bbox, span_ids=[sid]))
    return ExtractedPage(
        source_sha256=SHA,
        extractor=ExtractorIdentity(name="test", version="1", configuration={}),
        geometry=PageGeometry(
            page=number,
            width=200,
            height=20 + 12 * max(len(lines), 1),
            rotation=0,
            content_bbox=BBox(x0=0, y0=0, x1=200, y1=20 + 12 * max(len(lines), 1)),
        ),
        store=SpanStore(spans=spans, lines=source_lines),
    )


def pdf_page(number: int, lines: list[str]):
    return page_tokens(extracted_page(number, lines))


def run(xml: str, pages: list[list[str]]):
    doc = read_reference(xml.encode("utf-8"))
    book = [pdf_page(number, lines) for number, lines in enumerate(pages, 1)]
    return doc, book, align(doc, book)


def xml_values(doc, result, *, aligned=True):
    return [t.value for t in doc.tokens if (result.xml_page[t.index] >= 0) == aligned]


def linked_pdf(doc, book, result, index):
    page, ordinal = result.xml_page[index], result.xml_ordinal[index]
    return book[page].tokens[ordinal]


def assert_accounted(doc, book, result):
    """No token is dropped: each is aligned or carries a known cause; none is claimed twice."""
    primary = [
        (result.xml_page[i], result.xml_ordinal[i])
        for i in range(len(doc.tokens))
        if result.xml_page[i] >= 0 and result.xml_method[i] != "split"
    ]
    assert len(primary) == len(set(primary))
    for i in range(len(doc.tokens)):
        if result.xml_page[i] < 0:
            assert result.xml_cause[i] in XML_CAUSES
        else:
            assert result.xml_cause[i] == ""
    for p, page in enumerate(book):
        for o in range(len(page.tokens)):
            if result.pdf_xml[p][o] < 0:
                assert result.pdf_cause[p][o] in PDF_CAUSES
            else:
                assert result.pdf_cause[p][o] == ""


BODY = (
    "Los ríos del valle cambiaron la agricultura de la región durante siglos enteros "
    "y los pueblos construyeron canales para regar sus campos cada primavera"
)


def test_hyphenation_joins_line_broken_words():
    doc, book, result = run(
        f"<book><p>{BODY} con mucha información útil.</p></book>",
        [[BODY, "con mucha infor-", "mación útil."]],
    )
    assert not xml_values(doc, result, aligned=False)
    target = next(t for t in doc.tokens if t.value == "información")
    assert result.xml_method[target.index] == "join_hyphen"
    first = linked_pdf(doc, book, result, target.index)
    assert first.value == "infor" and first.hyphen_break
    assert [x for x, *_ in result.extra_links] == [target.index]
    assert_accounted(doc, book, result)


def test_soft_hyphen_and_spacing_split():
    doc, book, result = run(
        f"<book><p>{BODY} su deconfirmación final.</p></book>",
        [[BODY, "su de confirmación final."]],
    )
    target = next(t for t in doc.tokens if t.value == "deconfirmación")
    assert result.xml_method[target.index] == "join_split"
    doc, book, result = run(
        f"<book><p>{BODY} la agricultura moderna.</p></book>",
        [[BODY, "la agri­cultura moderna."]],
    )
    assert not xml_values(doc, result, aligned=False)
    target = [t for t in doc.tokens if t.value == "agricultura"][-1]
    assert result.xml_method[target.index] == "join_soft_hyphen"


def test_ligatures_align_through_nfkc():
    doc, book, result = run(
        f"<book><p>{BODY} financial flow and efficient office.</p></book>",
        [[BODY, "ﬁnancial ﬂow and eﬃcient oﬃce."]],
    )
    assert not xml_values(doc, result, aligned=False)
    assert all(result.xml_method[t.index] != "variant" for t in doc.tokens)
    assert_accounted(doc, book, result)


def test_furniture_only_pdf_tokens_are_classified_not_dropped():
    pages = [["Historia de los ríos", f"{BODY} parte {n}", str(10 + n)] for n in range(1, 5)]
    xml = (
        "<book>"
        + "".join(
            f'<pagenum page="normal">{10 + n}</pagenum><p>{BODY} parte {n}</p>' for n in range(1, 5)
        )
        + "</book>"
    )
    doc, book, result = run(xml, pages)
    assert not xml_values(doc, result, aligned=False)
    for p, page in enumerate(book):
        causes = {
            page.tokens[o].value: result.pdf_cause[p][o]
            for o in range(len(page.tokens))
            if result.pdf_xml[p][o] < 0
        }
        assert causes == {
            "Historia": "furniture_candidate",
            "de": "furniture_candidate",
            "los": "furniture_candidate",
            "ríos": "furniture_candidate",
            str(11 + p): "folio_candidate",
        }
    assert [s["page"] for s in result.segments[1:]] == [1, 2, 3, 4]
    assert_accounted(doc, book, result)


def test_xml_only_tokens_keep_their_cause():
    doc, book, result = run(
        "<book><head><title>Metadatos internos</title></head>"
        f"<p>{BODY}</p><imggroup><prodnote>Descripción del mapa costero</prodnote></imggroup>"
        "<p>Nota editorial añadida aparte</p></book>",
        [[BODY]],
    )
    causes = {
        t.value: result.xml_cause[t.index] for t in doc.tokens if result.xml_page[t.index] < 0
    }
    assert causes["Metadatos"] == "reference_metadata"
    assert causes["Descripción"] == causes["mapa"] == "image_description"
    assert causes["editorial"] == causes["añadida"] == "absent_from_pdf"
    assert all(o >= 0 for o in result.pdf_xml[0])
    assert_accounted(doc, book, result)


def test_duplicated_phrases_align_in_order():
    phrase = "el gato duerme en la casa"
    lines = [f"{phrase} y luego {phrase} otra vez", f"{BODY} y {phrase} al final"]
    doc, book, result = run(f"<book><p>{' '.join(lines)}</p></book>", [lines])
    assert not xml_values(doc, result, aligned=False)
    ordinals = [result.xml_ordinal[t.index] for t in doc.tokens]
    assert ordinals == list(range(len(doc.tokens)))


def test_moved_sidebar_with_duplicated_phrase():
    side = "Recuadro sobre el gato que duerme en la casa grande"
    main = f"{BODY} mientras el gato duerme en la casa"
    doc, book, result = run(
        f"<book><p>{main}</p><sidebar><p>{side}</p></sidebar></book>",
        [[side, main]],  # native order puts the sidebar first
    )
    assert not xml_values(doc, result, aligned=False)
    for token in doc.tokens:
        pdf = linked_pdf(doc, book, result, token.index)
        assert pdf.value == token.value
    side_tokens = [t for t in doc.tokens if doc.elements[t.element].name == "p"][-10:]
    assert {linked_pdf(doc, book, result, t.index).line for t in side_tokens} == {0}


def test_repeated_heading_aligns_to_the_heading_not_the_running_head():
    pages = [
        ["Ríos", "Ríos", f"{BODY} uno"],
        ["Ríos", f"{BODY} dos"],
        ["Ríos", f"{BODY} tres"],
    ]
    xml = (
        '<book><pagenum page="normal">1</pagenum><h1>Ríos</h1>'
        f'<p>{BODY} uno</p><pagenum page="normal">2</pagenum><p>{BODY} dos</p>'
        f'<pagenum page="normal">3</pagenum><p>{BODY} tres</p></book>'
    )
    doc, book, result = run(xml, pages)
    heading = next(t for t in doc.tokens if t.value == "Ríos")
    assert linked_pdf(doc, book, result, heading.index).line == 1
    running = [(p, 0) for p in range(3)]
    assert all(result.pdf_cause[p][o] == "furniture_candidate" for p, o in running)
    assert_accounted(doc, book, result)


def test_moved_block_of_pages_is_placed_by_segments():
    texts = [
        f"Página número {n} " + " ".join(f"palabra{n}x{k}" for k in range(30)) for n in range(6)
    ]
    order = [4, 5, 0, 1, 2, 3]  # the reference moves the last two pages to the front
    xml = (
        "<book>"
        + "".join(f'<pagenum page="normal">P{n}</pagenum><p>{texts[n]}</p>' for n in order)
        + "</book>"
    )
    doc, book, result = run(xml, [[text] for text in texts])
    assert [s["page"] for s in result.segments[1:]] == [5, 6, 1, 2, 3, 4]
    assert not xml_values(doc, result, aligned=False)
    assert all(result.xml_method[t.index] in {"anchor", "extension"} for t in doc.tokens)


def test_page_without_native_text():
    doc, book, result = run(
        f'<book><pagenum page="normal">1</pagenum><p>{BODY}</p>'
        '<pagenum page="normal">2</pagenum><p>Texto escaneado sin capa nativa</p></book>',
        [[BODY], []],
    )
    causes = {result.xml_cause[t.index] for t in doc.tokens if result.xml_page[t.index] < 0}
    assert causes == {"no_native_pdf_text"}


def test_alignment_is_deterministic():
    pages = [["Ríos", f"{BODY} uno con infor-", "mación"], ["Ríos", f"{BODY} dos"]]
    xml = f"<book><p>{BODY} uno con información</p><p>{BODY} dos</p></book>"
    first = run(xml, pages)[2].to_payload()
    second = run(xml, pages)[2].to_payload()
    assert first == second


def test_header_repair_changes_only_the_root_start_tag():
    body = '<book><p alt="">Texto ""citado"" aquí</p></book></dtbook>'
    original = (
        '<?xml version="1.0"?>\n<!DOCTYPE dtbook PUBLIC ""-//NISO//DTD dtbook 2005-3//EN"" '
        '""http://www.daisy.org/z3986/2005/dtbook-2005-3.dtd"">\n'
        '<dtbook xmlns=""http://www.daisy.org/z3986/2005/dtbook/"" version=""2005-3"">' + body
    ).encode()
    repaired, repairs = repair_header_quotes(original)
    assert [r.kind for r in repairs] == ["header_quote_delimiters"]
    assert repaired.endswith(body.encode())  # text after the root start tag is untouched
    assert repaired.count(b'""') == original[original.index(b"<book>") :].count(b'""')
    doc = read_reference(original)
    assert [r.kind for r in doc.repairs] == ["header_quote_delimiters"]
    assert [t.value for t in doc.tokens] == ["Texto", "citado", "aquí"]
    assert doc.sha256 != ""  # identity is the original file's hash


def test_fragment_wrap_and_unreadable_reference():
    doc = read_reference(b"<index><p>uno</p></index>\n<index><p>dos</p></index>")
    assert [r.kind for r in doc.repairs] == ["fragment_wrap"]
    assert [t.value for t in doc.tokens] == ["uno", "dos"]
    with pytest.raises(ReferenceRejected):
        read_reference(b"<book><p>sin cierre</book>")


def test_inline_markup_never_splits_words_and_blocks_always_do():
    doc = read_reference(
        b"<book><p>infor<strong>maci\xc3\xb3n</strong></p><list><li><lic>Tema</lic>"
        b"<lic>328</lic></li></list><h1>Uno</h1><p>Dos</p></book>"
    )
    assert [t.value for t in doc.tokens] == ["información", "Tema", "328", "Uno", "Dos"]


def test_link_step_refuses_an_already_claimed_pdf_token():
    from book_core.reference.aligner import _State

    doc = read_reference(b"<book><p>uno dos</p></book>")
    book = [pdf_page(1, ["uno dos"])]
    state = _State(doc, book)
    assert state.link([0], [(0, 0)], "anchor", 1.0)
    assert not state.link([1], [(0, 0)], "gap", 1.0)
    assert state.p_xml[0][0] == 0 and state.x_page[1] == -1 and state.refused == 1


@pytest.mark.parametrize("seed", range(200))
def test_repetitive_sequences_never_double_claim(seed):
    """Overlapping unique n-grams on repetitive text once claimed one PDF token twice."""
    import random

    rng = random.Random(seed)
    alphabet = ["ana", "bes", "cal", "dos", "eco"]
    words = [rng.choice(alphabet) for _ in range(rng.randint(6, 18))]
    lines = [" ".join(words[k : k + 4]) for k in range(0, len(words), 4)]
    shuffled = words[:]
    for _ in range(rng.randint(0, 3)):  # perturb the reference order a little
        a, b = rng.randrange(len(shuffled)), rng.randrange(len(shuffled))
        shuffled[a], shuffled[b] = shuffled[b], shuffled[a]
    doc, book, result = run(f"<book><p>{' '.join(shuffled)}</p></book>", [lines])
    assert_accounted(doc, book, result)
    owners = [result.pdf_xml[p][o] for p in range(len(book)) for o in range(len(book[p].tokens))]
    linked = [
        (result.xml_page[i], result.xml_ordinal[i])
        for i in range(len(doc.tokens))
        if result.xml_page[i] >= 0
    ]
    assert sum(1 for x in owners if x >= 0) >= len(set(linked))
