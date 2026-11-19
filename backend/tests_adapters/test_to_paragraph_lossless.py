"""A list made one paragraph (cut words joined by line-end join records) and merged paragraphs
export lossless: 0 missing, 0 extra, output matches the ledger, DTD valid. A small book; the
same change on the real German book is checked once by hand."""

from __future__ import annotations

import json
import shutil

from book_app import overlay

from .test_adapter_b import assert_lossless, base_book, export

TEXTS = ["Das ist kein Analysemo\ndell zu verstehen, sondern ein ", "Gegenstandsbereich der Arbeit auch an",
         "dere Fälle auf Meta- und Objektebene, vom Dis\nsens aus."]  # fmt: skip


def edited(tmp_path, *edits_for):
    b, pages = base_book()
    dash = {"text": "-", "type": "dash", "punctuation": "none", "value": None}
    lst = b.list(pages[0], [b.item(pages[0], t, dash) for t in TEXTS])
    one = b.para(pages[0], "Ein Methoden-")
    two = b.para(pages[0], "vergleich zeigt es")
    src = b.finish(tmp_path / "book")
    data = json.loads((src / "book.json").read_text())
    edits = [{"id": "e1", "op": "to_paragraph", "units": [lst["id"]]},
             {"id": "e2", "op": "merge", "units": [one["id"], two["id"]]}]  # fmt: skip
    out, _, failed = overlay.apply_edits(data, edits)
    assert not failed, failed
    dst = tmp_path / "edited"
    shutil.copytree(src, dst)
    (dst / "book.json").write_text(json.dumps(out))
    return dst


def test_export_after_to_paragraph_and_merge_is_lossless(tmp_path, store):
    report, _, xml = export(edited(tmp_path), tmp_path, store)
    assert_lossless(report)
    text = " ".join("".join(xml.itertext()).split())
    assert "Analysemodell" in text and "andere Fälle" in text and "Dissens" in text
    assert "Meta- und Objektebene" in text and "Methodenvergleich" in text
