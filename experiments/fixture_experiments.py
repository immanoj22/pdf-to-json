"""Step 1 experiments only. No converter or old-project imports/writes."""
import argparse, hashlib, json, time, unicodedata
from collections import Counter
from pathlib import Path
import numpy as np
import cv2
import pymupdf
import pypdfium2 as pdfium
import pdfplumber
import regex
from PIL import Image, ImageDraw
from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTTextLine, LTChar, LTImage, LTCurve

from reference_paths import reference_path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'experiments/out'
FIX=ROOT/'experiments/fixtures'
CACHE=reference_path("spanish_cache")
SPECS=[
 ('column_26',str(reference_path("spanish_pdf")),26,'column regression',2),
 ('column_100',str(reference_path("spanish_pdf")),100,'column regression',2),
 ('complex_map',str(reference_path("spanish_pdf")),314,'map with inset and two-column prose',2),
 ('complex_cards',str(reference_path("spanish_pdf")),465,'two-column summary plus four organization cards',2),
 ('complex_sidebar',str(reference_path("spanish_pdf")),500,'stacked colored sidebars with two-column prose',2),
 ('science_fission',str(reference_path("science_pdf")),527,'composite nuclear fission/chain reaction',1),
 ('science_dissolving',str(reference_path("science_pdf")),546,'one figure with three molecular panels',1),
 ('background_worksheet',str(reference_path("spanish_pdf")),389,'page background behind worksheet',2),
 ('colored_box',str(reference_path("spanish_pdf")),727,'colored guide box and footer behind text',1),
]
def tokens(s):
 return Counter(regex.findall(r'[\p{L}\p{M}\p{N}]+',unicodedata.normalize('NFKC',s)))
def metric(base,text):
 a,b=tokens(base),tokens(text);matched=sum((a&b).values())
 return {'baseline':sum(a.values()),'tokens':sum(b.values()),'matched':matched,'missing':sum((a-b).values()),'extra':sum((b-a).values()),'recall':matched/max(1,sum(a.values())),'missing_examples':(a-b).most_common(8),'extra_examples':(b-a).most_common(8)}
def inside(box,frame):
 x0,y0,x1,y1=box
 return frame[0]<=(x0+x1)/2<=frame[2] and frame[1]<=(y0+y1)/2<=frame[3]
def lines_mu(page):
 data=page.get_text('dict',flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES,sort=False)
 return [{'box':l['bbox'],'text':''.join(s['text'] for s in l['spans']),'size':max((s['size'] for s in l['spans']),default=0)} for b in data['blocks'] if b['type']==0 for l in b['lines']]
def walk(o):
 yield o
 if hasattr(o,'__iter__'):
  for c in o:yield from walk(c)
def extract(name,path,frame):
 if name=='pymupdf':
  with pymupdf.open(path) as d:
   ls=lines_mu(d[0]);return '\n'.join(l['text'] for l in ls if inside(l['box'],frame))
 if name=='pypdfium2':
  with pdfium.PdfDocument(path) as d:
   p=d[0];t=p.get_textpage()
   return t.get_text_bounded(left=frame[0],bottom=p.get_height()-frame[3],right=frame[2],top=p.get_height()-frame[1])
 if name=='pdfminer.six':
  p=next(extract_pages(path,laparams=LAParams(all_texts=True)))
  return '\n'.join(o.get_text() for o in walk(p) if isinstance(o,LTTextLine) and inside((o.x0,p.height-o.y1,o.x1,p.height-o.y0),frame))
 if name=='pdfplumber':
  with pdfplumber.open(path,laparams={'all_texts':True}) as d:
   p=d.pages[0]
   # Preserve characters; crop by character midpoint for explicit print frame.
   chars=[c for c in p.chars if inside((c['x0'],c['top'],c['x1'],c['bottom']),frame)]
   from pdfplumber.utils import extract_text
   return extract_text(chars,x_tolerance=3,y_tolerance=3) or ''
