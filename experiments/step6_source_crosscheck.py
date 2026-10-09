"""Step 6 unchanged 24-page text gate against original configured sources."""

import json
from pathlib import Path

from step4b_run import configured_source, retained_counter

from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step4b"


def main():
    originals = json.loads((ROOT / "experiments/out/fixtures_manifest.json").read_text("utf8"))
    originals += json.loads(
        (ROOT / "experiments/out/step4av/fixtures_manifest.json").read_text("utf8")
    )
    metadata = {row["id"]: row for row in originals}
    manifest = json.loads((OUT / "manifest.json").read_text("utf8"))
    extractor = PyMuPDFExtractor("cpu")
    rows = []
    for measured in manifest["pages"]:
        name = measured["page"]
        original = metadata[name]
        source = configured_source(original["source_key"])
        if source_digest(source) != original["source_sha256"]:
            raise ValueError(f"{name}: original source digest changed")
        source_page = extractor.extract_object_page(source, original["physical_page"]).page
        fixture = ROOT / measured["source"]
        fixture_page = extractor.extract_object_page(fixture, 1).page
        expected, actual = retained_counter(source_page), retained_counter(fixture_page)
        row = {
            "page": name,
            "source_key": original["source_key"],
            "physical_page": original["physical_page"],
            "retained_tokens": actual.total(),
            "missing": (expected - actual).total(),
            "extra": (actual - expected).total(),
        }
        rows.append(row)
        print(name, row["missing"], row["extra"], flush=True)
        if row["missing"] or row["extra"]:
            raise AssertionError(row)
    report = {
        "pages": len(rows),
        "missing": sum(row["missing"] for row in rows),
        "extra": sum(row["extra"] for row in rows),
        "results": rows,
        "method": (
            "Original native source vs fixture through Extractor; TrimBox-centre NFKC token Counter"
        ),
    }
    (ROOT / "experiments/out/step6/original_source_crosscheck.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf8"
    )


if __name__ == "__main__":
    main()
