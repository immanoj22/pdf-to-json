"""Step 13c source, ledger and final-archive gates (the Step 13b gates plus MathML records).

Added for 13c: every equation region has exactly one MathML record on its page; every
recorded MathML string is well-formed MathML 3 presentation markup (lxml); a record marked
``paths_agree`` has agreeing paths; a ``must_check`` record keeps its original evidence
(output text or image, never MathML) and carries an image fallback archived with its
checksum; every traced source of a reading is a character of an archived span or a drawn
object of the region; the archive images are the exported figure images plus the equation
image fallbacks. Text, units and lines are checked against the Step 13b baseline exactly as
in Step 13b.
"""

# ruff: noqa: E402
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step7_gates
import step13b_source_gates as gates13b
from reference_paths import reference_path
from step4b_run import retained_counter
from step11c_identity import digest
from step13_books import BOOKS

from book_core.cache_store import read_json
from book_core.equations.models import PageEquations
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.lists.models import PageLists
from book_core.mathml import markup
from book_core.mathml.models import PageMath
from book_core.model.spans import ExtractedPage
from book_core.run_context import source_session

RUN = ROOT / "experiments/out/step13c" / os.environ.get("STEP13_OUT", "final")
MATH_BOOK = "statistics"
SAMPLE = ROOT / "experiments/out/step11d/before/sample.json"
BASELINE = ROOT / "experiments/out/step13c/before"


def read(path):
    return json.loads(Path(path).read_text("utf-8"))


def write(name, value):
    path = RUN / name
    path.write_text(json.dumps(value, indent=1) + "\n", encoding="utf-8", newline="\n")


def check_mathml(payload, source, output):
    math = PageMath.model_validate(payload["mathml"])
    regions = {r.id: r for r in PageEquations.model_validate(payload["equations"]).regions}
    assert sorted(e.equation_id for e in math.equations) == sorted(regions)
    spans = source.store.spans
    counts = Counter()
    for record in math.equations:
        region = regions[record.equation_id]
        counts["records"] += 1
        counts[f"review_{record.review_status}"] += 1
        counts[f"output_{record.output}"] += 1
        counts[f"agreement_{record.agreement}"] += 1
        assert record.source == region.source and record.presentation == region.presentation
        # Output MathML (chosen reading, reference parts) must validate; a path reading that
        # fails validation is kept for review only with its validation problems listed.
        for value in [record.mathml, *(p.mathml for p in record.parts)]:
            if value is not None:
                assert markup.validate(value) == [], "invalid output MathML"
        for reading in record.readings:
            if reading.mathml is not None and (problems := markup.validate(reading.mathml)):
                assert set(problems) <= set(reading.problems), "unflagged invalid MathML"
                assert reading.mathml != record.mathml
                counts["invalid_readings_flagged"] += 1
        if record.review_status == "paths_agree":
            assert record.agreement == "agree"
        if record.review_status == "must_check":
            assert record.output in {"text", "image"} and record.fallback_image is not None
        if record.fallback_image is not None:
            data = (output / "images" / record.fallback_image.file_name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == record.fallback_image.sha256
            counts["fallback_images"] += 1
        if record.source == "text" and record.output == "text":
            counts["text_kept_as_text"] += 1
        objects = set(region.object_ids)
        for item in record.sources:
            if item is None:
                continue
            if ":" in item:
                span_id, offset = item.rsplit(":", 1)
                assert span_id in spans and 0 <= int(offset) < len(spans[span_id].raw_text)
            else:
                assert item in objects, "a traced source outside the region"
    return counts, [r.fallback_image.file_name for r in math.equations if r.fallback_image]


def main():
    sample = read(SAMPLE)
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
        assert manifest["complete"] and manifest["keys"] == run["cache_keys"]
        if not math:
            assert manifest["source_sha256"] == identity["source_sha256"]
        pages = {f"page_{n:06d}.json.gz" for n in range(1, run["pages"] + 1)}
        images = {name for name in manifest["files"] if name.startswith("images/")}
        assert set(manifest["files"]) == {"book.json.gz", *pages, *images}
        total = 0
        figure_counts, equation_counts, math_counts = Counter(), Counter(), Counter()
        equation_images = []
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
                not_exported = payload["equations"]["images_not_exported"]
                figure_images = payload["figures"]["profile"]["images"] - len(not_exported)
                assert figure_images + len(payload["mathml"]["images"]) == len(images)
                assert not {f"images/{n}" for n in not_exported} & images
                assert {f"images/{n}" for n in payload["mathml"]["images"]} <= images
                assert payload["equations"]["pages"] == payload["mathml"]["pages"] == run["pages"]
                continue
            source = ExtractedPage.model_validate(payload["source"])
            number = str(source.geometry.page)
            units = PageLists.model_validate(payload["units"])
            if not math:
                text_digest = digest(source.model_dump(mode="json"))
                assert text_digest == identity["pages"][number]["native_text"]
                assert text_digest == baseline["pages"][number]["native_text"]
                assert digest(units.model_dump(mode="json")) == identity["pages"][number]["lists"]
            counts = Counter(line for unit in units.units for line in unit.line_ids)
            assert set(counts) == set(payload["line_spans"]) and set(counts.values()) <= {1}
            assert all(
                ids and all(sid in source.store.spans for sid in ids)
                for ids in payload["line_spans"].values()
            )
            figure_counts.update(
                gates13b.check_figures(payload, units, payload["line_spans"], output)
            )
            equation_counts.update(gates13b.check_equations(payload, source, units))
            found, names = check_mathml(payload, source, output)
            math_counts.update(found)
            equation_images += names
            total += retained_counter(source).total()
        assert len(equation_images) == len(set(equation_images))
        archives[book] = {
            "output": str(output),
            "files": len(manifest["files"]),
            "image_files": len(images),
            "equation_image_files": len(equation_images),
            "figures": figure_counts["figures"],
            "equations": dict(sorted(equation_counts.items())),
            "mathml": dict(sorted(math_counts.items())),
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


if __name__ == "__main__":
    main()
