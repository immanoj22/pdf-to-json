"""The registered sampling/audit protocol; no judgments are generated automatically."""
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '.cache/step18_part2'
SEED = '20261024:step18:v1'

def require_conversions_finished():
    attempts = ['ent_textbook_attempt2', 'math_holdout_attempt1', 'mideast_attempt1']
    assert all((BASE / a / 'result.json').exists() for a in attempts), 'All conversions must finish before scoring/sampling'
    assert all(json.loads((BASE / a / 'result.json').read_text())['outcome'] in {'completed', 'failed'} for a in attempts), 'Environmental interruption needs owner decision'

def select(book, family, population, n=20):
    """population is {stable_item_id: evidence}; persist before rendering/judging."""
    require_conversions_finished()
    assert all(isinstance(k, str) for k in population)
    ranked = sorted(population, key=lambda uid: (hashlib.sha256(
        f'{SEED}:{book}:{family}:{uid}'.encode('utf8')).hexdigest(), uid))
    chosen = ranked[:min(n, len(ranked))]
    record = {'book_id': book, 'family': family, 'seed_namespace': SEED,
              'selection_rule': 'SHA256(namespace:book_id:family:stable_item_id), tie stable ID; no redraw',
              'population_ids': sorted(population), 'population_size': len(population),
              'selected_ids': chosen, 'selected': [dict(population[uid], target_id=uid) for uid in chosen]}
    path = BASE / 'samples' / book / (hashlib.sha256(family.encode('utf8')).hexdigest()[:20] + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(record, stream, indent=1, ensure_ascii=False); stream.write('\n')
    return record

def append_judgment(record):
    require_conversions_finished()
    required = {'judgment_id', 'book_id', 'family', 'target_id', 'crop_paths', 'context_paths',
                'agent_verdict', 'notes', 'viewed_at'}
    assert required <= record.keys()
    assert record['crop_paths'] and record['context_paths']
    assert all((ROOT / path).is_file() for path in [*record['crop_paths'], *record['context_paths']])
    destination = BASE / 'audit/judgments.jsonl'
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing = [json.loads(line) for line in destination.read_text('utf8').splitlines()] if destination.exists() else []
    assert not any(row['judgment_id'] == record['judgment_id'] for row in existing)
    record = {**record, 'independently_verified': False, 'owner_verdict': None,
              'crop_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                              for path in [*record['crop_paths'], *record['context_paths']]}}
    with destination.open('a', encoding='utf8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')

def select_owner_audit():
    require_conversions_finished()
    rows = [json.loads(line) for line in (BASE / 'audit/judgments.jsonl').read_text('utf8').splitlines()]
    rows.sort(key=lambda r: r['judgment_id'])
    assert len({r['judgment_id'] for r in rows}) == len(rows)
    chosen = random.Random('20261024:step18:v1:audit').sample(rows, min(20, len(rows)))
    record = {'seed': '20261024:step18:v1:audit', 'population_size': len(rows),
              'population_ids': [r['judgment_id'] for r in rows],
              'selected_ids': [r['judgment_id'] for r in chosen], 'selected': chosen,
              'status': 'awaiting owner re-judgment', 'agent_judgments_independently_verified': False}
    with (BASE / 'audit/owner_audit_selection.json').open('x', encoding='utf8') as stream:
        json.dump(record, stream, indent=1, ensure_ascii=False); stream.write('\n')
    return record
