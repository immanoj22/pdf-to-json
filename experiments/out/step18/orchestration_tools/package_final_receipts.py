"""Add late receipts/helpers without replacing existing evidence copies."""
import datetime,json,shutil
from pathlib import Path
from evaluation_routes import BASE,EVIDENCE,ROOT,sha,write_new

def main():
    assert (EVIDENCE/'measurement_evidence/final_verification_v1.json').exists()
    additions=[]
    for p in sorted((BASE/'evaluation_jobs').rglob('*')):
        if not p.is_file() or p.name=='live.json':continue
        t=EVIDENCE/'measurement_evidence'/p.relative_to(BASE)
        if t.exists():continue
        t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,t)
        additions.append({'path':t.relative_to(ROOT).as_posix(),'bytes':t.stat().st_size,'sha256':sha(t)})
    for p in sorted((BASE/'retry_preparation').glob('attempt1_unchanged_*.json')):
        t=EVIDENCE/'measurement_evidence'/p.relative_to(BASE)
        if t.exists():continue
        shutil.copyfile(p,t);additions.append({'path':t.relative_to(ROOT).as_posix(),'bytes':t.stat().st_size,'sha256':sha(t)})
    for p in sorted(BASE.glob('*.py')):
        t=EVIDENCE/'orchestration_tools'/p.name
        if t.exists():
            assert sha(t)==sha(p),p
            continue
        shutil.copyfile(p,t);additions.append({'path':t.relative_to(ROOT).as_posix(),'bytes':t.stat().st_size,'sha256':sha(t)})
    write_new(EVIDENCE/'measurement_evidence/copy_manifest_v2_additions.json',{'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'added':additions,'existing_files_replaced':0,'images_copied':0,'note':'Final packaging guard receipt remains local until its process finishes.'})
    ledger=ROOT/'experiments/holdout_runs.jsonl'
    rows=[json.loads(x) for x in ledger.read_text('utf8').splitlines()]
    assert not any(r['record_type']=='measurement_finished' for r in rows)
    event={'schema_version':1,'record_type':'measurement_finished','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'commit_hash':'8d6a0b0036db3f28dd8b671a2950ceca9918a680','freeze_tag':'holdout-freeze-1',
      'books':{'ent_textbook':{'outcome':'completed','missing':0,'extra':10,'I7':42},'math_holdout':{'outcome':'failed','failure_class':'code','stage':'layout.build_layout.PageLayout.validation','physical_page':348},'mideast':{'outcome':'completed','missing':0,'extra':0,'I1_I7_all_zero':True}},
      'report_path':'docs/step18_report.md','report_sha256':sha(ROOT/'docs/step18_report.md'),'results_path':'experiments/out/step18/results_v2.json','results_sha256':sha(EVIDENCE/'results_v2.json'),
      'agent_judgments':559,'owner_audit_selected':20,'owner_audit_status':'pending','agent_judgments_independently_verified':False,'no_converter_fixes':True,'no_more_holdout_runs':True,
      'final_integrity_receipt':'experiments/out/step18/measurement_evidence/final_verification_v1.json'}
    with ledger.open('a',encoding='utf8',newline='\n') as stream:stream.write(json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n')
    print('Late evidence added, ledger appended once; no existing evidence replaced',len(additions),flush=True)

if __name__=='__main__':main()
