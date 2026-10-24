"""Deferred readable JSON exports; originals and manifest data stay unchanged."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from evaluation_routes import BASE, EVIDENCE, ROOT, ATTEMPTS, finished, route, sha, write_new

def main(book):
    finished()
    attempt = json.loads((BASE / ATTEMPTS[book] / 'result.json').read_text('utf8'))
    target = EVIDENCE / book
    target.mkdir(parents=True, exist_ok=True)
    if attempt['outcome'] != 'completed':
        write_new(target / 'readable_copy_status.json', {'book_id':book,
            'status':'unavailable', 'reason':'No complete published output', 'attempt_id':ATTEMPTS[book]})
        return
    run, _, _ = route(book)
    original = Path(run['book_json'])
    book_data = json.loads((original / 'book.json').read_text('utf8'))
    manifest = json.loads((original / 'manifest.json').read_text('utf8'))
    # The review export is exactly the original book.review field, as in the
    # existing frontend download. It is not represented as a pre-existing file.
    values = {'book.json':book_data, 'manifest.json':manifest,
              'review_list.json':book_data.get('review')}
    receipt = {}
    for name, value in values.items():
        path = target / name
        write_new(path, value)
        assert json.loads(path.read_text('utf8')) == value
        receipt[name] = {'bytes':path.stat().st_size, 'sha256':sha(path),
            'same_parsed_data_as_original':True,
            'original':name if name != 'review_list.json' else 'book.json#/review'}
        if name != 'review_list.json':
            receipt[name]['original_sha256'] = sha(original / name)
    template = next(r for r in map(json.loads, (ROOT / 'experiments/holdout_runs.jsonl').read_text('utf8').splitlines()) if r['record_type']=='template' and r['book_id']==book)
    note = '\n'.join([
        'Step 18 readable evidence copy',
        'Book ID: ' + book,
        'Converter commit: ' + template['commit_hash'],
        'Freeze tag: ' + template['freeze_tag'],
        'Source SHA-256: ' + template['source_file_sha256'],
        'Profile ID: ' + template['profile_id'],
        'Profile canonical SHA-256: ' + template['profile_sha256'],
        'Attempt: ' + ATTEMPTS[book],
        'Run start: ' + attempt['start_time'],
        'Run end: ' + attempt['end_time'],
        'Original publication: ' + original.relative_to(ROOT).as_posix(),
        '',
        'These pretty-printed JSON files parse to the original data.',
        'review_list.json is an exact export of the original book.json review field.',
        'No images or crops have been copied; originals and their hash-named directory are untouched.',
        'The unchanged manifest describes original compact publication bytes and original assets.',
        'Pretty-printing changes byte hashes. Do not use the original manifest to verify these reformatted bytes.',
        'readable_copy_receipt.json records the export hashes and parsed-data equality.',
        'This directory is evidence, not a self-contained publication package.',
        ''
    ])
    with (target / 'README.txt').open('x', encoding='utf8', newline='\n') as stream:
        stream.write(note)
    write_new(target / 'readable_copy_receipt.json', {'book_id':book,
        'exported_at':datetime.now(timezone.utc).isoformat(), 'files':receipt,
        'original_publication_modified':False, 'images_or_crops_copied':False})
    print(book, 'readable JSON exports equal original data', flush=True)

if __name__ == '__main__':
    main(sys.argv[1])
