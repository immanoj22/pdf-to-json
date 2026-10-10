"""Step 9 Part 0: cache housekeeping. Deletes only entries whose producer is superseded.

An entry is superseded when the current key function, applied to the same source and
configuration, yields a different key: the current code can never read it again. Keys are
recomputed with the real key functions, never guessed:

- CachedExtractor namespaces (step5/native, step6/native): from each manifest's source digest
  and extractor identity, with the current extraction producer and runtime.
- Document metadata (step6/metadata, step8/metadata): from each entry's provenance, with the
  current producers and runtime.
- Step 7 native/analysis/layout/order and Step 8 furniture caches: the current keys of the
  three approved books; a non-current entry is deleted only when its payload names one of
  those books (anything else is kept as an unknown consumer).
- Step 5 alignments: all predate the current alignment producer; the newest entry per book is
  the evidence that Step 8/9 evaluation reads (kept); older entries for the same inputs were
  superseded by the logged Step 5b producer (deleted).

Never touched: gold, outputs, step6/document artifacts (read by Step 8/9), step6b (referenced by
the Step 6b report), objects (test caches with many configurations), model weights.
Usage: python step9_housekeeping.py [--apply]
"""

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402

CACHE = ROOT / ".cache"
OUT = ROOT / "experiments/out/step9"
BOOKS = {
    "spanish_us_history": "spanish_pdf",
    "immigrant_children": "small_pdf",
    "art_therapy_index": "art_index_pdf",
}


def size(path):
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def first_entry(directory):
    for path in sorted(Path(directory).glob("*.json")):
        return json.loads(path.read_text("utf-8"))
    return None


def native_namespaces(root, plan):
    from book_core.caching import code_digest, runtime_versions
    from book_core.extraction.cache import CACHE_VERSION
    from book_core.extraction.fingerprints import stable_id

    for directory in sorted(Path(root).iterdir()):
        manifest = directory / "manifest.json"
        if not directory.is_dir() or not manifest.exists():
            plan.append(("keep", directory, "no manifest: unknown"))
            continue
        data = json.loads(manifest.read_text("utf-8"))
        current = stable_id(
            data["source_sha256"],
            CACHE_VERSION,
            json.dumps(data["extractor"], sort_keys=True, separators=(",", ":")),
            code_digest("extraction"),
            json.dumps(runtime_versions(), sort_keys=True),
        )
        if directory.name == current:
            plan.append(("keep", directory, "current extraction namespace"))
        else:
            plan.append(("delete", directory, "extraction producer/runtime superseded"))


def metadata_entries(root, plan):
    from book_core.caching import code_digest, runtime_versions
    from book_core.document_analysis.metadata import LOADED_PRODUCER
    from book_core.extraction.cache import payload_digest

    for path in sorted(Path(root).glob("*.json")):
        provenance = json.loads(path.read_text("utf-8"))["provenance"]
        current = {
            **provenance,
            "extraction_producer_sha256": code_digest("extraction"),
            "metadata_producer_sha256": LOADED_PRODUCER,
            "runtime": runtime_versions(),
        }
        if path.stem == payload_digest(current):
            plan.append(("keep", path, "current metadata key"))
        else:
            plan.append(("delete", path, "metadata producer/runtime superseded"))


def book_keys():
    """Current Step 7/8 keys of the three approved books."""
    from book_core.document_analysis.metadata import cached_metadata
    from book_core.extraction.fingerprints import source_digest
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.furniture.cache import load_book_furniture
    from book_core.furniture.inputs import PageInputs
    from book_core.objects.analysis import cached_repetition, fingerprints
    from step8_run import vocabulary_for

    keys, sources = defaultdict(set), set()
    for book, key in BOOKS.items():
        source = reference_path(key)
        extractor = PyMuPDFExtractor(device="cpu")
        repetition = cached_repetition(source, extractor, CACHE / "step7")
        inputs = PageInputs(source, extractor, repetition, CACHE / "step7", vocabulary_for(book))
        native, analysis = fingerprints(source_digest(source), extractor, repetition)
        keys["native"].add(native)
        keys["analysis"].add(analysis)
        keys["layout"].add(inputs.layout_key)
        keys["reading_order"].add(inputs.order_key)
        metadata = cached_metadata(source, extractor, CACHE / "step8" / "metadata")
        decisions, decision_key = load_book_furniture(inputs, metadata, CACHE / "step8")
        keys["furniture"].add(decision_key)
        sources.add(inputs.digest)
    return keys, sources


