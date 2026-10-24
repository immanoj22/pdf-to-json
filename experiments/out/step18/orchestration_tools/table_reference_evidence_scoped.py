from ent_scope_bridge import require_scope_review
"""Deferred table input derivation; frozen readers/attachment/scoring rules unchanged."""
import gzip
import json
import sys
from evaluation_routes import BASE, EVIDENCE, route, sha, write_new

def main(book):
    run, _, keys = route(book)
    from reference_paths import reference_path
    from book_core.evaluation import math_gold, table_gold
    from book_core.reference.aligner import AlignmentResult
    from book_core.reference.xml_reader import load_tree
    import step14a_gold as frozen
    if book == 'ent_textbook':
        derived = EVIDENCE / book / 'alignment_evidence/scoped_derived'
        manifest = json.loads((derived / 'manifest.json').read_text('utf8'))
        dialect = manifest['provenance']['dialect']
        data = reference_path('ent_textbook_xml').read_bytes()
        root, repairs = load_tree(data)
        tables = table_gold.read_tables(table_gold.xml_tree(root), table_gold.vocabulary(dialect))
        with gzip.open(derived / 'units.jsonl.gz', 'rt', encoding='utf8') as stream:
            units = [json.loads(line) for line in stream]
        table_gold.attach_units(tables, units)
        assert sha(reference_path('ent_textbook_xml')) == manifest['provenance']['xml_sha256']
        provenance = {'reference_sha256': manifest['provenance']['xml_sha256'],
            'derived_manifest_sha256': sha(derived / 'manifest.json'),
            'derived_units_sha256': sha(derived / 'units.jsonl.gz'),
            'in_memory_repairs': [r.kind for r in repairs]}
    elif book == 'math_holdout':
        root = BASE / 'evaluations/math_holdout/selected_reference'
        reference = math_gold.read_math_reference(root, math_gold.profile_data())
        pattern = f'alignment_{reference.document.sha256[:16]}_{keys["native"][:16]}.json.gz'
        paths = list((BASE / 'evaluations/math_holdout/reference_work').glob(pattern))
        assert len(paths) == 1
        alignment = AlignmentResult.from_payload(json.loads(gzip.decompress(paths[0].read_bytes())))
        dialect = reference.document.dialect.name
        tables = table_gold.read_tables(table_gold.element_tree(reference.document.elements), table_gold.vocabulary(dialect))
        table_gold.attach_alignment(tables, reference.document, alignment, reference.slots)
        provenance = {'reference_sha256': reference.document.sha256,
            'alignment_sha256': sha(paths[0]), 'math_profile_sha256': reference.profile_sha256,
            'reference_commit': '8322d84e2df67cad5ba6616fd306eb22427a50c4'}
    else:
        raise ValueError('No table reference registered for ' + book)
    rows = table_gold.gold_rows(tables)
    frozen.boxes(book, rows)
    target = EVIDENCE / book / 'alignment_evidence/tables' / book
    assert not target.exists(), 'Do not overwrite provisional input evidence'
    frozen.write_gz_jsonl(target / 'tables.jsonl.gz', rows)
    write_new(target / 'manifest.json', {'book': book, 'human_approved': False,
        'status': 'provisional reference-derived table input; no independent visual verification claimed',
        'version': table_gold.TABLE_GOLD_VERSION, 'counts': table_gold.coverage(rows),
        'provenance': {**provenance, 'dialect': dialect, 'native_key': keys['native'],
            'table_profile_sha256': sha(table_gold.PROFILE)},
        'files': {'tables.jsonl.gz': sha(target / 'tables.jsonl.gz')}})
    print(book, table_gold.coverage(rows), flush=True)

if __name__ == '__main__':
    main(sys.argv[1])
