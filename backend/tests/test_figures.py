"""Step 12 figures: naming, kind/format, links, figure text, alt-text slot, caching, workers."""

import hashlib
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytest
from pydantic import ValidationError
from test_cache_keys import closure

from book_core import caching
from book_core.book_run import run_book
from book_core.cache_store import read_json
from book_core.figures import imaging
from book_core.figures.models import AltText
from book_core.figures.names import COLLISION, INFERRED, NO_LABEL, assign_names, safe_label
from book_core.figures.settings import FigureSettings
from book_core.model.common import BBox

# ------------------------------------------------------------------ naming


def test_names_follow_label_and_reading_position():
    names = assign_names(
        [("a", 12, "7", "printed", 1), ("b", 12, "7", "printed", 2)], FigureSettings()
    )
    assert names["a"] == ("page_7_1", "7", False, [])
    assert names["b"][0] == "page_7_2"


def test_inferred_label_is_marked_and_flagged():
    stem, label, inferred, reasons = assign_names(
        [("a", 3, "ix", "inferred", 1)], FigureSettings()
    )["a"]
    assert (stem, label, inferred) == ("page_ix_1", "ix", True)
    assert reasons == [INFERRED]


def test_unlabelled_page_uses_pdf_index_and_needs_review():
    stem, label, inferred, reasons = assign_names([("a", 41, None, "none", 2)], FigureSettings())[
        "a"
    ]
    assert (stem, label, inferred, reasons) == ("page_pdf41_2", None, False, [NO_LABEL])


def test_book_style_labels_keep_their_form():
    names = assign_names([("a", 900, "HT12", "printed", 1)], FigureSettings())
    assert names["a"][0] == "page_HT12_1"


def test_duplicate_names_are_never_repeated_even_by_case():
    names = assign_names(
        [("a", 1, "A1", "printed", 1), ("b", 9, "a1", "printed", 1), ("c", 10, "A1", "printed", 1)],
        FigureSettings(),
    )
    stems = [names[k][0] for k in "abc"]
    assert stems == ["page_A1_1", "page_a1_1_2", "page_A1_1_3"]
    assert len({s.casefold() for s in stems}) == 3
    assert COLLISION in names["b"][3] and COLLISION in names["c"][3]


@pytest.mark.parametrize(
    ("label", "expected"),
    [("FM 3", "FM-3"), ("a/b:c", "a-b-c"), ("١٢", "١٢"), ("  ", None), ("xii.", "xii")],
)
def test_labels_are_file_safe(label, expected):
    assert safe_label(label) == expected


def test_reserved_device_names_are_avoided():
    settings = FigureSettings(name_pattern="{label}{n}")
    assert assign_names([("a", 1, "con", "printed", "")], settings)["a"][0] == "con_"


def test_naming_pattern_is_configurable_without_code_change():
    settings = FigureSettings(name_pattern="page_no_{label}_picture_no_{n:02d}")
    assert assign_names([("a", 5, "12", "printed", 3)], settings)["a"][0] == (
        "page_no_12_picture_no_03"
    )
    with pytest.raises(ValidationError):
        FigureSettings(name_pattern="page_{label}")  # no reading position
    with pytest.raises(ValidationError):
        FigureSettings(name_pattern="page_{label}_{n}_{author}")
    with pytest.raises(ValidationError):
        FigureSettings(unlabelled_pattern="page_{n}")  # no physical page


# ---------------------------------------------------------- kind and format

BOX = BBox(x0=0, y0=0, x1=100, y1=100)


def _photo():
    rng = np.random.default_rng(7)
    base = cv2.GaussianBlur(rng.integers(0, 255, (200, 200, 3), dtype=np.uint8), (0, 0), 3)
    return np.clip(base.astype(int) + rng.integers(-20, 20, base.shape), 0, 255).astype(np.uint8)


def _drawing():
    image = np.full((200, 200, 3), 255, np.uint8)
    cv2.rectangle(image, (20, 20), (180, 120), (30, 60, 200), -1)
    cv2.line(image, (0, 190), (199, 150), (0, 0, 0), 2)
    return image


def test_raster_photograph_is_jpg():
    kind, fmt, _, evidence, flags = imaging.decide(BOX, _photo(), [BOX], 0)
    assert (kind, fmt, evidence.source_type, flags) == ("photo", "jpg", "raster", [])


