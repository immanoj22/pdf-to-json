"""Copy audited, path-independent caches; preserve every attempt-1 byte."""
import datetime
import gzip
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path.cwd()
OLD = ROOT / '.cache/step18_part2/ent_textbook_attempt1'
OUT = ROOT / '.cache/step18_part2/retry_preparation'
NEW = ROOT / '.cache/h18/e2'
audit = json.loads((OUT / 'cache_record_audit.json').read_text())
manifest = json.loads((OUT / 'attempt1_manifest.json').read_text())
assert not audit['errors']
assert json.loads((OUT / 'supplemental_gzip_audit.json').read_text())['passed']
storage_hits = [h for h in audit['absolute_path_hits'] if not
                ('.store.spans.' in h['field'] and h['field'].endswith(('.text', '.raw_text')))]
assert all(h['file'].startswith('ocr_cache/') for h in storage_hits)
assert not (OUT / 'reuse_receipt.json').exists(), 'Preparation already completed'
copied, stages = [], {}
for entry in manifest:
    relative = Path(entry['path'])
    if relative.parts[0] != 'cache' or relative.name == '.maintenance.lock':
        continue
    source = OLD / relative
    data = source.read_bytes()
    assert hashlib.sha256(data).hexdigest() == entry['sha256']
    if source.suffix == '.json':
        decoded = gzip.decompress(data) if data.startswith(b'\x1f\x8b') else data
        # Path decisions use decoded records, not regex over escaped JSON: URL schemes
        # and source labels ending in a colon otherwise produce false positives.
        value = json.loads(decoded)
        if 'payload_sha256' in value:
            payload = json.dumps(value['payload'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            assert hashlib.sha256(payload.encode('utf8')).hexdigest() == value['payload_sha256']
    destination = NEW / Path(*relative.parts[1:])
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == entry['sha256']
    else:
        with destination.open('xb') as stream:
            stream.write(data)
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == entry['sha256']
    copied.append({**entry, 'destination': destination.relative_to(ROOT).as_posix()})
    stage = relative.parts[1]
    stages.setdefault(stage, {'files': 0, 'bytes': 0, 'status': 'reused from attempt 1'})
    stages[stage]['files'] += 1
    stages[stage]['bytes'] += len(data)
for entry in manifest:
    assert hashlib.sha256((OLD / entry['path']).read_bytes()).hexdigest() == entry['sha256'], entry['path']
assert sorted(x.relative_to(OLD).as_posix() for x in OLD.rglob('*') if x.is_file()) == sorted(x['path'] for x in manifest)
report = {'record_type': 'cache_reuse_preparation', 'schema_version': 1,
          'time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'book_id': 'ent_textbook', 'attempt_id': 'ent_textbook_attempt2',
          'from_attempt_id': 'ent_textbook_attempt1', 'reason': 'path_length_wrapper_error',
          'failure_class': 'environmental', 'cache_root': NEW.relative_to(ROOT).as_posix(),
          'files_copied': len(copied), 'bytes_copied': sum(x['size'] for x in copied),
          'sha256_verified': True, 'attempt1_all_files_unchanged': True,
          'cache_records_have_no_absolute_storage_paths': True,
          'excluded': ['cache/.maintenance.lock', 'ocr_cache/ (manifest contains an absolute inputs.directory)',
                       'ocr_input.json (regenerated; not reused)'],
          'key_audit': 'Frozen cache keys bind source bytes, producer digests, runtime/device, settings, upstream keys and model identities; storage locations are not inputs. Absolute paths used for process-local source/digest memoization are not persistent keys.',
          'key_source_files': ['extraction/fingerprints.py', 'objects/analysis.py', 'paint/cache.py',
              'layout/pipeline.py', 'reading_order/cache.py', 'document_analysis/metadata.py',
              'furniture/cache.py', 'paragraphs/keys.py', 'structure/keys.py', 'lists/keys.py',
              'characters/cache.py', 'figures/cache.py', 'equations/cache.py', 'mathml/cache.py',
              'detection/cache.py', 'cache_identity.py'],
          'stages': stages,
          'timing_note': 'Original elapsed/peak measurements remain unchanged. Retry stage durations measure warm-cache validation/use, not fresh stage computation. Table assembly, continuity and publication are not completed attempt-1 stages.'}
(OUT / 'copy_manifest.json').write_text(json.dumps(copied, indent=2) + '\n', encoding='utf8')
(OUT / 'reuse_receipt.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
with (ROOT / 'experiments/holdout_runs.jsonl').open('a', encoding='utf8', newline='\n') as stream:
    stream.write(json.dumps(report) + '\n'); stream.flush(); os.fsync(stream.fileno())
print(json.dumps(report, indent=2))
