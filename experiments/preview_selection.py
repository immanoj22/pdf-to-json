from pathlib import Path
import json,pymupdf
from PIL import Image,ImageOps,ImageDraw
from reference_paths import reference_path
root=Path(__file__).resolve().parents[1];out=root/'experiments/out'
p=reference_path("spanish_pdf")
with pymupdf.open(p) as doc:
 print('source',p,'pages',len(doc))
 tiles=[]
 for n in (26,100,314,465,500,389,727):
  page=doc[n-1];pix=page.get_pixmap(matrix=pymupdf.Matrix(1,1),alpha=False)
  im=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
  im.save(out/f'preview_{n}.png')
  im.thumbnail((320,440));tile=Image.new('RGB',(340,470),'white');tile.paste(im,((340-im.width)//2,25));ImageDraw.Draw(tile).text((10,5),str(n),fill='black');tiles.append(tile)
 sheet=Image.new('RGB',(340*4,470*2),'#bbbbbb')
 for i,t in enumerate(tiles):sheet.paste(t,((i%4)*340,(i//4)*470))
 sheet.save(out/'selection_contact.png')
