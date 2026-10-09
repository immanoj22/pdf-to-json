"""Native-block language evidence preserves spans and supports mixed scripts."""

from dataclasses import asdict

import pytest

from book_core.document_analysis.language import (
    LanguageDetector,
    LanguageEvidence,
    LanguageScore,
    LinguaLanguageDetector,
    language_evidence,
    native_block_text,
)


@pytest.fixture(scope="module")
def bilingual_detector():
    return LinguaLanguageDetector(("eng", "spa"))


def test_bilingual_block_has_two_language_segments(bilingual_detector):
    text = (
        "The children learn together in the classroom. "
        "Los niños estudian juntos en la escuela y hablan español."
    )
    evidence = bilingual_detector.detect(text)
    assert evidence.mixed
    assert {segment.language for segment in evidence.segments} == {"en", "es"}
    assert all(0 <= segment.start < segment.end <= len(text) for segment in evidence.segments)
    assert all(0 <= segment.confidence <= 1 for segment in evidence.segments)
    assert evidence.reason == "mixed_language_evidence"


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("ar", "يتعلم الأطفال معًا في المدرسة ويقرؤون الكتب باللغة العربية كل يوم."),
        ("he", "הילדים לומדים יחד בבית הספר וקוראים ספרים בשפה העברית בכל יום."),
        ("ja", "子どもたちは毎日学校で日本語の本を読んで勉強しています。"),
    ],
)
def test_explicit_detector_accepts_rtl_and_unspaced_scripts(language, text):
    detector = LinguaLanguageDetector(("ar", "he", "ja"))
    evidence = detector.detect(text)
    assert evidence.candidates[0].language == language
    assert detector.identity["configuration"]["languages"] == ["ar", "he", "ja"]
    assert len(detector.identity["model"]["sha256"]) == 64


def test_short_or_nonlinguistic_text_is_uncertain(bilingual_detector):
    for text in ("", "123 .+-", "hello"):
        evidence = bilingual_detector.detect(text)
        assert evidence.language == "und"
        assert not evidence.mixed
    assert bilingual_detector.detect("hello").candidates


def test_language_configuration_is_explicit_and_validated():
    detector = LinguaLanguageDetector(("spa", "eng"))
    assert isinstance(detector, LanguageDetector)
    assert detector.identity["configuration"]["languages"] == ["en", "es"]
    for languages in (("not-a-code",), ("en", "eng"), ("es", "es")):
        with pytest.raises(ValueError):
            LinguaLanguageDetector(languages)
    with pytest.raises(ValueError):
        LinguaLanguageDetector(minimum_letters=0)


class RecordingDetector:
    def __init__(self):
        self.texts = []

    @property
    def identity(self):
        return {"name": "fixture", "version": "1", "configuration": {}}

    def detect(self, text):
        self.texts.append(text)
        return LanguageEvidence("en", 0.8, (LanguageScore("en", 0.8),), (), False, "fixture")


def test_native_block_references_are_read_only(make_page):
    page = make_page(("A multilingual ﬁxture ", "العربية"))
    before = page.model_dump_json()
    detector = RecordingDetector()
    mapping = [{"page": 1, "block": 7, "line_ids": ["line"]}]
    result = language_evidence([page], mapping, detector)
    assert detector.texts == ["A multilingual fixture العربية"]
    block = result["blocks"][0]
    assert block["span_ids"] == ["span-0", "span-1"]
    assert block["line_ids"] == ["line"]
    assert "text" not in block
    assert len(block["text_sha256"]) == 64
    assert page.model_dump_json() == before
    assert asdict(detector.detect(""))["language"] == "en"


def test_native_mapping_refuses_unknown_or_duplicate_lines(make_page):
    page = make_page()
    with pytest.raises(ValueError, match="unknown source line"):
        native_block_text(page, {"page": 1, "block": 0, "line_ids": ["missing"]})
    with pytest.raises(ValueError, match="Duplicate line"):
        native_block_text(page, {"page": 1, "block": 0, "line_ids": ["line", "line"]})
    with pytest.raises(ValueError, match="cover every source line"):
        language_evidence([page], [], RecordingDetector())
    with pytest.raises(ValueError, match="multiple native blocks"):
        language_evidence(
            [page],
            [
                {"page": 1, "block": 0, "line_ids": ["line"]},
                {"page": 1, "block": 1, "line_ids": ["line"]},
            ],
            RecordingDetector(),
        )
    with pytest.raises(ValueError, match="Duplicate source page"):
        language_evidence([page, page], [], RecordingDetector())
