"""Freeze the Step 11e producer before the Step 11d continuation; approved books only."""

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
from step4b_run import retained_counter
from step7_layouts import BOOKS as SOURCES
from step7_layouts import CACHE
from step11c_run import model_digest

from book_core.cache_store import read_json
from book_core.caching import SCOPES, code_digest
from book_core.extraction.fingerprints import stable_id
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout.invariants import check
from book_core.layout.models import PageLayout
from book_core.lists.keys import book_fingerprint
from book_core.lists.models import PageLists
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import verified_read
from book_core.objects.models import ObjectAnalysis
from book_core.run_context import source_session

OUT = ROOT / "experiments/out/step11d2/before"
BASE = ROOT / "experiments/out/step11e"


def read(path):
    return json.loads(path.read_text("utf8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", "utf8", newline="\n")


def freeze():
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert revision.startswith("ad1acfc"), revision
    assert not subprocess.check_output(["git", "diff", "HEAD", "--", "backend"], cwd=ROOT)
    free = shutil.disk_usage(ROOT).free
    estimate = 1412 * 12 * 1024 * 1024
    assert free - estimate >= 10_000_000_000, (free, estimate)
    current = {
        "revision": revision,
        "producer_scopes": {scope: code_digest(scope) for scope in SCOPES},
        "source_files": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "backend/src").rglob("*.py"))
        },
        "settings_sha256": hashlib.sha256(
            (ROOT / ".vscode/settings.json").read_bytes()
        ).hexdigest(),
        "free_bytes": free,
        "estimate_bytes": estimate,
        "remaining_after_estimate": free - estimate,
        "books": list(identity.BOOKS),
        "existing_python_jobs_on_resume": [],
    }
    path = OUT / "provenance.json"
    if path.exists():
        old = read(path)
        for key in ("revision", "producer_scopes", "source_files", "settings_sha256"):
            assert old[key] == current[key], key
    else:
        write(path, current)


def book_capture(book):
    target = OUT / f"{book}.json"
    source = reference_path(SOURCES[book][0])
    baseline = read(BASE / f"after/{book}.json")
    with source_session(source) as snapshot:
        assert snapshot.digest == baseline["source_sha256"]
        if target.exists():
            row = read(target)
        else:
            row = identity.capture(book)
            write(target, row)
        assert all(row[k] == baseline[k] for k in ("pages", "books", "keys", "source_sha256"))
        gates, ownership, objects = {}, {}, {}
        expected_objects = read(BASE / f"after/{book}_objects.json")
        for number in row["pages"]:
            checkpoint = ROOT / ".cache/step11d2/before" / book / f"{number}.json"
            if checkpoint.exists():
                data = read(checkpoint)
                assert data["keys"] == row["keys"]
            else:
                key = row["keys"]["analysis"]
                analysis = verified_read(
                    CACHE / "analysis" / key / f"{number}.json", ObjectAnalysis, key
                )
                key = row["keys"]["layout"]
                layout = verified_read(CACHE / "layout" / key / f"{number}.json", PageLayout, key)
                key = book_fingerprint(row["keys"]["lists"])
                units = verified_read(
                    ROOT / ".cache/step11/lists/page" / key / f"{number}.json",
                    PageLists,
                    stable_id(key, "page", int(number)),
                )
                assigned = [lid for unit in units.units for lid in unit.line_ids]
                ordered = [lid for stream in units.order.streams for lid in stream.line_ids]
                expected = {line.id for line in layout.lines}
                data = {
                    "keys": row["keys"],
                    "objects": {
                        "native": model_digest(analysis.native),
                        "analysis": model_digest(analysis),
                    },
                    "invariants": check(layout, analysis),
                    "ownership": {
                        "lines": len(expected),
                        "units_once": len(assigned) == len(set(assigned))
                        and set(assigned) == expected,
                        "ordered_once": len(ordered) == len(set(ordered))
                        and set(ordered) == expected,
                    },
                }
                assert data["objects"] == expected_objects[number]
                write(checkpoint, data)
                del analysis, layout, units
                gc.collect()
            objects[number] = data["objects"]
            gates[number] = data["invariants"]
            ownership[number] = data["ownership"]
            if int(number) % 25 == 0:
                print(book, "baseline proof", number, flush=True)
        assert objects == expected_objects
        assert all(not any(r.values()) for r in gates.values())
        assert all(r["units_once"] and r["ordered_once"] for r in ownership.values())
        write(OUT / f"{book}_objects.json", objects)
        write(
            OUT / f"{book}_full_gates.json",
            {
                "invariants": gates,
                "invariant_totals": {
                    name: sum(len(r[name]) for r in gates.values())
                    for name in (f"I{i}" for i in range(1, 8))
                },
                "ownership": ownership,
            },
        )
        metrics = OUT / f"metrics/{book}/summary.json"
        if not metrics.exists():
            step11_run.OUT = OUT / "metrics"
            step11_run.HOLDOUT = {}
            sys.argv = ["step11_run.py", "--book", book]
            step11_run.main()
        before, after = read(BASE / f"metrics/{book}/summary.json"), read(metrics)
        # Preserve both elapsed durations; every other metric/provenance field must match.
        assert {k: v for k, v in before.items() if k != "seconds"} == {
            k: v for k, v in after.items() if k != "seconds"
        }
    print(book, "baseline complete", flush=True)


def source_checks():
    sample = read(ROOT / "experiments/out/step11d/before/sample.json")
    rows = []
    for book, numbers in sample["pages"].items():
        run = read(BASE / f"performance/{book}.json")["run"]
        output = Path(run["output"])
        manifest = read_json(output / "manifest.json.gz")
        assert manifest == read(BASE / "final_outputs.json")[book]["manifest"]
        assert all(
            hashlib.sha256((output / name).read_bytes()).hexdigest() == value
            for name, value in manifest["files"].items()
        )
        source = reference_path(SOURCES[book][0])
        with source_session(source):
            for number in numbers:
                expected = retained_counter(
                    PyMuPDFExtractor("cpu").extract_object_page(source, number).page
                )
                actual = retained_counter(
                    ExtractedPage.model_validate(
                        read_json(output / f"page_{number:06d}.json.gz")["source"]
                    )
                )
                rows.append(
                    {
                        "book": book,
                        "page": number,
                        "tokens": expected.total(),
                        "missing": (expected - actual).total(),
                        "extra": (actual - expected).total(),
                    }
                )
    assert len(rows) == 24 and all(r["missing"] == r["extra"] == 0 for r in rows)
    write(
        OUT / "source_crosscheck.json",
        {"sample": sample, "results": rows, "pages": 24, "missing": 0, "extra": 0},
    )
    ledger = step7_gates.full_book()
    assert ledger["node_token_count"] == 495751 and all(ledger["gate"].values())
    write(OUT / "full_book.json", ledger)


def main():
    freeze()
    for book in identity.BOOKS:
        book_capture(book)
    source_checks()
    freeze()
    write(
        OUT / "complete.json",
        {
            "complete": True,
            "baseline": "ad1acfc",
            "pages": 1412,
            "no_product_changes_before_capture": True,
        },
    )
    print(
        "Baseline complete: all 1412 pages, four metric summaries, frozen sample and ledger",
        flush=True,
    )


if __name__ == "__main__":
    main()
