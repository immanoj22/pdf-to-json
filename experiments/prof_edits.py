import cProfile, pstats, pathlib
from book_app.config import AppSettings
from book_app.jobs import JobStore
from book_app.profiles import Profiles
from book_app.service import Service
s = AppSettings(data_folder="app_data", base=pathlib.Path.cwd(), models_folder="")
svc = Service(s, JobStore(s), Profiles(s.data_path, s.max_profile_bytes))
J = "965d78af65efc4c4"; svc.base_book(J)
pr = cProfile.Profile(); pr.enable(); svc.effective_book(J); pr.disable()
pstats.Stats(pr).sort_stats("tottime").print_stats(8)
