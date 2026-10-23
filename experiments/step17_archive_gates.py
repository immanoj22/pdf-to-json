"""Step 17 copy of the frozen source gate, extended for post-archive assembly and OCR.

All Step 14a/15 ownership, checksum, reference, source and ledger assertions remain.
Assembly evidence is produced after the archive, so it is not an archive manifest key.
OCR rasters are referenced evidence assets alongside figures and equation fallbacks;
all are required to match the manifest exactly and every asset checksum is verified.
The earlier gate files remain untouched.
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step7_gates
import step13b_source_gates as gates13b
import step13c_source_gates as gates13c
import step15_source_gates as s15
from reference_paths import reference_path
from step4b_run import retained_counter
from step11c_identity import digest
from step13_books import BOOKS
from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.model.spans import ExtractedPage
from book_core.run_context import source_session

RUN = ROOT / "experiments/out/step17/final"
BASELINE = RUN / "source_baseline"
MATH_BOOK = "statistics"
PageLists = s15.ListsView
check_tables = s15.check_tables


def read(path):
    return json.loads(Path(path).read_text("utf-8"))


def write(name, value):
    (RUN / name).write_text(json.dumps(value, indent=1) + "\n", "utf-8", newline="\n")


def main():
    sample = read(gates13c.SAMPLE)
    math_run = read(RUN / f"performance/{MATH_BOOK}.json")["run"]
    sample["pages"][MATH_BOOK] = gates13b.math_sample(math_run["pages"])
    rows, final_tokens, archives = [], {}, {}
    for book, numbers in sample["pages"].items():
        run = read(RUN / f"performance/{book}.json")["run"]
        output = Path(run["output"])
        math = book == MATH_BOOK
        identity = None if math else read(RUN / f"after/{book}.json")
        baseline = None if math else read(BASELINE / f"{book}.json")
        manifest = read_json(output / "manifest.json.gz")
        assert manifest["complete"] and manifest["keys"] == {
            k: v for k, v in run["cache_keys"].items() if k != "assembly_evidence"}
        pages = {f"page_{n:06d}.json.gz" for n in range(1, run["pages"] + 1)}
        images = {name for name in manifest["files"] if name.startswith("images/")}
        assert set(manifest["files"]) == {"book.json.gz", *pages, *images}
        total = 0
        counts = {k: Counter() for k in ("figures", "equations", "mathml", "tables")}
        expected_images, equation_images = set(), []
        for name, checksum in manifest["files"].items():
            path = output / name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
            if name.startswith("images/"):
                continue
            payload = read_json(path)
            if name == "book.json.gz":
                if not math:
                    assert digest(payload["structure"]) == identity["books"]["structure"]
                    assert digest(payload["lists"]) == identity["books"]["lists"]
                expected_images |= {f"images/{n}" for n in payload["mathml"]["images"]}
                continue
            source = ExtractedPage.model_validate(payload["source"])
            number = str(source.geometry.page)
            if payload.get("ocr", {}).get("raster_asset"):
                expected_images.add("images/" + payload["ocr"]["raster_asset"])
            units = PageLists.model_validate(payload["units"])
            if not math:
                text_digest = digest(source.model_dump(mode="json"))
                assert text_digest == identity["pages"][number]["native_text"]
                assert text_digest == baseline["pages"][number]["native_text"]
                assert digest(units.model_dump(mode="json")) == identity["pages"][number]["lists"]
            lines = Counter(line for unit in units.units for line in unit.line_ids)
            assert set(lines) == set(payload["line_spans"]) and set(lines.values()) <= {1}
            counts["figures"].update(
                gates13b.check_figures(payload, units, payload["line_spans"], output)
            )
            counts["equations"].update(gates13b.check_equations(payload, source, units))
            found, names = gates13c.check_mathml(payload, source, output)
            counts["mathml"].update(found)
            equation_images += names
            counts["tables"].update(check_tables(payload, source, units))
            expected_images |= {
                f"images/{f['image']['file_name']}"
                for f in payload["figures"]["figures"]
                if f.get("image")
            }
            total += retained_counter(source).total()
        assert images == expected_images, "archive images differ from final figures + fallbacks"
        assert len(equation_images) == len(set(equation_images))
        archives[book] = {
            "output": str(output),
            "files": len(manifest["files"]),
            "image_files": len(images),
            "figures": counts["figures"]["figures"],
            "equations": dict(sorted(counts["equations"].items())),
            "mathml": dict(sorted(counts["mathml"].items())),
            "tables": dict(sorted(counts["tables"].items())),
            "all_checks_pass": True,
        }
        final_tokens[book] = total
        with source_session(reference_path(BOOKS[book][0])):
            for number in numbers:
                fresh = (
                    PyMuPDFExtractor("cpu")
                    .extract_object_page(reference_path(BOOKS[book][0]), number)
                    .page
                )
                final = ExtractedPage.model_validate(
                    read_json(output / f"page_{number:06d}.json.gz")["source"]
                )
                expected, actual = retained_counter(fresh), retained_counter(final)
                rows.append(
                    {
                        "book": book,
                        "page": number,
                        "tokens": expected.total(),
                        "missing": (expected - actual).total(),
                        "extra": (actual - expected).total(),
                    }
                )
        if book == "spanish_us_history":
            assert total == 495751
    write(
        "source_crosscheck.json",
        {
            "sample": sample,
            "pages": len(rows),
            "missing": sum(r["missing"] for r in rows),
            "extra": sum(r["extra"] for r in rows),
            "results": rows,
            "final_archive_retained_tokens": final_tokens,
        },
    )
    assert len(rows) == 30 and all(r["missing"] == r["extra"] == 0 for r in rows)
    ledger = step7_gates.full_book()
    assert ledger["node_token_count"] == 495751 and all(ledger["gate"].values())
    write("full_book.json", ledger)
    write("final_outputs.json", archives)
    print(json.dumps({"archives": archives, "tokens": final_tokens}, indent=1))
    print("30 source pages: 0/0; Spanish ledger and final source archive: 495751")
