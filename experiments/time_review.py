"""Time the review list (cold, warm, 4 requests at once) and a fresh edited book (an undo
re-applies every edit). Read-only on the live data. Usage: PYTHONPATH=<src> python this."""
import sys, time, threading
from book_app.config import AppSettings
from book_app.jobs import JobStore
from book_app.profiles import Profiles
from book_app.service import Service
s = AppSettings(data_folder="app_data", base=__import__("pathlib").Path.cwd(), models_folder="")
svc = Service(s, JobStore(s), Profiles(s.data_path, s.max_profile_bytes))
big, edited = "b3c776e2cefe0c91", "965d78af65efc4c4"
t = time.time(); svc.review(big); print("review cold  %.1fs" % (time.time() - t))
t = time.time(); svc.review(big); print("review warm  %.1fs" % (time.time() - t))
t = time.time(); ts = [threading.Thread(target=svc.review, args=(big,)) for _ in range(4)]
[x.start() for x in ts]; [x.join() for x in ts]; print("review 4 at once %.1fs" % (time.time() - t))
n = len(svc.decisions(edited).edits()); svc.cache.clear()
t = time.time(); svc.effective_book(edited); print("edited book (%d edits, as after an undo) %.1fs" % (n, time.time() - t))
