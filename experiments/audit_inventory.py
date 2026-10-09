import hashlib, importlib.metadata as md, json, os, platform, sys
from pathlib import Path
import pymupdf
from reference_paths import reference_path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'experiments/out'
OUT.mkdir(parents=True,exist_ok=True)
packages=[]
for d in md.distributions():
 packages.append({'name':d.metadata.get('Name'),'version':d.version,'license_expression':d.metadata.get('License-Expression'),'license':d.metadata.get('License'),'classifiers':[c for c in d.metadata.get_all('Classifier',[]) if 'License' in c]})
env={'python':sys.version,'executable':sys.executable,'base_prefix':sys.base_prefix,'platform':platform.platform(),'cpu_count':os.cpu_count(),'packages':sorted(packages,key=lambda p:p['name'].lower())}
(OUT/'environment_initial.json').write_text(json.dumps(env,indent=2),encoding='utf-8')
pairs=[]
for p in (reference_path('old_root')/'book_xml_backend/data/profiles').rglob('source.pdf'):
 x=p.with_suffix('.xml')
 if not x.exists():continue
 with pymupdf.open(p) as doc:
  pairs.append({'pdf':str(p.relative_to(reference_path('old_root'))),'xml':str(x.relative_to(reference_path('old_root'))),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'xml_sha256':hashlib.sha256(x.read_bytes()).hexdigest(),'pages':len(doc),'metadata':doc.metadata,'first_text':doc[0].get_text()[:500]})
(OUT/'reference_pairs.json').write_text(json.dumps(pairs,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'python':sys.version,'packages':[(p['name'],p['version']) for p in packages],'pairs':pairs},ensure_ascii=False))
