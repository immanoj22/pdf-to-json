"""Step 20 runs: the Step 18 hold-out call (OCR preparation, then ``run_book``) on any book.

Every book uses the same production call: the default client profile, job languages
``spa``/``eng``, one worker unless given, CPU. Caches are short and per book
(``.cache/s20/<book>``); caches are keyed by producer fingerprints, so a later run reuses
only the stages whose producers did not change. ``--fresh`` uses an empty cache instead;
``--cache`` names a cache root explicitly (a variant run reusing another run's unchanged
stages).

Actions (results under ``experiments/out/step20/<tag>``):
  run    convert one book; ``performance/<book>.json`` holds the run record
  proof  I1-I7 and exact line ownership on every page, from the run's caches
  hashes SHA-256 of every archive and publication file

Paths come from ``references.toml`` (or ``BOOK_CONVERTER_REFERENCE_CONFIG``); the OCR
assets from ``--ocr-config`` (the Step 16 config layout). A memory watcher samples the
machine's available memory and the run's resident peak into the run record; below
``--memory-floor`` GB available it records the run as stopped and exits (caches resume it).

Usage:
  python step20_run.py run --book medical_anatomy --tag before --ocr-config cfg.json
  python step20_run.py proof --book medical_anatomy --tag before
"""

import argparse
import gc
import hashlib
import json
import os
import shutil
import sys
import threading
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

BOOKS = {
    "spanish_us_history": "spanish_pdf",
    "immigrant_children": "small_pdf",
    "art_therapy_index": "art_index_pdf",
    "medical_anatomy": "medical_pdf",
    "statistics": "statistics_pdf",
    "art_lab": "jaypee_art_pdf",
    "iap_mec": "iap_mec_pdf",
    "trichology": "trichology_pdf",
}
OUT = ROOT / "experiments/out/step20"
CACHE = ROOT / ".cache/s20"


def now():
    return datetime.now(UTC).isoformat()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False, default=str) + "\n", "utf-8")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def locations(book, tag, fresh, cache=None):
    base = Path(cache) if cache else CACHE / (f"{book}_{tag}" if fresh else book)
    return base, CACHE / "pub" / tag / book


def available_gb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024**2
    return float("nan")


def resident_gb(pid):
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1]) / 1024**2
    return float("nan")


class MemoryWatcher(threading.Thread):
    """Samples memory every few seconds; below the floor, records a stop and exits."""

    def __init__(self, record, target, floor):
        super().__init__(daemon=True)
        self.record, self.target, self.floor = record, target, floor
        self.minimum, self.peak, self.done = float("inf"), 0.0, threading.Event()

    def summary(self):
        return {"machine_min_available_gb": round(self.minimum, 2),
                "process_peak_gb": round(self.peak, 2), "floor_gb": self.floor}  # fmt: skip

    def run(self):
        while not self.done.wait(5):
            self.minimum = min(self.minimum, available_gb())
            self.peak = max(self.peak, resident_gb(os.getpid()))
            if self.minimum < self.floor:
                self.record.update(outcome="stopped", reason="memory floor", end=now(),
                                   memory=self.summary())  # fmt: skip
                write(self.target, self.record)
                print("stopped: memory floor", self.summary(), flush=True)
                os._exit(3)


def ocr_settings(config):
    from book_core.assembly.profile import load_profile
    from book_core.assembly.profile import ocr_settings as from_profile
    from book_core.ocr.settings import OcrJobSettings, OcrSettings

    settings = OcrSettings(
        executable=Path(config["tesseract_executable"]),
        tessdata=Path(config["tessdata"]),
        asset_manifest=ROOT / "experiments/out/step16/dependencies/tessdata_manifest.json",
        second_reader="on",
        detector_path=Path(config["pp_detector"]),
        recognizer_paths={r["name"]: Path(r["path"]) for r in config["pp_recognizers"]},
        model_revisions={"detector": config["pp_detector_revision"],
                         **{r["name"]: r["revision"] for r in config["pp_recognizers"]}},
    )  # fmt: skip
    return OcrJobSettings(device="cpu", ocr_languages=["spa", "eng"],
                          ocr=from_profile(load_profile(), settings))  # fmt: skip


