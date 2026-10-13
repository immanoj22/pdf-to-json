"""Identity proof for the four approved books; never accepts intake hold-outs.

Capture before editing producers. Cache identities are operational provenance and are
recorded separately; all other fields, including source text and IDs, enter the proof.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

BOOKS = ("spanish_us_history", "immigrant_children", "art_therapy_index", "medical_anatomy")
OUT = ROOT / "experiments/out/step11c"
OPERATIONAL = {"cache_key_inputs", "page_keys"}


def semantic(value):
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items() if k not in OPERATIONAL}
    if isinstance(value, list):
        return [semantic(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(
        json.dumps(
            semantic(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def structure_page(structure, number):
    data = structure.model_dump(mode="json")
    fields = ("navigation_pages", "headings", "styled", "rejected", "page_zones")
    result = {field: [r for r in data[field] if r["page"] == number] for field in fields}
    result["toc_links"] = [
        r for r in data["toc_links"] if number in (r["source_page"], r["target_page"])
    ]
    result["sections"] = [
        r for r in data["sections"] if r["first_page"] <= number <= r["last_page"]
    ]
    return result


def capture(book):
    from step7_layouts import CACHE
    from step8_run import CACHE8
    from step9_run import CACHE9
    from step10_run import CACHE10, evidence_for, load_book
    from step11_run import CACHE11

    from book_core.furniture.cache import page_furniture
    from book_core.lists.cache import analyze_book_lists
    from book_core.lists.cache import load_page as list_page
    from book_core.objects.analysis import fingerprints
    from book_core.paragraphs.cache import load_page as paragraph_page
    from book_core.paragraphs.keys import book_fingerprint
    from book_core.structure.cache import analyze_book_structure

    started = time.perf_counter()
    loaded = load_book(book)
    source, extractor, inputs, furniture, furniture_key, paragraphs, _, _ = loaded
    evidence, evidence_key, _ = evidence_for(book, loaded)
    structure, _ = analyze_book_structure(evidence, evidence_key, CACHE10)
    lists, _ = analyze_book_lists(
        lambda: extractor.extract_pages(source),
        inputs,
        paragraphs,
        CACHE9,
        structure,
        furniture,
        CACHE11,
    )
    native_key, analysis_key = fingerprints(inputs.digest, extractor, inputs.repetition)
    row = {
        "source_sha256": inputs.digest,
        "pages": {},
        "books": {
            "furniture": digest(furniture.model_dump(mode="json")),
            "paragraphs": digest(paragraphs.model_dump(mode="json")),
            "structure_evidence": digest(evidence),
            "structure": digest(structure.model_dump(mode="json")),
            "lists": digest(lists.model_dump(mode="json")),
        },
        "keys": {
            "native": native_key,
            "analysis": analysis_key,
            "layout": inputs.layout_key,
            "reading_order": inputs.order_key,
            "furniture": furniture_key,
            "paragraphs": book_fingerprint(paragraphs.book.cache_key_inputs),
            "structure_evidence": evidence_key,
            "lists": lists.book.cache_key_inputs,
        },
    }
    measured = {}
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        values = {"native_text": page}
        calls = {
            "layout_order": lambda page=page: inputs(page),
            "furniture": lambda page=page: page_furniture(
                page, inputs, furniture, furniture_key, CACHE8
            ),
            "paragraphs": lambda number=number: paragraph_page(paragraphs, number, CACHE9),
            "lists": lambda number=number: list_page(lists, number, CACHE11),
        }
        for stage, call in calls.items():
            wall, cpu = time.perf_counter(), time.process_time()
            value = call()
            totals = measured.setdefault(stage, {"wall_seconds": 0, "cpu_seconds": 0})
            totals["wall_seconds"] += time.perf_counter() - wall
            totals["cpu_seconds"] += time.process_time() - cpu
            if stage == "layout_order":
                values["layout"], values["reading_order"] = value
            else:
                values[stage] = value
        row["pages"][str(number)] = {
            stage: digest(value.model_dump(mode="json")) for stage, value in values.items()
        }
        row["pages"][str(number)]["structure"] = digest(structure_page(structure, number))
    row["measurements"] = measured
    row["seconds"] = time.perf_counter() - started
    row["cache_root"] = str(CACHE.relative_to(ROOT))
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label")
    parser.add_argument("--book", choices=BOOKS)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--complete-baseline-structure", action="store_true")
    parser.add_argument("--freeze-committed-metrics", action="store_true")
    args = parser.parse_args()
    target = OUT / args.label
    target.mkdir(parents=True, exist_ok=True)
    if args.freeze_committed_metrics:
        provenance = {"revision": "6ccc541", "books": {}}
        for book in BOOKS:
            relative = f"experiments/out/book_intake/metrics_check/{book}/summary.json"
            result = subprocess.run(
                ["git", "show", f"6ccc541:{relative}"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            )
            path = OUT / "before" / f"{book}_metrics.json"
            if path.exists() and path.read_bytes() != result.stdout:
                raise ValueError("Frozen baseline metrics changed")
            path.write_bytes(result.stdout)
            provenance["books"][book] = {
                "source": relative,
                "sha256": hashlib.sha256(result.stdout).hexdigest(),
            }
        (OUT / "before/metrics_provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n", "utf8"
        )
        return
    if args.complete_baseline_structure:
        from book_core.objects.analysis import verified_read
        from book_core.structure.models import BookStructure

        for book in BOOKS:
            path = OUT / "before" / f"{book}.json"
            row = json.loads(path.read_text("utf8"))
            key = row["keys"]["lists"]["structure_decision_key"]
            structure = verified_read(
                ROOT / ".cache/step10/structure/book" / f"{key}.json", BookStructure, key
            )
            if digest(structure.model_dump(mode="json")) != row["books"]["structure"]:
                raise ValueError("Captured baseline structure changed")
            for number, page in row["pages"].items():
                page["structure"] = digest(structure_page(structure, int(number)))
            path.write_text(json.dumps(row, indent=2) + "\n", "utf8")
        return
    if args.compare:
        comparison = {}
        for book in BOOKS:
            before = json.loads((OUT / "before" / f"{book}.json").read_text("utf8"))
            after = json.loads((target / f"{book}.json").read_text("utf8"))
            comparison[book] = {
                "pages": before["pages"] == after["pages"],
                "books": before["books"] == after["books"],
            }
        (target / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
        print(comparison)
        if not all(all(v.values()) for v in comparison.values()):
            raise SystemExit(1)
        return
    for book in (args.book,) if args.book else BOOKS:
        if args.label == "before" and (target / f"{book}.json").exists():
            raise ValueError("The pre-change baseline is frozen; never overwrite it")
        row = capture(book)
        (target / f"{book}.json").write_text(json.dumps(row, indent=2) + "\n", "utf8")
        print(book, len(row["pages"]), round(row["seconds"], 1), flush=True)


if __name__ == "__main__":
    main()
