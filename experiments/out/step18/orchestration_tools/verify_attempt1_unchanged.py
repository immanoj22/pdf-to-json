"""Read-only recheck of the preserved first attempt, writing a separate receipt."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
source = BASE / 'ent_textbook_attempt1'
rows = json.loads((BASE / 'retry_preparation/attempt1_manifest.json').read_text('utf8'))
expected = {r['path']: r for r in rows}
actual = {p.relative_to(source).as_posix(): p for p in source.rglob('*') if p.is_file()}
assert set(actual) == set(expected), 'Attempt 1 inventory changed'
for name, row in expected.items():
    path = actual[name]
    assert path.stat().st_size == row['size'], name
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b''):
            digest.update(chunk)
    assert digest.hexdigest() == row['sha256'], name
stamp = datetime.now(timezone.utc)
receipt = {'observed_at': stamp.isoformat(), 'files_checked': len(rows),
    'bytes_checked': sum(r['size'] for r in rows), 'attempt1_all_files_unchanged': True,
    'method': 'exact inventory, byte size and SHA256 compared with the pre-retry manifest'}
path = BASE / 'retry_preparation' / ('attempt1_unchanged_' + stamp.strftime('%Y%m%dT%H%M%SZ') + '.json')
with path.open('x', encoding='utf8') as stream:
    json.dump(receipt, stream, indent=1)
    stream.write('\n')
print(json.dumps(receipt))
