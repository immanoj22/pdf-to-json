"""Full-book extraction experiment; never imports/writes old code."""
import argparse,json,time
from pathlib import Path
import pymupdf,pypdfium2
from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams,LTTextLine
import pdfplumber
from fixture_experiments import tokens,metric,inside,lines_mu,walk,CACHE,OUT
from reference_paths import reference_path
def main():
 ap=argparse.ArgumentParser();ap.add_argument('kind',choices=['small','758']);a=ap.parse_args()
 source=reference_path("small_pdf") if a.kind=='small' else reference_path("spanish_pdf")
 texts={};result=[]
 with pymupdf.open(source) as d:
  frames=[list(p.trimbox) for p in d];count=len(d)
 start=time.perf_counter()
 with pymupdf.open(source) as d:
  texts['pymupdf']='\n'.join(l['text'] for p,f in zip(d,frames) for l in lines_mu(p) if inside(l['box'],f))
 times={'pymupdf':time.perf_counter()-start}
 start=time.perf_counter()
 with pypdfium2.PdfDocument(source) as d:
  texts['pypdfium2']='\n'.join(p.get_textpage().get_text_bounded(left=f[0],bottom=p.get_height()-f[3],right=f[2],top=p.get_height()-f[1]) for p,f in zip(d,frames))
 times['pypdfium2']=time.perf_counter()-start
 if a.kind=='small':
  start=time.perf_counter()
  texts['pdfminer.six']='\n'.join(o.get_text() for p,f in zip(extract_pages(source,laparams=LAParams(all_texts=True)),frames) for o in walk(p) if isinstance(o,LTTextLine) and inside((o.x0,p.height-o.y1,o.x1,p.height-o.y0),f))
  times['pdfminer.six']=time.perf_counter()-start
  start=time.perf_counter()
  chunks=[]
  with pdfplumber.open(source) as d:
   from pdfplumber.utils import extract_text
   for p,f in zip(d.pages,frames):
    chunks.append(extract_text([c for c in p.chars if inside((c['x0'],c['top'],c['x1'],c['bottom']),f)],x_tolerance=3,y_tolerance=3) or '')
  texts['pdfplumber']='\n'.join(chunks);times['pdfplumber']=time.perf_counter()-start
 baseline=texts['pymupdf'];definition='current PyMuPDF native proxy; no old conservation claim'
 if a.kind=='758':
  exclusions={e['source_id'] for e in json.loads((CACHE/'validation.json').read_text())['exclusions']}
  chunks=[]
  for n in range(1,count+1):
   old=json.loads((CACHE/f'normalized/pages/{n:06d}.json').read_text())
   chunks.extend(''.join(s['text'] for s in l['spans']) for b in old['blocks'] for l in b['lines'] if l['provenance']['source_id'] not in exclusions)
  baseline='\n'.join(chunks);definition='old 495751 retained tokens; TrimBox excluded, furniture included'
 for name,text in texts.items():
  r=metric(baseline,text);r.update(extractor=name,seconds=times[name],seconds_per_page=times[name]/count);result.append(r)
 out={'source':str(source),'pages':count,'baseline_definition':definition,'results':result,'timing_scope':'one sequential run, native text with bbox retention; excludes baseline/cache reading and token scoring'}
 (OUT/f'full_book_{a.kind}.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps(out,ensure_ascii=True),flush=True)
if __name__=='__main__':main()

