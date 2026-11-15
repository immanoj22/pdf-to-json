"""Profile Service.review on the live data, read-only (no app, no converter)."""
import cProfile, pstats, sys
sys.path.insert(0, "backend/src")
from book_app.config import AppSettings
from book_app.jobs import JobStore
from book_app.profiles import Profiles
from book_app.service import Service
import inspect
s = AppSettings.load("app_settings.yaml") if hasattr(AppSettings, "load") else AppSettings()
store = JobStore(s); svc = Service(s, store, Profiles(s.data_path, s.max_profile_bytes))
J = "b3c776e2cefe0c91"
import time; t=time.time(); svc.review(J); print("cold", round(time.time()-t,2)); pr = cProfile.Profile(); pr.enable(); t=time.time(); svc.review(J); pr.disable(); print("warm", round(time.time()-t,2))
pstats.Stats(pr).sort_stats("cumulative").print_stats(14)
