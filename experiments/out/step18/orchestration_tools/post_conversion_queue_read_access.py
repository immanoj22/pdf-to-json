"""Run approved measurement routing only after every conversion is terminal.

Stops after ENT registration, before any reference accuracy scoring, so its
page mapping can be inspected. No conversion, retry or source edit is invoked.
"""
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '.cache/step18_part2'
DEST = BASE / 'post_conversion_queue_v2_read_access'
ATTEMPTS = ['ent_textbook_attempt2', 'math_holdout_attempt1', 'mideast_attempt1']

def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def main():
    DEST.mkdir(exist_ok=False)
    state = {'start_time': stamp(), 'outcome': 'waiting_for_serial_conversions', 'jobs': []}
    def save():
        (DEST / 'live.json').write_text(json.dumps(state, indent=1) + '\n', encoding='utf8')
    save()
    while not all((BASE / a / 'result.json').exists() for a in ATTEMPTS):
        time.sleep(5)
    # Results may be observed during the final write; retry reads, never alter them.
    for _ in range(100):
        try:
            results = [json.loads((BASE / a / 'result.json').read_text('utf8')) for a in ATTEMPTS]
            break
        except json.JSONDecodeError:
            time.sleep(.1)
    else:
        raise RuntimeError('Unable to read terminal conversion receipts')
    if any(r['outcome'] not in {'completed', 'failed'} for r in results):
        state.update(outcome='owner_decision_required', end_time=stamp())
        save()
        return 43
    jobs = [
        ('robustness_ent_v2', 'robustness_metrics.py', ['ent_textbook']),
        ('robustness_mideast_v2', 'robustness_metrics.py', ['mideast']),
        ('failed_math_v2', 'failed_book_metrics.py', ['math_holdout']),
        ('readable_ent_v2', 'write_readable_copies.py', ['ent_textbook']),
        ('readable_math_v2', 'write_readable_copies.py', ['math_holdout']),
        ('readable_mideast_v2', 'write_readable_copies.py', ['mideast']),
        ('ent_alignment_v2', 'ent_reference_alignment.py', []),
    ]
    for label, script, args in jobs:
        state.update(outcome='running', current_job=label)
        row = {'job_id': label, 'script': script, 'arguments': args, 'start_time': stamp()}
        state['jobs'].append(row)
        save()
        with (DEST / (label + '.log')).open('x', encoding='utf8') as stream:
            result = subprocess.run([sys.executable, '-B', '-u', str(BASE / 'evaluation_guard.py'),
                label, str(BASE / script), *args], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        row.update(exit_code=result.returncode, end_time=stamp())
        save()
        if result.returncode:
            state.update(outcome='stopped_after_job_failure', end_time=stamp())
            save()
            return result.returncode
    state.update(outcome='awaiting_ENT_mapping_inspection_before_accuracy_scoring', end_time=stamp())
    save()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
