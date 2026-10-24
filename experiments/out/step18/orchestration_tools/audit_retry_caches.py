"""Read-only audit of attempt 1; evidence is written outside that attempt."""
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
SOURCE = ROOT / '.cache/step18_part2/ent_textbook_attempt1'
OUT = ROOT / '.cache/step18_part2/retry_preparation'
OUT.mkdir(exist_ok=True)
absolute = re.compile(r'^(?:[A-Za-z]:[\\/]|\\\\|/(?!/))')
hits, errors, records, manifest = [], [], Counter(), []

def walk(value, file, field=''):
    if isinstance(value, dict):
        for k, v in value.items():
            walk(k, file, field + '.<key>')
            walk(v, file, field + '.' + k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            walk(v, file, field + f'[{i}]')
    elif isinstance(value, str):
        if absolute.match(value):
            hits.append({'file': file, 'field': field, 'value': value})
        if field.endswith('.payload'):
            walk(json.loads(value), file, field + ':decoded')

for path in sorted(SOURCE.rglob('*')):
    if not path.is_file():
        continue
    data = path.read_bytes()
    name = path.relative_to(SOURCE).as_posix()
    manifest.append({'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    if not name.startswith(('cache/', 'ocr_cache/')) or path.suffix != '.json':
        continue
    try:
        value = json.loads(gzip.decompress(data) if data.startswith(b'\x1f\x8b') else data)
        if isinstance(value, dict) and 'payload' in value and 'sha256' in value:
            assert hashlib.sha256(value['payload'].encode('utf8')).hexdigest() == value['sha256'], 'payload checksum'
        walk(value, name)
        records['/'.join(name.split('/')[:2])] += 1
    except Exception as e:
        errors.append({'file': name, 'error': repr(e)})

report = {'files': len(manifest), 'bytes': sum(x['size'] for x in manifest),
          'records': dict(records), 'absolute_path_hits': hits, 'errors': errors,
          'note': 'Every JSON cache record decoded, including nested model payload; envelope SHA256 verified where present. Binary assets hashed. No source file was written.'}
(OUT / 'attempt1_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
(OUT / 'cache_record_audit.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
print(json.dumps({**report, 'absolute_path_hits': hits[:15]}, indent=2))
