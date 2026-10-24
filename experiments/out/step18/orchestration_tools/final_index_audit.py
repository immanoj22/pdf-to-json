"""Verify staged evidence bytes and create the final inventory, no source changes."""
import datetime,hashlib,json,subprocess
from pathlib import Path
from evaluation_routes import EVIDENCE,ROOT,write_new

def main():
    paths=subprocess.check_output(['git','diff','--cached','--name-only','-z'],cwd=ROOT).decode('utf8').split('\0')[:-1]
    assert all(p in {'docs/step18_report.md','experiments/holdout_runs.jsonl'} or p.startswith('experiments/out/step18/') for p in paths)
    index={}
    for row in subprocess.check_output(['git','ls-files','--stage','-z'],cwd=ROOT).split(b'\0'):
        if not row:continue
        meta,name=row.split(b'\t',1);index[name.decode('utf8')]=meta.split()[1].decode()
    manifest=[]
    for name in sorted(paths):
        p=ROOT/name;size=p.stat().st_size
        blob=hashlib.sha1(b'blob '+str(size).encode()+b'\0');raw=hashlib.sha256()
        with p.open('rb') as stream:
            for chunk in iter(lambda:stream.read(8*1024**2),b''):blob.update(chunk);raw.update(chunk)
        assert blob.hexdigest()==index[name],name
        manifest.append({'path':name,'bytes':size,'sha256':raw.hexdigest(),'git_blob_oid':index[name]})
    bad=subprocess.check_output(['git','diff','--cached','--name-only','--','backend','configs','profiles','gold','reference'],cwd=ROOT)
    assert not bad
    assert not subprocess.check_output(['git','diff','--name-only'],cwd=ROOT)
    attrs=subprocess.check_output(['git','check-attr','text','--','experiments/out/step18/measurement_evidence/audit/judgments.jsonl'],cwd=ROOT).decode()
    assert attrs.strip().endswith('text: unset')
    large=[r for r in manifest if r['bytes']>5_000_000]
    result={'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':manifest,'file_count':len(manifest),'total_bytes':sum(x['bytes'] for x in manifest),
      'large_files_over_5_MB':large,'all_staged_files_equal_working_bytes':True,'source_or_config_paths_staged':False,
      'evidence_exact_bytes_preserved_by_nested_attributes':True,
      'inventory_scope':'Staged report, append-only ledger and all Step 18 evidence before this inventory/receipt is added. Historical v1 inventory is retained; this v2 supersedes its file metadata. Final new receipts are separately byte-checked before commit.'}
    write_new(EVIDENCE/'measurement_evidence/final_inventory_v2.json',result)
    write_new(EVIDENCE/'measurement_evidence/staged_bytes_verification.json',{'recorded_at':result['recorded_at'],'files_checked':len(manifest),'all_staged_files_equal_working_bytes':True,'paths_limited_to_report_ledger_results':True,'backend_configs_profiles_gold_reference_staged':False,'large_files':large,'metadata_only_followup':['final_inventory_v2.json','staged_bytes_verification.json','evaluation_jobs/final_index_audit_v1/result.json']})
    print('Index audit passed:',len(manifest),'files,',result['total_bytes'],'bytes; all staged blobs preserve exact working bytes',flush=True)

if __name__=='__main__':main()
