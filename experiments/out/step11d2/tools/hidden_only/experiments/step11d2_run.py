"""Step 11d continuation variants: four-book measurements and complete page gates."""

# ruff: noqa: E402
import argparse
import gc
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step11_run
import step11c_identity as identity
from reference_paths import reference_path
from step7_layouts import BOOKS as SOURCES
from step7_layouts import CACHE
from step8_run import CACHE8, step6_artifact, vocabulary_for
from step9_run import CACHE9
from step10_run import CACHE10
from step11_run import CACHE11
from step11c_run import model_digest
from step11d2_hidden import write as write_file

BASE = ROOT / "experiments/out/step11d2/before"
VARIANT = "hidden"
OUT = ROOT / "experiments/out/step11d2" / VARIANT


def write(name, value):
    write_file(OUT / name, value)


from book_core.book_run import run_book
from book_core.extraction.fingerprints import stable_id
from book_core.layout.invariants import check
from book_core.layout.models import PageLayout
from book_core.lists.keys import book_fingerprint
from book_core.lists.models import PageLists
from book_core.objects.analysis import verified_read
from book_core.objects.models import ObjectAnalysis
from book_core.run_context import source_session


def read(path):
    return json.loads(path.read_text("utf8"))


def capacity():
    free = shutil.disk_usage(ROOT).free
    estimate = 1412 * 12 * 1024 * 1024
    if free - estimate < 10_000_000_000:
        raise ValueError("Insufficient free disk after the 11c estimate")
    return {"free_bytes": free, "estimate_bytes": estimate, "remaining_bytes": free - estimate}


