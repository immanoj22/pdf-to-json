"""Math needs mathematical evidence: a letter with a lowered digit is not enough alone.

Step 18: anatomical labels (``V₃``, ``C₂``) typed as inline math. A lowered script on an
upright Latin letter needs equation context on its page: its line, or the same symbol
elsewhere on the page, holds independent evidence (an operator, a math font, a function). A
slanted or Greek variable and a raised exponent need no context. Step 19: slanted includes
an upright font sheared by its text matrix (synthetic italic): the Statistics book sets
``H₀`` that way, and the font name and flags cannot show it.
"""

from types import SimpleNamespace

import pymupdf
import pytest

from book_core.equations import slant
from book_core.equations.detect import confirm_by_context
from book_core.equations.text import line_runs
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

ROMAN, ITALIC = ("Times-Roman", 0), ("Times-Italic", 0)


def runs(parts, line_id="l1", sheared=()):
    """[(text, size, shift, font, flags)] spans set left to right; shift is -1 raised,
    +1 lowered, 0 on the baseline (PDF space: y grows downward); ``sheared``: indices of the
    parts drawn slanted by their text matrix. Returns detect drafts."""
    spans, geometry, x = {}, {}, 0
    for index, (text, size, shift, font, flags) in enumerate(parts):
        sid = f"{line_id}s{index}"
        spans[sid] = SimpleNamespace(id=sid, raw_text=text, size=size, font=font, flags=flags)
        geometry[sid] = SimpleNamespace(origin=(x, 100 + 3 * shift), direction=(1, 0))
        x += 10 * len(text)
    slanted = frozenset(
        (f"{line_id}s{i}", offset) for i in sheared for offset in range(len(parts[i][0]))
    )
    line = SimpleNamespace(span_ids=list(spans), font_size=10, horizontal=True)
    return [
        {
            "rules": list(run.rules),
            "signals": dict(run.signals),
            "line_ids": [line_id],
            "text": "".join(spans[s].raw_text[a:b] for s, a, b in run.ranges),
            "atoms": [],
            "part": not run.rules,
        }
        for run in line_runs(
            SimpleNamespace(spans=spans), line, geometry, frozenset(), slanted=slanted
        )
    ]


def equations(*lines):
    drafts = [draft for line in lines for draft in line]
    confirm_by_context(drafts)
    return [d["text"] for d in drafts if d["rules"]]


def label(letter, line_id="l1"):
    return runs([("the mandibular nerve (", 10, 0, *ROMAN), (letter, 10, 0, *ROMAN),
                 ("3", 6, 1, *ROMAN), (") supplies", 10, 0, *ROMAN)], line_id)  # fmt: skip


@pytest.mark.parametrize("letter", ["V", "C", "T"])
def test_a_lowered_digit_on_an_upright_capital_without_context_is_a_label(letter):
    assert equations(label(letter)) == []


def test_the_same_notation_is_math_beside_independent_evidence():
    def reject():
        return runs([("we reject H", 10, 0, *ROMAN), ("0", 6, 1, *ROMAN), (" now", 10, 0, *ROMAN)])

    def stated():
        return runs([("H", 10, 0, *ROMAN), ("0", 6, 1, *ROMAN), (": μ = 5", 10, 0, *ROMAN)], "l2")

    # Alone on its page, H0 is not math; its line or its symbol in a stated hypothesis is.
    assert equations(reject()) == []
    assert equations(reject(), stated()) == ["H0", "H0", "μ = 5"]
    # A label on a page with unrelated equations stays a label.
    assert equations(label("V"), stated()) == ["H0", "μ = 5"]


@pytest.mark.parametrize("face", [ITALIC, ("Times-Roman", 2), ("MinionPro-It", 0)])
def test_a_slanted_variable_with_an_index_needs_no_context(face):
    parts = [("sample size ", 10, 0, *ROMAN), ("n", 10, 0, *face), ("1", 6, 1, *face),
             (" here", 10, 0, *ROMAN)]  # fmt: skip
    assert equations(runs(parts)) == ["n1"]


def test_greek_indices_and_raised_exponents_need_no_context():
    greek = runs([("mean ", 10, 0, *ROMAN), ("μ", 10, 0, *ROMAN), ("0", 6, 1, *ROMAN),
                  (" here", 10, 0, *ROMAN)])  # fmt: skip
    exponent = runs([("area x", 10, 0, *ROMAN), ("2", 6, -1, *ROMAN), (" u", 10, 0, *ROMAN)], "l2")
    assert equations(greek, exponent) == ["μ0", "x2"]


def test_a_variable_sheared_by_its_text_matrix_needs_no_context():
    # An upright font (no italic name or flag) drawn slanted: alone on its page, still math.
    parts = [("we reject ", 10, 0, *ROMAN), ("H", 10, 0, *ROMAN), ("0", 6, 1, *ROMAN),
             (" now", 10, 0, *ROMAN)]  # fmt: skip
    assert equations(runs(parts, sheared=(1, 2))) == ["H0"]
    assert equations(runs(parts)) == []


def test_glyphs_sheared_by_the_text_matrix_are_read_as_slanted(tmp_path):
    path = tmp_path / "sheared.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 100), "upright", fontname="helv", fontsize=11)
    shear = (pymupdf.Point(72, 140), pymupdf.Matrix(1, 0, -0.2, 1, 0, 0))
    page.insert_text((72, 140), "sheared", fontname="helv", fontsize=11, morph=shear)
    document.save(path)
    (extracted,) = PyMuPDFExtractor(device="cpu").extract_pages(path)
    store = extracted.store
    with pymupdf.open(path) as source:
        found = slant.slanted_characters(source[0], store)
    text = {sid: span.raw_text for sid, span in store.spans.items()}
    assert {text[sid][offset] for sid, offset in found} == set("sheard")
    assert all(text[sid] == "sheared" for sid, _ in found)
    assert len(found) == len("sheared")


def test_an_upright_label_stays_a_label_beside_sheared_variables():
    # "C5" upright, no other math evidence: not math, even when the same page draws a
    # variable slanted by its text matrix (slant is read per character, never per page).
    vertebra = runs([("the vertebra ", 10, 0, *ROMAN), ("C", 10, 0, *ROMAN), ("5", 6, 1, *ROMAN),
                     (" here", 10, 0, *ROMAN)])  # fmt: skip
    sheared = runs([("we reject ", 10, 0, *ROMAN), ("H", 10, 0, *ROMAN), ("0", 6, 1, *ROMAN)],
                   "l2", sheared=(1, 2))  # fmt: skip
    assert equations(vertebra) == []
    assert equations(vertebra, sheared) == ["H0"]
