"""Source view of the single failed conversion, not a rerun or accuracy score."""
import json
from evaluation_routes import BASE, ROOT, finished, sha, write_new
from fixed_sampling import select

def main():
    finished()
    failure = json.loads((BASE / 'math_holdout_attempt1_failure_classification.json').read_text('utf8'))
    print('classification keys:', list(failure), flush=True)
    page = failure.get('failing_page') or failure.get('failing_physical_page')
    if page is None:
        raise ValueError('Failure receipt does not expose its physical page; preserve receipt for routing review')
    uid = 'math_holdout_attempt1:layout:page:' + str(page) + ':duplicate_region_id'
    sample = select('math_holdout', 'taxonomy:M01', {uid: {
        'page': page, 'attempt_id': 'math_holdout_attempt1',
        'classification_receipt': 'math_holdout_attempt1_failure_classification.json',
        'reason': 'The one observed converter failure; all errors retained, no redraw.'}})
    from reference_paths import reference_path
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    source = reference_path('math_holdout_pdf')
    raster = PyMuPDFExtractor('cpu').render_page(source, page, dpi=160)
    target = BASE / 'audit/math_holdout/failure/context' / f'page_{page:06d}.png'
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raster.png)
    image_path = target.relative_to(ROOT).as_posix()
    write_new(BASE / 'audit/math_holdout/failure_render_receipt.json', {
        'book_id': 'math_holdout', 'family': 'taxonomy:M01', 'target_id': uid,
        'source_sha256': sha(source), 'page': page, 'crop_paths': [image_path],
        'context_paths': [image_path], 'image_sha256': sha(target),
        'render_method': 'Original PDF through frozen PyMuPDFExtractor.render_page, 160 dpi',
        'agent_verdict': None, 'independently_verified': False,
        'scope': 'Single code-failure source-page diagnostic, not a successful conversion or mathematical accuracy score.'})
    print(image_path, flush=True)

if __name__ == '__main__':
    main()
