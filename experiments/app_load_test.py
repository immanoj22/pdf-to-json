"""Load test of the app: several people at once, each on their own book.

usage: app_load_test.py BASE_URL JOB_ID [JOB_ID ...] [--timeout SECONDS] [--json OUT.json]

Every job gets one simulated user, all started together: open the review list, open Details,
open a page in Browse, make an edit, look at the chapters (Check), confirm the details, open the
review list again, make a second edit. A monitor asks the quick requests (/api/profiles,
/api/health) twice a second the whole time. A request that answers 202 "preparing" is asked again
(like the page does); both the first answer and the time until the real answer are recorded.
It changes only the app it is pointed at: run it on a copy of the data, never on the office app."""

from __future__ import annotations

import json
import statistics
import sys
import threading
import time

import requests

HEAD = {"X-User": "Load", "X-Role": "manager"}
ONLY_EXPORT = False


def call(base, method, path, body=None, timeout=3600):
    """(status, data, first_answer_s, until_ready_s, answers_202)."""
    start, first, waited = time.time(), None, 0
    while True:
        r = requests.request(method, base + path, json=body, headers=HEAD, timeout=timeout)
        if first is None:
            first = time.time() - start
        if r.status_code == 202 and r.json().get("code") == "preparing" and method == "GET":
            waited += 1
            time.sleep(max(1, r.json().get("retry_after", 2)) * 0.5)
            continue
        try:
            data = r.json()
        except ValueError:
            data = None
        return r.status_code, data, first, time.time() - start, waited


def supported(base, job):
    """The formats the job's profile can make (the profiles list says)."""
    ref = requests.get(f"{base}/api/jobs/{job}", headers=HEAD, timeout=60).json().get("profile")
    rows = requests.get(f"{base}/api/profiles", headers=HEAD, timeout=60).json()["profiles"]
    return next((r["formats"] for r in rows if r["ref"] == ref), ["docbook"])


def export_step(base, job, results):
    """Start a docbook export (the placeholder override on) and wait for it, like the page does."""
    start = time.time()
    fmt = next((f for f in ("docbook", "bits", "jats", "html", "daisy3", "dtbook_nimas", "epub")
                if f in supported(base, job)), "docbook")
    r = requests.post(f"{base}/api/jobs/{job}/export/start", headers=HEAD, timeout=600,
                      json={"who": "Load", "formats": [fmt], "allow_alt_text_placeholders": True})
    first = time.time() - start
    state = r.json() if r.ok else {"state": f"http {r.status_code}"}
    while state.get("state") == "running":
        time.sleep(1)
        state = requests.get(f"{base}/api/jobs/{job}/export/progress", headers=HEAD, timeout=600).json()
    results.append({"job": job, "step": "export", "status": 200 if state.get("state") == "done" else
                    f"{state.get('state')}: {str(state.get('error'))[:60]}", "first": round(first, 2),
                    "total": round(time.time() - start, 2), "p202": 0})


def user(base, job, results):
    if ONLY_EXPORT:
        export_step(base, job, results)
        return
    def step(name, method, path, body=None):
        try:
            status, data, first, total, waited = call(base, method, path, body)
        except Exception as exc:  # noqa: BLE001
            results.append({"job": job, "step": name, "status": "error", "error": str(exc)[:120],
                            "first": None, "total": None, "p202": 0})
            return None
        results.append({"job": job, "step": name, "status": status, "first": round(first, 2),
                        "total": round(total, 2), "p202": waited})
        return data

    step("review list", "GET", f"/api/jobs/{job}/review")
    details = step("details", "GET", f"/api/jobs/{job}/details")
    units = step("browse page 5", "GET", f"/api/jobs/{job}/pages/5/units")
    para = None
    if units:
        para = next((u for u in units.get("units", []) if u.get("type") == "paragraph"), None)
    if para:
        step("edit 1", "POST", f"/api/jobs/{job}/edits",
             {"who": "Load", "edit": {"op": "heading_set", "unit": para["id"], "level": 3}})
    step("chapters (check)", "GET", f"/api/jobs/{job}/chapters")
    if details and details.get("details"):
        step("confirm details", "PUT", f"/api/jobs/{job}/details", {**details["details"], "who": "Load"})
    step("review list again", "GET", f"/api/jobs/{job}/review")
    if para:
        step("edit 2", "POST", f"/api/jobs/{job}/edits",
             {"who": "Load", "edit": {"op": "heading_set", "unit": para["id"], "level": 2}})
        step("review list after edit", "GET", f"/api/jobs/{job}/review")


def monitor(base, stop, samples):
    while not stop.is_set():
        for path in ("/api/profiles", "/api/health"):
            t = time.time()
            try:
                code = requests.get(base + path, headers=HEAD, timeout=600).status_code
            except Exception:  # noqa: BLE001
                code = "error"
            samples.append({"path": path, "status": code, "s": round(time.time() - t, 3), "at": round(t, 1)})
        stop.wait(0.5)


def main(argv):
    timeout = 3600
    out = None
    args = []
    it = iter(argv[1:])
    for a in it:
        if a == "--timeout":
            timeout = int(next(it))
        elif a == "--json":
            out = next(it)
        elif a == "--only-export":
            globals()["ONLY_EXPORT"] = True
        else:
            args.append(a)
    base, jobs = args[0], args[1:]
    results, samples, stop = [], [], threading.Event()
    mon = threading.Thread(target=monitor, args=(base, stop, samples), daemon=True)
    mon.start()
    started = time.time()
    threads = [threading.Thread(target=user, args=(base, j, results)) for j in jobs]
    [t.start() for t in threads]
    for t in threads:
        t.join(timeout)
    stop.set()
    mon.join(5)
    wall = time.time() - started
    steps = []
    for r in results:
        if r["step"] not in steps:
            steps.append(r["step"])
    print(f"{len(jobs)} users, total {wall:.0f} s\n")
    print(f"{'step':<24}{'first answer (s)':>26}{'until ready (s)':>26}   202s")
    for name in steps:
        rows = [r for r in results if r["step"] == name]
        fa = [r["first"] for r in rows if r["first"] is not None]
        tr = [r["total"] for r in rows if r["total"] is not None]
        bad = [r for r in rows if r["status"] not in (200,)]
        fmt = lambda v: f"med {statistics.median(v):6.2f} max {max(v):7.2f}" if v else "-"  # noqa: E731
        print(f"{name:<24}{fmt(fa):>26}{fmt(tr):>26}   {sum(r['p202'] for r in rows)}"
              + (f"   NOT 200: {[(r['status'], r.get('error')) for r in bad]}" if bad else ""))
    for path in ("/api/profiles", "/api/health"):
        v = [s["s"] for s in samples if s["path"] == path]
        if v:
            slow = sum(1 for x in v if x > 1.0)
            p95 = sorted(v)[int(0.95 * (len(v) - 1))]
            print(f"\nquick request {path}: {len(v)} asked, median {statistics.median(v):.3f} s, "
                  f"p95 {p95:.3f} s, max {max(v):.2f} s, slower than 1 s: {slow}")
    if out:
        json.dump({"wall": wall, "results": results, "samples": samples}, open(out, "w"))


if __name__ == "__main__":
    main(sys.argv)
