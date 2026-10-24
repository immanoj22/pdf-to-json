"""Apply the pre-registered marker-page scope to new provisional input copies only.

No aligner, score, matching rule, threshold, original alignment or old gold changes.
All native registration losses/outliers are recorded before reference scores exist.
"""
import copy,datetime,gzip,hashlib,json
from collections import Counter
from pathlib import Path
from evaluation_routes import BASE,EVIDENCE,ROOT,sha,write_new

def main():
    target=EVIDENCE/'ent_textbook/alignment_evidence'
    mapping=json.loads((target/'scope_mapping.json').read_text('utf8'))
    aligned=json.loads((target/'alignment_payload.json').read_text('utf8'))
    scope=set(mapping['accuracy_pages'])
    assert len(scope)==43 and mapping['reference_markers']==46
    assert all(m['segment_tokens']==0 and m['pdf_page'] is None for m in mapping['unlocated_or_excluded_markers'])
    outliers=[i for i,p in enumerate(aligned['xml_page']) if p>=0 and aligned['pages'][p] not in scope]
    by_page=Counter(aligned['pages'][aligned['xml_page'][i]] for i in outliers)
    original=target/'derived';dest=target/'scoped_derived'
    dest.mkdir(exist_ok=False)
    units=[json.loads(s) for s in gzip.decompress((original/'units.jsonl.gz').read_bytes()).decode('utf8').splitlines()]
    excluded=[];scoped=[]
    for u in units:
        v=copy.deepcopy(u)
        outside=[p for p in u['pdf'] if p[0] not in scope]
        if outside:excluded.append({'unit':u.get('id') or u.get('unit') or u.get('path'),'kind':u['kind'],'outside_segments':outside})
        v['pdf']=[p for p in u['pdf'] if p[0] in scope]
        scoped.append(v)
    (dest/'units.jsonl.gz').write_bytes(gzip.compress(('\n'.join(json.dumps(u,ensure_ascii=False) for u in scoped)+'\n').encode('utf8'),mtime=0))
    markers=json.loads((original/'page_markers.json').read_text('utf8'))
    pages=json.loads((original/'pages.json').read_text('utf8'))
    write_new(dest/'page_markers.json',markers)
    write_new(dest/'pages.json',[p for p in pages if p['page'] in scope])
    manifest=json.loads((original/'manifest.json').read_text('utf8'))
    manifest['notes'] += ['Step 18 pre-registered accuracy scope bridge: only the 43 located marker pages; 3 zero-token markers unlocated. Original units/registration retained separately.',
        'Uncovered-page alignment positions removed from this new provisional input copy before any reference scores. No evaluator/normalization/matching rule changed.']
    manifest['files']={name:sha(dest/name) for name in ['units.jsonl.gz','page_markers.json','pages.json']}
    manifest['human_approved']=False
    write_new(dest/'manifest.json',manifest)
    scoped_alignment=copy.deepcopy(aligned)
    for i in outliers:
        scoped_alignment['xml_page'][i]=-1
        scoped_alignment['xml_ordinal'][i]=-1
    write_new(target/'scoped_alignment_payload.json',scoped_alignment)
    receipt={'book_id':'ent_textbook','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'expected_markers':46,'located_marker_pages':43,'unlocated_markers':mapping['unlocated_or_excluded_markers'],
        'accuracy_pages':sorted(scope),'native_reference_tokens':mapping['reference_tokens'],
        'native_aligned_reference_tokens':mapping['aligned_reference_tokens'],
        'outside_scope_aligned_tokens':len(outliers),'outside_scope_tokens_by_page':by_page,
        'scoped_aligned_reference_tokens':sum(p>=0 for p in scoped_alignment['xml_page']),
        'outside_segments_by_unit':excluded,'all_reference_units_retained':len(scoped)==len(units),
        'original_mapping_sha256':sha(target/'scope_mapping.json'),'original_alignment_sha256':sha(target/'alignment_payload.json'),
        'scoped_alignment_sha256':sha(target/'scoped_alignment_payload.json'),
        'original_units_sha256':sha(original/'units.jsonl.gz'),'scoped_units_sha256':sha(dest/'units.jsonl.gz'),
        'reason':'Registered uncovered ENT pages may never enter an accuracy denominator. The native aligner left 3 empty markers unlocated and placed some tokens outside located marker pages. Preserve losses, do not fill pages, retune alignment, or count outside-scope pages.',
        'score_status':'No reference scores computed before this receipt; all later scores conditional on located scope, not complete 46-page accuracy.',
        'algorithm_changes':False,'old_gold_reference_or_original_alignment_edited':False,'human_approved':False}
    write_new(target/'mapping_inspection.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k not in {'outside_segments_by_unit','unlocated_markers'}},indent=1))

def require_scope_review(mapping):
    target=EVIDENCE/'ent_textbook/alignment_evidence'
    review=json.loads((target/'mapping_inspection.json').read_text('utf8'))
    assert sha(target/'scope_mapping.json')==review['original_mapping_sha256']
    assert mapping['accuracy_pages']==review['accuracy_pages']
    from book_core.evaluation.derived_harness import DerivedGold
    import step14a_common as common
    common.derived_gold=lambda name: DerivedGold.load(target/'scoped_derived') if name=='ent_textbook' else (_ for _ in ()).throw(ValueError(name))

if __name__=='__main__':main()
