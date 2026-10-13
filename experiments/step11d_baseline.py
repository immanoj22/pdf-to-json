"""Freeze the unchanged bad1516 baseline before editing any existing producer.

Frozen output refuses replacement. The executed source snapshot and resumable
per-page proof describe the original capture; this maintained copy is formatted.
"""

# ruff: noqa: E402
import gc
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step7_gates
import step11_run
import step11c_identity as identity
from reference_paths import reference_path
from step7_layouts import BOOKS as SOURCES
from step7_layouts import CACHE
from step11c_run import model_digest

from book_core.objects.analysis import verified_read
from book_core.objects.models import ObjectAnalysis
from book_core.run_context import source_session

OUT = ROOT / "experiments/out/step11d/before"
if (OUT / "complete.json").exists():
    raise SystemExit("Baseline is frozen; use the committed evidence, not an overwrite.")


def write(path, value):
    if path.exists():
        raise ValueError("Baseline is frozen: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", "utf8")


revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
assert revision.startswith("bad1516")
assert not subprocess.check_output(["git", "diff", "HEAD", "--", "backend", "experiments", "docs"])
status = subprocess.check_output(
    ["git", "status", "--porcelain=v1", "--untracked-files=all"], text=True
)
assert "?? .vscode/settings.json" in status
tracked = subprocess.check_output(
    ["git", "ls-files", "backend/src", "backend/tests", "experiments/step11c*", "docs"], text=True
).splitlines()
source_proof = {}
for name in tracked:
    committed = subprocess.check_output(["git", "show", revision + ":" + name])
    actual = (ROOT / name).read_bytes()
    # Git checkout may use CRLF; compare Git's own clean-filter blob hash.
    expected = subprocess.check_output(
        ["git", "rev-parse", revision + ":" + name], text=True
    ).strip()
    got = subprocess.check_output(["git", "hash-object", "--path=" + name, name], text=True).strip()
    assert got == expected, name
    source_proof[name] = expected
