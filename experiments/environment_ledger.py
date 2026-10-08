"""Environment ledger for Phase 0; reads package metadata, writes new audit artifacts."""
import importlib.metadata as md,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'experiments/out'
def bytes_at(p):return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())
def rows():
 out=[]
 for d in md.distributions():
  out.append({'name':d.metadata['Name'],'version':d.version,'license_expression':d.metadata.get('License-Expression'),'license':d.metadata.get('License'),'classifiers':[c for c in d.metadata.get_all('Classifier',[]) if 'License' in c]})
 return sorted(out,key=lambda r:r['name'].lower())
data={'python':sys.version,'packages':rows(),'venv_bytes':bytes_at(Path(sys.prefix)),'opencv_distribution_bytes':sum(md.distribution('opencv-python-headless').locate_file(f).stat().st_size for f in md.distribution('opencv-python-headless').files if md.distribution('opencv-python-headless').locate_file(f).is_file())}
(OUT/'environment_extract.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
(ROOT/'experiments/requirements-extract.txt').write_text('\n'.join(r['name']+'=='+r['version'] for r in data['packages'])+'\n',encoding='utf-8')
ledger={}
inputs=[('Initial',json.loads((OUT/'environment_initial.json').read_text())['packages']),('Extract',data['packages']),('Layout',json.loads((OUT/'layout_environment_final.json').read_text())['packages'])]
for env,ps in inputs:
 for r in ps:
  name=r['name'];key=(name.lower(),r['version']);lic=r.get('license_expression') or r.get('license_metadata') or r.get('license') or '; '.join(r.get('classifiers') or r.get('license_classifiers') or []) or 'Not declared'
  lic=lic.replace('\n',' ')[:700]
  fixes={'colorama':'BSD-3-Clause (license file)','pdfplumber':'MIT (license file and upstream)','pymupdf':'AGPL-3.0 OR Artifex commercial','pypdfium2':'Apache-2.0 OR BSD-3-Clause; bundled dependency notices'}
  lic=fixes.get(name.lower(),lic)
  if key not in ledger:ledger[key]={'name':name,'version':r['version'],'license':lic,'envs':[]}
  ledger[key]['envs'].append(env)
items=sorted(ledger.values(),key=lambda r:(r['name'].lower(),r['version']))
(OUT/'installed_package_licenses.json').write_text(json.dumps(items,indent=2),encoding='utf-8')
lines=['| Package | Version | License from installed metadata/notices | Environment |','|---|---|---|---|']
for r in items:lines.append('| '+r['name']+' | '+r['version']+' | '+r['license'].replace('|','/')+' | '+', '.join(r['envs'])+' |')
(OUT/'installed_package_licenses.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('versions',len(items),'extract bytes',data['venv_bytes'],'opencv bytes',data['opencv_distribution_bytes'])