def keyed_dirs(root, current, sources, plan, label):
    for directory in sorted(Path(root).iterdir()):
        if directory.name in current:
            plan.append(("keep", directory, f"current {label} key"))
            continue
        entry = first_entry(directory)
        payload = json.loads(entry["payload"]) if entry else {}
        source = payload.get("source_sha256") or payload.get("page", {}).get("source_sha256")
        if source in sources:
            plan.append(("delete", directory, f"{label} key of an approved book, superseded"))
        else:
            plan.append(("keep", directory, f"{label}: other source (unknown consumer)"))


def furniture_books(root, current, sources, plan):
    for path in sorted(Path(root).glob("*.json")):
        if path.stem in current:
            plan.append(("keep", path, "current furniture decision"))
            continue
        payload = json.loads(json.loads(path.read_text("utf-8"))["payload"])
        if payload["book"]["source_sha256"] in sources:
            plan.append(("delete", path, "furniture decision superseded"))
        else:
            plan.append(("keep", path, "furniture: other source"))


def alignments(root, plan):
    groups = defaultdict(list)
    for path in Path(root).glob("*.json"):
        payload = json.loads(path.read_text("utf-8"))["payload"]
        payload = json.loads(payload) if isinstance(payload, str) else payload
        groups[(payload["xml_sha256"], tuple(payload["page_digests"]))].append(path)
    for paths in groups.values():
        paths.sort(key=lambda p: p.stat().st_mtime)
        plan.append(("keep", paths[-1], "newest alignment: evaluation evidence (Step 5b)"))
        for path in paths[:-1]:
            plan.append(("delete", path, "alignment superseded by the logged Step 5b producer"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    before = {d.name: size(d) for d in CACHE.iterdir() if d.is_dir()}
    plan = []
    for root in (CACHE / "step5/native", CACHE / "step6/native"):
        native_namespaces(root, plan)
    for root in (CACHE / "step6/metadata", CACHE / "step8/metadata"):
        metadata_entries(root, plan)
    keys, sources = book_keys()
    for name in ("native", "analysis", "layout", "reading_order"):
        keyed_dirs(CACHE / "step7" / name, keys[name], sources, plan, name)
    furniture_books(CACHE / "step8/furniture/book", keys["furniture"], sources, plan)
    for directory in sorted((CACHE / "step8/furniture/page").iterdir()):
        current = directory.name in keys["furniture"]
        plan.append(
            ("keep" if current else "delete", directory,
             "current furniture pages" if current else "furniture pages superseded")
        )  # fmt: skip
    alignments(CACHE / "step5/alignment", plan)
    rows = [
        {"action": action, "path": str(path.relative_to(ROOT)).replace("\\", "/"),
         "bytes": size(path), "reason": reason}
        for action, path, reason in plan
    ]  # fmt: skip
    freed = sum(r["bytes"] for r in rows if r["action"] == "delete")
    if args.apply:
        for action, path, _ in plan:
            if action != "delete":
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    after = {d.name: size(d) for d in CACHE.iterdir() if d.is_dir()}
    report = {
        "applied": args.apply,
        "deleted_entries": sum(r["action"] == "delete" for r in rows),
        "kept_entries": sum(r["action"] == "keep" for r in rows),
        "bytes_freed": freed if args.apply else 0,
        "bytes_to_free": freed,
        "per_folder_before": before,
        "per_folder_after": after,
        "entries": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    name = "housekeeping.json" if args.apply else "housekeeping_plan.json"
    (OUT / name).write_text(json.dumps(report, indent=1) + "\n", "utf-8")
    for row in rows:
        if row["action"] == "delete" or "unknown" in row["reason"] or "other" in row["reason"]:
            print(row["action"], row["bytes"] // 2**20, "MiB", row["path"], "-", row["reason"])
    print(f"{'freed' if args.apply else 'would free'} {freed / 2**30:.2f} GiB")


if __name__ == "__main__":
    main()
