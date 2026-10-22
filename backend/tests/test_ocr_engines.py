"""OCR contract/geometry tests without model downloads or external PDF references."""

from contextlib import contextmanager

import cv2
import numpy as np
import pytest

from book_core.extraction.rasters import RasterPage
from book_core.ocr.engines import (
    OcrOrientation,
    OcrPageContext,
    OcrReading,
    OcrWord,
    PpOcrV5Engine,
    PpRecognitionModel,
    TesseractEngine,
    compare_readings,
    parse_tesseract_data,
    text_properties,
)
from book_core.ocr.geometry import (
    ImageTransform,
    apply_transform,
    decode_image,
    encode_image,
    estimate_deskew,
    pixel_box_to_pdf,
    prepare_image,
    rotation_transform,
    source_pixel_box,
)
from book_core.ocr.languages import (
    LINGUA_TO_TESSERACT,
    installed_languages,
    map_languages,
    require_language_packs,
    script_languages,
)


def image_bytes():
    image = np.full((60, 100, 3), 255, dtype=np.uint8)
    image[10:20, 30:50] = (12, 34, 56)
    return encode_image(image)


def tsv():
    return {
        "text": ["", "العربية", "ABC", "中文"],
        "level": [1, 5, 5, 5],
        "conf": [-1, 90, 80, 60],
        "left": [0, 80, 20, 10],
        "top": [0, 20, 20, 5],
        "width": [100, 15, 20, 10],
        "height": [60, 10, 10, 10],
        "page_num": [1, 1, 1, 1],
        "block_num": [0, 1, 1, 2],
        "par_num": [0, 1, 1, 1],
        "line_num": [0, 1, 1, 1],
    }


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_quarter_turns_are_lossless_and_geometry_returns_to_pdf(angle):
    png = image_bytes()
    prepared, transform = prepare_image(png, rotation_clockwise=angle)
    image = decode_image(prepared)
    assert image.shape[1::-1] == (transform.output_width, transform.output_height)
    expected = np.rot90(decode_image(png), k=-(angle // 90))
    np.testing.assert_array_equal(image, expected)
    matrix = np.asarray(transform.source_to_processed).reshape(2, 3)
    points = np.array([[30, 10, 1], [50, 10, 1], [50, 20, 1], [30, 20, 1]]) @ matrix.T
    box = (*points.min(axis=0), *points.max(axis=0))
    assert source_pixel_box(transform, box).model_dump() == {"x0": 30, "y0": 10, "x1": 50, "y1": 20}
    raster = RasterPage(png=png, width=100, height=60, page_width=72, page_height=43.2)
    pdf = pixel_box_to_pdf(transform, box, raster)
    assert (pdf.x0, pdf.y0, pdf.x1, pdf.y1) == pytest.approx((21.6, 7.2, 36, 14.4))


def test_geometry_refuses_mismatched_images_and_invalid_rotation():
    with pytest.raises(ValueError, match="multiple of 90"):
        rotation_transform(10, 10, 15)
    with pytest.raises(ValueError, match="dimensions"):
        apply_transform(np.zeros((10, 20, 3), dtype=np.uint8), ImageTransform.identity(10, 10))
    with pytest.raises(ValueError, match="decodable"):
        decode_image(b"not an image")


def test_blank_image_deskew_abstains_and_skewed_lines_are_corrected():
    image = np.full((400, 600, 3), 255, dtype=np.uint8)
    assert estimate_deskew(image) == 0
    for y in range(50, 350, 30):
        cv2.putText(
            image, "Some sample words 123", (50, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1
        )
    matrix = cv2.getRotationMatrix2D((300, 200), 2, 1)
    skewed = cv2.warpAffine(image, matrix, (600, 400), borderValue=(255, 255, 255))
    assert estimate_deskew(skewed) == pytest.approx(-2, abs=0.25)
    prepared, transform = prepare_image(encode_image(skewed), deskew=True)
    assert transform.deskew_degrees == pytest.approx(-2, abs=0.25)
    assert decode_image(prepared).shape[1] > 600  # expansion avoids clipping edges


def test_language_mapping_covers_lingua_and_explicit_orthography_without_default_english():
    lingua = pytest.importorskip("lingua")
    for language in lingua.Language.all():
        assert language.iso_code_639_1.name.lower() in LINGUA_TO_TESSERACT
        assert language.iso_code_639_3.name.lower() in LINGUA_TO_TESSERACT
    assert map_languages(["es", "eng", "spa", "hi"]) == ("spa", "eng", "hin")
    assert map_languages(["zh"]) == ("chi_sim", "chi_tra")
    assert map_languages(["chi_tra"]) == ("chi_tra",)
    assert map_languages(["nb", "nn", "tl"]) == ("nor", "fil")
    assert script_languages("Han") == ("script/HanS", "script/HanT")
    assert script_languages("Devanagari") == ("script/Devanagari",)
    with pytest.raises(ValueError, match="no tessdata_best"):
        map_languages(["zu"])
    with pytest.raises(ValueError, match="languages required"):
        script_languages(None)


@pytest.mark.parametrize("code", ["../eng", "script/../eng", " eng", "eng+spa", "script//Latin"])
def test_language_paths_cannot_escape_the_install(code):
    with pytest.raises(ValueError):
        map_languages([code])


def test_pack_discovery_is_read_only_and_missing_pack_is_explicit(tmp_path):
    (tmp_path / "script").mkdir()
    (tmp_path / "eng.traineddata").write_bytes(b"a")
    (tmp_path / "script/Latin.traineddata").write_bytes(b"b")
    assert installed_languages(tmp_path) == ("eng", "script/Latin")
    require_language_packs(tmp_path, ("eng", "script/Latin"))
    with pytest.raises(FileNotFoundError, match="spa"):
        require_language_packs(tmp_path, ("spa",))


def test_tsv_preserves_emission_order_unicode_and_separate_line_confidence():
    words = parse_tesseract_data(tsv(), languages=("ara", "eng"), script="Arabic")
    assert [word.text for word in words] == ["العربية", "ABC", "中文"]
    assert [word.script for word in words] == ["Arab", "Latn", "Hani"]
    assert [word.text_direction for word in words] == ["rtl", "ltr", "ltr"]
    assert words[0].line_confidence == pytest.approx(0.85)
    assert words[2].line_confidence == pytest.approx(0.6)
    assert all(word.language == "und" for word in words)
    broken = tsv()
    broken["conf"] = [0]
    with pytest.raises(ValueError, match="inconsistent"):
        parse_tesseract_data(broken, languages=("eng",))


def test_mixed_script_and_direction_stay_unknown():
    assert text_properties("ABCالعربية") == (None, None)
    assert text_properties("123 +") == (None, None)


def reading(words, engine="test", transform=None):
    return OcrReading(
        engine,
        "test",
        ("eng",),
        tuple(words),
        OcrOrientation(),
        transform or ImageTransform.identity(100, 60),
    )


def test_comparison_keeps_primary_text_and_lowers_disagreement_score():
    primary = reading(
        [OcrWord("the", (0, 0, 20, 10), 0.9, (1,)), OcrWord("cat", (25, 0, 45, 10), 0.9, (1,))]
    )
    second = reading(
        [
            OcrWord("the cut", (0, 0, 45, 10), 0.99, (7,), granularity="line"),
            OcrWord("other", (0, 40, 30, 50), 0.5, (8,)),
        ],
        "secondary",
    )
    compared = compare_readings(primary, second)
    assert [word.text for word in compared.words] == ["the", "cat"]
    assert compared.words[0].confidence == 0.9
    assert compared.words[1].confidence < 0.9
    assert compared.words[1].raw_confidence == 0.9
    assert compared.words[1].alternatives[0].text == "cut"
    assert compared.words[1].alternatives[0].pixel_bbox == (0, 0, 45, 10)
    assert compared.unmatched_secondary[0].text == "other"


def test_comparison_matches_geometry_across_different_rotations():
    primary = reading([OcrWord("abc", (30, 10, 50, 20), 0.9, (1,))])
    transform = rotation_transform(100, 60, 90)
    secondary = reading([OcrWord("abc", (40, 30, 50, 50), 0.8, (2,))], "secondary", transform)
    result = compare_readings(primary, secondary)
    assert result.words[0].alternatives[0].text == "abc"
    assert not result.unmatched_secondary


def test_tesseract_uses_configured_paths_languages_osd_and_source_hashes(tmp_path, monkeypatch):
    from book_core.ocr import engines

    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"mock only")
    for name in ("osd", "eng", "spa"):
        (tmp_path / f"{name}.traineddata").write_bytes(name.encode())
    calls = []

    class Runtime:
        class Output:
            DICT = "dict"

        class TesseractError(Exception):
            pass

        def get_tesseract_version(self):
            return "5.5.3"

        def image_to_osd(self, image, **kwargs):
            calls.append(("osd", kwargs))
            return {"rotate": 90, "orientation_conf": 4.0, "script": "Latin", "script_conf": 2.0}

        def image_to_data(self, image, **kwargs):
            calls.append(("data", kwargs))
            assert image.size == (60, 100)
            return tsv()

    @contextmanager
    def runtime(path, tessdata=None):
        assert path == executable.resolve()
        assert tessdata in (None, tmp_path.resolve())
        yield Runtime()

    monkeypatch.setattr(engines, "_tesseract_runtime", runtime)
    result = TesseractEngine(executable, tmp_path).read(image_bytes(), languages=["es", "en"])
    assert result.source == "ocr"
    assert result.languages == ("spa", "eng")
    assert result.transform.rotation_clockwise == 90
    assert calls[1][1]["lang"] == "spa+eng"
    assert "--oem 1 --psm 3" in calls[1][1]["config"]
    assert "tessdata-dir" not in calls[1][1]["config"]  # pytesseract keeps quotes on Windows
    assert set(dict(result.model_fingerprints)) == {"spa", "eng", "osd"}


def test_pp_models_require_pinned_local_files(tmp_path):
    with pytest.raises(ValueError, match="immutable"):
        PpRecognitionModel(tmp_path, "main", ("eng",), "english")
    with pytest.raises(ValueError, match="installed"):
        PpRecognitionModel(tmp_path / "missing", "1" * 40, ("eng",), "english")


def test_recognize_requires_explicit_page_context_and_maps_to_pdf(tmp_path, monkeypatch):
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"mock only")
    engine = TesseractEngine(executable, tmp_path)
    with pytest.raises(ValueError, match="OcrPageContext"):
        list(engine.recognize(image_bytes(), languages=["eng"]))
    raster = RasterPage(png=image_bytes(), width=100, height=60, page_width=72, page_height=43.2)
    context = OcrPageContext("1" * 64, 17, raster)
    engine = TesseractEngine(executable, tmp_path, page_context=context)
    result = reading([OcrWord("hello", (30, 10, 50, 20), 0.9, (1,))])
    monkeypatch.setattr(engine, "read", lambda image, languages: result)
    span = list(engine.recognize(raster.png, languages=["eng"]))[0]
    assert span.page == 17
    assert span.provenance.source_sha256 == "1" * 64
    assert span.provenance.method == "ocr"
    assert span.bbox.x0 == pytest.approx(21.6)
    with pytest.raises(ValueError, match="differs"):
        list(engine.recognize(b"different", languages=["eng"]))


def test_pp_identity_changes_when_local_model_files_change(tmp_path, monkeypatch):
    from book_core.ocr import engines

    monkeypatch.setattr(engines, "version", lambda name: "test")
    detector = tmp_path / "detector"
    detector.mkdir()
    file = detector / "config.json"
    file.write_text("{}", encoding="utf-8")
    engine = PpOcrV5Engine(detector, "1" * 40, (), device="cpu")
    before = engine.identity["model_fingerprints"]
    file.write_text('{"changed":true}', encoding="utf-8")
    after = engine.identity["model_fingerprints"]
    assert before != after
    assert not engine.supports(["eng"])


def test_pack_hash_changes_after_local_asset_change(tmp_path):
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"mock")
    pack = tmp_path / "eng.traineddata"
    pack.write_bytes(b"before")
    engine = TesseractEngine(executable, tmp_path)
    before = engine.model_fingerprints(("eng",))
    pack.write_bytes(b"afterwards")
    assert before != engine.model_fingerprints(("eng",))


def test_tessdata_directory_is_passed_by_environment_and_restored(tmp_path, monkeypatch):
    import os

    from book_core.ocr import engines

    pytesseract = pytest.importorskip("pytesseract")
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"mock only")
    monkeypatch.setenv("TESSDATA_PREFIX", "previous")
    with engines._tesseract_runtime(executable, tmp_path / "data folder") as runtime:
        assert runtime is pytesseract
        assert os.environ["TESSDATA_PREFIX"] == str(tmp_path / "data folder")
    assert os.environ["TESSDATA_PREFIX"] == "previous"
