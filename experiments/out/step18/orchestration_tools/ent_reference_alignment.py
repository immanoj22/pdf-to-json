"""Deferred ENT reference registration using frozen algorithms; not a run or a fix."""
import json
from pathlib import Path
from evaluation_routes import BASE, CACHES, EVIDENCE, ROOT, finished, route, sha, write_new

def main():
    finished()
    book = 'ent_textbook'
    run, capture, keys = route(book)
    from reference_paths import reference_path
    from book_core.book_run import CachedTextPages
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.reference.cache import align_cached
    from book_core.reference.dialects import load_dialects
    from book_core.evaluation.derived_gold import write_derived_gold
    from book_core.evaluation.dialect_profiles import profile_digest
    from book_core.settings import Settings
    target = EVIDENCE / book / 'alignment_evidence'
    assert not target.exists(), 'Preserve existing alignment receipts; do not overwrite'
    source = reference_path('ent_textbook_pdf')
    xml = reference_path('ent_textbook_xml')
    template = next(r for r in map(json.loads, (ROOT / 'experiments/holdout_runs.jsonl').read_text('utf8').splitlines()) if r['record_type'] == 'template' and r['book_id'] == book)
    assert sha(source) == template['source_file_sha256']
    native = PyMuPDFExtractor('cpu')
    extractor = CachedTextPages(native, CACHES[book], keys['native'], run['pages'], template['source_file_sha256'])
    dialect_path = Settings().reference_dialects
    dialects = load_dialects(dialect_path)
    # Native object extraction here supplies only the unchanged aligner's figure-text
    # regions. All alignment caches are new Step 18 evidence, never old gold.
    document, pages, result = align_cached(xml, source, extractor, dialects,
        BASE / 'evaluations/ent_textbook/reference_work', object_extractor=native)
    profiles = json.loads(Path(dialect_path).read_text('utf8'))
    entry = next(d for d in profiles['dialects'] if d['name'] == document.dialect.name)
    manifest = write_derived_gold(target / 'derived', book=book, split='holdout',
        notes=['Step 18 partial ENT reference; provisional registration only; human_approved=false',
               'Only mapped reference-covered pages enter accuracy denominators'],
        pdf_sha256=template['source_file_sha256'], extractor=extractor.identity.model_dump(mode='json'),
        doc=document, pages=pages, result=result, dialects_digest=dialects.digest,
        dialect_profile_digest=profile_digest(profiles, document.dialect.name),
        marker_label=entry.get('page_marker_label'))
    markers = json.loads((target / 'derived/page_markers.json').read_text('utf8'))
    eligible = [m for m in markers if m['pdf_page'] is not None and m['located'] and not m['excluded_from_gates']]
    mapped = sorted({m['pdf_page'] for m in eligible})
    mapping = {'book_id': book, 'reference_sha256': document.sha256, 'source_sha256': template['source_file_sha256'],
        'expected_reference_markers': 46, 'markers': markers, 'accuracy_pages': mapped,
        'reference_markers': len(markers), 'located_eligible_markers': len(eligible),
        'unlocated_or_excluded_markers': [m for m in markers if m not in eligible],
        'duplicate_physical_page_markers': len(eligible) - len(mapped),
        'reference_tokens': len(result.xml_page), 'aligned_reference_tokens': sum(p >= 0 for p in result.xml_page),
        'expected_coverage_complete': len(markers) == len(eligible) == len(mapped) == 46,
        'human_approved': False, 'scoring_has_not_started': True,
        'scope_note': 'Freeze this mapping and inspect ambiguities before scoring; never assume physical pages 1-46.'}
    write_new(target / 'scope_mapping.json', mapping)
    write_new(target / 'alignment_payload.json', result.to_payload())
    print(json.dumps({k: v for k,v in mapping.items() if k not in {'markers', 'unlocated_or_excluded_markers'}}, indent=1), flush=True)

if __name__ == '__main__':
    main()
