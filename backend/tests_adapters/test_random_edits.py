"""Whatever edits a reviewer makes (repeated chapter numbers, headings made parts or chapters,
headings removed), the DocBook and ePub exports keep every word, write each once, and give
every chapter, part and file its own name."""

from __future__ import annotations

import json
import random
import re
import zipfile

import pytest

from book_adapters.engine.epub_run import run_epub
from book_adapters.engine.run import run_book
from book_app import overlay

from .adapter_fixtures import BookBuilder

MOD = "2026-11-04T00:00:00Z"
CHAPTERS = 4


def make_book(folder):
    b = BookBuilder()
    s = b.section("chapter", "body")
    heads = []
    for n in range(1, CHAPTERS + 1):
        p = b.page(str(n), "body", s)
        heads.append(b.heading(p, f"Chapter title {n}", 1, "chapter")["id"])
        heads.append(b.heading(p, f"Section {n}", 2, "section")["id"])
        b.para(p, f"Words of chapter {n} alpha{n} beta{n}.")
    return json.loads((b.finish(folder) / "book.json").read_text()), heads


def random_edit(rng, heads):
    unit = rng.choice(heads)
    return rng.choice([
        {"op": "heading_number", "unit": unit, "number": rng.choice(["1", "2", "3", "A", "IV"])},
        {"op": "heading_kind", "unit": unit, "kind": rng.choice(["part", "chapter", "section"])},
        {"op": "new_chapter", "unit": unit},
        {"op": "heading_remove", "unit": unit},
        {"op": "heading_attach", "unit": unit},
        {"op": "heading_set", "unit": unit, "level": rng.choice([1, 2, 3])},
    ])


def words_in(text):
    return sorted(re.findall(r"(?:alpha|beta)\d|Chapter|Section|title|Words|of|chapter", text))


@pytest.mark.parametrize("seed", range(6))
def test_random_edits_never_lose_or_repeat_text(tmp_path, store, settings_file, seed):
    rng = random.Random(seed)
    data, heads = make_book(tmp_path / "bk")
    edits = [{"id": f"e{i}", **random_edit(rng, heads)} for i in range(rng.randint(3, 12))]
    edited, applied, _ = overlay.apply_checked(data, edits)
    book = overlay.write_overlay(tmp_path / "bk", edited, tmp_path / "edited", check=False)
    report = run_book(book, tmp_path / "docbook", settings_file, None, store,
                      allow_alt_text_placeholders=True)  # fmt: skip
    loss = report["checks"]["lossless"]
    assert (loss["missing"], loss["extra"]) == (0, 0), (seed, applied)
    assert not (report["checks"].get("dtd") or {}).get("errors"), (seed, report["checks"]["dtd"])
    epub = run_epub(book, tmp_path / "epub", settings_file, None, store,
                    allow_alt_text_placeholders=True, modified=MOD)  # fmt: skip
    own = epub["checks"]["epub"]["lossless"]
    assert (own["missing"], own["extra"]) == (0, 0), (seed, applied)
    names = zipfile.ZipFile(epub["epub"]).namelist()
    assert len(names) == len(set(names))
    text = "".join(zipfile.ZipFile(epub["epub"]).read(n).decode() for n in names if n.endswith(".xhtml"))
    for n in range(1, CHAPTERS + 1):  # each chapter's words are written once
        assert text.count(f"alpha{n}") == 1, (seed, n)


def test_chapters_with_one_number_get_their_own_ids_and_files(tmp_path, store, settings_file):
    data, heads = make_book(tmp_path / "bk")
    edits = [{"id": f"e{i}", "op": "heading_number", "unit": heads[i * 2], "number": "1"}
             for i in range(CHAPTERS)]  # fmt: skip
    edited, applied, failed = overlay.apply_checked(data, edits)
    assert not failed
    book = overlay.write_overlay(tmp_path / "bk", edited, tmp_path / "edited", check=False)
    run_book(book, tmp_path / "docbook", settings_file, None, store, allow_alt_text_placeholders=True)
    ids = re.findall(r'<chapter[^>]* id="([^"]+)"', "".join(
        p.read_text("utf-8") for p in (tmp_path / "docbook").rglob("Chapters/*.xml")))
    assert len(ids) == len(set(ids)) == CHAPTERS, ids


def test_a_number_set_as_printed_is_the_label_and_a_safe_id(tmp_path, store, settings_file):
    """"2.1", "IV" and "A" are accepted by Set number and used as printed: the label shows
    them, the id and file are made safe (ch2.1 -> ch2_1), nothing is lost (lossless 0/0)."""
    data, heads = make_book(tmp_path / "bk")
    printed = ["2.1", "IV", "A.1", "3.10"]
    edits = [{"id": f"e{i}", "op": "heading_number", "unit": heads[i * 2], "number": printed[i]}
             for i in range(CHAPTERS)]  # fmt: skip
    edited, applied, failed = overlay.apply_checked(data, edits)
    assert not failed and len(applied) == CHAPTERS
    book = overlay.write_overlay(tmp_path / "bk", edited, tmp_path / "edited", check=False)
    report = run_book(book, tmp_path / "docbook", settings_file, None, store,
                      allow_alt_text_placeholders=True)  # fmt: skip
    xml = "".join(p.read_text("utf-8") for p in (tmp_path / "docbook").rglob("Chapters/*.xml"))
    ids = re.findall(r'<chapter[^>]* id="([^"]+)"', xml)
    assert sorted(ids) == sorted(["ch2_1", "chIV", "chA_1", "ch3_10"]), ids
    labels = re.findall(r'<chapter[^>]* label="([^"]+)"', xml)
    assert sorted(labels) == sorted(f"CHAPTER {n}" for n in printed), labels
    loss = report["checks"]["lossless"]
    assert (loss["missing"], loss["extra"]) == (0, 0)
    epub = run_epub(book, tmp_path / "epub", settings_file, None, store,
                    allow_alt_text_placeholders=True, modified=MOD)  # fmt: skip
    own = epub["checks"]["epub"]["lossless"]
    assert (own["missing"], own["extra"]) == (0, 0)
    names = zipfile.ZipFile(epub["epub"]).namelist()
    assert any(n.endswith("ch2_1.xhtml") for n in names), names
    with pytest.raises(overlay.EditError):
        overlay._number("2..1")
