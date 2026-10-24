"""Deferred frozen chosen-path MathML scores and boundary/coverage counts."""
import json
from collections import Counter, defaultdict
from evaluation_routes import BASE, CACHES, EVIDENCE, route, write_new

def main():
    book = 'math_holdout'
    run, _, keys = route(book)
    import step14a_common as common
    import step13c_dev as frozen
    from step13_boundaries import classify
    from book_core.mathml.cache import load_page
    frozen.GOLD = EVIDENCE / book / 'alignment_evidence/math'
    rows, _ = frozen.gold()
    regions_by_page, records = {}, {}
    for number in range(1, run['pages'] + 1):
        regions_by_page[number] = common.equation_page(book, number).regions
        page = load_page(CACHES[book], keys['mathml'], number)
        records.update({r.equation_id:r for r in page.equations})
    values = frozen.evaluate(regions_by_page, records, range(1, run['pages'] + 1))
    located = defaultdict(list)
    for row in rows:
        if row['status'] == 'located':
            located[row['page']].append(row)
    boundary_counts = Counter()
    boundary_rows = []
    for number, page_rows in located.items():
        all_objects = {o for row in page_rows for o in row['object_ids']}
        for row in page_rows:
            if not row['verified']:
                continue
            label, used = classify(row, regions_by_page.get(number, []), all_objects - set(row['object_ids']))
            boundary_counts[label] += 1
            boundary_rows.append({'slot':row['slot'], 'page':number, 'presentation':row['presentation'],
                'classification':label, 'region_ids':[r.id for r in used],
                'reference_bbox':row['bbox'], 'reference_text':row['leaf_text']})
    result = {'book_id':book, 'reference_equations':len(rows),
        'reference_by_status':dict(Counter(r['status'] for r in rows)),
        'located':sum(r['status']=='located' for r in rows),
        'automatically_geometry_eligible_located':len(boundary_rows),
        'located_not_geometry_eligible':sum(r['status']=='located' and not r['verified'] for r in rows),
        'boundary_counts':dict(boundary_counts), 'boundary_rows':boundary_rows,
        'output_regions':sum(map(len, regions_by_page.values())),
        'frozen_mathml_scores':values,
        'coverage_note':'All scores are conditional on frozen reference location and automatic glyph_count_fits eligibility. The verified field does not mean human or independent verification.',
        'human_approved':False, 'alternative_model_run':False}
    write_new(BASE / 'evaluations/math_holdout/math_reference_metrics.json', result)
    print('math_holdout frozen MathML scores complete', flush=True)

if __name__ == '__main__':
    main()
