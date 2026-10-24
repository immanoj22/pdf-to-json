"""Record actual source-first page observations before output typing is examined."""
import datetime
import hashlib
import json
from pathlib import Path
import sys
from evaluation_routes import BASE, ROOT, finished

def main():
    finished()
    book, batch_path = sys.argv[1:]
    batch = json.loads(Path(batch_path).read_text('utf8'))
    receipt = json.loads((BASE / 'audit' / book / 'render_receipt.json').read_text('utf8'))
    eligible = {int(t['target_id']) for t in receipt['targets'] if t['family']=='page_census'}
    dest = BASE / 'audit' / book / 'source_census_observations.jsonl'
    old = [json.loads(s) for s in dest.read_text('utf8').splitlines()] if dest.exists() else []
    seen = {r['page'] for r in old}
    for row in batch:
        page = row['page']
        assert page in eligible and page not in seen
        context = (BASE / 'audit' / book / 'context' / f'page_{page:06d}.png').relative_to(ROOT).as_posix()
        assert (ROOT / context).exists()
        row = {**row, 'book_id':book, 'family':'page_census', 'target_id':str(page),
            'source_first':not bool(row.get('prior_output_exposure')), 'output_typing_not_inspected':not bool(row.get('prior_output_exposure')),
            'crop_paths':[context], 'context_paths':[context],
            'context_sha256':hashlib.sha256((ROOT/context).read_bytes()).hexdigest(),
            'viewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'independently_verified':False, 'owner_verdict':None}
        with dest.open('a',encoding='utf8',newline='\n') as stream:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        seen.add(page)
    print(book, 'source-first pages recorded:', [r['page'] for r in batch])

if __name__ == '__main__':
    main()