def test_vector_or_flat_drawing_is_png():
    assert imaging.decide(BOX, _drawing(), [], 12)[:2] == ("drawing", "png")
    # A raster of a few flat colours (a scanned diagram) is still a drawing.
    assert imaging.decide(BOX, _drawing(), [BOX], 0)[:2] == ("drawing", "png")


def test_mixed_evidence_is_png_and_flagged():
    half = BBox(x0=0, y0=0, x1=40, y1=100)
    kind, fmt, confidence, evidence, flags = imaging.decide(BOX, _photo(), [half], 3)
    assert evidence.source_type == "mixed" and fmt == "png" and flags == [imaging.UNCERTAIN]
    assert confidence < 0.6


def test_decision_never_reads_a_file_name(tmp_path):
    # Same pixels, same evidence, regardless of any name.
    first = imaging.decide(BOX, _photo(), [BOX], 0)
    second = imaging.decide(BOX, _photo(), [BOX], 0)
    assert first == second


# ------------------------------------------------------------ alt-text slot


def test_alt_text_slot_is_empty_and_needs_review_by_default():
    slot = AltText()
    assert (slot.text, slot.status, slot.source) == ("", "needs_review", "none")


def test_model_drafts_are_never_verified():
    AltText(text="A map.", source="model_draft", language="en")
    with pytest.raises(ValidationError):
        AltText(text="A map.", source="model_draft", status="verified")
    with pytest.raises(ValidationError):
        AltText(text="A map.", status="verified", source="none")
    assert AltText(text="A map.", source="human", status="verified").status == "verified"


def test_generator_is_off_by_default(monkeypatch, figure_pdf, tmp_path):
    import book_core.figures.alt_text as alt_text

    class Forbidden:
        def __init__(self, *args, **kwargs):
            raise AssertionError("the draft generator must not be constructed by default")

    monkeypatch.setattr(alt_text, "DraftGenerator", Forbidden)
    assert FigureSettings().alt_text_drafts is False
    result = run_book(figure_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    figures = _figures(result)
    assert figures and all(
        f["alt_text"] == {"text": "", "status": "needs_review", "source": "none",
                          "language": None, "model": None}
        for f in figures
    )  # fmt: skip


def test_drafts_on_use_the_supplied_generator(figure_pdf, tmp_path):
    class Stub:
        def describe(self, rgb):
            return AltText(text="Stub draft.", source="model_draft", language="en", model="stub")

    result = run_book(
        figure_pdf,
        tmp_path / "out",
        tmp_path / "cache",
        workers=1,
        device="cpu",
        figure_settings=FigureSettings(alt_text_drafts=True),
        alt_text_generator=Stub(),
    )
    alt = [f["alt_text"] for f in _figures(result) if f["image"]]
    assert alt and all(a["status"] == "needs_review" and a["source"] == "model_draft" for a in alt)


# ------------------------------------------------- synthetic book: pipeline


def _png(rgb):
    return cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))[1].tobytes()


def _figure_book(path, pages, numbered):
    """Pages with a composite (photo + adjacent vector artwork + a label), a caption below
    in a smaller style, a rotated credit beside it, a separate distant photo, body text."""
    photo = _png(_photo())
    with pymupdf.open() as document:
        for number in range(pages):
            page = document.new_page(width=420, height=600)
            page.insert_text((40, 50), f"Lesson {number + 1}", fontsize=16)
            for row in range(4):
                page.insert_text(
                    (40, 80 + 14 * row),
                    "Body text of the lesson continues across the column here.",
                    fontsize=10,
                )
            page.insert_image(pymupdf.Rect(60, 150, 220, 290), stream=photo)
            shape = page.new_shape()
            for i in range(5):
                shape.draw_rect(pymupdf.Rect(226 + 12 * i, 160, 234 + 12 * i, 280))
                shape.finish(fill=(0.2, 0.4, 0.8 - 0.1 * i), color=None)
            shape.commit()
            page.insert_text((228, 158), "Lab", fontsize=6)
            page.insert_text(
                (40, 305),
                f"{'Fig. ' + str(number + 1) + ': ' if numbered else ''}Figure caption: a "
                "composite of a photo and a chart.",
                fontsize=8,
            )
            page.insert_text((300, 290), "PHOTO: Example Archive", fontsize=6, rotate=90)
            page.insert_image(pymupdf.Rect(60, 420, 200, 540), stream=photo)
            page.insert_text((40, 580), f"{number + 1}", fontsize=9)
        document.save(path)
    return path


