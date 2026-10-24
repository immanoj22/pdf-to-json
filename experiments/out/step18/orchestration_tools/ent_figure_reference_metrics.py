"""Deferred ENT figure-stage reference scores, through the frozen Step 12 evaluator."""
import ast
import hashlib
import inspect
import json
from collections import Counter
from pathlib import Path
from evaluation_routes import BASE, CACHES, EVIDENCE, route, write_new

def main():
    book = 'ent_textbook'
    run, _, keys = route(book)
    import step7_layouts
    import step14a_common as common
    import step12_reference as reference
    import step12_evaluate as frozen
    from book_core.evaluation.derived_harness import DerivedGold
    target = EVIDENCE / book / 'alignment_evidence'
    mapping = json.loads((target / 'scope_mapping.json').read_text('utf8'))
    assert mapping['expected_coverage_complete'], 'Review reference registration before figure scoring'
    scope = set(mapping['accuracy_pages'])
    class DerivedRoot:
        def __truediv__(self, name):
            assert name == book
            return target / 'derived'
    reference.GOLD = DerivedRoot()
    reference.XML_KEYS = {book:'ent_textbook_xml'}
    step7_layouts.CACHE = CACHES[book]
    gold = DerivedGold.load(target / 'derived')
    def pages():
        for number in sorted(scope):
            yield common.text_page(book, number), common.layout_page(book, number), common.list_page(book, number)
    frozen.load = lambda name: (gold, pages, None, None)
    result = frozen.evaluate(book, keys['figures'])
    # Execute the exact existing nested count scorer; its model-support variants
    # are outside this registry and are neither executed nor selected by results.
    import step12_model_evidence as count_source
    from book_core.cache_store import read_json
    source = inspect.getsource(count_source.figure_variants)
    tree = ast.parse(source)
    score_node = next(n for n in tree.body[0].body if isinstance(n, ast.FunctionDef) and n.name == 'score')
    _, ref_pages, _ = frozen.reference_view(book)
    ref_labels = Counter()
    for figure in reference.inventory(book)['figures']:
        for name in figure['images']:
            parsed = frozen.file_label(name)
            if parsed:
                ref_labels[parsed[0].casefold()] += 1
    markers = read_json(Path(run['output']) / 'book.json.gz')['furniture']['markers']
    labels = {m['page']:m['label'] for m in markers}
    counts = {p:len(common.figure_page(book,p).figures) for p in sorted(scope)}
    environment = {'Counter':Counter, 'ref_pages':ref_pages, 'ref_labels':ref_labels, 'labels':labels}
    exec(compile(ast.Module(body=[score_node], type_ignores=[]), '<unchanged frozen figure_variants.score>', 'exec'), environment)
    result['fixed_page_and_printed_label_counts'] = environment['score'](counts)
    result['printed_label_score_provenance'] = {
        'function':'step12_model_evidence.figure_variants.score',
        'unchanged_body_sha256':hashlib.sha256(ast.dump(score_node, include_attributes=False).encode()).hexdigest(),
        'reference_label_counts':dict(ref_labels), 'output_page_counts':counts,
        'output_printed_labels':{p:labels.get(p) for p in counts},
        'note':'Exact frozen nested scorer, with the registered figure-stage records as inputs; no model-support variants run.'}
    result['accuracy_pages'] = sorted(scope)
    result['scope_note'] = 'Frozen Step 12 figure-stage scoring on the 46 mapped reference pages. Page-count metrics are proxies; final JSON exported/converted counts are separate.'
    write_new(BASE / 'evaluations' / book / 'figure_reference_metrics.json', result)
    print(book, 'frozen figure reference scores complete', flush=True)

if __name__ == '__main__':
    main()
