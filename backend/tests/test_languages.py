"""Multilingual metadata/configuration never changes native token conservation."""

from collections import Counter

import pytest
from pydantic import ValidationError

from book_core.ingestion.provisional import provision_page
from book_core.ledger.accounting import check
from book_core.ledger.tokenization import token_counter
from book_core.model.document import Document
from book_core.settings import LanguagePack, RegionSettings, Settings


@pytest.mark.parametrize(
    "text,script,direction",
    [
        ("\u0627\u0644\u0639\u0631\u0628\u064a\u0629 \u0661\u0662", "Arab", "rtl"),
        ("\u4e2d\u6587\u6d4b\u8bd5", "Hans", "ttb"),
        ("\u0939\u093f\u0928\u094d\u0926\u0940 \u0967", "Deva", "ltr"),
        ("\u05e2\u05d1\u05e8\u05d9\u05ea", "Hebr", "rtl"),
    ],
)
def test_non_latin_conservation_and_json_metadata(make_page, text, script, direction):
    page = make_page((text,))
    payload = page.model_dump()
    payload["store"]["spans"]["span-0"].update(script=script, text_direction=direction)
    page = type(page).model_validate(payload)
    document, ledger = provision_page(page)
    node = document.body_matter.children[0]
    assert node.script == script and node.text_direction == direction
    assert node.content[0].span_id == "span-0"
    assert check(document, ledger, token_counter(text)).passing
    assert Document.model_validate_json(document.model_dump_json()) == document
    assert document.span_store.spans["span-0"].raw_text == text


def test_cjk_current_rule_is_conservation_not_word_segmentation():
    assert token_counter("\u4e2d\u6587\u6d4b\u8bd5") == Counter({"\u4e2d\u6587\u6d4b\u8bd5": 1})


def test_unknown_script_and_direction_are_not_latin_defaults(make_page):
    document, _ = provision_page(make_page())
    assert document.body_matter.children[0].script is None
    assert document.body_matter.children[0].text_direction is None
    span = document.span_store.spans["span-0"]
    assert span.script is None and span.text_direction is None
    with pytest.raises(ValidationError):
        type(span).model_validate({**span.model_dump(), "text_direction": "guess"})


def test_job_and_region_language_settings_round_trip():
    default = Settings()
    assert default.ocr_languages == ["spa", "eng"]
    assert default.language_packs.packs == {}
    job = Settings(
        ocr_languages=["ara", "chi_sim", "hin"],
        regions={"quote": RegionSettings(ocr_languages=["heb"]), "inherit": RegionSettings()},
    )
    assert job.languages_for_region("quote") == ["heb"]
    assert job.languages_for_region("inherit") == ["ara", "chi_sim", "hin"]
    assert job.languages_for_region("unconfigured") == job.ocr_languages
    result = job.languages_for_region("quote")
    result.append("eng")
    assert job.languages_for_region("quote") == ["heb"]
    assert Settings.model_validate_json(job.model_dump_json()) == job
    assert LanguagePack(code="ara").installed is False


@pytest.mark.parametrize("languages", [[], [" "], ["spa", "spa"], [" eng"]])
def test_invalid_language_requests_rejected(languages):
    with pytest.raises(ValidationError):
        Settings(ocr_languages=languages)