def assets():
 FIX.mkdir(exist_ok=True); manifest=[]
 docs={}
 for fid,src,n,kind,actual in SPECS:
  if src not in docs:docs[src]=pymupdf.open(src)
  d=docs[src];p=d[n-1]
  dest=FIX/f'{fid}.pdf'
  with pymupdf.open() as single:
   single.insert_pdf(d,from_page=n-1,to_page=n-1);single.save(dest,garbage=3,deflate=True)
  pix=p.get_pixmap(matrix=pymupdf.Matrix(1,1),alpha=False)
  im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples);im.save(OUT/f'{fid}_page.png')
  manifest.append({'id':fid,'source':src,'physical_page':n,'kind':kind,'actual_main_prose_columns':actual,'width':p.rect.width,'height':p.rect.height,'trimbox':list(p.trimbox),'fixture':str(dest.relative_to(ROOT)),'fixture_sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
 for src,d in docs.items():d.close()
 for row in manifest:
  row['source_key']='science_pdf' if row['id'].startswith('science_') else 'spanish_pdf'
  row['source_sha256']=hashlib.sha256(Path(row['source']).read_bytes()).hexdigest()
 (OUT/'fixtures_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
 print('Created and reopened',len(manifest),'single-page fixtures',flush=True)
 for r in manifest:
  with pymupdf.open(ROOT/r['fixture']) as d:assert len(d)==1
def geometry(page):
 # One fixed heuristic, no fixture-specific thresholds or answer-XML input.
 # Text geometry selects prose-length lines; OpenCV projects a mask and checks raster gutters.
 start=time.perf_counter();frame=page.trimbox;w,h=int(page.rect.width),int(page.rect.height)
 mask=np.zeros((h,w),dtype=np.uint8)
 ls=lines_mu(page)
 for l in ls:
  x0,y0,x1,y1=l['box']
  if len(l['text'].strip())>=35 and 6<=l['size']<=13 and inside(l['box'],frame) and x1-x0<0.72*frame.width:
   cv2.rectangle(mask,(int(x0),int(y0)),(int(x1),int(y1)),255,-1)
 pix=page.get_pixmap(matrix=pymupdf.Matrix(1,1),colorspace=pymupdf.csGRAY,alpha=False)
 gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
 _,foreground=cv2.threshold(gray,235,255,cv2.THRESH_BINARY_INV)
 y0,y1=int(frame.y0+40),int(frame.y1-35)
 projection=(mask[y0:y1]>0).sum(axis=0).astype(float)
 raster=(foreground[y0:y1]>0).sum(axis=0).astype(float)
 projection=cv2.GaussianBlur(projection.reshape(1,-1),(9,1),0).ravel()
 lo,hi=int(frame.x0+0.20*frame.width),int(frame.x0+0.80*frame.width)
 candidates=[];beg=None
 for x in range(lo,hi+1):
  is_gap=projection[x]<=max(2,0.025*(y1-y0))
  if is_gap and beg is None:beg=x
  if (not is_gap or x==hi) and beg is not None:
   end=x
   if 8<=end-beg<=80:
    mid=(beg+end)/2
    left=projection[max(int(frame.x0),beg-100):beg].sum()
    right=projection[end:min(int(frame.x1),end+100)].sum()
    # Raster allows decoration to obstruct a gutter, but records it as disagreement.
    if min(left,right)>120:
     candidates.append({'x':mid,'width':end-beg,'raster_ink_fraction':float(np.mean(raster[beg:end])/(y1-y0))})
   beg=None
 gutters=[c['x'] for c in candidates]
 edges=[frame.x0]+gutters+[frame.x1]
 boxes=[[edges[i],y0,edges[i+1],y1] for i in range(len(edges)-1)]
 return {'columns':len(boxes),'gutters':candidates,'boxes':boxes,'seconds':time.perf_counter()-start,'policy':'left to right columns; top to bottom lines within each; spanning/sidebar scope unresolved'}
def probe(page):
 start=time.perf_counter()
 images=page.get_image_info(xrefs=True);drawings=page.get_drawings();log=page.get_bboxlog();trace=page.get_texttrace()
 roles=Counter(x[0] for x in log)
 under_images=0;under_fills=0
 for kind,box in log:
  if kind!='fill-image':continue
  idx=next((i for i,x in enumerate(log) if x[0]==kind and x[1]==box),0)
  if any(i>idx and t.get('type')!=3 and pymupdf.Rect(box).intersects(pymupdf.Rect(t['bbox'])) for i,t in ((t['seqno'],t) for t in trace)):under_images+=1
 for d in drawings:
  if d.get('fill') is not None and d['rect'].get_area()>64 and max(d['fill'])-min(d['fill'])>0.1:
   if any(t['seqno']>d['seqno'] and pymupdf.Rect(d['rect']).intersects(pymupdf.Rect(t['bbox'])) for t in trace):under_fills+=1
 return {'get_image_info':len(images),'distinct_image_xrefs':len({i.get('xref') for i in images}),'get_drawings':len(drawings),'vector_items':sum(len(d['items']) for d in drawings),'get_bboxlog':len(log),'bboxlog_roles':dict(roles),'get_texttrace':len(trace),'image_placements_under_later_text':under_images,'colored_fill_paths_under_later_text':under_fills,'seconds':time.perf_counter()-start,'sample_keys':{'image':list(images[0]) if images else [],'drawing':list(drawings[0]) if drawings else [],'trace':list(trace[0]) if trace else []}}
def compare():
 manifest=json.loads((OUT/'fixtures_manifest.json').read_text())
 exclusions={e['source_id'] for e in json.loads((CACHE/'validation.json').read_text())['exclusions']}
 result=[];geo=[]
 for row in manifest:
  fid=row['id'];path=ROOT/row['fixture'];frame=row['trimbox']
  with pymupdf.open(path) as d:
   p=d[0];native=extract('pymupdf',path,frame)
   if row['source'].endswith('9781264958665-Binder1.pdf'):
    old=json.loads((CACHE/f"normalized/pages/{row['physical_page']:06d}.json").read_text())
    baseline='\n'.join(''.join(s['text'] for s in l['spans']) for b in old['blocks'] for l in b['lines'] if l['provenance']['source_id'] not in exclusions)
    baseline_kind='old retained cached lines'
   else:baseline=native;baseline_kind='current PyMuPDF native proxy; no equivalent old token benchmark'
   apis=probe(p)
   g=geometry(p);g.update({'id':fid,'actual_main_prose_columns':row['actual_main_prose_columns']})
   geo.append(g)
   im=Image.open(OUT/f'{fid}_page.png').convert('RGB');dr=ImageDraw.Draw(im)
   for i,b in enumerate(g['boxes']):
    dr.rectangle(b,outline=['red','blue','green','purple'][i%4],width=3);dr.text((b[0]+3,b[1]+3),f'Gutter C{i+1}',fill='red')
   im.save(OUT/f'{fid}_geometry_overlay.png')
  for name in ('pymupdf','pypdfium2','pdfminer.six','pdfplumber'):
   times=[];text=''
   try:
    for _ in range(3):
     start=time.perf_counter();text=extract(name,path,frame);times.append(time.perf_counter()-start)
    stats=metric(baseline,text);stats.update({'id':fid,'extractor':name,'baseline_kind':baseline_kind,'median_seconds':float(np.median(times)),'repeats':3})
    if name=='pymupdf':stats['apis']=apis
    result.append(stats)
   except Exception as e:result.append({'id':fid,'extractor':name,'error':repr(e)})
  (OUT/'extractor_results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
  (OUT/'geometry_results.json').write_text(json.dumps(geo,indent=2),encoding='utf-8')
  print(fid,[(r['extractor'],r.get('tokens'),r.get('missing'),round(r.get('median_seconds',0),4)) for r in result if r['id']==fid],flush=True)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['assets','compare']);a=ap.parse_args()
 assets() if a.mode=='assets' else compare()


