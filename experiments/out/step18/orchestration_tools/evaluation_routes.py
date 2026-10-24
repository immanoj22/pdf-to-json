"""Deferred input/output routing for frozen Step 18 evaluation functions."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '.cache/step18_part2'
sys.path[:0] = [str(ROOT / 'backend/src'), str(ROOT / 'experiments')]
ATTEMPTS = {'ent_textbook': 'ent_textbook_attempt2', 'math_holdout': 'math_holdout_attempt1', 'mideast': 'mideast_attempt1'}
CACHES = {'ent_textbook': ROOT / '.cache/h18/e2', 'math_holdout': Path('C:/h/m'), 'mideast': Path('C:/h/d')}
SOURCE_KEYS = {'ent_textbook': 'ent_textbook_pdf', 'math_holdout': 'math_holdout_pdf', 'mideast': 'mideast_pdf'}
EVIDENCE = ROOT / 'experiments/out/step18'

def finished():
    rows = [json.loads((BASE / a / 'result.json').read_text('utf8')) for a in ATTEMPTS.values()]
    assert all(r['outcome'] in {'completed', 'failed'} for r in rows), 'All conversions must finish; an environmental interruption requires owner review'
    return rows

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b''):
            digest.update(chunk)
    return digest.hexdigest()

def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=1, default=str)
        stream.write('\n')

def route(book):
    finished()
    performance = json.loads((BASE / ATTEMPTS[book] / 'performance.json').read_text('utf8'))
    run = performance['run']
    capture = BASE / 'evaluations' / book / 'inputs'
    path = capture / 'performance' / f'{book}.json'
    if path.exists():
        assert json.loads(path.read_text('utf8')) == performance
    else:
        write_new(path, performance)
    from book_core.lists.keys import book_fingerprint
    from book_core.evaluation.derived_harness import DerivedGold
    import step10_run
    import step14a_common as common
    import step17_json_eval as json_eval
    import step17_assemble_dev as assembly_dev
    keys = dict(run['cache_keys'])
    keys.update(_pages=run['pages'], _capture=str(capture))
    keys['lists_fp'] = book_fingerprint(keys['lists']) if isinstance(keys['lists'], dict) else keys['lists']
    original_keys = common.keys
    original_source = common.source
    original_gold = common.derived_gold
    common.CACHE = common.CACHE11 = CACHES[book]
    step10_run.CACHE10 = CACHES[book]
    common.keys = lambda name, capture=None: keys if name == book else original_keys(name, capture)
    from reference_paths import reference_path
    common.source = lambda name: reference_path(SOURCE_KEYS[name]) if name == book else original_source(name)
    common.derived_gold = lambda name: DerivedGold.load(EVIDENCE / name / 'alignment_evidence/derived') if name == book else original_gold(name)
    common.GOLD_TABLES = EVIDENCE / book / 'alignment_evidence/tables'
    json_eval.CAPTURE = capture
    assembly_dev.CACHE = CACHES[book]
    assembly_dev.BOOKS = {**assembly_dev.BOOKS, book: (SOURCE_KEYS[book], 'holdout')}
    return run, capture, keys
