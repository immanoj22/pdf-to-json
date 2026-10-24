"""Deferred reporting of an unsuccessful conversion; no accuracy is manufactured."""
import json
from pathlib import Path
import sys
from evaluation_routes import BASE, CACHES, ATTEMPTS, SOURCE_KEYS, finished, write_new


def main(book):
    finished()
    directory = BASE / ATTEMPTS[book]
    attempt = json.loads((directory / 'result.json').read_text('utf8'))
    assert attempt['outcome'] == 'failed'
    reason = 'Conversion failed before a complete archive/publication; no complete-output accuracy or invariant result is available.'
    result = {'book_id': book, 'attempt_id': ATTEMPTS[book], 'metrics': {
        f'M{i:02d}': {'status': 'unmeasured', 'reason': reason}
        for i in range(1, 19)}}
    result['metrics']['M01'] = {'status': 'failed', 'stage': attempt['stage'],
        'last_completed_pages': attempt.get('completed'), 'total_pages': attempt.get('total'),
        'exception_type': attempt.get('exception_type'), 'error': attempt.get('error'),
        'schema_errors': None, 'roundtrip_equal': None, 'contract_violations': None,
        'asset_hash_mismatches': None}
    ocr_path = directory / 'ocr_input.json'
    if ocr_path.exists():
        prepared = json.loads(ocr_path.read_text('utf8'))
        result['metrics']['M14']['preparation_only'] = {
            'replacement_page_keys': sorted(map(int, prepared.get('page_keys', {}))),
            'comparison_page_keys': sorted(map(int, prepared.get('comparison_keys', {}))),
            'output_usage_rates_available': False,
            'note': 'Completed screening/preparation is not a published OCR usage or accuracy result.'}
    from reference_paths import reference_path
    result['metrics']['M18'] = {'status': 'measured_for_failed_attempt',
        'wall_seconds': attempt['elapsed_seconds'],
        'peak_tree_rss_bytes': attempt['peak_tree_rss_bytes'],
        'minimum_free_bytes': attempt['minimum_free_bytes'],
        'end_free_bytes': attempt['free_bytes'],
        'source_bytes': reference_path(SOURCE_KEYS[book]).stat().st_size,
        'partial_cache_bytes': sum(p.stat().st_size for p in CACHES[book].rglob('*') if p.is_file()),
        'archive_bytes': None, 'publication_bytes': None,
        'individual_stage_wall_seconds': None,
        'stage_timing_note': 'The frozen runner did not return its per-stage result after the exception. Preserve event observations separately; do not invent stage timings.'}
    events = directory / 'stage_events.jsonl'
    if events.exists():
        result['stage_observations_not_exact_stage_timings'] = [json.loads(s) for s in events.read_text('utf8').splitlines()]
    classification = BASE / (ATTEMPTS[book] + '_failure_classification.json')
    if classification.exists():
        result['failure_classification'] = json.loads(classification.read_text('utf8'))
    write_new(BASE / 'evaluations' / book / 'failed_book_metrics.json', result)
    print(book, 'all M01-M18 retained; unsuccessful-conversion limitations recorded', flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
