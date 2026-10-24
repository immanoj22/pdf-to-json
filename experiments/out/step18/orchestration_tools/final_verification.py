"""Read-only integrity verification; writes a new close-out receipt/inventory."""
import datetime,hashlib,json,random,re,shutil,subprocess
from pathlib import Path
from evaluation_routes import BASE,EVIDENCE,ROOT,sha,write_new

FREEZE='8d6a0b0036db3f28dd8b671a2950ceca9918a680'
def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf8').strip()
def main():
    assert git('rev-parse','holdout-freeze-1')==FREEZE
    for base in ['holdout-freeze-1','d0625e8','HEAD']:
        assert not git('diff',base,'--','backend'),base
    assert not git('diff','--cached','--','backend')
    assert not git('ls-files','--others','--exclude-standard','backend')
    assert git('rev-parse','HEAD')=='ba8897c05fea63aa903a1b56dd4a72404cde4018'
    assert sha(ROOT/'docs/step18_preregistration.md')=='3bcbe704ff5d3994c61aecb8cc6a451e81c1e4c67a4c72ec23b1d94a5f64610b'
    addendum_bytes=subprocess.check_output(['git','show','HEAD:docs/step18_preregistration_addendum.md'],cwd=ROOT)
    assert (ROOT/'docs/step18_preregistration_addendum.md').read_bytes()==addendum_bytes
    profile=ROOT/'backend/src/book_core/assembly/profiles/default.toml'
    assert sha(profile)=='85b4d469b6322fcfa086a4a112306c539ea9903fe700c81fda37d26cc200ce2a'
    templates=[r for r in map(json.loads,(ROOT/'experiments/holdout_runs.jsonl').read_text('utf8').splitlines()) if r['record_type']=='template']
    assert len(templates)==3
    from reference_paths import reference_path
    sources=[]
    for t in templates:
        p=reference_path(t['source_key']);digest=sha(p);assert digest==t['source_file_sha256']
        sources.append({'book_id':t['book_id'],'sha256':digest,'bytes':p.stat().st_size})
    copies=[]
    for book,attempt in [('ent_textbook','ent_textbook_attempt2'),('mideast','mideast_attempt1')]:
        perf=json.loads((BASE/attempt/'performance.json').read_text('utf8'));original=Path(perf['run']['book_json'])
        data=json.loads((original/'book.json').read_text('utf8'));target=EVIDENCE/book
        assert json.loads((target/'book.json').read_text('utf8'))==data
        assert json.loads((target/'review_list.json').read_text('utf8'))==data['review']
        assert json.loads((target/'manifest.json').read_text('utf8'))==json.loads((original/'manifest.json').read_text('utf8'))
        receipt=json.loads((target/'readable_copy_receipt.json').read_text('utf8'))
        for name,row in receipt['files'].items():
            assert sha(target/name)==row['sha256']
            if name!='review_list.json':assert sha(original/name)==row['original_sha256']
        copies.append({'book_id':book,'all_three_parsed_equal':True,'original_and_copy_hashes_equal_receipt':True})
    rows=[json.loads(x) for x in (BASE/'audit/judgments.jsonl').read_text('utf8').splitlines()]
    assert len(rows)==559 and len({r['judgment_id'] for r in rows})==559
    images={}
    for r in rows:
        assert r['target_id'] and r['agent_verdict'] and r['crop_paths'] and r['context_paths']
        assert r['independently_verified'] is False and r['owner_verdict'] is None
        for p in set(r['crop_paths']+r['context_paths']):
            assert p in r['crop_sha256'],(r['judgment_id'],p)
        for p,digest in r['crop_sha256'].items():
            assert p not in images or images[p]==digest
            images[p]=digest
    for p,digest in images.items():assert sha(ROOT/p)==digest,p
    owner=json.loads((BASE/'audit/owner_audit_selection.json').read_text('utf8'))
    selected=random.Random('20261024:step18:v1:audit').sample(sorted(r['judgment_id'] for r in rows),20)
    assert owner['selected_ids']==selected and owner['population_size']==559
    result=json.loads((EVIDENCE/'results_v2.json').read_text('utf8'))
    assert all(set(m)=={f'M{i:02}' for i in range(1,19)} for m in result['books'].values())
    report=(ROOT/'docs/step18_report.md').read_text('utf8')
    assert '<!-- GENERATED_' not in report
    broken=[]
    for target in re.findall(r'\]\(([^)]+)\)',report):
        if target.startswith('https://'):continue
        p=(ROOT/'docs'/target.split('#')[0]).resolve()
        if not p.exists():broken.append(str(p))
    assert not broken,broken
    # Verify every originally packaged source receipt/copy; nothing replaced.
    manifest=json.loads((EVIDENCE/'measurement_evidence/copy_manifest_v1.json').read_text('utf8'))
    for row in manifest['copied_verbatim']:
        p=ROOT/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],row['path']
    fs=[p for p in EVIDENCE.rglob('*') if p.is_file()]
    image_files=[p for p in fs if p.suffix.lower() in {'.png','.jpg','.jpeg','.tiff','.webp','.pdf','.djvu'}]
    assert not image_files
    assert all(p.stat().st_size<100*1024**2 for p in fs)
    allowed=('docs/step18_report.md','experiments/holdout_runs.jsonl','experiments/out/step18/')
    status=git('status','--porcelain','--untracked-files=all').splitlines()
    unexpected=[line for line in status if not line[3:].replace('\\','/').startswith(allowed)]
    assert not unexpected,unexpected[:10]
    free=shutil.disk_usage(ROOT).free;assert free>5_000_000_000
    inventory=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(fs)]
    write_new(EVIDENCE/'measurement_evidence/final_inventory_v1.json',{'files':inventory,'file_count':len(fs),'total_bytes':sum(x['bytes'] for x in inventory),'large_files_over_5_MB':[x for x in inventory if x['bytes']>5_000_000],'no_images_or_crops':True,'includes_redundant_attempt1_compressed_cache_evidence':True,'note':'Inventory excludes itself and subsequently added final receipts; no files removed.'})
    proof={'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'freeze_tag':FREEZE,'precommit_HEAD':git('rev-parse','HEAD'),
      'backend_tree':git('rev-parse','HEAD:backend'),'backend_diff_vs_freeze_HEAD_and_d0625e8_empty':True,
      'no_untracked_backend':True,'preregistration_and_addendum_unchanged':True,'profile_file_unchanged':True,
      'sources':sources,'readable_copies':copies,'judgments':len(rows),'unique_crop_context_images_hash_checked':len(images),
      'owner_audit_reproduced':True,'owner_audit_pending':True,'all_18_metrics_each_book':True,'report_local_links_exist':True,
      'copied_evidence_hash_checks':len(manifest['copied_verbatim']),'evidence_image_files':0,'free_bytes':free,
      'unexpected_status_paths':unexpected,'changes_limited_to_authorized_report_results_ledger':True,
      'no_new_tests':'No converter/evaluator implementation changed; accepted Part 0 suite/Ruff/gates remain frozen.',
      'git_status_before_commit_count':len(status)}
    write_new(EVIDENCE/'measurement_evidence/final_verification_v1.json',proof)
    print(json.dumps(proof),flush=True)

if __name__=='__main__':main()
