"""Deferred unchanged Step 17 reference-style evaluator, with a publication parity check."""
from collections import Counter
import gzip
import json
from pathlib import Path
import sys
from evaluation_routes import BASE, EVIDENCE, route, write_new

def main():
    book = 'ent_textbook'
    run, capture, _ = route(book)
    import step17_styling_eval as frozen
    from prepare_visual_populations import texts
    scope = json.loads((EVIDENCE / book / 'alignment_evidence/scope_mapping.json').read_text('utf8'))
    assert scope['expected_coverage_complete'], 'Review reference scope before style scoring'
    alignment = json.loads((EVIDENCE / book / 'alignment_evidence/alignment_payload.json').read_text('utf8'))
    aligned_pages = {alignment['pages'][p] for p in alignment['xml_page'] if p >= 0}
    assert aligned_pages <= set(scope['accuracy_pages']), 'Aligned style evidence extends beyond registered covered pages'
    frozen.XML = {book:'ent_textbook_xml'}
    frozen.CAPTURE = capture
    frozen.OUT = BASE / 'evaluations/ent_textbook/reference_styles'
    assert not frozen.OUT.exists(), 'Preserve existing style evaluation evidence'
    def supplied_alignment(xml_sha):
        assert alignment['xml_sha256'] == xml_sha
        return alignment
    frozen.alignment = supplied_alignment
    prior = sys.argv
    sys.argv = [str(frozen.__file__), '--book', book]
    try:
        frozen.main()
    finally:
        sys.argv = prior
    with gzip.open(frozen.OUT / f'{book}_spans.json.gz', 'rt', encoding='utf8') as stream:
        samples = json.load(stream)
    data = json.loads((Path(run['book_json']) / 'book.json').read_text('utf8'))
    emitted = Counter()
    for content, _, pages, _, _ in texts({'content':data['content'], 'furniture':data.get('furniture') or []}):
        if not pages:
            pages = sorted({r['page'] for r in content.get('source_runs', [])})
        for span in content['spans']:
            if span['kind'] in {'math','run_in_heading'}:
                continue  # unchanged frozen reference evaluator exclusions, retained in the visual audit
            emitted[(pages[0],span['kind'],content['text'][span['start']:span['end']])] += 1
    recorded = Counter((s['page'],s['kind'],s['text']) for s in samples)
    write_new(frozen.OUT / 'publication_span_parity.json', {'book_id':book,
        'publication_style_population_equal':recorded == emitted,
        'recorded_spans':sum(recorded.values()), 'published_spans':sum(emitted.values()),
        'recorded_only_instances':sum((recorded-emitted).values()),
        'published_only_instances':sum((emitted-recorded).values()),
        'scope_note':'Whole-book population parity of the frozen evaluator-supported emitted style kinds. Reference metrics still use only aligned tokens on the 46 registered pages. Math and run-in-heading spans remain in the visual populations.',
        'interpretation':'Reference-style scoring is a measurement limitation if this parity check fails; do not substitute the reassembly for published output silently.'})

if __name__ == '__main__':
    main()