free = shutil.disk_usage(ROOT).free
estimate = 1412 * 12 * 1024 * 1024
assert free - estimate >= 10_000_000_000
(lambda p, v: None if p.exists() else write(p, v))(
    OUT / "provenance.json",
    {
        "revision": revision,
        "tracked_blobs": source_proof,
        "preexisting_untracked_exception": status.strip(),
        "exception_authorized_by_user": True,
        "settings_sha256": hashlib.sha256(
            (ROOT / ".vscode/settings.json").read_bytes()
        ).hexdigest(),
        "disk_free_bytes": free,
        "estimated_additional_bytes": estimate,
        "remaining_after_estimate_bytes": free - estimate,
        "sealed_and_robustness_books_run": False,
    },
)
for book in identity.BOOKS:
    with source_session(reference_path(SOURCES[book][0])):
        row = (
            json.loads((OUT / f"{book}.json").read_text("utf8"))
            if (OUT / f"{book}.json").exists()
            else identity.capture(book)
        )
        committed = json.loads(
            (ROOT / "experiments/out/step11c/after" / f"{book}.json").read_text("utf8")
        )
        assert (
            row["pages"] == committed["pages"]
            and row["books"] == committed["books"]
            and row["keys"] == committed["keys"]
        ), book
        (lambda p, v: None if p.exists() else write(p, v))(OUT / f"{book}.json", row)
        print("identity", book, len(row["pages"]), flush=True)
        from book_core.extraction.fingerprints import stable_id
        from book_core.layout.invariants import check as invariant_check
        from book_core.layout.models import PageLayout
        from book_core.lists.keys import book_fingerprint
        from book_core.lists.models import PageLists

        objects = {}
        invariant_rows = {}
        ownership = {}
        frozen = json.loads(
            (ROOT / "experiments/out/step11c/before" / f"{book}_objects.json").read_text("utf8")
        )
        for number in row["pages"]:
            checkpoint = ROOT / ".cache/step11d/proof" / book / f"{number}.json"
            if checkpoint.exists():
                proof = json.loads(checkpoint.read_text("utf8"))
            else:
                key = row["keys"]["analysis"]
                value = verified_read(
                    CACHE / "analysis" / key / f"{int(number)}.json", ObjectAnalysis, key
                )
                proof = {
                    "objects": {
                        "native": model_digest(value.native),
                        "analysis": model_digest(value),
                    }
                }
                layout = verified_read(
                    CACHE / "layout" / row["keys"]["layout"] / f"{number}.json",
                    PageLayout,
                    row["keys"]["layout"],
                )
                proof["invariants"] = invariant_check(layout, value)
                key = book_fingerprint(row["keys"]["lists"])
                units = verified_read(
                    ROOT / ".cache/step11/lists/page" / key / f"{number}.json",
                    PageLists,
                    stable_id(key, "page", int(number)),
                )
                assigned = [lid for u in units.units for lid in u.line_ids]
                ordered = [lid for stream in units.order.streams for lid in stream.line_ids]
                expected = {line.id for line in layout.lines}
                proof["ownership"] = {
                    "lines": len(expected),
                    "units_once": len(assigned) == len(set(assigned)) and set(assigned) == expected,
                    "ordered_once": len(ordered) == len(set(ordered)) and set(ordered) == expected,
                }
                assert proof["objects"] == frozen[number], (book, number)
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                checkpoint.write_text(json.dumps(proof, indent=2) + "\n", "utf8")
                del value, layout, units
                gc.collect()
            objects[number] = proof["objects"]
            invariant_rows[number] = proof["invariants"]
            ownership[number] = proof["ownership"]
            if int(number) % 50 == 0:
                print("objects/invariants", book, number, flush=True)
        assert objects == frozen, book
        (lambda p, v: None if p.exists() else write(p, v))(OUT / f"{book}_objects.json", objects)
        write(
            OUT / f"{book}_full_gates.json",
            {
                "invariants": invariant_rows,
                "invariant_totals": {
                    name: sum(len(r[name]) for r in invariant_rows.values())
                    for name in ("I1", "I2", "I3", "I4", "I5", "I6", "I7")
                },
                "ownership": ownership,
            },
        )
        step11_run.OUT = OUT / "metrics"
        step11_run.HOLDOUT = {}
        sys.argv = ["step11_run.py", "--book", book]
        step11_run.main()
        print("metrics", book, flush=True)
# Fresh source sample restricted to the four approved books. Historical fixture
# driver is not invoked because it opens science and Canadian-index sources.
import random

from step4b_run import retained_counter

from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.model.spans import ExtractedPage

sample = {
    book: sorted(
        random.Random("step11d-baseline:" + book).sample(
            range(1, len(json.loads((OUT / f"{book}.json").read_text("utf8"))["pages"]) + 1), 6
        )
    )
    for book in identity.BOOKS
}
write(
    OUT / "sample.json",
    {
        "procedure": (
            "six pages per approved book, random.Random(step11d-baseline:<book>), "
            "sorted; frozen before producer changes"
        ),
        "pages": sample,
    },
)
checks = []
for book, numbers in sample.items():
    source = reference_path(SOURCES[book][0])
    archive = json.loads(
        (ROOT / "experiments/out/step11c/archive" / f"{book}.json").read_text("utf8")
    )
    with source_session(source):
        for number in numbers:
            expected = retained_counter(
                PyMuPDFExtractor("cpu").extract_object_page(source, number).page
            )
            actual = retained_counter(
                ExtractedPage.model_validate(
                    read_json(Path(archive["output"]) / f"page_{number:06d}.json.gz")["source"]
                )
            )
            checks.append(
                {
                    "book": book,
                    "page": number,
                    "tokens": expected.total(),
                    "missing": (expected - actual).total(),
                    "extra": (actual - expected).total(),
                }
            )
write(
    OUT / "source_crosscheck.json",
    {
        "pages": 24,
        "missing": sum(r["missing"] for r in checks),
        "extra": sum(r["extra"] for r in checks),
        "results": checks,
    },
)
write(OUT / "full_book.json", step7_gates.full_book())
write(OUT / "complete.json", {"complete": True, "revision": revision, "books": identity.BOOKS})
