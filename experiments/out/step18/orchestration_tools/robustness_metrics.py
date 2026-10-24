"""Deferred M01-M03 and descriptive evidence using frozen evaluators, no conversion."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '.cache/step18_part2'
sys.path[:0] = [str(ROOT / 'backend/src'), str(ROOT / 'experiments')]
BOOK = sys.argv[1]
ATTEMPTS = {'ent_textbook': 'ent_textbook_attempt2', 'math_holdout': 'math_holdout_attempt1', 'mideast': 'mideast_attempt1'}
CACHES = {'ent_textbook': ROOT / '.cache/h18/e2', 'math_holdout': Path('C:/h/m'), 'mideast': Path('C:/h/d')}
assert all((BASE / a / 'result.json').exists() for a in ATTEMPTS.values()), 'All conversions must finish first'

from book_core.assembly import validate
from book_core.assembly.build import content_hash
from book_core.assembly.cache import _verify
from book_core.assembly.schema import Book, iter_units
from book_core.cache_store import read_json
import step13_run
import step17_contract_check
import step17_json_eval
import step17_lossless

OUT = BASE / 'evaluations' / BOOK
OUT.mkdir(parents=True, exist_ok=True)
def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=1, ensure_ascii=False); stream.write('\n')
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def size(path):
    return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file())

attempt = json.loads((BASE / ATTEMPTS[BOOK] / 'result.json').read_text())
if attempt['outcome'] != 'completed':
    write(OUT / 'robustness.json', {'attempt': attempt, 'M01': {'completion': 'failed'},
          'M02': {'status': 'unmeasured', 'reason': 'no complete published output'},
          'M03': {'status': 'unmeasured', 'reason': 'no complete published output'}})
    raise SystemExit(0)
performance = json.loads((BASE / ATTEMPTS[BOOK] / 'performance.json').read_text())
run = performance['run']
archive, published = Path(run['output']), Path(run['book_json'])
data = json.loads((published / 'book.json').read_text(encoding='utf8'))
model = Book.model_validate(data)
manifest = json.loads((published / 'manifest.json').read_text())
schema_errors = validate.errors(data)
_verify(published, manifest)
archive_manifest = read_json(archive / 'manifest.json.gz')
archive_mismatches = [name for name, digest in archive_manifest['files'].items() if sha(archive / name) != digest]
contract = step17_contract_check.inspect(model)
lossless = step17_lossless.check(published / 'book.json', archive)
write(OUT / 'inputs/performance' / f'{BOOK}.json', performance)
step13_run.OUT = OUT
step13_run.MATH_BOOK = BOOK
step13_run.CACHE = CACHES[BOOK]
step13_run.CACHE11 = CACHES[BOOK]
step13_run.proof_math_book('inputs')
proof = json.loads((OUT / 'inputs/after' / f'{BOOK}_full_gates.json').read_text())
units = list(iter_units(model.content))
review = (data.get('review') or {}).get('items', [])
nodes = [node for top in data['content'] for node, *_ in step17_json_eval.walk(top)]
texts = [n['content'] for n in nodes if isinstance(n.get('content'), dict)]
texts += [f['content'] for f in data.get('furniture') or []]
direction = Counter(t.get('direction') or 'unknown' for t in texts)
script = Counter(t.get('script') or 'unknown' for t in texts)
language = Counter(t.get('language') or 'inherits_book_or_unknown' for t in texts)
result = {
 'book_id': BOOK, 'attempt': attempt,
 'M01': {'completion': 'completed', 'schema_errors': schema_errors, 'contract': contract,
         'roundtrip_equal': json.loads(model.model_dump_json(by_alias=True)) == data,
         'manifest_mismatches': [], 'archive_manifest_mismatches': archive_mismatches,
         'content_hash_equal': content_hash(data) == data['metadata']['content_sha256'],
         'pages': run['pages'], 'book_sha256': sha(published / 'book.json')},
 'M02': lossless,
 'M03': {'invariant_totals': proof['invariant_totals'], 'pages_checked': len(proof['ownership']),
         'all_units_once': all(x['units_once'] for x in proof['ownership'].values()),
         'all_ordered_once': all(x['ordered_once'] for x in proof['ownership'].values()),
         'proof_path': str(OUT / 'inputs/after' / f'{BOOK}_full_gates.json')},
 'M10_descriptive': {'figure_nodes': sum(n.get('type') == 'figure' for n in nodes),
          'assets_by_kind': dict(Counter(a['kind'] for a in data['assets'])), 'assembly_counts': run.get('assembly', {}).get('counts')},
 'M14_descriptive': {'pages_by_source': dict(Counter(p['source'] for p in data['pages'])),
          'ocr_inputs': {k: v for k,v in performance['ocr'].items() if k != 'directory'},
          'CER': 'unmeasured: no independent transcript registered', 'WER': 'unmeasured: no independent transcript registered'},
 'M15_descriptive': {'book_languages': data['metadata']['languages'], 'text_records': len(texts),
          'directions_including_unknown': dict(direction), 'scripts_including_unknown': dict(script),
          'text_language_labels': dict(language), 'note': 'Counts describe emitted records; inherited/missing values are not inferred truth.'},
 'M17_workload': {'items': len(review), 'items_per_page': len(review) / run['pages'],
          'by_kind': dict(Counter(r['kind'] for r in review)), 'by_severity': dict(Counter(r['severity'] for r in review)),
          'by_kind_severity': dict(Counter(r['kind'] + ':' + r['severity'] for r in review)),
          'distinct_target_units': len({r['unit'] for r in review if r.get('unit')}),
          'content_units': len(units), 'items_per_1000_content_units': 1000 * len(review) / len(units) if units else None,
          'accuracy_note': 'Recall and correctness require the separately registered judgment audit.'},
 'M18': {'attempt_elapsed_seconds': attempt['elapsed_seconds'], 'peak_tree_rss_bytes': attempt['peak_tree_rss_bytes'],
          'minimum_free_bytes': attempt['minimum_free_bytes'], 'cache_bytes': size(CACHES[BOOK]),
          'archive_bytes': size(archive), 'publication_bytes': size(published),
          'stage_measurements': run['stages'], 'timing_note': 'ENT attempt-2 warm stage measurements are labelled; do not treat them as fresh computation.'}
}
write(OUT / 'robustness.json', result)
print(BOOK, 'fresh robustness evidence complete', flush=True)
