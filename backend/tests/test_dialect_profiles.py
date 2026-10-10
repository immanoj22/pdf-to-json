"""Step 10b infrastructure fix: gold manifests are validated per dialect profile."""

import copy
import json
from pathlib import Path

import pytest

from book_core.evaluation.derived_gold import marker_label_of
from book_core.evaluation.dialect_profiles import (
    DialectProfileChanged,
    check_manifest,
    file_digest,
    load_history,
    profile_digest,
    profile_digests,
)
from book_core.reference.dialects import dialects_from_data
from book_core.reference.xml_reader import read_reference
from book_core.settings import Settings

GOLD = Path(__file__).resolve().parent / "gold_derived"
DATA = json.loads(Path(Settings().reference_dialects).read_text("utf-8"))


def manifest(dialect, data=None, per_dialect=None):
    provenance = {"dialect": dialect, "dialect_profiles_sha256": file_digest(data or DATA)}
    if per_dialect:
        provenance["dialect_profile_sha256"] = per_dialect
    return {"provenance": provenance}


def test_file_digest_matches_the_loader():
    assert file_digest(DATA) == dialects_from_data(DATA).digest


def test_committed_gold_validates_against_its_own_dialect():
    for book in ("spanish_us_history", "immigrant_children", "art_therapy_index"):
        gold = json.loads((GOLD / book / "manifest.json").read_text("utf-8"))
        assert check_manifest(gold, DATA) in {"per_dialect", "recorded_file_digest"}


def test_new_dialect_entry_does_not_invalidate_other_books():
    before = copy.deepcopy(DATA)
    old = {"file_digests": {file_digest(before): profile_digests(before)}}
    after = copy.deepcopy(before)
    after["dialects"].insert(0, {"name": "new-book", "detect": {"root_names": ["x"]},
                                 "page_marker_elements": []})  # fmt: skip
    assert file_digest(after) != file_digest(before)
    for name in profile_digests(before):
        assert profile_digest(after, name) == profile_digest(before, name)
        assert check_manifest(manifest(name, before), after, old) == "recorded_file_digest"


def test_changed_dialect_entry_invalidates_only_its_books():
    before = copy.deepcopy(DATA)
    old = {"file_digests": {file_digest(before): profile_digests(before)}}
    after = copy.deepcopy(before)
    docbook = next(d for d in after["dialects"] if d["name"] == "docbook")
    docbook["page_marker_elements"] = ["anchor"]
    with pytest.raises(DialectProfileChanged):
        check_manifest(manifest("docbook", before), after, old)
    assert check_manifest(manifest("dtbook", before), after, old) == "recorded_file_digest"
    common = copy.deepcopy(before)
    common["common"]["inline_elements"].append("mark")
    with pytest.raises(DialectProfileChanged):
        check_manifest(manifest("dtbook", before), common, old)
    with pytest.raises(DialectProfileChanged):  # an unknown earlier file is never trusted
        check_manifest(manifest("dtbook", before), after, {})


def test_new_manifests_record_the_per_dialect_digest():
    name = "dtbook"
    row = manifest(name, per_dialect=profile_digest(DATA, name))
    row["provenance"]["dialect_profiles_sha256"] = "0" * 64  # whole file changed since
    assert check_manifest(row, DATA, {}) == "per_dialect"
    row["provenance"]["dialect_profile_sha256"] = "1" * 64
    with pytest.raises(DialectProfileChanged):
        check_manifest(row, DATA, {})


def test_history_records_the_profile_before_the_book4_entry():
    history = load_history()
    recorded = history["file_digests"][
        "4c904954db13262a443ae88fd925026e64587b4fd5696b01b639434dffaba0ab"
    ]
    assert set(recorded) == {"dtbook", "docbook", "docbook-like-fragments"}
    for name, digest in recorded.items():
        assert profile_digest(DATA, name) == digest


def test_page_anchor_dialect_reads_labels_from_ids():
    dialects = dialects_from_data(DATA)
    data = (
        b'<?xml version="1.0"?><book><chapter><title><anchor id="pageFM3"/>Front</title>'
        b'<para>Alpha</para><para><anchor id="page1"/>Beta gamma</para></chapter></book>'
    )
    doc = read_reference(data, dialects)
    assert doc.dialect.name == "docbook4-page-anchors"
    assert [m.label for m in doc.markers] == ["", ""]  # the frozen reader keeps no label
    entry = next(d for d in DATA["dialects"] if d["name"] == doc.dialect.name)
    labels = [marker_label_of(doc, m, entry["page_marker_label"]) for m in doc.markers]
    assert labels == ["FM3", "1"]
    namespaced = b'<book xmlns="http://docbook.org/ns/docbook"><para>x</para></book>'
    assert read_reference(namespaced, dialects).dialect.name == "docbook"
