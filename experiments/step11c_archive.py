"""Republish verified Stage 1 outputs with the final visual-line/span reference map.

No extraction, classification, scoring or source-text transformation is performed.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step11c"
sys.path.insert(0, str(ROOT / "backend/src"))

from reference_paths import reference_path  # noqa: E402
from step7_layouts import BOOKS as SOURCES  # noqa: E402
from step11c_identity import BOOKS, digest  # noqa: E402

from book_core.book_run import LOADED_FINAL_DIGEST, _publish_final  # noqa: E402
from book_core.cache_store import read_json, read_model  # noqa: E402
from book_core.layout.models import PageLayout  # noqa: E402
from book_core.run_context import source_session  # noqa: E402
from book_core.telemetry import measure  # noqa: E402


def republish(book):
    run = json.loads((OUT / "performance" / f"{book}_workers1.json").read_text("utf8"))
    identity = json.loads((OUT / "after" / f"{book}.json").read_text("utf8"))
    original = Path(run["output"])
    manifest = read_json(original / "manifest.json.gz")
    assert manifest["complete"] and manifest["keys"] == run["cache_keys"]
    for name, checksum in manifest["files"].items():
        assert hashlib.sha256((original / name).read_bytes()).hexdigest() == checksum
    measured = {}
    checked = []
    with (
        measure(measured, "publication"),
        source_session(reference_path(SOURCES[book][0])) as snapshot,
    ):
        assert snapshot.digest == identity["source_sha256"] == manifest["source_sha256"]

        def pages():
            for number in range(1, run["pages"] + 1):
                payload = read_json(original / f"page_{number:06d}.json.gz")
                frozen = identity["pages"][str(number)]
                assert digest(payload["source"]) == frozen["native_text"]
                assert digest(payload["units"]) == frozen["lists"]
                key = run["cache_keys"]["layout"]
                layout = read_model(
                    ROOT / ".cache/step7/layout" / key / f"{number}.json", PageLayout, key
                )
                assert layout.source_sha256 == snapshot.digest and layout.page == number
                lines = {line for unit in payload["units"]["units"] for line in unit["line_ids"]}
                payload["line_spans"] = {
                    line.id: line.span_ids for line in layout.lines if line.id in lines
                }
                assert set(payload["line_spans"]) == lines
                spans = payload["source"]["store"]["spans"]
                assert all(span in spans for ids in payload["line_spans"].values() for span in ids)
                checked.append(number)
                yield payload

        output = _publish_final(
            snapshot,
            pages(),
            read_json(original / "book.json.gz"),
            run["cache_keys"],
            original.parent,
            run["pages"],
        )
    result = {
        "output": str(output),
        "original_output": str(original),
        "producer": LOADED_FINAL_DIGEST,
        "pages": len(checked),
        "source_and_units_identical": True,
        "line_span_references_resolved": True,
        "measurements": measured,
    }
    target = OUT / "archive"
    target.mkdir(exist_ok=True)
    (target / f"{book}.json").write_text(json.dumps(result, indent=2) + "\n", "utf8")
    print(book, result, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=BOOKS)
    args = parser.parse_args()
    for book in (args.book,) if args.book else BOOKS:
        republish(book)