def differences(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        return [
            d
            for k in sorted(a.keys() | b.keys())
            for d in differences(a.get(k), b.get(k), f"{path}/{k}")
        ]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [
            d
            for i, (x, y) in enumerate(zip(a, b, strict=True))
            for d in differences(x, y, f"{path}/{i}")
        ]
    return [] if a == b else [{"path": path, "before": a, "after": b}]


def run(book):
    from book_core.caching import SCOPES, code_digest

    disk = capacity()
    producers = {scope: code_digest(scope) for scope in SCOPES}
    saved = OUT / "producers.json"
    if saved.exists():
        assert read(saved) == producers, "Producer changed during variant measurement"
    else:
        write("producers.json", producers)
    base = read(BASE / f"{book}.json")
    artifact, _ = step6_artifact(base["source_sha256"])

    def progress(stage, completed, total):
        if completed % 25 == 0 or completed == total:
            print(book, stage, completed, total, flush=True)

    result = run_book(
        reference_path(SOURCES[book][0]),
        ROOT / ".cache/step11d2/final_books" / VARIANT,
        ROOT / ".cache",
        workers=1,
        device="cpu",
        evidence=artifact,
        vocabulary=vocabulary_for(book),
        cache_dirs={
            "page": CACHE,
            "furniture": CACHE8,
            "metadata": CACHE8 / "metadata",
            "paragraphs": CACHE9,
            "structure": CACHE10,
            "lists": CACHE11,
        },
        progress=progress,
    )
    write(f"performance/{book}.json", {"disk_before": disk, "run": result})
    assert result["source_hashes"] == 1
    print(book, "run complete", flush=True)
    with source_session(reference_path(SOURCES[book][0])):
        row = identity.capture(book)
        write(f"after/{book}.json", row)
        step11_run.OUT = OUT / "metrics"
        step11_run.HOLDOUT = {}
        sys.argv = ["step11_run.py", "--book", book]
        step11_run.main()
    print(book, "identity and metrics complete", flush=True)


def proof(book, fresh=False):
    row = read(OUT / f"after/{book}.json")
    base = read(BASE / f"{book}.json")
    frozen = read(BASE / f"{book}_objects.json")
    assert all(row["keys"][k] == base["keys"][k] for k in ("native", "analysis"))
    gates, objects, ownership = {}, {}, {}
    with source_session(reference_path(SOURCES[book][0])) as snapshot:
        assert snapshot.digest == row["source_sha256"]
        for number in row["pages"]:
            checkpoint = ROOT / ".cache/step11d2/proof" / VARIANT / book / f"{number}.json"
            if checkpoint.exists() and not fresh:
                data = read(checkpoint)
                assert data["keys"] == row["keys"]
            else:
                key = row["keys"]["analysis"]
                analysis = verified_read(
                    CACHE / "analysis" / key / f"{number}.json", ObjectAnalysis, key
                )
                layout = verified_read(
                    CACHE / "layout" / row["keys"]["layout"] / f"{number}.json",
                    PageLayout,
                    row["keys"]["layout"],
                )
                key = book_fingerprint(row["keys"]["lists"])
                units = verified_read(
                    CACHE11 / "lists/page" / key / f"{number}.json",
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
                assert data["objects"] == frozen[number]
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                checkpoint.write_text(
                    json.dumps(data, indent=2) + "\n", encoding="utf8", newline="\n"
                )
                del analysis, layout, units
                gc.collect()
            objects[number] = data["objects"]
            gates[number] = data["invariants"]
            ownership[number] = data["ownership"]
            if int(number) % 25 == 0:
                print(book, "full proof", number, flush=True)
    write(f"after/{book}_objects.json", objects)
    write(
        f"after/{book}_full_gates.json",
        {
            "invariants": gates,
            "invariant_totals": {
                name: sum(len(r[name]) for r in gates.values())
                for name in ("I1", "I2", "I3", "I4", "I5", "I6", "I7")
            },
            "ownership": ownership,
        },
    )
    assert objects == frozen
    assert all(not any(v.values()) for v in gates.values())
    assert all(v["units_once"] and v["ordered_once"] for v in ownership.values())


def compare():
    rows = {}
    for book in identity.BOOKS:
        before, after = read(BASE / f"{book}.json"), read(OUT / f"after/{book}.json")
        rows[book] = {
            "changed_pages": {
                stage: [
                    int(n)
                    for n in before["pages"]
                    if before["pages"][n][stage] != after["pages"][n][stage]
                ]
                for stage in next(iter(before["pages"].values()))
            },
            "book_changes": differences(before["books"], after["books"]),
            "key_changes": differences(before["keys"], after["keys"]),
            "metric_changes": differences(
                read(BASE / f"metrics/{book}/summary.json"),
                read(OUT / f"metrics/{book}/summary.json"),
            ),
        }
    write("comparison.json", rows)
    print({book: row["changed_pages"] for book, row in rows.items()})


def details(book_filter=None):
    from book_core.furniture.models import PageFurniture
    from book_core.lists.cache import BookListsResult
    from book_core.lists.cache import load_page as list_page
    from book_core.paragraphs.cache import BookParagraphResult
    from book_core.paragraphs.cache import load_page as paragraph_page
    from book_core.reading_order.models import PageReadingOrder
    from book_core.structure.evidence import _read as read_evidence
    from book_core.structure.models import BookStructure

    comparison = read(OUT / "comparison.json")
    result = {}
    for book in (book_filter,) if book_filter else identity.BOOKS:
        versions = [read(BASE / f"{book}.json"), read(OUT / f"after/{book}.json")]
        cached = []
        for version in versions:
            keys = version["keys"]
            paragraphs = verified_read(
                CACHE9 / "paragraphs/book" / f"{keys['paragraphs']}.json",
                BookParagraphResult,
                keys["paragraphs"],
            )
            list_key = book_fingerprint(keys["lists"])
            lists = verified_read(
                CACHE11 / "lists/book" / f"{list_key}.json", BookListsResult, list_key
            )
            structure_key = keys["lists"]["structure_decision_key"]
            structure = verified_read(
                CACHE10 / "structure/book" / f"{structure_key}.json", BookStructure, structure_key
            )
            cached.append((keys, paragraphs, lists, structure))
        pages = {}
        for stage, numbers in comparison[book]["changed_pages"].items():
            for number in numbers:
                values = []
                for keys, paragraphs, lists, structure in cached:
                    if stage in {"layout", "reading_order"}:
                        model = PageLayout if stage == "layout" else PageReadingOrder
                        value = verified_read(
                            CACHE / stage / keys[stage] / f"{number}.json", model, keys[stage]
                        )
                    elif stage == "furniture":
                        key = keys["furniture"]
                        value = verified_read(
                            CACHE8 / "furniture/page" / key / f"{number}.json", PageFurniture, key
                        )
                    elif stage == "paragraphs":
                        value = paragraph_page(paragraphs, number, CACHE9)
                    elif stage == "lists":
                        value = list_page(lists, number, CACHE11)
                    elif stage == "structure":
                        value = identity.structure_page(structure, number)
                    else:
                        raise ValueError("Unexpected changed stage: " + stage)
                    values.append(
                        identity.semantic(
                            value if isinstance(value, dict) else value.model_dump(mode="json")
                        )
                    )
                pages.setdefault(stage, {})[str(number)] = differences(*values)
        book_changes = {}
        for name, index in (("paragraphs", 1), ("lists", 2), ("structure", 3)):
            book_changes[name] = differences(
                *[identity.semantic(version[index].model_dump(mode="json")) for version in cached]
            )
        evidence = []
        for version in versions:
            key = version["keys"]["structure_evidence"]
            evidence.append(
                identity.semantic(
                    read_evidence(CACHE10 / "structure/evidence" / f"{key}.json.gz", key)
                )
            )
        book_changes["structure_evidence"] = differences(*evidence)
        result[book] = {"pages": pages, "books": book_changes}
    write(f"page_changes_{book_filter}.json" if book_filter else "page_changes.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "proof", "compare", "details"])
    parser.add_argument("--book", choices=identity.BOOKS)
    parser.add_argument("--fresh", action="store_true", help="Recheck every proof page from caches")
    parser.add_argument("--variant", choices=["hidden", "markers", "combined"], default="hidden")
    args = parser.parse_args()
    VARIANT = args.variant
    OUT = ROOT / "experiments/out/step11d2" / VARIANT
    if args.action == "compare":
        compare()
    elif args.action == "details":
        details(args.book)
    else:
        if not args.book:
            parser.error("--book is required")
        if args.action == "run":
            run(args.book)
        else:
            proof(args.book, fresh=args.fresh)
