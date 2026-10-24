"""Guard later evaluation jobs; never run them before all three conversions finish."""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '.cache/step18_part2'
ATTEMPTS = ['ent_textbook_attempt2', 'math_holdout_attempt1', 'mideast_attempt1']

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def main():
    if len(sys.argv) < 3:
        raise SystemExit('Usage: evaluation_guard.py JOB_ID SCRIPT [ARGS...]')
    label, script, *args = sys.argv[1:]
    assert all((BASE / attempt / 'result.json').exists() for attempt in ATTEMPTS), 'Serial conversions have not all finished'
    results = [json.loads((BASE / attempt / 'result.json').read_text()) for attempt in ATTEMPTS]
    assert all(r['outcome'] in {'completed', 'failed'} for r in results), 'Owner decision needed after reserve/monitor interruption'
    destination = BASE / 'evaluation_jobs' / label
    destination.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('step18_measurement_helpers', BASE / 'run_book_short.py')
    helpers = importlib.util.module_from_spec(spec)
    # Import measurement helpers without invoking main; no converter runs here.
    prior_argv = sys.argv
    sys.argv = [str(BASE / 'run_book_short.py'), 'ent_textbook']
    spec.loader.exec_module(helpers)
    sys.argv = prior_argv
    sys.path[:0] = [str(ROOT / 'backend/src'), str(ROOT / 'experiments')]
    from book_core.process_metrics import rss
    started = time.perf_counter()
    free = shutil.disk_usage(ROOT).free
    assert free > 5_000_000_000
    state = {'job_id': label, 'start_time': now(), 'outcome': 'running',
             'minimum_free_bytes': free, 'peak_tree_rss_bytes': 0, 'pid': os.getpid()}
    stop = threading.Event()
    def sample():
        owned = helpers.children()
        free = shutil.disk_usage(ROOT).free
        state.update(free_bytes=free, elapsed_seconds=time.perf_counter()-started, updated_at=now())
        state['minimum_free_bytes'] = min(state['minimum_free_bytes'], free)
        state['peak_tree_rss_bytes'] = max(state['peak_tree_rss_bytes'], sum(rss(pid) for pid in owned))
        helpers.write(destination / 'live.json', state)
        if free < 5_000_000_000:
            state.update(outcome='reserve_stopped', end_time=now())
            helpers.write(destination / 'result.json', state)
            helpers.terminate_owned(owned)
            os._exit(42)
    def watch():
        while not stop.wait(0.5):
            try:
                sample()
            except BaseException as e:
                state.update(outcome='monitor_failed', error=repr(e), end_time=now())
                helpers.write(destination / 'result.json', state)
                helpers.terminate_owned(helpers.children())
                os._exit(43)
    sample()
    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    try:
        sys.argv = [script, *args]
        runpy.run_path(script, run_name='__main__')
        state['outcome'] = 'completed'
    except SystemExit as e:
        state.update(outcome='completed' if e.code in {None, 0} else 'failed', exit_code=e.code)
        raise
    except BaseException as e:
        state.update(outcome='failed', error=repr(e))
        raise
    finally:
        stop.set(); thread.join(); sample()
        state['end_time'] = now()
        helpers.write(destination / 'result.json', state)

if __name__ == '__main__':
    main()
