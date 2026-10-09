"""Frozen, manually annotated native-block comparison; not a hold-out analysis run.

Run --select before annotation or prediction. The selection algorithm is source-independent:
12 uniform page quantiles, alternating short/medium/long character targets. Inspect extracted
text, annotate expected languages, then run --compare. Book 2 is used only for this explicitly
requested language-library sample; all document evidence remains held out until the final run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import distribution, version
from pathlib import Path

from reference_paths import PROJECT_ROOT, reference_path

from book_core.document_analysis.language import LinguaLanguageDetector, native_block_text
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

SAMPLE = PROJECT_ROOT / "experiments/step6_language_sample.json"
OUT = PROJECT_ROOT / "experiments/out/step6"
BOOKS = {
    "spanish_us_history": {
        "reference_key": "spanish_pdf",
        "source_sha256": "de9d916687ecbe556f7a01f1d871048ec89f362ae5c4b399bd08098b1fddc951",
    },
    "immigrant_children": {
        "reference_key": "small_pdf",
        "source_sha256": "4825a40c9905048df0cee7eb173802438e5c7b71fe2d768255dc09314baa593f",
    },
}
LICENSES = {
    "lingua-language-detector": {
        "license": "Apache-2.0",
        "url": "https://raw.githubusercontent.com/pemistahl/lingua-py/main/LICENSE.txt",
        "copyleft": False,
    },
    "langid": {
        "license": "BSD-2-Clause",
        "url": "https://raw.githubusercontent.com/saffsd/langid.py/master/LICENSE",
        "copyleft": False,
    },
}


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", "utf-8")


def _log(record: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    record = {"utc": datetime.now(UTC).isoformat(), **record}
    with (OUT / "language_sample_runs.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def select() -> None:
    if SAMPLE.exists():
        raise SystemExit("Refusing to overwrite the annotated sample")
    extractor = PyMuPDFExtractor("cpu")
    rows = []
    for book, spec in BOOKS.items():
        source = reference_path(spec["reference_key"])
        if source_digest(source) != spec["source_sha256"]:
            raise SystemExit("Approved source digest differs")
        metadata = extractor.extract_navigation(source)
        count = metadata["page_count"]
        selected = {1 + int(count * (index + 0.5) / 12): index for index in range(12)}
        blocks = defaultdict(list)
        for block in metadata["native_blocks"]:
            if block["page"] in selected:
                blocks[block["page"]].append(block)
        for page in extractor.extract_pages(source):
            number = page.geometry.page
            if number not in selected:
                continue
            index = selected[number]
            target = (40, 140, 450)[index % 3]
            candidates = []
            for block in blocks[number]:
                text, span_ids = native_block_text(page, block)
                letters = sum(character.isalpha() for character in text)
                if letters >= 20:
                    candidates.append(
                        (abs(letters - target), block["block"], block, text, span_ids)
                    )
            if not candidates:
                raise SystemExit(
                    f"No sufficiently letter-bearing native block on sampled page {number}"
                )
            _, _, block, text, span_ids = min(candidates)
            rows.append(
                {
                    "id": f"{book}-{index + 1:02d}",
                    "book": book,
                    "source_sha256": page.source_sha256,
                    "extractor": page.extractor.model_dump(mode="json"),
                    "page": number,
                    "native_block": block["block"],
                    "line_ids": block["line_ids"],
                    "span_ids": span_ids,
                    "text": text,
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "expected_language": None,
                    "annotation_notes": None,
                }
            )
            if number == max(selected):
                break
        _log(
            {
                "action": "select_language_sample",
                "book": book,
                "selected_blocks": 12,
                "scope": "LID comparison sample only; no document-wide evidence or gold evaluation",
            }
        )
    _write(
        SAMPLE,
        {
            "schema_version": 1,
            "human_approved": False,
            "annotation_method": (
                "manual inspection of source-native text before library predictions"
            ),
            "selection": (
                "12 uniform page quantiles; alternating letter targets "
                "40/140/450; minimum 20 letters"
            ),
            "frozen_configuration": LinguaLanguageDetector().identity,
            "licenses_audited_before_installation": LICENSES,
            "blocks": rows,
        },
    )


def _size(name: str) -> int:
    package = distribution(name)
    return sum(
        path.stat().st_size
        for file in package.files or ()
        if (path := Path(package.locate_file(file))).is_file()
    )


def compare() -> None:
    sample = json.loads(SAMPLE.read_text("utf-8"))
    for block in sample["blocks"]:
        if not block["expected_language"] or not block["annotation_notes"]:
            raise SystemExit("Annotate every sample manually before predictions")
        if hashlib.sha256(block["text"].encode()).hexdigest() != block["text_sha256"]:
            raise SystemExit("Sample text digest differs")
    if sample["frozen_configuration"] != LinguaLanguageDetector().identity:
        raise SystemExit("The pre-annotation language configuration changed")
    start = time.perf_counter()
    lingua = LinguaLanguageDetector()
    lingua_init = time.perf_counter() - start
    start = time.perf_counter()
    from langid.langid import LanguageIdentifier, model

    langid = LanguageIdentifier.from_modelstring(model, norm_probs=True)
    langid_init = time.perf_counter() - start
    predictions = []
    for block in sample["blocks"]:
        text = block["text"]
        start = time.perf_counter()
        first = lingua.detect(text)
        lingua_cold = time.perf_counter() - start
        start = time.perf_counter()
        second = langid.classify(text)
        langid_cold = time.perf_counter() - start
        warm = {}
        for name, operation in (
            ("lingua-language-detector", lambda text=text: lingua.detect(text)),
            ("langid", lambda text=text: langid.classify(text)),
        ):
            start = time.perf_counter()
            for _ in range(5):
                operation()
            warm[name] = (time.perf_counter() - start) / 5
        predictions.append(
            {
                "id": block["id"],
                "book": block["book"],
                "expected": block["expected_language"],
                "evaluable_top1": block.get("evaluable_top1", True),
                "letter_count": sum(character.isalpha() for character in text),
                "lingua-language-detector": {
                    "top1": first.candidates[0].language if first.candidates else "und",
                    "evidence": asdict(first),
                    "first_seconds": lingua_cold,
                    "warm_seconds_per_block": warm["lingua-language-detector"],
                },
                "langid": {
                    "top1": second[0],
                    "confidence": float(second[1]),
                    "first_seconds": langid_cold,
                    "warm_seconds_per_block": warm["langid"],
                },
            }
        )
    metrics = []
    for book in BOOKS:
        rows = [row for row in predictions if row["book"] == book]
        for name in LICENSES:
            metrics.append(
                {
                    "book": book,
                    "library": name,
                    "samples": len(rows),
                    "language_bearing_samples": sum(row["evaluable_top1"] for row in rows),
                    "top1_correct": sum(
                        row["evaluable_top1"] and row[name]["top1"] == row["expected"]
                        for row in rows
                    ),
                    "nonlinguistic_blocks": sum(not row["evaluable_top1"] for row in rows),
                    "nonlinguistic_abstentions": sum(
                        not row["evaluable_top1"] and row[name]["evidence"]["language"] == "und"
                        for row in rows
                    )
                    if name == "lingua-language-detector"
                    else None,
                    "first_seconds": round(sum(row[name]["first_seconds"] for row in rows), 6),
                    "warm_milliseconds_per_block": round(
                        1000 * sum(row[name]["warm_seconds_per_block"] for row in rows) / len(rows),
                        4,
                    ),
                    "accepted_evidence": sum(
                        row[name]["evidence"]["language"] != "und" for row in rows
                    )
                    if name == "lingua-language-detector"
                    else None,
                    "accepted_correct": sum(
                        row[name]["evidence"]["language"] != "und"
                        and row[name]["evidence"]["language"] == row["expected"]
                        for row in rows
                    )
                    if name == "lingua-language-detector"
                    else None,
                }
            )
        _log(
            {
                "action": "predict_annotated_language_sample",
                "book": book,
                "sample_sha256": source_digest(SAMPLE),
                "selected_blocks": len(rows),
                "scope": "LID comparison sample only; no document-wide evidence or gold evaluation",
                "frozen_configuration": sample["frozen_configuration"],
            }
        )
    _write(
        OUT / "language_comparison.json",
        {
            "sample_sha256": source_digest(SAMPLE),
            "environment": {"python": platform.python_version(), "platform": platform.platform()},
            "libraries": {
                name: {
                    **license_info,
                    "version": version(name),
                    "installed_bytes": _size(name),
                    "init_seconds": lingua_init
                    if name == "lingua-language-detector"
                    else langid_init,
                }
                for name, license_info in LICENSES.items()
            },
            "metrics": metrics,
            "predictions": predictions,
            "decision": (
                "Lingua: high-accuracy unrestricted languages with native mixed-language segments"
            ),
            "limitations": [
                "24 manually annotated samples are a smoke check, "
                "not a representative accuracy benchmark",
                "No naturally bilingual block occurred in this deterministic sample; "
                "bilingual coverage is synthetic",
                "Library confidence values are not comparable "
                "or calibrated correctness probabilities",
                "First inference includes lazy model loading; "
                "warm timing includes Lingua segmentation",
                "Installed size includes bundled model data; "
                "langid reuses existing NumPy dependency",
            ],
        },
    )
    print(json.dumps(metrics, indent=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--select", action="store_true")
    action.add_argument("--compare", action="store_true")
    arguments = parser.parse_args()
    select() if arguments.select else compare()
