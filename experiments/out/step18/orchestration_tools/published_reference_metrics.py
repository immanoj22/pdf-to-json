"""Deferred published-JSON scoring using frozen Step 17 and table evaluators."""
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from evaluation_routes import BASE, EVIDENCE, route, write_new

def main(book):
    run, capture, keys = route(book)
    import step14a_common as common
    import step17_json_eval as frozen
    import step14b_dev as tables
    from book_core.cache_store import read_json
    from book_core.evaluation import table_scoring
    archive = Path(run['output'])
    data = json.loads((Path(run['book_json']) / 'book.json').read_text('utf8'))
    lines, spans, units = frozen.json_view(data)
    owner, views = frozen.owners_of(book, lines, spans, run['pages'])
    result = {'book_id': book,
        'main_flow_order_vs_archive': frozen.order_agreement(book, owner, data, archive),
        'scope_note': 'Reference accuracy uses only the registered supported scope; internal agreement is separate.'}
    if book == 'ent_textbook':
        mapping = json.loads((EVIDENCE / book / 'alignment_evidence/scope_mapping.json').read_text('utf8'))
        assert mapping['expected_coverage_complete'], 'Review registration coverage before scoring'
        scope = set(mapping['accuracy_pages'])
        scoped_owner = {k:v for k,v in owner.items() if k[0] in scope}
        scoped_views = {p:v for p,v in views.items() if p in scope}
        result.update(paragraphs=frozen.paragraphs(book, scoped_owner, data),
            lists=frozen.lists(book, scoped_owner, units, data, scoped_views),
            reading_order=frozen.reading_order(book, scoped_owner, data, scoped_views))
    elif book == 'math_holdout':
        scope = set(range(1, run['pages'] + 1))
        result['non_math_reference_accuracy'] = {'status': 'unmeasured',
            'reason': 'CNXML is not registered paragraph, list, heading, order or style truth'}
    else:
        scope = set()
        result['reference_accuracy'] = {'status': 'unmeasured', 'reason': 'No matching reference registered'}
    if book in {'ent_textbook', 'math_holdout'}:
        grids = {}
        table_nodes = [node for top in data['content'] for node,*_ in frozen.walk(top)
            if node.get('type') == 'table' and node['pages'][0] in scope]
        for table in table_nodes:
            number = table['pages'][0]
            payload = read_json(archive / f'page_{number:06d}.json.gz')
            full_lines = {lid[:16]: lid for lid in payload['line_spans']}
            source_spans = payload['source']['store']['spans']
            full_spans = {sid[:16]: sid for sid in source_spans}
            span_text = {sid:s['raw_text'] for sid,s in source_spans.items()}
            cells = []
            # This is the unchanged JSON-to-record input bridge used in
            # step17_json_eval.joined_tables, including figure-text exclusion.
            for cell in table['cells']:
                line_ids, span_refs = [], []
                for item,*_ in (x for top in cell['content'] for x in frozen.walk(top)):
                    if 'refs' not in item or item.get('type') == 'figure_text':
                        continue
                    line_ids.extend(full_lines[prefix] for prefix in item['refs']['lines'] if prefix in full_lines)
                    span_refs.extend(SimpleNamespace(span_id=full_spans[r['span']], start=r['start'], end=r['end'])
                        for r in item['refs'].get('spans', []))
                cells.append(SimpleNamespace(id=cell['id'], row=cell['row'], column=cell['column'],
                    row_span=cell['row_span'], column_span=cell['column_span'], header=cell['role']=='column_header',
                    role=cell['role'], header_cell_ids=cell['headers'], line_ids=line_ids, span_refs=span_refs))
            record = SimpleNamespace(cells=cells, header_rows=table['header_rows'])
            grids[(number, table['id'])] = tables.record_grid(number, record, views[number], span_text, None)
        gold_rows = common.gold_tables(book)
        gold = {key:value for key,value in table_scoring.gold_segments(gold_rows).items() if key[1] in scope}
        result['tables'] = table_scoring.score(gold, grids)
        details = []
        for gkey, okey, count in result['tables']['matches']:
            g, o = gold[tuple(gkey)], grids[tuple(okey)]
            details.append({'gold_key':gkey, 'output_key':okey, 'matched_tokens':count,
                'problems':g['problems'], 'structural_score_excluded':bool(g['problems']),
                'teds':table_scoring.teds(g,o), 'teds_full':table_scoring.teds(g,o,content=True),
                'adjacency_counts':table_scoring.adjacency(g,o),
                'header_token_counts':table_scoring.header_tokens(g,o),
                'header_association_counts':table_scoring.header_association(g,o)})
        result['tables']['matched_detail'] = details
        result['tables']['reference_rows'] = len(gold_rows)
        result['tables']['reference_problems'] = [{'table':r['table'], 'problems':r['problems']} for r in gold_rows if r['problems']]
        result['joined_tables'] = frozen.joined_tables(book, data, views, archive)
    write_new(BASE / 'evaluations' / book / 'published_reference_metrics.json', result)
    print(book, 'registered published reference metrics complete', flush=True)

if __name__ == '__main__':
    main(sys.argv[1])
