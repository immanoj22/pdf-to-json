"""Read-only corpus inventory. All artifacts are written under experiments/out/."""
from pathlib import Path
import hashlib,json,re
import pymupdf
from lxml import etree
from reference_paths import private_file_names, reference_path
BASE=reference_path("old_root")
DOWNLOADS=reference_path("downloads")
CANONICAL=[reference_path("spanish_pdf"),reference_path("spanish_xml"),reference_path("partial_xml")]
FILES=sorted(p for p in DOWNLOADS.rglob('*') if p.suffix.lower() in ('.pdf','.xml') and p.name not in private_file_names())+CANONICAL
rows=[]
for p in FILES:
 row={'name':p.name,'path':str(p),'bytes':p.stat().st_size}
 with p.open('rb') as stream:row['sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
 if p.suffix=='.pdf':
  with pymupdf.open(p) as doc:
   row['pages']=len(doc);row['first_text']=' | '.join(doc[i].get_text()[:250].replace('\n',' ') for i in range(min(3,len(doc))))[:550]
 else:
  raw=p.read_text(encoding='utf8');parser=etree.XMLParser(resolve_entities=False,no_network=True)
  try:rt=etree.fromstring(raw.encode(),parser)
  except etree.XMLSyntaxError as error:
   row['original_syntax_error']=str(error)
   if p.name=='9781264958665NIMAS.xml':
    parts=raw.splitlines(keepends=True);parts[1]=parts[1].replace('""','"');parts[2]=parts[2].replace('""','"');raw=''.join(parts);row['inspection_only_transform']='doubled quote delimiters in opening lines 2 and 3 repaired in memory'
   elif p.name=='docbook index output.xml':
    raw='<inspection>'+re.sub(r'<\?xml.*?\?>','',raw,flags=re.S)+'</inspection>';row['inspection_only_transform']='two top-level fragments wrapped in memory'
   else:raise
   rt=etree.fromstring(raw.encode(),parser)
  row['root']=rt.tag;row['titles_or_headings']=[' '.join(x.itertext())[:150] for x in rt.xpath('//*[local-name()="title" or local-name()="doctitle" or local-name()="h1" or local-name()="h2" or local-name()="hd"]')[:6]];row['pagenums']=len(rt.xpath('//*[local-name()="pagenum"]'))
 rows.append(row)
profiles=BASE/'book_xml_backend/data/profiles'
for p in sorted(profiles.glob('*/samples/*/source.pdf')):
 x=p.with_suffix('.xml');row={'name':str(p.relative_to(profiles)),'path':str(p),'reference_xml':str(x),'bytes':p.stat().st_size}
 for key,file in [('sha256',p),('xml_sha256',x)]:
  with file.open('rb') as stream:row[key]=hashlib.file_digest(stream,'sha256').hexdigest()
 with pymupdf.open(p) as doc:row['pages']=len(doc);row['first_text']=doc[0].get_text()[:550].replace('\n',' ')
 rt=etree.parse(str(x),etree.XMLParser(resolve_entities=False,no_network=True));row['xml_root']=rt.getroot().tag;row['xml_headings']=[' '.join(t.itertext())[:150] for t in rt.xpath('//*[local-name()="h1" or local-name()="h2" or local-name()="hd"]')[:6]];row['xml_pagenums']=len(rt.xpath('//*[local-name()="pagenum"]'))
 rows.append(row)
out=Path(__file__).resolve().parents[1]/'experiments/out';out.mkdir(parents=True,exist_ok=True)
(out/'corpus_inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'inventory_items':len(rows),'pdfs':sum('pages' in r for r in rows),'xmls':sum('root' in r for r in rows),'profile_samples':sum('reference_xml' in r for r in rows),'output':str(out/'corpus_inventory.json')},ensure_ascii=False),flush=True)

