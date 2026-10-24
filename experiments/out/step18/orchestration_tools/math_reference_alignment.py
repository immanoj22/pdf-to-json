"""Deferred math-reference derivation with frozen Step 13 algorithms and new routes."""
import json
import shutil
import xml.etree.ElementTree as ET
from evaluation_routes import BASE, CACHES, EVIDENCE, ROOT, finished, route, sha, write_new

def main():
    finished()
    book = 'math_holdout'
    run, _, keys = route(book)
    from reference_paths import reference_path
    import step13_gold as frozen
    source = reference_path('math_holdout_pdf')
    reference_root = reference_path('math_holdout_cnxml')
    # Four collections share the registered repository; the frozen reader takes
    # exactly one. Supply a byte-identical view of the preselected title.
    collection = reference_root / 'collections/algebra-and-trigonometry.collection.xml'
    assert collection.is_file(), 'The preselected sealed collection is missing'
    template = next(r for r in map(json.loads, (ROOT / 'experiments/holdout_runs.jsonl').read_text('utf8').splitlines()) if r['record_type'] == 'template' and r['book_id'] == book)
    assert sha(source) == template['source_file_sha256']
    target = EVIDENCE / book / 'alignment_evidence/math'
    assert not target.exists(), 'Preserve existing derivation evidence'
    view = BASE / 'evaluations/math_holdout/selected_reference'
    assert not view.exists(), 'Preserve an existing input-view receipt'
    (view / 'collections').mkdir(parents=True)
    shutil.copy2(collection, view / 'collections' / collection.name)
    profile = frozen.math_gold.profile_data()
    collection_spec = profile['dialects'][0]['collection']
    tree = ET.parse(collection).getroot()
    modules = [node.get(collection_spec['module_attribute']) for node in tree.iter()
        if node.tag == '{' + collection_spec['namespace'] + '}' + collection_spec['module_element']]
    copied = {'collections/' + collection.name: sha(collection)}
    for module in sorted(set(modules)):
        relative = collection_spec['module_path'].format(module=module)
        original = reference_root / relative
        destination = view / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
        assert sha(original) == sha(destination)
        copied[relative] = sha(destination)
    assert sha(view / 'collections' / collection.name) == sha(collection)
    write_new(view / 'input_view_receipt.json', {'selected_collection': collection.name,
        'source_key': 'math_holdout_cnxml', 'selection': 'sealed Algebra and Trigonometry 1e, not result-dependent',
        'module_count': len(modules), 'files_sha256': copied,
        'source_reference_modified': False, 'reader_algorithm_changed': False})
    frozen.reference_path = lambda key: view if key == 'math_holdout_cnxml' else reference_path(key)
    frozen.MATH_BOOK = book
    frozen.BOOKS = {book: ('math_holdout_pdf', 'holdout')}
    frozen.CNXML = {book: 'math_holdout_cnxml'}
    frozen.CACHE = CACHES[book]
    frozen.GOLD = target
    frozen.WORK = BASE / 'evaluations/math_holdout/reference_work'
    frozen.OUT = BASE / 'evaluations/math_holdout/reference_coverage'
    original_write = frozen.write_json
    def routed_write(path, value):
        if path == target / 'manifest.json':
            value = {**value, 'book': book, 'split': 'holdout',
                'notes': ['Sealed OpenStax Algebra and Trigonometry 1e (CC BY 4.0), Step 18',
                    'CNXML supports math/table reference evidence only; no paragraph, heading, list or style truth',
                    'The verified field is the unchanged automatic geometry-eligibility predicate, not human verification'],
                'provenance': {**value['provenance'],
                    'reference_repository': 'https://github.com/openstax/osbooks-college-algebra-bundle',
                    'reference_commit': '8322d84e2df67cad5ba6616fd306eb22427a50c4'},
                'geometry_eligibility_note': 'rows.verified is glyph_count_fits, not independently verified; human_approved remains false'}
        original_write(path, value)
    frozen.write_json = routed_write
    frozen.main('registered', native_key=keys['native'])
    manifest = json.loads((target / 'manifest.json').read_text('utf8'))
    assert manifest['human_approved'] is False and manifest['book'] == book
    write_new(target.parent / 'math_scope_receipt.json', {'book_id': book,
        'source_sha256': template['source_file_sha256'], 'reference_sha256': manifest['provenance']['reference_sha256'],
        'collection_file': collection.name, 'collection_sha256': sha(collection),
        'reference_commit': '8322d84e2df67cad5ba6616fd306eb22427a50c4',
        'native_key': keys['native'], 'pages': run['pages'], 'counts': manifest['counts'],
        'scope': 'Only located automatically eligible reference equations can enter frozen math scoring; all exclusions and unlocated counts remain visible.',
        'human_approved': False, 'scoring_has_not_started': True})

if __name__ == '__main__':
    main()
