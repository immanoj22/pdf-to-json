"""Deferred frozen reference heading scores and published page-label scores."""
import json
from pathlib import Path
from types import SimpleNamespace
from evaluation_routes import BASE, CACHES, EVIDENCE, route, write_new

def main():
    book = 'ent_textbook'
    run, _, keys = route(book)
    import step14a_common as common
    from book_core.structure.evidence import _read
    from book_core.structure.models import BookStructure
    from book_core.objects.analysis import verified_read
    from book_core.evaluation.structure import heading_scores
    from book_core.evaluation.furniture import marker_scores
    mapping = json.loads((EVIDENCE / book / 'alignment_evidence/scope_mapping.json').read_text('utf8'))
    assert mapping['expected_coverage_complete'], 'Review coverage before reference typing scores'
    scope = set(mapping['accuracy_pages'])
    key = keys['structure_evidence']
    evidence = _read(CACHES[book] / 'structure/evidence' / f'{key}.json.gz', key)
    structure = verified_read(CACHES[book] / 'structure/book' / f'{keys["structure"]}.json', BookStructure, keys['structure'])
    unit_tokens = {u['unit']:[(p['page'],o) for o in u['token_ordinals']]
        for p in evidence['pages'] if p['page'] in scope for u in p['units']}
    headings = [h for h in structure.headings if h.page in scope]
    zones = {z.page:z.zone for z in structure.page_zones}
    gold = common.derived_gold(book)
    heading_result = heading_scores(gold, headings, unit_tokens, zones)
    data = json.loads((Path(run['book_json']) / 'book.json').read_text('utf8'))
    markers = [SimpleNamespace(page=p['index'], label=p.get('label'), source=p['label_source']) for p in data['pages']]
    result = {'book_id':book, 'accuracy_pages':sorted(scope), 'headings':heading_result,
        'published_page_labels':marker_scores(gold, markers),
        'scope_note':'Heading metrics use the frozen Step 11 structure-stage evaluator; final JSON heading/footnote/glossary/folio typing is also checked by the separate seeded page census. Page labels here come from published JSON; reference accuracy is confined to mapped reference markers.'}
    write_new(BASE / 'evaluations' / book / 'heading_folio_reference_metrics.json', result)
    print(book, 'frozen heading and published folio reference scores complete', flush=True)

if __name__ == '__main__':
    main()
