"""Build a new local wrapper, leaving original orchestration/evidence untouched."""
import ast
import difflib
from pathlib import Path

base = Path('.cache/step18_part2')
original = (base / 'run_book_once.py').read_text(encoding='utf8')
text = original
def replace(old, new):
    global text
    assert text.count(old) == 1, old[:80]
    text = text.replace(old, new)

replace('ATTEMPT = f"{BOOK}_attempt1"\nDEST = BASE / ATTEMPT', '''ATTEMPT = f"{BOOK}_attempt{2 if BOOK == 'ent_textbook' else 1}"
DEST = BASE / ATTEMPT
CACHE = {"ent_textbook": ROOT / ".cache/h18/e2", "math_holdout": Path("C:/h/m"),
         "mideast": Path("C:/h/d")}[BOOK]
SHORT_ID = {"ent_textbook": "e2", "math_holdout": "m", "mideast": "d"}[BOOK]
OCR_CACHE = ROOT / ".cache/h18" / (SHORT_ID + "o")
PUBLISHED = ROOT / ".cache/h18" / (SHORT_ID + "p")
REUSED = ["book_metadata", "native", "analysis", "layout", "reading_order", "furniture",
          "paragraphs", "structure_evidence", "structure", "lists", "characters", "figures",
          "equations", "mathml"] if BOOK == "ent_textbook" else []

def path_preflight():
    digest, uuid = "f" * 64, "a" * 32
    candidates = {}
    for family in ("formula_readings", "table_readings"):
        path = CACHE.resolve() / family / digest / "ff" / f".{digest}.json.{uuid}.tmp"
        candidates[family] = {"path": str(path), "characters": len(str(path))}
    # All other fixed cache record layouts have one digest level and a shorter filename.
    # Figure/equation asset names use the frozen page-label naming patterns.
    maximum = max(p["characters"] for p in candidates.values())
    limit = 260 if BOOK == "ent_textbook" else 200
    return {"cache_root": str(CACHE.resolve()), "ocr_cache_root": str(OCR_CACHE.resolve()),
            "publication_root": str(PUBLISHED.resolve()), "expected_deepest": candidates,
            "maximum_expected_characters": maximum, "strict_limit": limit,
            "passed": maximum < limit}
''')
replace('json.dumps({"schema_version": 1, **value}, default=str)', '''json.dumps({"schema_version": 1,
            **({"reason": "path_length_wrapper_error", "failure_class": "environmental",
                "from_attempt_id": "ent_textbook_attempt1"} if BOOK == "ent_textbook" else {}),
            **value}, default=str)''')
replace('    free = shutil.disk_usage(ROOT).free\n    checks["free_above_40GB"]', '''    paths = path_preflight()
    checks["cache_paths_within_limit"] = paths["passed"]
    if BOOK == "ent_textbook":
        reuse = json.loads((BASE / "retry_preparation/reuse_receipt.json").read_text("utf8"))
        checks["reuse_preparation_verified"] = reuse["sha256_verified"] and reuse["attempt1_all_files_unchanged"]
        checks["supplemental_record_audit_passed"] = json.loads((BASE / "retry_preparation/supplemental_gzip_audit.json").read_text())["passed"]
    else:
        checks["cold_cache_empty"] = CACHE.exists() and not any(CACHE.iterdir())
    free = shutil.disk_usage(ROOT).free
    checks["free_above_40GB"]''')
replace('"profile_sha256": profile.sha256}', '''"profile_sha256": profile.sha256, "path_preflight": paths,
                 "stage_reuse": {stage: "reused from attempt 1" for stage in REUSED},
                 "recomputed": ["ocr_eligibility_and_preparation", "book_evidence"],
                 "fresh": ["tables (model detections reused from attempt 1)" if REUSED else "tables",
                           "continuity", "final_output", "assembly"]}''')
replace('    DEST.mkdir(parents=True)\n', '''    DEST.mkdir(parents=True)
    write(DEST / "cache_reuse.json", {"stages": {s: "reused from attempt 1" for s in REUSED},
        "note": "Retry timings for reused stages measure cache validation/use, not fresh computation. OCR preparation and book evidence are recomputed. Tables reuse detector evidence but table structure/assembly are fresh."})
''')
replace('"outcome": "running", "stage": "initialization", "pid": os.getpid(),', '''"outcome": "running", "stage": "initialization", "pid": os.getpid(),
             "stage_reuse": {stage: "reused from attempt 1" for stage in REUSED},''')
replace('ocr = prepare_book(source, DEST / "ocr_cache", settings, primary, secondary,\n                           visual_checks=visual_checks(source, DEST / "ocr_cache"))', '''ocr = prepare_book(source, OCR_CACHE, settings, primary, secondary,
                           visual_checks=visual_checks(source, OCR_CACHE))
        if BOOK == "ent_textbook":
            old_ocr = json.loads((BASE / "ent_textbook_attempt1/ocr_input.json").read_text("utf8"))
            assert ocr.fingerprint == old_ocr["fingerprint"], "Regenerated OCR fingerprint changed"
            assert settings.model_dump(mode="json") == json.loads((BASE / "ent_textbook_attempt1/effective_settings.json").read_text("utf8")), "Settings changed"''')
replace('result = run_book(source, DEST / "published", DEST / "cache", mode="development",', 'result = run_book(source, PUBLISHED, CACHE, mode="development",')
replace('        write(DEST / "performance.json", {"run": result, "ocr": ocr.model_dump(mode="json"),', '''        for name, measurement in result.get("stages", {}).items():
            if name in REUSED:
                measurement.update(execution_status="reused from attempt 1",
                    timing_scope="cache validation/use; not a fresh computation timing")
            elif name == "tables" and REUSED:
                measurement.update(execution_status="fresh table structure/assembly; detector evidence reused from attempt 1")
            else:
                measurement.update(execution_status="recomputed" if name == "book_evidence" else "fresh")
        write(DEST / "performance.json", {"run": result, "ocr": ocr.model_dump(mode="json"),''')
replace('        state.update(outcome="failed", exception_type=type(error).__name__, error=str(error),', '''        state.update(outcome="failed", failure_stage_note="See traceback for actual stage; progress callbacks cover page stages only",
                     exception_type=type(error).__name__, error=str(error),''')
ast.parse(text)
target = base / 'run_book_short.py'
with target.open('x', encoding='utf8', newline='\n') as stream:
    stream.write(text)
(base / 'retry_preparation/wrapper_routing.diff').write_text(''.join(difflib.unified_diff(
    original.splitlines(True), text.splitlines(True), fromfile='run_book_once.py', tofile='run_book_short.py')), encoding='utf8')
print('New local wrapper syntax passed; frozen backend is not edited.')
