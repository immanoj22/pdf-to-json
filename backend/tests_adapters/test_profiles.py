"""Profiles: schema validation with lines and suggestions, extends, the store."""

from __future__ import annotations

import json

import pytest

from book_adapters.engine.profile import ProfileError, load_profile, load_schema
from book_adapters.rules import RULES

from .adapter_fixtures import PROFILES


def write(tmp_path, text, name="client.yaml"):
    path = tmp_path / name
    path.write_text(text, "utf-8")
    return path


HEAD = "profile: client\nversion: 1.0.0\ndate: '2026-10-30'\nextends: _base/docbook_base\n"


def problems(path):
    with pytest.raises(ProfileError) as exc:
        load_profile(path, [PROFILES])
    return exc.value.problems


def test_jaypee_profile_loads_and_extends_base():
    profile = load_profile(PROFILES / "jaypee/jaypee_v3.yaml")
    assert profile.name == "jaypee_v3" and profile.version == "3.0.0"
    assert profile.get("ids.section") == "ch{chapter}lev{level}sec{n}"
    # inherited from the base, not set by Jaypee
    assert profile.get("front_matter.sections.preface.element") == "preface"
    # defaults from the schema
    assert profile.get("tables.join_continued") is True
    assert [c["profile"] for c in profile.chain] == ["jaypee_v3", "docbook_base"]
    assert len(profile.resolved_sha256) == 64


def test_unknown_field_reports_line_and_suggestion(tmp_path):
    path = write(tmp_path, HEAD + "ids:\n  chaptr: 'c{chapter}'\n")
    [p] = problems(path)
    assert p.line == 6 and p.path == "ids.chaptr" and p.suggestion == "chapter"
    assert "client.yaml:6" in str(p)


def test_bad_enum_and_type(tmp_path):
    path = write(tmp_path, HEAD + "tables:\n  frame: none\nimages:\n  quality: high\n")
    found = {p.path: p for p in problems(path)}
    assert "tables.frame" in found and found["tables.frame"].line == 6
    assert "images.quality" in found


def test_regex_and_placeholder_checks(tmp_path):
    path = write(
        tmp_path,
        HEAD + "tables:\n  title_label: '(unclosed'\nids:\n  section: 'ch{chapter}lev{levl}'\n",
    )
    found = {p.path: p for p in problems(path)}
    assert "tables.title_label" in found
    assert found["ids.section"].suggestion == "{level}"


def test_missing_required_and_duplicate_key(tmp_path):
    path = write(tmp_path, "profile: client\nversion: 1.0.0\nversion: 1.0.1\n")
    messages = " ".join(p.message for p in problems(path))
    assert "duplicate field" in messages and "'date' is a required property" in messages


def test_extends_merges_and_child_wins(tmp_path):
    write(
        tmp_path,
        "profile: parent\nversion: 1.0.0\ndate: '2026-01-01'\n"
        "ids:\n  chapter: 'c{chapter}'\n  part: 'p{part}'\n",
        "parent.yaml",
    )
    child = write(
        tmp_path,
        "profile: child\nversion: 2.0.0\ndate: '2026-02-02'\nextends: parent\n"
        "ids:\n  chapter: 'chap{chapter}'\n",
    )
    profile = load_profile(child, [tmp_path])
    assert profile.get("ids.chapter") == "chap{chapter}" and profile.get("ids.part") == "p{part}"
    assert profile.version == "2.0.0"


def test_extends_cycle_rejected(tmp_path):
    write(tmp_path, "profile: a\nversion: 1.0.0\ndate: '2026-01-01'\nextends: b\n", "a.yaml")
    write(tmp_path, "profile: b\nversion: 1.0.0\ndate: '2026-01-01'\nextends: a\n", "b.yaml")
    with pytest.raises(ProfileError):
        load_profile(tmp_path / "a.yaml", [tmp_path])


def test_schema_rule_names_match_the_registry():
    schema = load_schema()
    assert set(schema["properties"]["rules"]["items"]["enum"]) == set(RULES)


def test_schema_fields_have_descriptions_for_the_profile_maker():
    schema = load_schema()
    missing = [
        k
        for k, v in schema["properties"].items()
        if k not in ("profile", "version", "date")
        and not v.get("description")
        and v.get("type") != "object"
    ]
    assert not missing


def test_upload_is_stored_as_new_untested_version(store, tmp_path):
    path = write(tmp_path, HEAD.replace("client", "uploaded"))
    stored = store.add(path)
    assert stored.status == "untested" and stored.ref == "uploaded@1.0.0#r1"
    assert store.add(path).file == stored.file  # identical bytes: same entry
    path.write_text(HEAD.replace("client", "uploaded") + "description: changed\n", "utf-8")
    second = store.add(path)
    assert second.ref == "uploaded@1.0.0#r2" and second.file != stored.file
    assert stored.file.read_text("utf-8") == HEAD.replace("client", "uploaded")


def test_existing_profile_is_never_overwritten(store, tmp_path):
    builtin = PROFILES / "jaypee/jaypee_v3.yaml"
    before = builtin.read_bytes()
    copy = write(
        tmp_path,
        before.decode("utf-8").replace("description: >-", "description: >-\n  Edited."),
        "jaypee_v3.yaml",
    )
    stored = store.add(copy)
    assert stored.origin == "uploaded" and stored.status == "untested"
    assert builtin.read_bytes() == before
    assert store.find("jaypee_v3").origin == "builtin"  # the built-in stays the default
    assert store.find(stored.ref).file == stored.file


def test_bad_upload_rejected_before_storing(store, tmp_path):
    path = write(tmp_path, HEAD + "tables:\n  frame: none\n")
    with pytest.raises(ProfileError):
        store.add(path)
    assert not (store.store / "index.jsonl").exists()


def test_list_profiles(store):
    refs = {p.ref for p in store.list()}
    assert "jaypee_v3@3.0.0" in refs and "docbook_base@1.0.0" in refs


def test_cli_validate_reports_problems(tmp_path, capsys):
    from book_adapters.cli import main

    path = write(tmp_path, HEAD + "ids:\n  chaptr: x\n")
    assert main(["--profiles-store", str(tmp_path / "s"), "profiles", "validate", str(path)]) == 1
    err = capsys.readouterr().err
    assert "client.yaml:6" in err and "chapter" in err
    _ = json
