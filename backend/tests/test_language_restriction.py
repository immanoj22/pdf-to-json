"""Explicit job-language candidates and relative native-block uncertainty evidence."""

from dataclasses import replace

import pytest

from book_core.document_analysis.cache import (
    DocumentConfig,
    book_language_threshold,
    fingerprint,
)
from book_core.document_analysis.language import LinguaLanguageDetector, relative_letter_threshold
from book_core.settings import RegionSettings, Settings


def test_default_candidates_follow_settings_and_empty_never_enables_all():
    config = DocumentConfig()
    assert config.language_candidates == tuple(Settings().ocr_languages) == ("spa", "eng")
    assert LinguaLanguageDetector().identity["configuration"]["languages"] == ["en", "es"]
    with pytest.raises(ValueError, match="nonempty"):
        LinguaLanguageDetector(())
    with pytest.raises(ValueError, match="nonempty"):
        DocumentConfig(language_candidates=())


def test_job_candidates_and_explicit_additions_remain_explicit():
    settings = Settings(
        ocr_languages=["eng"], regions={"example": RegionSettings(ocr_languages=["arb"])}
    )
    config = DocumentConfig.from_settings(settings, additional_languages=("eng", "spa", "jpn"))
    assert config.language_candidates == ("eng", "spa", "jpn")
    assert settings.ocr_languages == ["eng"]
    assert LinguaLanguageDetector(config.language_candidates).languages == ("en", "es", "ja")
    with pytest.raises(ValueError, match="Unsupported"):
        LinguaLanguageDetector(
            DocumentConfig.from_settings(
                settings, additional_languages=("not-a-code",)
            ).language_candidates
        )


def test_single_candidate_is_supported_without_implicit_extra_language():
    detector = LinguaLanguageDetector(("eng",))
    result = detector.detect("Children learn together at school and read their books every day.")
    assert detector.languages == ("en",)
    assert {score.language for score in result.candidates} == {"en"}
    assert result.language == "en"
    assert "conditional on configured candidates" in detector.identity["score_interpretation"]
    assert LinguaLanguageDetector(("eng",)).detect("tiny").language == "und"


def test_relative_threshold_is_robust_to_nonletters_and_one_long_block():
    stats = relative_letter_threshold([0, 20, 40, 60, 10000])
    assert stats["median_letters"] == 50
    assert stats["positive_letter_blocks"] == 4
    assert stats["resolved_minimum_letters"] == 13
    assert relative_letter_threshold([0, 1, 2])["resolved_minimum_letters"] == 10
    assert relative_letter_threshold([])["resolved_minimum_letters"] == 10
    assert (
        relative_letter_threshold([40, 80], median_fraction=0.5)["resolved_minimum_letters"] == 30
    )


@pytest.mark.parametrize(
    "parameters",
    [
        {"floor": 0},
        {"floor": True},
        {"floor": 1.5},
        {"median_fraction": 0},
        {"median_fraction": 1.1},
        {"median_fraction": float("nan")},
        {"median_fraction": float("inf")},
    ],
)
def test_invalid_relative_threshold_is_rejected(parameters):
    with pytest.raises(ValueError):
        relative_letter_threshold([10], **parameters)
    translated = {
        {"floor": "minimum_letters", "median_fraction": "minimum_letter_median_fraction"}[k]: v
        for k, v in parameters.items()
    }
    with pytest.raises(ValueError):
        DocumentConfig(**translated)


def test_native_relative_threshold_uses_letters_and_preserves_text(make_page):
    page = make_page(("a" * 80, " 123456"))
    before = page.model_dump_json()
    blocks = [{"page": 1, "block": 0, "line_ids": ["line"]}]
    stats = book_language_threshold([page], blocks, DocumentConfig())
    assert stats["median_letters"] == 80
    assert stats["resolved_minimum_letters"] == 20
    detector = LinguaLanguageDetector(("en", "es"), minimum_letters=20)
    assert detector.detect("hello to everyone").reason == "short_text_uncertain"
    assert page.model_dump_json() == before


def test_relative_parameters_and_explicit_candidates_change_cache_key(make_page):
    pages = [make_page()]
    metadata = {"source_sha256": "a" * 64, "page_count": 1, "page_labels": [], "bookmarks": []}
    blocks = [{"page": 1, "block": 0, "line_ids": ["line"]}]
    config = DocumentConfig()
    key = fingerprint(pages, metadata, blocks, config)[0]
    for changed in (
        replace(config, minimum_letter_median_fraction=0.5),
        replace(config, minimum_letters=15),
        replace(config, language_candidates=("en", "es", "ar")),
    ):
        assert fingerprint(pages, metadata, blocks, changed)[0] != key


def test_optional_language_dependency_is_lazy_and_has_clear_error(monkeypatch):
    import builtins

    original = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "lingua":
            raise ModuleNotFoundError("fixture missing optional Lingua")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    assert DocumentConfig.from_settings(Settings()).language_candidates == ("spa", "eng")
    with pytest.raises(RuntimeError, match=r"universal-book-core\[language-evidence\]"):
        LinguaLanguageDetector()
