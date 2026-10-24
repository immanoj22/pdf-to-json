"""Deferred original-PDF crop/context rendering through the Extractor interface."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
from evaluation_routes import BASE, ROOT, SOURCE_KEYS, route, sha, write_new

def main(book):
    run, _, _ = route(book)
    from reference_paths import reference_path
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from step17_json_eval import walk
    from step17b_all_text_styles import source_box
    from PIL import Image
    source = reference_path(SOURCE_KEYS[book])
    document = json.loads((Path(run['book_json']) / 'book.json').read_text('utf8'))
    nodes = {n['id']:n for top in document['content'] for n,*_ in walk(top) if n.get('id')}
    nodes.update({n['id']:{**n,'type':'furniture','pages':[n['page']]} for n in document.get('furniture') or []})
    destination = BASE / 'audit' / book
    receipt_path = destination / 'render_receipt.json'
    assert not receipt_path.exists(), 'Do not overwrite existing audit crops or their receipt'
    extractor = PyMuPDFExtractor('cpu')
    contexts = {}
    receipt = []
    def page_image(number):
        if number not in contexts:
            raster = extractor.render_page(source, number, dpi=160)
            path = destination / 'context' / f'page_{number:06d}.png'
            path.parent.mkdir(parents=True, exist_ok=True)
            assert not path.exists(), 'Preserve previously rendered evidence'
            path.write_bytes(raster.png)
            contexts[number] = {'path':path.relative_to(ROOT).as_posix(),
                'width':raster.width, 'height':raster.height,
                'page_width':raster.page_width, 'page_height':raster.page_height,
                'sha256':sha(path)}
        record = contexts[number]
        image = Image.open(ROOT / record['path']).convert('RGB')
        return image, record
    def bounds(boxes):
        if not boxes:
            return None
        if isinstance(boxes[0], dict):
            boxes = [[b[k] for k in ('x0','y0','x1','y1')] for b in boxes]
        return [min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
    for path in sorted((BASE / 'samples' / book).glob('*.json')):
        sample = json.loads(path.read_text('utf8'))
        if 'selected' not in sample:
            continue
        for selected in sample['selected']:
            row = copy.deepcopy(selected)
            family, uid = sample['family'], row['target_id']
            pages = list(row.get('pages') or ([row['page']] if row.get('page') else []))
            boxes = {}
            box_method = 'full original page; target requires visual disambiguation'
            if family.startswith('style:'):
                try:
                    source_box(row, {'archive':run['output']})
                    boxes[row['page']] = row['box']
                    box_method = row.get('box_method')
                except (ValueError,KeyError,TypeError,IndexError) as error:
                    row['box_limitation'] = repr(error)
                    boxes[row['page']] = bounds(row.get('owner_boxes') or [])
            elif family.startswith('flag:'):
                if row.get('box'):
                    boxes[row['page']] = bounds([row['box']])
                    box_method = 'review target box'
                elif row.get('unit') in nodes:
                    node = nodes[row['unit']]
                    boxes[row['page']] = bounds(node.get('boxes') or [])
                    box_method = 'review owning-unit box'
            elif family.startswith('continuity:'):
                pages = []
                for key in ('from_unit','to_unit'):
                    node = nodes.get(row[key])
                    if node is not None:
                        for number in node.get('pages') or []:
                            if number not in pages:
                                pages.append(number)
                            boxes[number] = bounds(node.get('boxes') or [])
                box_method = 'continuity endpoint owner boxes; both endpoints and full pages retained'
            context_paths, crop_paths = [], []
            target_key = hashlib.sha256((family + ':' + uid).encode('utf8')).hexdigest()[:24]
            for number in sorted(set(pages)):
                image, context = page_image(number)
                context_paths.append(context['path'])
                box = boxes.get(number)
                if box is None:
                    crop_paths.append(context['path'])
                    continue
                sx,sy = context['width']/context['page_width'], context['height']/context['page_height']
                # A constant context margin is an audit presentation rule, never a
                # converter decision or a page-specific source coordinate.
                clip = (max(0,int((box[0]-36)*sx)),max(0,int((box[1]-28)*sy)),
                    min(image.width,int((box[2]+36)*sx)+1),min(image.height,int((box[3]+28)*sy)+1))
                if clip[2] <= clip[0] or clip[3] <= clip[1]:
                    crop_paths.append(context['path'])
                    row['box_limitation'] = 'invalid or empty target crop; full context retained'
                    continue
                output = destination / 'crops' / f'{target_key}_p{number:06d}.png'
                output.parent.mkdir(parents=True, exist_ok=True)
                assert not output.exists()
                image.crop(clip).save(output)
                crop_paths.append(output.relative_to(ROOT).as_posix())
            receipt.append({'book_id':book,'family':family,'target_id':uid,
                'selection_file':path.relative_to(ROOT).as_posix(),'selected_evidence':row,
                'context_paths':context_paths,'crop_paths':crop_paths,'box_method':box_method,
                'render_status':'ready_for_agent_view' if context_paths else 'unscorable_no_mapped_source_page',
                'agent_verdict':None,'independently_verified':False})
    write_new(receipt_path, {'book_id':book,'source_sha256':sha(source),
        'render_method':'PyMuPDFExtractor.render_page, frozen Extractor API, 160 dpi; original full pages plus target crops',
        'contexts':contexts,'targets':receipt,'judgments_performed':0})
    print(book,'original source images prepared; no judgments performed',flush=True)

if __name__ == '__main__':
    main(sys.argv[1])
