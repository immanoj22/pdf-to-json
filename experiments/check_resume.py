"""Resumed builds equal full ones: on a real edited book, rebuild after an undo of the last
edit, after a new edit and after an undo in the middle; compare with overlay.apply_edits."""
import json, pathlib, time
from book_app import overlay
from book_app.config import AppSettings
from book_app.jobs import JobStore
from book_app.profiles import Profiles
from book_app.service import Service
s = AppSettings(data_folder="app_data", base=pathlib.Path.cwd(), models_folder="")
svc = Service(s, JobStore(s), Profiles(s.data_path, s.max_profile_bytes))
J = "965d78af65efc4c4"; job = svc.store.get(J); base = svc.base_book(J)
marks = svc.profiles.list_marks(job["profile"]); E = svc.decisions(J).edits()
dump = lambda r: json.dumps(r, sort_keys=True)
def check(label, edits):
    t = time.time(); got = svc._apply_resumed(J, job, edits, marks); dt = time.time() - t
    want = overlay.apply_edits(base, edits, marks)
    print(f"{label:28s} {len(edits):3d} edits {dt:5.1f}s  same={dump(got) == dump(want)}", flush=True)
check("full", E)
check("undo last", E[:-1])
check("undo last again", E[:-2])
check("new edit after undo", E[:-2] + [E[-1]])
check("one more", E[:-2] + [E[-1], E[-2]])
check("undo in the middle", E[:50] + E[51:])
check("same list", E[:50] + E[51:])
