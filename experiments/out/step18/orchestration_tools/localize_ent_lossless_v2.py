"""Diagnostic page localization of the unchanged registered global token failure."""
import json
from collections import Counter,defaultdict
from pathlib import Path
from evaluation_routes import BASE,route,write_new
from prepare_visual_populations import texts
from fixed_sampling import select

def main():
    run,_,_=route('ent_textbook')
    from book_core.assembly.lossless import _records,json_tokens
    from book_core.ledger.tokenization import token_counter
    from book_core.model.spans import ExtractedPage
    from book_core.cache_store import read_json
    data=json.loads((Path(run['book_json'])/'book.json').read_text('utf8'))
    global_found=json_tokens(data)
    frozen_ids=Counter(id(r) for n in data['content'] for r in _records(n))
    frozen_ids.update(id(f['content']) for f in data.get('furniture') or [])
    found_records={}
    def exact_records(value,path='$',owner=None,pages=()):
        if isinstance(value,list):
            for i,x in enumerate(value):yield from exact_records(x,f'{path}[{i}]',owner,pages)
        elif isinstance(value,dict):
            if value.get('id') or 'pages' in value:owner=value
            pages=tuple(value.get('pages') or ([value['page']] if 'page' in value else pages))
            if id(value) in frozen_ids:
                yield value,owner or {},pages,path
                return
            for k,x in value.items():yield from exact_records(x,f'{path}.{k}',owner,pages)
    for record,owner,pages,path in exact_records({'content':data['content'],'furniture':data.get('furniture') or []}):
        assert frozen_ids[id(record)]==1
        pages=tuple(sorted({r['page'] for r in record.get('source_runs',[])})) or pages
        assert len(pages)==1,('Cannot localize a cross-page record without changing reconstruction',path,pages)
        found_records[id(record)]={'record':record,'page':pages[0],'owner':owner.get('id'),'path':path,'section':'furniture' if path.startswith('$.furniture') else 'content'}
    assert set(found_records)==set(frozen_ids),'Diagnostic enumeration must cover the exact frozen gate records'
    buckets=defaultdict(lambda:{'content':[],'furniture':[],'suppressed':[]})
    evidence=defaultdict(list)
    for r in found_records.values():
        p=r['page'];sec=r['section']
        if sec=='content':buckets[p]['content'].append({'content':r['record']})
        else:buckets[p]['furniture'].append({'content':r['record']})
        evidence[p].append(r)
    for r in data.get('suppressed') or []:buckets[r['page']]['suppressed'].append(r)
    sums={k:Counter() for k in global_found};details=[];population={}
    for p in range(1,run['pages']+1):
        actual=json_tokens(buckets[p])
        for k,c in actual.items():sums[k].update(c)
        source=ExtractedPage.model_validate(read_json(Path(run['output'])/f'page_{p:06d}.json.gz')['source'])
        kept,discard=Counter(),Counter()
        for line in source.store.lines:
            c=token_counter(source.store.raw_line_text(line))
            (kept if source.geometry.content_bbox.contains_center(line.bbox) else discard).update(c)
        visible=actual['content']+actual['furniture']+actual['suppressed_retained']
        missing=kept-visible;extra=visible-kept
        if missing or extra:
            row={'page':p,'missing':dict(missing),'extra':dict(extra),'records':evidence[p]}
            details.append(row)
            for token,n in extra.items():
                for i in range(n):population[f'{p}:extra:{token}:{i}']={'page':p,'token':token,'extra_occurrence':i,'status':'page-localized; owning occurrence requires source/output inspection'}
            print('page',p,'missing',dict(missing),'extra',dict(extra),flush=True)
    assert sums==global_found,'Per-page diagnostic must exactly reconstruct registered global counters'
    result={'book_id':'ent_textbook','registered_global_unchanged':True,'per_page_reconstruction_equal':True,'details':details,
        'page_extra_total':sum(len([1 for _ in range(v)]) for r in details for v in r['extra'].values()),
        'page_missing_total':sum(v for r in details for v in r['missing'].values())}
    write_new(BASE/'evaluations/ent_textbook/lossless_page_localization.json',result)
    select('ent_textbook','taxonomy:M02',population)
    print('lossless diagnostic complete',flush=True)

if __name__=='__main__':main()
