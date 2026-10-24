"""Observe an existing owned conversion from a separate interpreter; no converter edits."""
import ctypes
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '.cache/step18_part2'
book, target_text = sys.argv[1:]
target = int(target_text)
destination = BASE / (book + '_attempt1') / 'external_monitor'
destination.mkdir(parents=True, exist_ok=False)
spec = importlib.util.spec_from_file_location('measurement_helpers', BASE / 'run_book_short.py')
helpers = importlib.util.module_from_spec(spec)
previous = sys.argv
sys.argv = [str(BASE / 'run_book_short.py'), book]
spec.loader.exec_module(helpers)
sys.argv = previous
helpers.os = types.SimpleNamespace(getpid=lambda: target)
from book_core.process_metrics import rss

kernel = ctypes.windll.kernel32
kernel.OpenProcess.restype = ctypes.c_void_p
handle = kernel.OpenProcess(0x100000, False, target)  # SYNCHRONIZE; pins the original process
if not handle:
    raise OSError('Cannot observe the original process lifetime')
started = time.perf_counter()
state = {'book_id': book, 'target_pid': target, 'monitor_pid': os.getpid(),
    'start_time': datetime.now(timezone.utc).isoformat(), 'outcome': 'monitoring',
    'sample_interval_seconds': .5, 'reserve_bytes': 5_000_000_000,
    'minimum_free_bytes': shutil.disk_usage(ROOT).free, 'peak_tree_rss_bytes': 0,
    'sampling_scope': 'Separate interpreter; supplemental interval only, not a replacement for the complete-attempt monitor.',
    'reason': 'Observed delayed in-process snapshots during metadata processing; preserve that sampling limitation.'}
try:
    while True:
        wait_result = kernel.WaitForSingleObject(ctypes.c_void_p(handle), 0)
        if wait_result == 0:
            state['outcome'] = 'target_exited'
            break
        if wait_result != 258:
            raise OSError('Unable to verify original process lifetime')
        free = shutil.disk_usage(ROOT).free
        owned = helpers.children()
        state.update(free_bytes=free, updated_at=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=time.perf_counter()-started,
            minimum_free_bytes=min(state['minimum_free_bytes'], free),
            peak_tree_rss_bytes=max(state['peak_tree_rss_bytes'], sum(rss(pid) for pid in owned)))
        helpers.write(destination / 'live.json', state)
        if free < state['reserve_bytes']:
            state['outcome'] = 'reserve_stopped'
            # Restore only this module's real os binding so the existing kill helper
            # excludes the monitor itself, rather than excluding the target process.
            helpers.os = os
            helpers.terminate_owned(owned)
            break
        time.sleep(.5)
except BaseException as error:
    state.update(outcome='monitor_failed', error=repr(error))
    # The independent monitor cannot silently disappear while relied upon.
    helpers.os = os
    helpers.terminate_owned(owned if 'owned' in globals() else {target})
    raise
finally:
    kernel.CloseHandle(ctypes.c_void_p(handle))
    state['end_time'] = datetime.now(timezone.utc).isoformat()
    helpers.write(destination / 'result.json', state)
    print(json.dumps(state), flush=True)
