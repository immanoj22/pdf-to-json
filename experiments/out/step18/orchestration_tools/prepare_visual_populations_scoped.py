from ent_scope_bridge import require_scope_review
"""Deferred registered populations and fixed selections; never creates verdicts."""
import hashlib
import json
from collections import Counter, defaultdict
import sys
from evaluation_routes import BASE, EVIDENCE, finished, route, write_new
from fixed_sampling import select

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

def texts(value, path='$', owner=None, pages=(), contexts=()):
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from texts(item, f'{path}[{index}]', owner, pages, contexts)
    elif isinstance(value, dict):
        if 'type' in value or 'refs' in value:
            owner = value
            contexts = (*contexts, value.get('type', 'furniture' if '.furniture[' in path else 'text_record'))
        pages = tuple(value.get('pages') or ([value['page']] if 'page' in value else pages))
        if isinstance(value.get('text'), str) and isinstance(value.get('spans'), list):
            yield value, owner or {}, pages, contexts, path
            return
        for key, item in value.items():
            yield from texts(item, f'{path}.{key}', owner, pages, contexts)

def main(book):
    finished()
    run, _, _ = route(book)
    data = json.loads((__import__('pathlib').Path(run['book_json']) / 'book.json').read_text('utf8'))
    if book == 'ent_textbook':
        mapping = json.loads((EVIDENCE / book / 'alignment_evidence/scope_mapping.json').read_text('utf8'))
        accuracy_pages = set(mapping['accuracy_pages'])
        require_scope_review(mapping)
    else:
        accuracy_pages = set(range(1, run['pages'] + 1))
    select(book, 'page_census', {str(p): {'page': p} for p in sorted(accuracy_pages)})
    styles = defaultdict(dict)
    style_total = Counter()
    rtl = {}
    seen = set()
    records = []
    for content, owner, pages, contexts, path in texts({'content': data['content'], 'furniture': data.get('furniture') or []}):
        if not pages:
            pages = tuple(sorted({r['page'] for r in content.get('source_runs', [])}))
        identity = owner.get('id') or hashlib.sha256(canonical({'refs': owner.get('refs'), 'path': path, 'text': content['text']}).encode('utf8')).hexdigest()
        entry = {'unit': owner.get('id'), 'text_field_path': path, 'pages': pages,
                 'node_type': owner.get('type', 'furniture' if 'furniture' in path else 'text'),
                 'context': contexts, 'refs': owner.get('refs'), 'owner_boxes': owner.get('boxes') or ([owner['box']] if owner.get('box') else []),
                 'unit_text': content['text'], 'source_runs': content.get('source_runs', [])}
        if content.get('direction') == 'rtl' and pages and set(pages) <= accuracy_pages:
            rtl[identity + ':' + path] = {**entry, 'direction': 'rtl'}
        for span in content['spans']:
            target_pages = sorted({r['page'] for r in content.get('source_runs', []) if r['start'] < span['end'] and r['end'] > span['start']}) or list(pages)
            kinds = ('bold', 'italic') if span['kind'] == 'bold_italic' else (span['kind'],)
            for kind in kinds:
                style_total[kind] += 1
                styles[kind]  # retain kinds with zero eligible spans in ENT's covered scope
            if not target_pages or not set(target_pages) <= accuracy_pages:
                continue
            for kind in kinds:
                uid = f'{identity}:{path}:{kind}:{span["start"]}:{span["end"]}'
                assert uid not in seen
                seen.add(uid)
                styles[kind][uid] = {**entry, 'page': target_pages[0], 'pages': target_pages,
                    'kind': kind, 'emitted_kind': span['kind'], 'start': span['start'], 'end': span['end'],
                    'text': content['text'][span['start']:span['end']], 'span_record': span}
        records.append(entry)
    counts = {}
    for kind, population in sorted(styles.items()):
        selected = select(book, 'style:' + kind, population)
        counts[kind] = {'population': len(population), 'selected': len(selected['selected_ids']),
            'whole_book_population':style_total[kind], 'outside_accuracy_scope':style_total[kind]-len(population)}
    flags = defaultdict(dict)
    flag_totals = Counter()
    for item in (data.get('review') or {}).get('items', []):
        family = 'flag:' + item['kind'] + ':' + item['severity']
        flag_totals[family] += 1
        flags[family]
        if item['page'] in accuracy_pages:
            flags[family][item['id']] = item
    for family, population in sorted(flags.items()):
        select(book, family, population)
    select(book, 'rtl_unit', rtl)
    ocr = json.loads((BASE / ('ent_textbook_attempt2' if book == 'ent_textbook' else book + '_attempt1') / 'ocr_input.json').read_text('utf8'))
    ocr_pages = sorted((set(map(int, ocr.get('page_keys', {}))) | set(map(int, ocr.get('comparison_keys', {})))) & accuracy_pages)
    select(book, 'ocr_page', {str(p): {'page': p} for p in ocr_pages})
    from step17_json_eval import walk
    links = defaultdict(dict)
    link_totals = Counter()
    all_nodes = [node for top in data['content'] for node,*_ in walk(top)]
    node_by_id = {n['id']:n for n in all_nodes if n.get('id')}
    for top in data['content']:
        for node, *_ in walk(top):
            link = node.get('continues_to')
            if link:
                family = 'continuity:' + node['type'] + ':' + link['kind']
                link_totals[family] += 1
                links[family]
                endpoint = node_by_id.get(link['unit'])
                both_pages = set(node.get('pages') or []) | set((endpoint or {}).get('pages') or [])
                if not endpoint or not node.get('pages') or not endpoint.get('pages') or not both_pages <= accuracy_pages:
                    continue
                uid = node['id'] + '->' + link['unit']
                links[family][uid] = {'from_unit': node['id'], 'to_unit': link['unit'],
                    'link': link, 'node_type': node['type'], 'pages': node.get('pages'), 'refs': node.get('refs')}
    for family, population in sorted(links.items()):
        select(book, family, population)
    write_new(BASE / 'samples' / book / 'population_summary.json', {'book_id': book,
        'accuracy_pages': sorted(accuracy_pages), 'style_kinds': counts,
        'review_strata': {k: len(v) for k,v in flags.items()},
        'review_strata_whole_book':dict(flag_totals),
        'continuity_strata': {k: len(v) for k,v in links.items()},
        'continuity_strata_whole_book':dict(link_totals),
        'ocr_eligible_pages': ocr_pages, 'rtl_units': len(rtl), 'text_records': len(records),
        'judgments_performed': 0, 'note': 'Fixed selections saved before any crop judgments. ENT quality judgments use only its covered pages (both endpoints for continuity); uncovered counts remain workload/robustness only. Zero-eligible kinds/strata stay visible. Mideast findings are descriptive only.'})
    print(book, 'registered populations saved; no judgments performed', flush=True)

if __name__ == '__main__':
    main(sys.argv[1])
