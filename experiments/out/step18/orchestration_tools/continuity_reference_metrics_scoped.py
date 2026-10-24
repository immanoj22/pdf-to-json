from ent_scope_bridge import require_scope_review
"""Deferred unchanged Step 15 reference continuity measurement and complete error rows."""
from evaluation_routes import BASE, CACHES, EVIDENCE, route, write_new
import json
import sys

def main(book):
    _, capture, _ = route(book)
    import step14a_common as common
    import step15_common as views
    import step15_measure as frozen
    common.MATH_BOOK = 'math_holdout'
    frozen.CACHE9 = CACHES[book]
    views.OUT = BASE / 'evaluations' / book
    if book == 'ent_textbook':
        mapping = json.loads((EVIDENCE / book / 'alignment_evidence/scope_mapping.json').read_text('utf8'))
        require_scope_review(mapping)
    elif book != 'math_holdout':
        raise ValueError('No independent continuity reference registered for ' + book)
    result = frozen.measure(book, capture, 'continuity_reference')
    if book == 'ent_textbook':
        pages, archive = views.book_view(book, str(capture))
        gold = common.derived_gold(book)
        chains = views.chains(pages, archive)
        candidates = frozen.step9_candidates(book, capture)
        dropped = {(d['from_page'],d['to_page']) for d in archive['lists']['book']['dropped_page_joins']}
        # ENT has no registered Spanish-style inferred continuation-pair heuristic.
        write_new(views.OUT / 'continuity_reference/all_link_rows.json', frozen.link_rows(pages, archive, gold, []))
        write_new(views.OUT / 'continuity_reference/all_reference_cross_page_rows.json',
            frozen.unit_rows(book, pages, chains, gold, candidates, dropped))
        write_new(views.OUT / 'continuity_reference/all_column_rows.json', frozen.column_rows(book, pages, gold))
    write_new(views.OUT / 'continuity_reference/scope_note.json', {'book_id':book,
        'note':'Frozen archive continuity scores; links without aligned reference evidence on both endpoints remain unscored. Math prose/list continuity accuracy is unmeasured; only supported table continuation checks run there. Final JSON link diagnostics are separate.',
        'reference_supported':book == 'ent_textbook', 'table_reference_supported':True})

if __name__ == '__main__':
    main(sys.argv[1])
