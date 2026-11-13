"""Stage 1 sectioning words and section titles in Italian, Spanish, French and German."""

import pytest

from book_core.structure.navigation import _title_kind
from book_core.structure.numbering import numbering
from book_core.structure.zones import title_kind


@pytest.mark.parametrize(("text", "role"), [
    ("Parte II", "part"), ("Capitolo 3", "chapter"), ("Sezione 2", "section"),
    ("Appendice 1", "appendix"),
    ("Parte 1", "part"), ("Capítulo 4", "chapter"), ("Sección 2", "section"),
    ("Apéndice 1", "appendix"),
    ("Partie 2", "part"), ("Chapitre 5", "chapter"), ("Section 3", "section"),
    ("Annexe 1", "appendix"),
    ("Teil 3", "part"), ("Kapitel 6", "chapter"), ("Abschnitt 4", "section"),
    ("Anhang 1", "appendix"),
])  # fmt: skip
def test_numbered_sectioning_words(text, role):
    marker = numbering(text)
    assert marker["kind"] == "keyword" and marker["role_hint"] == role


@pytest.mark.parametrize(("text", "kind"), [
    ("Indice", "index"), ("Indice analitico", "index"), ("Bibliografia", "bibliography"),
    ("Riferimenti bibliografici", "bibliography"), ("Índice analítico", "index"),
    ("Bibliografía", "bibliography"), ("Bibliographie", "bibliography"),
    ("Stichwortverzeichnis", "index"), ("Literaturverzeichnis", "bibliography"),
])  # fmt: skip
def test_list_titles(text, kind):
    assert _title_kind(text) == kind


@pytest.mark.parametrize(("text", "kind"), [
    ("Appendice", "appendix"), ("Bibliografia", "bibliography"), ("Apéndice", "appendix"),
    ("Annexe", "appendix"), ("Anhang", "appendix"), ("Prefazione", "preface"),
])  # fmt: skip
def test_section_titles(text, kind):
    assert title_kind(text) == kind
