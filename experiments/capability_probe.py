"""Verify installed extractor metadata/geometry capabilities, not conversion."""
import ctypes,json
from collections import Counter
from pathlib import Path
import pypdfium2 as p
import pdfplumber
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar,LTImage,LTCurve,LAParams
from fixture_experiments import walk,OUT
rows=[]
for fid in ('science_dissolving','background_worksheet'):
 path=Path(__file__).resolve().parent/'fixtures'/f'{fid}.pdf'
 with p.PdfDocument(path) as d:
  page=d[0];text=page.get_textpage();idx=0
  obj=text.get_textobj(idx)
  flags=ctypes.c_int();n=p.raw.FPDFText_GetFontInfo(text.raw,idx,None,0,ctypes.byref(flags))
  buf=ctypes.create_string_buffer(n);p.raw.FPDFText_GetFontInfo(text.raw,idx,buf,n,ctypes.byref(flags))
  rgba=[ctypes.c_uint() for _ in range(4)]
  ok=p.raw.FPDFText_GetFillColor(text.raw,idx,*[ctypes.byref(c) for c in rgba])
  objects=list(page.get_objects());types=Counter(o.type for o in objects)
  images=[o.get_bounds() for o in objects if o.type==p.raw.FPDF_PAGEOBJ_IMAGE]
  pathobjs=[o for o in objects if o.type==p.raw.FPDF_PAGEOBJ_PATH]
  segments=sum(p.raw.FPDFPath_CountSegments(o.raw) for o in pathobjs)
  rows.append({'id':fid,'engine':'pypdfium2','font':buf.value.decode(errors='replace'),'font_size_untransformed':obj.get_font_size(),'text_matrix':repr(obj.get_matrix()),'effective_size_axis_aligned':obj.get_font_size()*(obj.get_matrix().c**2+obj.get_matrix().d**2)**0.5,'char_bbox':text.get_charbox(idx),'fill_color_ok':bool(ok),'fill_rgba':[v.value for v in rgba],'object_types':dict(types),'image_boxes':len(images),'paths':len(pathobjs),'path_segments':segments,'shadings':types[p.raw.FPDF_PAGEOBJ_SHADING]})
 layout=next(extract_pages(path,laparams=LAParams(all_texts=True)));items=list(walk(layout))
 ch=next(o for o in items if isinstance(o,LTChar))
 rows.append({'id':fid,'engine':'pdfminer.six','font':ch.fontname,'font_size':ch.size,'char_bbox':ch.bbox,'fill_color':ch.graphicstate.ncolor,'images':sum(isinstance(o,LTImage) for o in items),'curves_lines_rects':sum(isinstance(o,LTCurve) for o in items),'note':'shade objects are not raster LTImage boxes'})
 with pdfplumber.open(path) as d:
  page=d.pages[0];ch=page.chars[0]
  rows.append({'id':fid,'engine':'pdfplumber','font':ch['fontname'],'font_size':ch['size'],'char_bbox':[ch['x0'],ch['top'],ch['x1'],ch['bottom']],'fill_color':ch['non_stroking_color'],'images':len(page.images),'vector_edges':len(page.edges),'curves':len(page.curves),'rects':len(page.rects)})
(OUT/'capability_probe.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(rows))


