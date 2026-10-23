"""Step 17b: new assembly publications and fresh gates, preserving Step 17 evidence.

Only the five development books are accepted. No cleanup or upstream conversion.
Each phase runs in a fresh process so the producer digest is always frozen at import.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.assembly import schema as S
from book_core.assembly import validate
from book_core.assembly.cache import _verify
from book_core.caching import SCOPES, code_digest
from step13_books import BOOKS
from step17b_investigate import OUT, walk, write

BASE = ROOT / "experiments/out/step17/final"
FINAL = OUT / "final"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reserve():
    free = shutil.disk_usage(ROOT).free
    if free < 5_000_000_000:
        raise OSError(f"Free space {free} is below 5 GB: stop, no cleanup authorized")
    return free


def unchanged_inputs():
    for row in json.loads((OUT / "inputs.json").read_text("utf-8")).values():
        assert digest(row["json"]) == row["sha256"], "Frozen Step 17 publication changed"


def initialize():
    unchanged_inputs()
    FINAL.mkdir(exist_ok=True)
    assert not (FINAL / "epoch.json").exists(), "Do not reset the frozen validation epoch"
    for folder in ("performance", "after", "source_baseline"):
        shutil.copytree(BASE / folder, FINAL / folder)
    write(FINAL / "epoch.json", {"started": now(), "free_before": reserve(),
          "producers": {scope: code_digest(scope) for scope in SCOPES},
          "source_files": {str(p.relative_to(ROOT)): digest(p)
                           for tree in (ROOT / "backend/src", ROOT / "backend/tests")
                           for p in tree.rglob("*.py")},
          "scope": "Assembly-only refresh of unchanged five Step 17 archives"})


def frozen():
    epoch = json.loads((FINAL / "epoch.json").read_text("utf-8"))
    assert epoch["producers"] == {s: code_digest(s) for s in SCOPES}
    assert all(digest(ROOT / p) == h for p, h in epoch["source_files"].items())
    unchanged_inputs()
    reserve()


def publish(book):
    import step17_refresh_assembly as refresh
    refresh.FINAL = FINAL
    refresh.main(book)


def proof(book):
    import step13_run as driver
    started = now()
    driver.OUT, driver.MATH_BOOK = OUT, book
    driver.proof_math_book("final")  # fresh every-page reads/checks, no proof-cache reuse
    row = json.loads((FINAL / f"after/{book}_full_gates.json").read_text("utf-8"))
    assert row["invariant_totals"] == {f"I{i}": int(book == "statistics" and i == 7)
                                        for i in range(1, 8)}
    assert all(v["units_once"] and v["ordered_once"] for v in row["ownership"].values())
    write(FINAL / f"validation/proof_{book}.json", {"started": started, "finished": now(),
          "fresh_every_page": True, "pages": len(row["ownership"]),
          "invariant_totals": row["invariant_totals"],
          "gate_sha256": digest(FINAL / f"after/{book}_full_gates.json"),
          "assembly_producer": code_digest("assembly")})


def proof_inputs(book):
    """Read-only checksum closure for a proposed proof reuse; does not accept a proof.

    No native model construction is needed. UTF-8 hashing is chunked so the largest
    native payload does not acquire another full-size encoded copy.
    """
    import gc

    import step13_run as driver
    from book_core.cache_store import FORMAT_VERSION, read_json
    from book_core.extraction.fingerprints import stable_id
    from book_core.lists.keys import book_fingerprint

    before = json.loads((BASE / f"performance/{book}.json").read_text("utf-8"))["run"]
    run = json.loads((FINAL / f"performance/{book}.json").read_text("utf-8"))["run"]
    keys = run["cache_keys"]
    assert before["pages"] == run["pages"]
    assert all(keys[k] == before["cache_keys"][k] for k in ("native", "analysis", "layout", "lists"))
    old_producers = json.loads((BASE / "producers.json").read_text("utf-8"))
    assert all(code_digest(scope) == value for scope, value in old_producers.items()
               if scope not in {"assembly", "assembly_evidence"})
    list_key = book_fingerprint(keys["lists"]) if isinstance(keys["lists"], dict) else keys["lists"]
    rows = []
    started = now()
    for number in range(1, run["pages"] + 1):
        paths = [(stage, driver.CACHE / stage / keys[stage] / f"{number}.json", keys[stage])
                 for stage in ("native", "analysis", "layout")]
        paths.append(("lists", driver.CACHE11 / "lists/page" / list_key / f"{number}.json",
                      stable_id(list_key, "page", number)))
        for stage, path, fingerprint in paths:
            stat = path.stat()
            envelope = read_json(path)
            assert envelope.get("format_version", 1) in {1, FORMAT_VERSION}
            assert envelope["fingerprint"] == fingerprint, (stage, number)
            payload_hash = hashlib.sha256()
            payload = envelope["payload"]
            for offset in range(0, len(payload), 1024 * 1024):
                payload_hash.update(payload[offset:offset + 1024 * 1024].encode("utf-8"))
            payload_sha = payload_hash.hexdigest()
            assert payload_sha == envelope["sha256"], (stage, number)
            del envelope, payload
            gc.collect()
            with path.open("rb") as stream:
                file_sha = hashlib.file_digest(stream, "sha256").hexdigest()
            after = path.stat()
            assert (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) == (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns), (stage, number)
            rows.append({"page": number, "stage": stage, "path": str(path.relative_to(ROOT)),
                         "bytes": stat.st_size, "fingerprint": fingerprint,
                         "payload_sha256": payload_sha, "file_sha256": file_sha})
        if number % 50 == 0 or number == run["pages"]:
            print(book, "proof input checksums", number, run["pages"], flush=True)
    old_proof = BASE / f"after/{book}_full_gates.json"
    committed = subprocess.check_output(["git", "show", "c7cffdf:" + old_proof.relative_to(ROOT).as_posix()],
                                        cwd=ROOT)
    assert committed == old_proof.read_bytes()
    write(FINAL / f"proof_input_closure/{book}.json", {"started": started, "finished": now(),
          "pages": run["pages"], "files_checked": len(rows), "rows": rows,
          "all_fingerprints_and_payload_checksums_valid": True,
          "all_non_assembly_producers_unchanged": True,
          "proof_matches_committed_step17": True, "prior_proof_sha256": digest(old_proof),
          "status": "Input closure only; no invariant proof reuse has been accepted."})


def reuse_proof(book):
    """Accept the prepared unchanged proof only after explicit scoped user approval."""
    approval_path = OUT / "proof_reuse_approval.json"
    approval = json.loads(approval_path.read_text("utf-8"))
    assert approval["approved"] is True and book in approval["books"]
    assert approval["source"] == "explicit user reply" and approval["reply"]
    path = FINAL / f"validation/proof_{book}.json"
    assert not path.exists(), "Keep previous proof receipts"
    closure_path = FINAL / f"proof_input_closure/{book}.json"
    closure = json.loads(closure_path.read_text("utf-8"))
    assert closure["all_fingerprints_and_payload_checksums_valid"]
    assert closure["all_non_assembly_producers_unchanged"]
    assert closure["proof_matches_committed_step17"]
    assert closure["files_checked"] == closure["pages"] * 4
    assert {(r["page"], r["stage"]) for r in closure["rows"]} == {
        (n, stage) for n in range(1, closure["pages"] + 1)
        for stage in ("native", "analysis", "layout", "lists")}
    old = json.loads((BASE / f"performance/{book}.json").read_text("utf-8"))["run"]
    run = json.loads((FINAL / f"performance/{book}.json").read_text("utf-8"))["run"]
    assert old["pages"] == run["pages"] == closure["pages"]
    assert all(old["cache_keys"][k] == run["cache_keys"][k]
               for k in ("native", "analysis", "layout", "lists"))
    producers = json.loads((BASE / "producers.json").read_text("utf-8"))
    assert all(code_digest(k) == v for k, v in producers.items()
               if k not in {"assembly", "assembly_evidence"})
    started = now()
    # Recheck the exact closed file bytes after all intervening read-only gates.
    for row in closure["rows"]:
        with (ROOT / row["path"]).open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == row["file_sha256"]
    gate = FINAL / f"after/{book}_full_gates.json"
    assert digest(gate) == closure["prior_proof_sha256"] == digest(BASE / f"after/{book}_full_gates.json")
    data = json.loads(gate.read_text("utf-8"))
    assert data["invariant_totals"] == {f"I{i}": int(book == "statistics" and i == 7)
                                         for i in range(1, 8)}
    assert all(v["units_once"] and v["ordered_once"] for v in data["ownership"].values())
    write(path, {"started": started, "finished": now(), "fresh_every_page": False,
          "method": "approved replay of exact unchanged Step 17 invariant proof",
          "pages": closure["pages"], "invariant_totals": data["invariant_totals"],
          "gate_sha256": digest(gate), "assembly_producer": code_digest("assembly"),
          "input_closure_sha256": digest(closure_path), "approval_sha256": digest(approval_path),
          "all_closed_cache_file_bytes_rechecked": True})


def census(document):
    counts = Counter()
    for top in document["content"]:
        for node, contexts, _ in walk(top):
            counts["type:" + node.get("type", "text_fragment")] += 1
            if node.get("role"):
                counts["role:" + node["role"]] += 1
            content = node.get("content")
            if isinstance(content, dict):
                for span in content["spans"]:
                    kinds = ("bold", "italic") if span["kind"] == "bold_italic" else (span["kind"],)
                    for kind in kinds:
                        counts["style:" + kind] += 1
                        for context in contexts:
                            counts[f"style:{kind}:{context}"] += 1
    counts["review:total"] = len(document["review"]["items"])
    for item in document["review"]["items"]:
        counts["review:" + item["kind"]] += 1
    return dict(counts)


def metrics(book):
    from step17_contract_check import inspect
    from step17_lossless import check
    run = json.loads((FINAL / f"performance/{book}.json").read_text("utf-8"))["run"]
    folder = Path(run["book_json"])
    path = folder / "book.json"
    result = check(path, run["output"])
    write(FINAL / f"lossless/{book}.json", result)
    assert result["missing"] == result["extra"] == 0
    assert result["discard_missing"] == result["discard_extra"] == 0
    data = json.loads(path.read_text("utf-8"))
    errors = validate.errors(data)
    assert not errors
    model = S.Book.model_validate(data)
    assert validate.dumps(model.model_dump(mode="json", by_alias=True)).encode("utf-8") == path.read_bytes()
    contract = inspect(model)
    assert not contract["defects"] and not contract["unresolved_review_unit_ids_by_kind"]
    headings = {u.id for u in S.iter_units(model.content) if isinstance(u, S.Heading)}
    assert all(e.heading in headings for e in model.navigation.outline)
    _verify(folder, json.loads((folder / "manifest.json").read_text("utf-8")))
    inputs = json.loads((OUT / "inputs.json").read_text("utf-8"))[book]
    old = json.loads(Path(inputs["json"]).read_text("utf-8"))
    old_nodes = [row for top in old["content"] for row in walk(top)]
    new_nodes = [row for top in data["content"] for row in walk(top)]
    before = {n["id"]: n for n, *_ in old_nodes if "id" in n}
    after = {n["id"]: n for n, *_ in new_nodes if "id" in n}
    assert set(before) == set(after), "Unexpected unit identity/ownership change"
    for position, ((node, *_), (new_node, *_)) in enumerate(zip(old_nodes, new_nodes, strict=True)):
        uid = node.get("id", f"fragment at {position}")
        assert node.get("id") == new_node.get("id"), (uid, "tree order")
        for key in ("refs", "pages", "boxes"):
            assert node.get(key) == new_node.get(key), (uid, key)
        if node.get("type") == "table":
            meta = lambda c: {k: v for k, v in c.items() if k != "content"}
            assert [meta(c) for c in node["cells"]] == [meta(c) for c in new_node["cells"]]
        a, b = node.get("content"), new_node.get("content")
        if isinstance(a, dict):
            assert a["text"] == b["text"] and a["source_runs"] == b["source_runs"], uid
            other = lambda c: [s for s in c["spans"] if s["kind"] != "underline"]
            assert other(a) == other(b), (uid, "non-underline styling")
    write(FINAL / f"contracts/{book}.json", {"schema_errors": errors,
          "round_trip_identical": True, "manifest_verified": True, **contract})
    write(FINAL / f"changes/{book}.json", {"before": census(old), "after": census(data),
          "all_unit_ids_unchanged": True, "all_text_source_runs_refs_boxes_unchanged": True,
          "all_non_underline_style_decisions_unchanged": True,
          "book_json": str(path), "sha256": digest(path)})
    sampled = json.loads((OUT / "style_verdicts.json").read_text("utf-8"))
    survival = []
    for row in sampled:
        if row["book"] != book:
            continue
        if row["unit"] is not None:
            content = after[row["unit"]]["content"]
        else:
            matches = [n for n, _, pages in new_nodes if pages and pages[0] == row["page"]
                       and n.get("refs") == row["refs"] and n.get("type") == row["node_type"]
                       and n["content"]["text"] == row["unit_text"]]
            assert len(matches) == 1, (row["sample_id"], len(matches))
            content = matches[0]["content"]
        covered = set()
        for span in content["spans"]:
            kinds = ("bold", "italic") if span["kind"] == "bold_italic" else (span["kind"],)
            if span["kind"] == row["kind"] or row["kind"] in kinds:
                covered.update(range(max(row["start"], span["start"]),
                                     min(row["end"], span["end"])))
        survival.append({"sample_id": row["sample_id"], "kind": row["kind"],
                         "original_verdict": row["verdict"], "covered_characters": len(covered),
                         "sample_characters": row["end"] - row["start"]})
    index = json.loads((OUT / "index_hand_count.json").read_text("utf-8"))[book]
    pages = []
    for sample in index["hand_count"]:
        found = [n["content"]["text"].strip() for n in after.values()
                 if n.get("type") == "index_divider" and sample["page"] in n["pages"]]
        assert Counter(found) == Counter(sample["printed_letters"]), (book, sample["page"], found)
        pages.append({"page": sample["page"], "printed": sample["printed_letters"],
                      "json_after": found})
    write(FINAL / f"sample_after/{book}.json", {"style": survival, "index_pages": pages})
    print(book, "lossless", result["missing"], result["extra"], "schema/contract/manifest pass", flush=True)


def source():
    import step17_archive_gates as gates
    gates.RUN, gates.BASELINE = FINAL, FINAL / "source_baseline"
    gates.s15.gates.RUN = FINAL
    for book in BOOKS:
        gates.s15._load(book)
    gates.main()


def evaluate(book):
    import step17_json_eval as evaluator
    run = json.loads((FINAL / f"performance/{book}.json").read_text("utf-8"))["run"]
    evaluator.OUT = FINAL / "json_eval"
    sys.argv = ["step17_json_eval", "--book", book, "--json",
                str(Path(run["book_json"]) / "book.json"), "--archive", run["output"]]
    evaluator.main()


def parity(book, *, bounded=False):
    import step17_parity as check
    check.FINAL = FINAL
    original_assemble = check.assemble
    original_assembly = check.assembly
    import step14b_bundles as bundles
    original_read = bundles.verified_read

    def bounded_read(path, model, fingerprint, *, native=None):
        from types import SimpleNamespace

        from book_core.objects.models import ObjectAnalysis
        from step17b_table_inputs import TableObjects
        if model is not ObjectAnalysis or native is not None:
            return original_read(path, model, fingerprint, native=native)
        keys = bundles.common.keys(book)
        native_path = bundles.CACHE / "native" / keys["native"] / Path(path).name
        values = TableObjects(native_path, keys["native"], path, fingerprint)
        # The iterable includes native objects followed by compounds, exactly as
        # the original builder. Only path instances/render glyphs avoid eager load.
        return SimpleNamespace(native=SimpleNamespace(objects=values), compounds=())

    def checkpoint_assembly(name):
        result = original_assembly(name)
        assert result["identical"], result
        run = json.loads((FINAL / f"performance/{name}.json").read_text("utf-8"))["run"]
        write(FINAL / f"parity_parts/{name}_assembly.json", {
            "finished": now(), "assembly_producer": code_digest("assembly"),
            "book_json_sha256": digest(Path(run["book_json"]) / "book.json"),
            "fresh_development_assembly": True, "result": result})
        return result

    def traced_assemble(*args, **kwargs):
        def progress(stage, number, total):
            if number % 100 == 0 or number == total:
                print(book, "parity", stage, number, total, flush=True)
        kwargs["progress"] = progress
        return original_assemble(*args, **kwargs)

    check.assemble = traced_assemble
    if bounded:
        bundles.verified_read = bounded_read
        check.assembly = checkpoint_assembly
    sys.argv = ["step17_parity", "--book", book]
    try:
        check.main()
    except SystemExit as result:
        assert result.code in (None, 0), f"Parity failed for {book}"
    finally:
        check.assemble = original_assemble
        check.assembly = original_assembly
        bundles.verified_read = original_read


def parity_bounded(book):
    """Fresh full parity with a bounded reader for table-consumed native fields."""
    parity(book, bounded=True)


def table_input_check(book):
    """Compare every table-consumed field on seeded, memory-bounded real pages."""
    import gc
    import random
    from statistics import median

    from book_core.layout.models import PageLayout
    from book_core.objects.analysis import verified_read
    from book_core.objects.models import ObjectAnalysis
    from book_core.tables.rulings import freeform, page_rules
    from step17b_table_inputs import TableObjects

    run = json.loads((FINAL / f"performance/{book}.json").read_text("utf-8"))["run"]
    keys = run["cache_keys"]
    import step14b_bundles as bundles
    candidates = [(number, bundles.CACHE / "native" / keys["native"] / f"{number}.json")
                  for number in range(1, run["pages"] + 1)]
    # The ordinary reader is the comparison oracle; cap only this audit's input
    # size so it cannot reproduce the full-model resource failure during the check.
    eligible = [(n, p) for n, p in candidates if p.stat().st_size <= 1_000_000]
    selected = random.Random("17023:bounded:" + book).sample(eligible, min(3, len(eligible)))
    largest = max(eligible, key=lambda item: item[1].stat().st_size)
    selected = sorted({*selected, largest})
    rows = []
    def features(values, font):
        return (page_rules(values, font), freeform(values),
                {o.id: o.kind for o in values if o.kind in {"drawing", "image", "compound"}},
                {o.id: list(o.member_ids) for o in values if o.kind == "compound"})

    for number, native_path in selected:
        analysis_path = bundles.CACHE / "analysis" / keys["analysis"] / f"{number}.json"
        analysis = verified_read(analysis_path, ObjectAnalysis, keys["analysis"])
        ordinary = [*analysis.native.objects, *analysis.compounds]
        bounded = TableObjects(native_path, keys["native"], analysis_path, keys["analysis"])
        layout = verified_read(bundles.CACHE / "layout" / keys["layout"] / f"{number}.json",
                               PageLayout, keys["layout"])
        sizes = [line.font_size for line in layout.lines if not line.blank and line.font_size > 0]
        font = median(sizes) if sizes else 10.0
        assert features(ordinary, font) == features(bounded, font), (book, number)
        # All paths, not only accepted rules, must be identical in source order.
        assert [(o.id, list(o.path_items)) for o in ordinary] == [
            (o.id, list(o.path_items)) for o in bounded]
        rows.append({"page": number, "objects": len(ordinary),
                     "native_file_sha256": digest(native_path),
                     "analysis_file_sha256": digest(analysis_path), "identical": True})
        print(book, "bounded-reader comparison", number, "identical", flush=True)
        del analysis, ordinary, bounded, layout
        gc.collect()
    number, native_path = max(candidates, key=lambda item: item[1].stat().st_size)
    print(book, "bounded-reader largest-page stress", number, flush=True)
    analysis_path = bundles.CACHE / "analysis" / keys["analysis"] / f"{number}.json"
    bounded = list(TableObjects(native_path, keys["native"], analysis_path, keys["analysis"]))
    layout = verified_read(bundles.CACHE / "layout" / keys["layout"] / f"{number}.json",
                           PageLayout, keys["layout"])
    sizes = [line.font_size for line in layout.lines if not line.blank and line.font_size > 0]
    (rules, fills), curves, kinds, members = features(bounded, median(sizes) if sizes else 10.0)
    stress = {"page": number, "native_file_bytes": native_path.stat().st_size,
              "native_file_sha256": digest(native_path),
              "analysis_file_sha256": digest(analysis_path), "objects": len(bounded),
              "path_items": sum(len(o.path_items) for o in bounded),
              "rules": len(rules), "fills": len(fills), "freeform": len(curves),
              "object_kinds": len(kinds), "compounds": len(members),
              "completed": True, "ordinary_reader_comparison": False}
    print(book, "bounded-reader stress complete", stress, flush=True)
    write(FINAL / f"table_input_checks/{book}.json", {
        "seed": "17023:bounded:" + book, "ordinary_reader_size_cap_bytes": 1_000_000,
        "selection": "three seeded pages plus largest eligible native cache",
        "all_table_consumed_features_and_all_paths_identical": True, "pages": rows,
        "largest_page_bounded_stress": stress})


def workers():
    import uuid

    import step17_workers as check
    check.OUT, check.WORK = FINAL, ROOT / ".cache/s17bi" / uuid.uuid4().hex[:8]
    original_run = check.run_book
    cache_paths = {}

    def independent_run(source, output, cache, **kwargs):
        workers = kwargs["workers"]
        actual_cache = check.WORK / f"cache_w{workers}"
        assert not actual_cache.exists(), "Worker proofs need independent fresh caches"
        assert workers not in cache_paths
        cache_paths[workers] = str(actual_cache)
        return original_run(source, output, actual_cache, **kwargs)

    check.run_book = independent_run
    try:
        check.main()
    finally:
        check.run_book = original_run
    row = json.loads((FINAL / "workers_book3.json").read_text("utf-8"))
    assert row["one_vs_two_workers_identical"] and row["production_vs_development_identical"]
    assert len(cache_paths) == 2 and len(set(cache_paths.values())) == 2
    row.update(independent_upstream_caches=True, both_caches_absent_before_run=True,
               cache_directories=cache_paths)
    write(FINAL / "workers_book3.json", row)


def command_check(name, args):
    path = FINAL / "validation" / f"{name}.log"
    path.parent.mkdir(exist_ok=True)
    assert not path.exists(), "Keep previous validation logs; choose a new name for a retry"
    started = now()
    clock = time.perf_counter()
    with path.open("wb") as log:
        result = subprocess.run([sys.executable, *args], cwd=ROOT, stdout=log,
                                stderr=subprocess.STDOUT, check=False,
                                env=os.environ | {"PYTHONIOENCODING": "utf-8"})
    write(path.with_suffix(".json"), {"started": started, "finished": now(),
          "seconds": time.perf_counter() - clock, "exit_code": result.returncode,
          "command": [sys.executable, *args], "log_sha256": digest(path),
          "assembly_producer": code_digest("assembly")})
    assert result.returncode == 0, f"{name} failed: {path}"
    print(name, "passed", flush=True)


def suite():
    files = [ROOT / "docs/step17b_report.md", OUT / "README.md", ROOT / ".gitignore",
             ROOT / ".gitattributes", *(ROOT / "experiments").glob("step17b_*.py")]
    files += [p for tree in (ROOT / "backend/src", ROOT / "backend/tests")
              for p in tree.rglob("*.py")]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in files}
    write(FINAL / "validation/final_suite_inputs.json", hashes)
    command_check("full_suite_final", ["-m", "pytest", "backend/tests", "-q",
        "--basetemp=" + str(ROOT / ".s17bt/final"),
        "-o", "cache_dir=" + str(ROOT / ".s17bt/pytest_metadata")])
    assert all(digest(ROOT / p) == h for p, h in hashes.items()), "An edit followed suite start"


def closure():
    command_check("cache_closure", ["-m", "pytest", "backend/tests", "-q", "-k", "closure",
        "--basetemp=" + str(OUT / "test_runs/final_closure"),
        "-o", "cache_dir=" + str(OUT / "test_runs/closure_metadata")])


def ruff():
    command_check("ruff_final", ["-m", "ruff", "check", "backend/src", "backend/tests",
        *[str(p.relative_to(ROOT)) for p in (ROOT / "experiments").glob("step17b_*.py")]])


def record():
    """Accept only completed, current proofs; never the copied historical gate files."""
    producer = code_digest("assembly")
    books = {}
    for book in BOOKS:
        run = json.loads((FINAL / f"performance/{book}.json").read_text("utf-8"))
        assert run["producers"]["assembly"] == producer
        lossless = json.loads((FINAL / f"lossless/{book}.json").read_text("utf-8"))
        assert all(lossless[k] == 0 for k in ("missing", "extra", "discard_missing", "discard_extra"))
        contract = json.loads((FINAL / f"contracts/{book}.json").read_text("utf-8"))
        assert not contract["schema_errors"] and not contract["defects"]
        assert not contract["unresolved_review_unit_ids_by_kind"]
        proof = json.loads((FINAL / f"validation/proof_{book}.json").read_text("utf-8"))
        assert proof["assembly_producer"] == producer
        assert proof["gate_sha256"] == digest(FINAL / f"after/{book}_full_gates.json")
        if not proof["fresh_every_page"]:
            approval = json.loads((OUT / "proof_reuse_approval.json").read_text("utf-8"))
            assert approval["approved"] is True and book in approval["books"]
            assert proof["approval_sha256"] == digest(OUT / "proof_reuse_approval.json")
            assert proof["input_closure_sha256"] == digest(FINAL / f"proof_input_closure/{book}.json")
            assert proof["all_closed_cache_file_bytes_rechecked"]
        parity_result = json.loads((FINAL / f"parity/{book}.json").read_text("utf-8"))
        assert parity_result["assembly"]["identical"] and parity_result["continuity"]["identical"]
        assert not parity_result["tables"]["differ"]
        publication = Path(run["run"]["book_json"]) / "book.json"
        changes = json.loads((FINAL / f"changes/{book}.json").read_text("utf-8"))
        assert changes["book_json"] == str(publication) and changes["sha256"] == digest(publication)
        reference = json.loads((FINAL / f"json_eval/{book}.json").read_text("utf-8"))
        baseline_reference = json.loads((ROOT / f"experiments/out/step17/json_eval/{book}.json").read_text("utf-8"))
        assert reference == baseline_reference
        books[book] = {"json": str(publication), "sha256": digest(publication),
                       "lossless": lossless, "invariant_proof": proof,
                       "reference_evaluation_identical_to_step17": True,
                       "schema_errors": 0, "parity": parity_result}
    suite_result = json.loads((FINAL / "validation/full_suite_final.json").read_text("utf-8"))
    log = FINAL / "validation/full_suite_final.log"
    assert suite_result["exit_code"] == 0 and suite_result["log_sha256"] == digest(log)
    counts = re.findall(r"(\d+) passed", log.read_text("utf-8"))
    assert len(counts) == 1
    suite_inputs = json.loads((FINAL / "validation/final_suite_inputs.json").read_text("utf-8"))
    assert all(digest(ROOT / p) == h for p, h in suite_inputs.items())
    workers_result = json.loads((FINAL / "workers_book3.json").read_text("utf-8"))
    assert workers_result["assembly_producer"] == producer
    assert workers_result["one_vs_two_workers_identical"]
    assert workers_result["production_vs_development_identical"]
    assert workers_result["independent_upstream_caches"] and workers_result["both_caches_absent_before_run"]
    source_result = json.loads((FINAL / "source_crosscheck.json").read_text("utf-8"))
    assert source_result["pages"] == 30 and source_result["missing"] == source_result["extra"] == 0
    samples = [row for book in BOOKS for row in
               json.loads((FINAL / f"sample_after/{book}.json").read_text("utf-8"))["style"]]
    assert len(samples) == 160
    assert all(r["covered_characters"] == r["sample_characters"]
               for r in samples if r["original_verdict"] == "correct")
    removed = [r for r in samples if r["covered_characters"] == 0]
    assert len(removed) == 7 and all(r["original_verdict"] == "wrong" and
                                    r["sample_id"].startswith("spanish_us_history-")
                                    for r in removed)
    all_text_summary = json.loads((OUT / "all_text_hand_check_summary.json").read_text("utf-8"))
    all_text_verdicts = json.loads((OUT / "all_text_style_verdicts.json").read_text("utf-8"))
    all_text_coverage = json.loads((FINAL / "all_text_sample_after.json").read_text("utf-8"))
    all_text_census = json.loads((OUT / "all_text_style_census.json").read_text("utf-8"))
    assert all_text_summary["targets"] == len(all_text_verdicts) == len(all_text_coverage) == 160
    assert all_text_summary["overall"] == dict(Counter(r["verdict"] for r in all_text_verdicts))
    assert all_text_summary["overall"] == {"correct": 148, "wrong": 12}
    assert len(all_text_summary["cells"]) == len(all_text_census["cells"]) == 8
    assert all(sum(cell.values()) == 20 for cell in all_text_summary["cells"].values())
    assert {r["sample_id"] for r in all_text_verdicts} == {r["sample_id"] for r in all_text_coverage}
    assert all(r["covered_characters"] == r["sample_characters"]
               for r in all_text_coverage if r["verdict"] == "correct")
    all_text_removed = [r for r in all_text_coverage if r["covered_characters"] == 0]
    assert len(all_text_removed) == 7 and all(r["verdict"] == "wrong" and
                                             r["sample_id"].startswith("spanish_us_history-")
                                             for r in all_text_removed)
    assert all(row["all_furniture_fields_identical"]
               for row in all_text_census["all_kind_before_after"].values())
    assert set(all_text_census["all_kind_before_after"]) == set(BOOKS)
    lint = json.loads((FINAL / "validation/ruff_final.json").read_text("utf-8"))
    assert lint["exit_code"] == 0
    assert lint["log_sha256"] == digest(FINAL / "validation/ruff_final.log")
    packaging = json.loads((FINAL / "packaging/verification.json").read_text("utf-8"))
    assert packaging["wheel_sha256"] == digest(FINAL / "packaging" / packaging["wheel"])
    for member, result in packaging["assets"].items():
        assert result["identical"] and result["sha256"] == digest(ROOT / "backend/src" / member)
    assert packaging["python_sources_identical"]
    assert all(digest(ROOT / "backend/src" / member) == checksum
               for member, checksum in packaging["python_sources"].items())
    accepted_names = {"publication_reserve.json", "full_suite_reserve.json"}
    for phase in ("proof", "evaluate", "parity", "workers"):
        for book in [None] if phase == "workers" else BOOKS:
            method = "reuse_proof" if phase == "proof" and not books[book]["invariant_proof"]["fresh_every_page"] else phase
            if phase == "parity" and (FINAL / f"validation/parity_bounded_{book}_execution.json").exists():
                method = "parity_bounded"
            name = method + ("_" + book if book else "")
            execution = json.loads((FINAL / f"validation/{name}_execution.json").read_text("utf-8"))
            assert execution["passed"] and execution["assembly_producer"] == producer
            accepted_names.add(execution["reserve_record"])
            if method == "reuse_proof":
                closed = json.loads((FINAL / f"validation/proof_inputs_{book}_execution.json").read_text("utf-8"))
                assert closed["passed"] and closed["assembly_producer"] == producer
                accepted_names.add(closed["reserve_record"])
    if any((FINAL / f"validation/parity_bounded_{book}_execution.json").exists() for book in BOOKS):
        for book in BOOKS:
            checked = json.loads((FINAL / f"table_input_checks/{book}.json").read_text("utf-8"))
            assert checked["all_table_consumed_features_and_all_paths_identical"]
            assert len(checked["pages"]) >= 3 and all(r["identical"] for r in checked["pages"])
            assert checked["largest_page_bounded_stress"]["completed"]
            execution = json.loads((FINAL / f"validation/table_input_check_{book}_execution.json").read_text("utf-8"))
            assert execution["passed"] and execution["assembly_producer"] == producer
            accepted_names.add(execution["reserve_record"])
    all_monitors = {p.name: json.loads(p.read_text("utf-8"))
                    for p in (FINAL / "validation").glob("*_reserve.json")}
    monitors = {name: all_monitors[name] for name in sorted(accepted_names)}
    history = {name: value for name, value in all_monitors.items() if name not in accepted_names}
    assert all(not m["stopped_below_reserve"] for m in monitors.values())
    assert all(m["minimum_free_bytes"] >= 5_000_000_000 for m in monitors.values())
    write(FINAL / "validation_record.json", {"finished": now(), "passed": True,
          "assembly_producer": producer, "books": books,
          "full_suite": {"tests_passed": int(counts[0]), **suite_result},
          "ruff": lint, "packaging": packaging, "accepted_reserve_monitors": monitors,
          "historical_or_interrupted_reserve_monitors": history,
          "initial_content_style_sample": {"targets": len(samples), "correct_retained": 147,
                           "wrong_removed": len(removed), "wrong_retained_backlog": 5,
                           "unclear_retained": 1},
          "all_text_style_sample": {**all_text_summary, "wrong_removed": len(all_text_removed),
                                    "wrong_retained_backlog": 5,
                                    "all_furniture_fields_identical_on_all_five_books": True},
          "no_edit_after_final_suite_started": True, "free_bytes": reserve()})
    print("All final records accepted; tests passed:", counts[0], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("init", "publish", "proof", "proof_inputs", "reuse_proof", "metrics", "source",
                                           "evaluate", "parity", "parity_bounded", "table_input_check",
                                           "workers", "suite", "closure", "ruff", "record"))
    parser.add_argument("--book", choices=BOOKS)
    args = parser.parse_args()
    print("validation process PID", os.getpid(), flush=True)
    if args.phase == "init":
        initialize()
    else:
        frozen()
        action = globals()[args.phase]
        if args.phase in {"source", "workers", "suite", "closure", "ruff", "record"}:
            action()
        else:
            for name in [args.book] if args.book else BOOKS:
                action(name)
        frozen()
