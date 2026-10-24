"""Read a complete live snapshot and explicitly label page-callback cache reuse."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '.cache/step18_part2'
book = sys.argv[1]
attempt = f"{book}_attempt{2 if book == 'ent_textbook' else 1}"
directory = BASE / attempt
path = directory / ('result.json' if (directory / 'result.json').exists() else 'live.json')
for _ in range(30):
    try:
        row = json.loads(path.read_text('utf8'))
        break
    except (OSError, ValueError):
        time.sleep(.05)
else:
    raise RuntimeError('No complete status snapshot available')
status = {k: row.get(k) for k in ['book_id', 'attempt_id', 'outcome', 'stage', 'completed', 'total',
          'elapsed_seconds', 'peak_tree_rss_bytes', 'free_bytes', 'minimum_free_bytes', 'updated_at']}
stage = row['stage']
reuse = row.get('stage_reuse', {})
phase = {'_page_job': 'native/analysis/layout', '_order_job': 'reading_order'}.get(stage, stage)
if reuse and stage == '_page_job' or phase in reuse:
    interpretation = 'reused from attempt 1; cache validation/use, not fresh computation'
elif stage == 'tables' and reuse:
    interpretation = 'fresh table structure/assembly; detector evidence reused from attempt 1'
else:
    interpretation = 'fresh/recomputed' if row['outcome'] == 'running' else 'see per-stage performance labels'
status.update(stage_interpretation=interpretation, observed_at=datetime.now(timezone.utc).isoformat(),
              source_path=str(path), note='Raw live stage_execution_status may lag page callbacks; this view uses the explicit reuse map.')
(directory / 'status.json').write_text(json.dumps(status, indent=1) + '\n', encoding='utf8')
print(json.dumps(status))
