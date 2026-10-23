"""Sequential final gates for the five approved Step 17b publications.

The caller monitors this explicitly verified process lifetime against the reserve.
No source changes, cache cleanup, upstream conversion or hold-out runs are performed.
"""
import argparse
import os
import subprocess
import sys
import threading
import time

import step17b_finish as finish
from step17b_watch import watch


def main(phases, selected=None):
    print("validation queue PID", os.getpid(), flush=True)
    for phase in phases:
        books = [None] if phase == "workers" else selected or finish.BOOKS
        for book in books:
            name = phase + ("_" + book if book else "")
            receipt = finish.FINAL / "validation" / (name + "_execution.json")
            assert not receipt.exists(), f"Keep the previous receipt: {receipt}"
            finish.frozen()
            started, clock = finish.now(), time.perf_counter()
            print("starting", name, started, flush=True)
            command = [sys.executable, str(finish.ROOT / "experiments/step17b_finish.py"), phase]
            if book:
                command += ["--book", book]
            reserve_record = receipt.with_name(name + "_reserve.json")
            assert not reserve_record.exists()
            with subprocess.Popen(command, cwd=finish.ROOT, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                  env=os.environ | {"PYTHONIOENCODING": "utf-8"}) as child:
                first = child.stdout.readline()
                print(first, end="", flush=True)
                assert first.startswith("validation process PID "), first
                # This is the actual interpreter, reported by our known child script;
                # Windows' venv launcher can have a different Popen PID.
                actual_pid = int(first.split()[-1])
                monitor = threading.Thread(target=watch, args=(actual_pid, reserve_record))
                monitor.start()
                for line in child.stdout:
                    print(line, end="", flush=True)
                exit_code = child.wait()
                monitor.join()
            watched = finish.json.loads(reserve_record.read_text("utf-8"))
            assert exit_code == 0 and not watched["stopped_below_reserve"], name
            finish.frozen()
            finish.write(receipt, {"started": started, "finished": finish.now(),
                         "seconds": time.perf_counter() - clock,
                         "assembly_producer": finish.code_digest("assembly"),
                         "reserve_record": reserve_record.name,
                         "passed": True})
            print("passed", name, round(time.perf_counter() - clock, 2), flush=True)


if __name__ == "__main__":
    # Model loaders can print Unicode progress glyphs on redirected Windows I/O.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("phases", nargs="+", choices=("metrics", "proof", "proof_inputs", "reuse_proof", "evaluate",
                                                     "parity", "parity_bounded", "table_input_check", "workers"))
    parser.add_argument("--books", nargs="+", choices=finish.BOOKS)
    args = parser.parse_args()
    main(args.phases, args.books)
