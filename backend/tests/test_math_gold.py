"""Math gold reader: equations become slots between reference tokens, from profile data."""

from book_core.evaluation.math_gold import _count_fits, _expected_glyphs, read_math_reference

COLLECTION = """<col:collection xmlns:col="http://cnx.rice.edu/collxml"
 xmlns:md="http://cnx.rice.edu/mdml"><col:content>
<col:subcollection><md:title>Chapter One</md:title><col:content>
<col:module document="m1"/></col:content></col:subcollection>
</col:content></col:collection>"""

MODULE = """<document xmlns="http://cnx.rice.edu/cnxml" xmlns:m="http://www.w3.org/1998/Math/MathML"
 xmlns:md="http://cnx.rice.edu/mdml"><title>Means</title>
<metadata><md:title>Hidden metadata</md:title></metadata><content>
<para id="p1">The fraction <m:math><m:mfrac><m:mn>1</m:mn><m:mn>2</m:mn></m:mfrac></m:math>
 equals one half.</para>
<equation id="e1"><m:math><m:mi>x</m:mi><m:mo>=</m:mo><m:mn>2</m:mn></m:math></equation>
<para>After it, <m:math display="block"><m:mi>y</m:mi></m:math> ends.</para>
</content></document>"""


def _collection(tmp_path):
    (tmp_path / "collections").mkdir()
    (tmp_path / "collections" / "book.collection.xml").write_text(COLLECTION, "utf-8")
    (tmp_path / "modules" / "m1").mkdir(parents=True)
    (tmp_path / "modules" / "m1" / "index.cnxml").write_text(MODULE, "utf-8")
    return tmp_path


def test_equations_are_slots_between_reference_tokens(tmp_path):
    reference = read_math_reference(_collection(tmp_path))
    tokens = [t.value for t in reference.document.tokens]
    assert "Hidden" not in tokens  # metadata is not printed text
    assert "1" not in tokens and "x" not in tokens  # equation leaves are not text tokens
    first, block, last = reference.slots
    assert tokens[first.token_before] == "fraction" and tokens[first.token_after] == "equals"
    assert (first.presentation, block.presentation, last.presentation) == (
        "inline",
        "display",
        "display",
    )
    assert first.leaf_text == "1 2" and block.anchor_id == "e1"
    assert "equation_block" in block.contexts
    assert all(len(s.mathml_sha256) == 64 for s in reference.slots)
    assert reference.mathml[0].startswith("<math")


def test_glyph_count_check():
    assert _expected_glyphs("2,000 / 5") == 7
    assert _count_fits(8, 7) and not _count_fits(12, 7) and not _count_fits(1, 0)


def test_committed_math_gold_is_provisional_and_consistent():
    import gzip
    import hashlib
    import json
    from pathlib import Path

    folder = Path(__file__).parent / "gold_derived_math" / "statistics"
    manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
    assert manifest["human_approved"] is False
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
    with gzip.open(folder / "equations.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    assert len(rows) == manifest["counts"]["equations"]
    verified = [row for row in rows if row["verified"]]
    assert len(verified) == manifest["counts"]["verified"]
    assert all(row["status"] == "located" and row["glyph_count_fits"] for row in verified)
    assert all(row["page"] and row["bbox"] for row in rows if row["status"] == "located")
