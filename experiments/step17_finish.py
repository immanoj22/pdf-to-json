"""Resume Step 17 in ordered, fail-fast phases; never remove any cache.

Each child has a separate UTF-8 log. The state records command, exit status, time and
free space. Existing performance records are copied before final producer reruns.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step17"
FINAL = OUT / "final"
BOOKS = ("art_therapy_index", "medical_anatomy", "spanish_us_history", "statistics",
         "immigrant_children")


def now():
    return datetime.now(timezone.utc).isoformat()


def run(phase, label, script, *args):
    command = [sys.executable, str(ROOT / "experiments" / script), *map(str, args)]
    log = OUT / "final_logs" / f"frozen_{label}.log"
    row = {"command": command, "started": now(), "free_before": shutil.disk_usage(ROOT).free,
           "log": str(log.relative_to(ROOT))}
    print(label, "started", row["started"], flush=True)
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    row.update(exit_code=result.returncode, finished=now(), free_after=shutil.disk_usage(ROOT).free)
    with (OUT / f"finish_{phase}.jsonl").open("a", encoding="utf-8") as record:
        record.write(json.dumps(row) + "\n")
    print(label, "exit", result.returncode, "free", row["free_after"], flush=True)
    if result.returncode:
        raise SystemExit(f"Stopped at {label}; inspect {log}. No cleanup performed.")


def reusable_proof(book):
    """Reuse an already-passed full proof only when all its input cache keys match."""
    if book not in {"art_therapy_index", "medical_anatomy", "spanish_us_history", "statistics"}:
        return False
    epoch = json.loads((FINAL / "run_epoch.json").read_text("utf-8"))
    previous = Path(epoch["previous_records"]) / f"{book}.json"
    proof = FINAL / "after" / f"{book}_full_gates.json"
    if not previous.exists() or not proof.exists():
        return False
    before = json.loads(previous.read_text("utf-8"))["run"]
    after = json.loads((FINAL / "performance" / f"{book}.json").read_text("utf-8"))["run"]
    keys = ("native", "analysis", "layout", "lists")
    same = before["pages"] == after["pages"] and all(
        before["cache_keys"].get(k) == after["cache_keys"].get(k) for k in keys)
    evidence = json.loads(proof.read_text("utf-8"))
    expected = {f"I{n}": int(book == "statistics" and n == 7) for n in range(1, 8)}
    passed = evidence["invariant_totals"] == expected and all(
        row["units_once"] and row["ordered_once"] for row in evidence["ownership"].values())
    if not same or not passed or len(evidence["ownership"]) != after["pages"]:
        return False
    record = {"book": book, "pages": after["pages"], "previous_record": str(previous),
              "cache_keys": {k: after["cache_keys"][k] for k in keys},
              "proof_sha256": hashlib.sha256(proof.read_bytes()).hexdigest(),
              "reason": "Every full-proof input cache key is unchanged; only final publication changed"}
    with (FINAL / "proof_reuse.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(record) + "\n")
    print("reused passed proof", book, after["pages"], flush=True)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("runs", "publish", "proofs", "metrics", "parity", "report"))
    parser.add_argument("--book", choices=BOOKS)
    args = parser.parse_args()
    phase = args.phase
    books = (args.book,) if args.book else BOOKS
    (OUT / "final_logs").mkdir(exist_ok=True)
    if phase == "runs":
        history = FINAL / "run_history" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        history.mkdir(parents=True)
        # A new complete measurement epoch follows the reviewed producer corrections.
        # Preserve the previous guard and records; never mix them with the frozen reruns.
        for previous in [FINAL / "producers.json", *(FINAL / "performance").glob("*.json")]:
            if previous.exists():
                shutil.copyfile(previous, history / previous.name)
        sys.path.insert(0, str(ROOT / "backend/src"))
        from book_core.caching import SCOPES, code_digest

        producers = {scope: code_digest(scope) for scope in SCOPES}
        (FINAL / "producers.json").write_text(json.dumps(producers, indent=1) + "\n", "utf-8")
        (FINAL / "run_epoch.json").write_text(
            json.dumps({"started": now(), "previous_records": str(history),
                        "producers": producers}, indent=1) + "\n", "utf-8")
        for book in books:
            if book == "immigrant_children":
                run(phase, f"run_{book}", "step17_ocr_cover.py", "run", "--out", "final")
            else:
                run(phase, f"run_{book}", "step17_run.py", "run", "--book", book,
                    "--out", "final")
    elif phase == "publish":
        sys.path.insert(0, str(ROOT / "backend/src"))
        from book_core.caching import code_digest

        (FINAL / "publication_epoch.json").write_text(json.dumps(
            {"started": now(), "assembly_producer": code_digest("assembly"),
             "reason": "Publication-only entry-level preservation; upstream conversion archives reused"},
            indent=1) + "\n", "utf-8")
        publish_books = books if args.book else (
            "art_therapy_index", "immigrant_children", "medical_anatomy",
            "spanish_us_history", "statistics")
        for book in publish_books:
            run(phase, f"publish_{book}", "step17_refresh_assembly.py", "--book", book)
    elif phase == "proofs":
        for book in books:
            if book == "immigrant_children":
                run(phase, f"proof_{book}", "step17_ocr_cover.py", "proof", "--out", "final")
            else:
                if not reusable_proof(book):
                    run(phase, f"proof_{book}", "step17_run.py", "proof", "--book", book,
                        "--out", "final")
                if book != "statistics":
                    run(phase, f"compare_{book}", "step17_run.py", "compare", "--book", book,
                        "--out", "final")
        if args.book is None:
            run(phase, "source_gates", "step17_source_gates.py")
    elif phase == "metrics":
        (FINAL / "lossless").mkdir(exist_ok=True)
        for book in books:
            record = json.loads((FINAL / "performance" / f"{book}.json").read_text("utf-8"))["run"]
            document = Path(record["book_json"]) / "book.json"
            run(phase, f"lossless_{book}", "step17_lossless.py", "--json", document,
                "--archive", record["output"], "--out", FINAL / "lossless" / f"{book}.json")
            run(phase, f"json_eval_{book}", "step17_json_eval.py", "--book", book,
                "--json", document, "--archive", record["output"])
            run(phase, f"cleanup_{book}", "step17_cleanup_counts.py", "--book", book,
                "--json", document)
    elif phase == "parity":
        sys.path.insert(0, str(ROOT / "backend/src"))
        from book_core.caching import code_digest

        run(phase, "parity", "step17_parity.py")
        worker_path = FINAL / "workers_book3.json"
        epoch = json.loads((FINAL / "run_epoch.json").read_text("utf-8"))
        started = datetime.fromisoformat(epoch["started"]).timestamp()
        worker = json.loads(worker_path.read_text("utf-8")) if worker_path.exists() else {}
        if not (worker_path.exists() and worker_path.stat().st_mtime >= started
                and worker.get("one_vs_two_workers_identical")
                and worker.get("production_vs_development_identical")
                and worker.get("assembly_producer") == code_digest("assembly")):
            run(phase, "workers", "step17_workers.py")
        else:
            print("reused passed worker comparison from current frozen epoch", flush=True)
    else:
        run(phase, "report", "step17_report_data.py", "--out", "final")


if __name__ == "__main__":
    main()