def run(book, tag, ocr_config, workers, fresh, mode, cache=None, floor=1.0):
    from book_core.assembly.profile import load_profile
    from book_core.book_run import run_book
    from book_core.caching import SCOPES, code_digest
    from book_core.ocr.prepare import prepare_book
    from reference_paths import reference_path
    from step16_benchmark import make_engines
    from step16_downstream import visual_checks

    source = reference_path(BOOKS[book])
    cache, published = locations(book, tag, fresh, cache)
    if fresh and cache.exists() and any(cache.iterdir()):
        raise SystemExit(f"Fresh cache {cache} is not empty")
    if published.exists():
        shutil.rmtree(published)
    config = {**json.loads(Path(ocr_config).read_text("utf-8")), "device": "cpu"}
    settings = ocr_settings(config)
    primary, secondary = make_engines(config)
    record = {"book": book, "tag": tag, "start": now(), "pid": os.getpid(),
              "source_sha256": sha(source), "cache": str(cache), "fresh": fresh,
              "workers": workers, "mode": mode,
              "threads": {"OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
                          "torch_start": __import__("torch").get_num_threads()},
              "settings": settings.model_dump(mode="json")}  # fmt: skip
    target = OUT / tag / "performance" / f"{book}.json"
    tick = time.perf_counter()
    watcher = MemoryWatcher(record, target, floor)
    watcher.start()
    try:
        ocr = prepare_book(source, cache / "o", settings, primary, secondary,
                           visual_checks=visual_checks(source, cache / "o"))  # fmt: skip

        def progress(stage, completed, total):
            if completed % 50 == 0 or completed == total:
                print(book, stage, completed, total, flush=True)

        result = run_book(source, published, cache, mode=mode, workers=workers,
                          device="cpu", settings=settings, progress=progress,
                          model_cache_dir=ROOT / ".cache/huggingface", ocr_input=ocr,
                          profile=load_profile())  # fmt: skip
        record.update(outcome="completed", run=result,
                      ocr={"page_keys": ocr.page_keys, "comparison_keys": ocr.comparison_keys},
                      producers={scope: code_digest(scope) for scope in SCOPES})  # fmt: skip
    except Exception as error:  # noqa: BLE001 - every failure is the run's recorded outcome
        record.update(outcome="failed", exception_type=type(error).__name__,
                      error=str(error), traceback=traceback.format_exc())  # fmt: skip
        print(record["traceback"], flush=True)
    watcher.done.set()
    record.update(end=now(), wall_seconds=time.perf_counter() - tick, memory=watcher.summary())
    write(target, record)
    print(book, record["outcome"], f"{record['wall_seconds']:.0f}s", flush=True)
    return 0 if record["outcome"] == "completed" else 1


def proof(book, tag):
    """Every page: I1-I7 from the layout and analysis, and each line owned once."""
    from book_core.extraction.fingerprints import stable_id
    from book_core.layout.invariants import check
    from book_core.layout.models import PageLayout
    from book_core.lists.keys import book_fingerprint
    from book_core.lists.models import PageLists
    from book_core.objects.analysis import verified_read
    from book_core.objects.models import ObjectAnalysis

    record = json.loads((OUT / tag / "performance" / f"{book}.json").read_text("utf-8"))
    root, keys = Path(record["cache"]), record["run"]["cache_keys"]
    lists = book_fingerprint(keys["lists"]) if isinstance(keys["lists"], dict) else keys["lists"]
    gates, ownership = {}, {}
    for number in range(1, record["run"]["pages"] + 1):
        analysis = verified_read(
            root / "analysis" / keys["analysis"] / f"{number}.json",
            ObjectAnalysis,
            keys["analysis"],
        )
        layout = verified_read(
            root / "layout" / keys["layout"] / f"{number}.json", PageLayout, keys["layout"]
        )
        units = verified_read(
            root / "lists/page" / lists / f"{number}.json",
            PageLists,
            stable_id(lists, "page", int(number)),
        )
        assigned = [lid for unit in units.units for lid in unit.line_ids]
        ordered = [lid for stream in units.order.streams for lid in stream.line_ids]
        expected = {line.id for line in layout.lines}
        gates[str(number)] = check(layout, analysis)
        ownership[str(number)] = {
            "lines": len(expected),
            "units_once": len(assigned) == len(set(assigned)) and set(assigned) == expected,
            "ordered_once": len(ordered) == len(set(ordered)) and set(ordered) == expected,
        }
        del analysis, layout, units
        gc.collect()
    totals = {
        name: sum(len(r[name]) for r in gates.values())
        for name in ("I1", "I2", "I3", "I4", "I5", "I6", "I7")
    }
    owned = all(v["units_once"] and v["ordered_once"] for v in ownership.values())
    write(
        OUT / tag / "gates" / f"{book}.json",
        {"invariant_totals": totals, "every_line_owned_once": owned,
         "invariants": {n: r for n, r in gates.items() if any(r.values())},
         "ownership_failures": {n: r for n, r in ownership.items()
                                if not (r["units_once"] and r["ordered_once"])}},
    )  # fmt: skip
    print(book, totals, "owned once:", owned, flush=True)


def hashes(book, tag):
    record = json.loads((OUT / tag / "performance" / f"{book}.json").read_text("utf-8"))
    rows = {}
    for key in ("output", "book_json"):
        folder = Path(record["run"][key])
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            rows[f"{key}/{path.relative_to(folder).as_posix()}"] = sha(path)
    write(OUT / tag / "hashes" / f"{book}.json", rows)
    print(book, len(rows), "files", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "proof", "hashes"])
    parser.add_argument("--book", choices=BOOKS, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--ocr-config")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--mode", choices=["development", "production"], default="development")
    parser.add_argument("--cache", help="an explicit cache root (reuse another run's caches)")
    parser.add_argument("--memory-floor", type=float, default=1.0, help="GB available")
    args = parser.parse_args()
    if args.action == "run":
        if not args.ocr_config:
            parser.error("--ocr-config is required for run")
        return run(args.book, args.tag, args.ocr_config, args.workers, args.fresh, args.mode,
                   args.cache, args.memory_floor)
    return {"proof": proof, "hashes": hashes}[args.action](args.book, args.tag)


if __name__ == "__main__":
    raise SystemExit(main())
