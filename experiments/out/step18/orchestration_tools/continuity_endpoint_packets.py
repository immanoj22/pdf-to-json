"""Supplemental presentation: preserve distinct endpoint crops on the same page."""
import json,sys,hashlib
from evaluation_routes import BASE,ROOT,write_new,sha
from PIL import Image,ImageDraw,ImageFont

def main(book):
    base=BASE/'audit'/book
    original=json.loads((base/'render_receipt.json').read_text('utf8'))
    contexts=original['contexts']
    dest=base/'endpoint_packets';dest.mkdir(exist_ok=False)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
    receipt=[]
    for packet in sorted((base/'packets').glob('*_targets.json')):
        data=json.loads(packet.read_text('utf8'))
        if not data['family'].startswith('continuity:'):continue
        panels=[]
        for row in data['targets']:
            imgs=[];paths=[]
            for key in ['owning_output','to_output']:
                node=row[key]
                boxes=node.get('boxes') or []
                for page in node.get('pages') or []:
                    c=contexts[str(page)]
                    im=Image.open(ROOT/c['path']).convert('RGB')
                    bs=[b for b in boxes if b.get('page')==page]
                    if bs:
                        sx,sy=c['width']/c['page_width'],c['height']/c['page_height']
                        b=[min(b['x0'] for b in bs),min(b['y0'] for b in bs),max(b['x1'] for b in bs),max(b['y1'] for b in bs)]
                        im=im.crop((max(0,int((b[0]-18)*sx)),max(0,int((b[1]-14)*sy)),min(im.width,int((b[2]+18)*sx)+1),min(im.height,int((b[3]+14)*sy)+1)))
                    name=f'{packet.stem}_{row["index"]:02d}_{key}_{page}.png'
                    im.save(dest/name);paths.append((dest/name).relative_to(ROOT).as_posix())
                    im.thumbnail((1250,1600));imgs.append(im)
            panel=Image.new('RGB',(2600,90+max(i.height for i in imgs)),'white')
            d=ImageDraw.Draw(panel);d.text((8,8),f'{data["family"]} index {row["index"]}: from LEFT, to RIGHT',font=font,fill='black')
            d.text((8,40),row['target_id'],font=font,fill='black')
            for j,im in enumerate(imgs):panel.paste(im,(j*1300+8,85))
            output=dest/f'{packet.stem}_{row["index"]:02d}_sheet.png';panel.save(output)
            receipt.append({'family':data['family'],'index':row['index'],'target_id':row['target_id'],'supplemental_paths':paths,'sheet':output.relative_to(ROOT).as_posix(),'sha256':sha(output)})
    write_new(dest/'receipt.json',{'presentation_only':True,'reason':'Original renderer kept full contexts but same-page crop box selected the to endpoint only. Supplemental distinct endpoint crops; original evidence unchanged.','targets':receipt})
    print(book,len(receipt),'endpoint presentations; no verdicts')

if __name__=='__main__':main(sys.argv[1])
