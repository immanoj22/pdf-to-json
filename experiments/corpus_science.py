from pathlib import Path
import fitz,json,re
from reference_paths import reference_path
p=reference_path("science_pdf")
d=fitz.open(p);rows=[]
for i,page in enumerate(d):
 images=page.get_image_info()
 text=page.get_text()
 if len(images)>=8:
  captions=re.findall(r'.{0,70}Figure.{0,150}',text.replace('\n',' '))
  rows.append({'page':i+1,'images':len(images),'captions':captions[:10],'rect':list(page.rect),'image_boxes':[x['bbox'] for x in images]})
rows.sort(key=lambda x:x['images'],reverse=True)
out=Path(__file__).resolve().parents[1] / "experiments/out";out.mkdir(exist_ok=True)
(out/'corpus_science_image_pages.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
for r in rows[:25]: print(json.dumps({k:v for k,v in r.items() if k!='image_boxes'}),flush=True)
for r in rows[:8]:
 d[r['page']-1].get_pixmap(matrix=fitz.Matrix(0.7,0.7)).save(out/f"corpus_science_p{r['page']}.png")