@pytest.fixture
def figure_pdf(tmp_path):
    """Four pages with numbered captions (the book's caption label is learned)."""
    return _figure_book(tmp_path / "figures.pdf", 4, numbered=True)


def _figures(result, page=None):
    output = Path(result["output"])
    pages = sorted(output.glob("page_*.json.gz")) if page is None else [
        output / f"page_{page:06d}.json.gz"
    ]  # fmt: skip
    return [f for p in pages for f in read_json(p)["figures"]["figures"]]


def test_composite_is_one_figure_and_distinct_figures_stay_apart(figure_pdf, tmp_path):
    result = run_book(figure_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    figures = _figures(result, 1)
    assert len(figures) == 2
    composite = max(figures, key=lambda f: f["bbox"]["x1"] - f["bbox"]["x0"])
    assert composite["bbox"]["x1"] >= 280  # the vector chart joined the photo
    assert len(composite["object_ids"]) >= 2
    assert sorted(f["anchor"]["reading_index"] for f in figures) == [1, 2]
    names = {f["name"] for f in _figures(result)}
    assert len(names) == 8  # never repeated in the book


def test_numbered_caption_links_and_credit_is_a_page_level_proposal(figure_pdf, tmp_path):
    result = run_book(figure_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    page = read_json(Path(result["output"]) / "page_000001.json.gz")
    figures = page["figures"]["figures"]
    composite = max(figures, key=lambda f: f["bbox"]["x1"] - f["bbox"]["x0"])
    texts = _unit_texts(page)
    captions = [texts[c["unit_id"]] for c in composite["captions"]]
    assert any("Figure caption" in t for t in captions)
    # A credit line is never linked to a figure; its rule's figure is only a proposal.
    assert all(not f["credits"] for f in figures)
    credit = next(c for c in page["figures"]["page_credits"] if "PHOTO" in texts[c["unit_id"]])
    assert credit["proposed_figure_ids"] == [composite["id"]]
    assert "review" in credit["reason"]
    other = min(figures, key=lambda f: f["bbox"]["x1"] - f["bbox"]["x0"])
    assert not other["captions"]


def _unit_texts(page):
    spans = page["source"]["store"]["spans"]
    texts = {}
    for unit in page["units"]["units"]:
        texts[unit["id"]] = " ".join(
            spans[s]["raw_text"] for lid in unit["line_ids"] for s in page["line_spans"][lid]
        )
    return texts


def test_figure_text_stays_in_units_and_ledger(figure_pdf, tmp_path):
    result = run_book(figure_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    page = read_json(Path(result["output"]) / "page_000001.json.gz")
    units = {u["id"]: u for u in page["units"]["units"]}
    linked = [
        link
        for f in page["figures"]["figures"]
        for link in (*f["captions"], *f["credits"], *f["internal_text"])
    ]
    assert linked
    for link in linked:
        # Reassigned with provenance, never deleted: the unit and its lines still exist.
        assert units[link["unit_id"]]["line_ids"] == link["line_ids"]
        assert link["rule"] and 0 < link["confidence"] <= 1
    credits = page["figures"]["page_credits"]
    assert credits
    figures = {f["id"] for f in page["figures"]["figures"]}
    for credit in credits:
        # Page-level credit lines: kept as text, never linked, always under review.
        assert units[credit["unit_id"]]["line_ids"] == credit["line_ids"]
        assert credit["rule"] and 0 < credit["confidence"] <= 1
        assert credit["review_required"] is True
        assert set(credit["proposed_figure_ids"]) <= figures
    internal = [link for f in page["figures"]["figures"] for link in f["internal_text"]]
    assert any("Lab" in _unit_texts(page)[link["unit_id"]] for link in internal)
    lines = [lid for u in page["units"]["units"] for lid in u["line_ids"]]
    assert len(lines) == len(set(lines)) == len(page["line_spans"])


def test_images_are_exported_named_and_checksummed(figure_pdf, tmp_path):
    result = run_book(figure_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    output = Path(result["output"])
    manifest = read_json(output / "manifest.json.gz")
    for figure in _figures(result):
        image = figure["image"]
        path = output / "images" / image["file_name"]
        data = path.read_bytes()
        assert manifest["files"][f"images/{image['file_name']}"] == image["sha256"]
        assert hashlib.sha256(data).hexdigest() == image["sha256"]
        if figure["page_label"] is None:
            # No folio sequence in this short book: named by the physical page, under review.
            assert image["file_name"].startswith(f"page_pdf{figure['page']}_")
            assert NO_LABEL in figure["review_flags"]
        else:
            assert image["file_name"].startswith(f"page_{figure['page_label']}_")
        assert image["file_name"] == f"{figure['name']}.{image['format']}"
        assert image["format"] == "jpg" or figure["kind"] == "drawing" or figure["review_flags"]


def test_workers_and_production_give_identical_figures(figure_pdf, tmp_path):
    serial = run_book(figure_pdf, tmp_path / "a_out", tmp_path / "a", workers=1, device="cpu")
    parallel = run_book(figure_pdf, tmp_path / "b_out", tmp_path / "b", workers=2, device="cpu")
    production = run_book(
        figure_pdf, tmp_path / "c_out", tmp_path / "c", mode="production", workers=2, device="cpu"
    )

    def files(result):
        root = Path(result["output"])
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*")
            if p.is_file()
        }

    assert files(serial) == files(parallel) == files(production)
    assert any(name.startswith("images/") for name in files(serial))
    assert not (tmp_path / "c" / "figures").exists()  # production keeps final outputs only


# ------------------------------------------------------------- cache closure


def test_figures_cache_closure_covers_its_imports():
    assert closure("figures/cache.py") <= set(caching.coverage_files("figures"))
    assert closure("book_run.py") <= set(caching.coverage_files("final"))


def test_missing_figures_dependency_is_detected(monkeypatch):
    monkeypatch.setitem(caching.DEPENDENCIES, "final", ("lists", "metadata", "characters"))
    missing = closure("book_run.py") - set(caching.coverage_files("final"))
    assert "figures/cache.py" in missing


# ------------------------------------------------------- numbered captions


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("Fig. 3.2: Bones", "fig"),
        ("Figs. 1.6A and B: Planes", "figs"),
        ("Abb. 4 Karte", "abb"),
        ("Structure (Figs. 2.6A to C)", None),
        ("En este grabado aparece", None),
        ("TABLE 1.5: Planes", "table"),
    ],
)
def test_caption_label_is_the_word_before_a_number(text, label):
    from book_core.figures.page import caption_label

    assert caption_label(text) == label


def test_black_and_white_photograph_is_not_a_drawing():
    ramp = np.add.outer(np.arange(200), np.arange(200)) * 255 / 398
    noise = np.random.default_rng(3).normal(0, 6, ramp.shape)
    gray = np.clip(ramp + noise, 0, 255).astype(np.uint8)  # a shaded, full-range photograph
    rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    kind, fmt, _, evidence, flags = imaging.decide(BOX, rgb, [BOX], 0)
    # Few quantized colours, but many grey tones: a photograph.
    assert evidence.dominant_colour_share >= imaging.PHOTO_DOMINANT
    assert evidence.dominant_tone_share < imaging.PHOTO_DOMINANT
    assert (kind, fmt, flags) == ("photo", "jpg", [])


def test_unnumbered_attached_captions_stay_text_and_are_flagged(tmp_path):
    source = _figure_book(tmp_path / "plain.pdf", 2, numbered=False)
    result = run_book(source, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    page = read_json(Path(result["output"]) / "page_000001.json.gz")
    texts = _unit_texts(page)
    linked = [c["unit_id"] for f in page["figures"]["figures"] for c in f["captions"]]
    assert not any("Figure caption" in texts[u] for u in linked)
    unlinked = page["figures"]["unlinked_captions"]
    caption = next(c for c in unlinked if "Figure caption" in texts[c["unit_id"]])
    assert "review" in caption["reason"]
    assert caption["unit_id"] in {u["id"] for u in page["units"]["units"]}  # still text


def test_small_artwork_is_a_client_setting_never_a_drop(figure_pdf, tmp_path):
    default = run_book(figure_pdf, tmp_path / "a", tmp_path / "ca", workers=1, device="cpu")
    strict = run_book(
        figure_pdf,
        tmp_path / "b",
        tmp_path / "cb",
        workers=1,
        device="cpu",
        figure_settings=FigureSettings(small_figure_share=0.5),
    )
    before, after = _figures(default), _figures(strict)
    assert len(before) == len(after)  # marked, never dropped
    assert not any(f["small_artwork"] for f in before)
    assert all(f["small_artwork"] for f in after)
    assert all(0 < f["content_area_share"] < 0.5 for f in after)


class _StubEvidence:
    """Layout-model evidence that finds only the left photo of each page (heron and pp)."""

    identity = {"heron": "stub@0", "pp": "stub@0"}

    def __call__(self, number):
        photo = BBox(x0=55, y0=410, x1=205, y1=545)  # the separate lower photo
        return {"heron": [photo], "pp": [photo]}


def test_model_disagreement_flags_but_never_drops(figure_pdf, tmp_path):
    from book_core.figures.evidence import MODEL_DISAGREES

    plain = run_book(figure_pdf, tmp_path / "a", tmp_path / "ca", workers=1, device="cpu")
    flagged = run_book(
        figure_pdf,
        tmp_path / "b",
        tmp_path / "cb",
        workers=1,
        device="cpu",
        figure_settings=FigureSettings(model_evidence="on"),
        figure_evidence=_StubEvidence(),
    )
    before, after = _figures(plain), _figures(flagged)
    assert [f["name"] for f in before] == [f["name"] for f in after]  # nothing dropped
    assert all(not f["model_support"] for f in before)
    for figure in after:
        found = figure["model_support"] == {"heron": True, "pp": True}
        assert (MODEL_DISAGREES in figure["review_flags"]) == (not found)
        assert figure["image"] is not None
    assert sum(MODEL_DISAGREES in f["review_flags"] for f in after) == 4  # the composites


def test_model_evidence_must_be_supplied_when_on(figure_pdf, tmp_path):
    from book_core.figures.cache import analyze_book_figures

    with pytest.raises(ValueError, match="exactly when it is on"):
        analyze_book_figures(
            figure_pdf, None, None, None, None, {}, "k" * 64, tmp_path, 1, None,
            FigureSettings(model_evidence="on"),
        )  # fmt: skip


def test_workers_equal_with_model_evidence(figure_pdf, tmp_path):
    settings = FigureSettings(model_evidence="on")
    runs = [
        run_book(figure_pdf, tmp_path / f"{n}o", tmp_path / f"{n}c", workers=n, device="cpu",
                 figure_settings=settings, figure_evidence=_StubEvidence())
        for n in (1, 2)
    ]  # fmt: skip

    def files(result):
        root = Path(result["output"])
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*")
            if p.is_file()
        }

    assert files(runs[0]) == files(runs[1])


def test_auto_model_evidence_warns_when_models_are_missing(figure_pdf, tmp_path, caplog):
    from book_core.figures.evidence import MODELS_MISSING
    from book_core.mathml.settings import MODELS_MISSING as FORMULA_MODELS_MISSING

    assert FigureSettings().model_evidence == "auto"
    assert FigureSettings().model_disagreement == "not_both"
    with caplog.at_level("WARNING", logger="book_core.figures"):
        result = run_book(figure_pdf, tmp_path / "o", tmp_path / "c", workers=1, device="cpu")
    assert result["figure_model_evidence"] == "off"
    from book_core.tables.settings import MODELS_MISSING as TABLE_MODELS_MISSING

    # Tests also run without the formula and table models: those stages warn as well.
    assert result["warnings"] == [MODELS_MISSING, FORMULA_MODELS_MISSING, TABLE_MODELS_MISSING]
    assert MODELS_MISSING in caplog.text
    assert all(not f["model_support"] for f in _figures(result))


def test_explicit_model_evidence_fails_clearly_without_models(figure_pdf, tmp_path):
    with pytest.raises(RuntimeError, match="not installed"):
        run_book(figure_pdf, tmp_path / "o", tmp_path / "c", workers=1, device="cpu",
                 figure_settings=FigureSettings(model_evidence="on"))  # fmt: skip


def test_auto_model_evidence_is_on_when_models_are_installed(figure_pdf, tmp_path, monkeypatch):
    import book_core.figures.evidence as evidence

    monkeypatch.setattr(evidence, "models_available", lambda: True)
    resolved, warning = evidence.resolve(FigureSettings())
    assert (resolved.model_evidence, warning) == ("on", None)
    result = run_book(figure_pdf, tmp_path / "o", tmp_path / "c", workers=1, device="cpu",
                      figure_evidence=_StubEvidence())  # fmt: skip
    from book_core.mathml.settings import MODELS_MISSING as FORMULA_MODELS_MISSING
    from book_core.tables.settings import MODELS_MISSING as TABLE_MODELS_MISSING

    # No figure warning; only the MathML and table stages' (tests run without those models).
    assert result["figure_model_evidence"] == "on"
    assert result["warnings"] == [FORMULA_MODELS_MISSING, TABLE_MODELS_MISSING]
    assert all(f["model_support"] for f in _figures(result))
