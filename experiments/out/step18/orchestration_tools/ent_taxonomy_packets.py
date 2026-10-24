"""Presentation/data enumeration only; preserve frozen selections and scores."""
import datetime,hashlib,json
from pathlib import Path
from evaluation_routes import BASE,EVIDENCE,ROOT,route,write_new
from fixed_sampling import SEED,select

def main():
    route('ent_textbook')
    import step14a_common as common
    import step17_json_eval as frozen
    import step17_styling_eval as styles
    from book_core.reference.pdf_tokens import page_tokens
    from reference_paths import reference_path
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    gold=common.derived_gold('ent_textbook');us={u['unit']:u for u in gold.units}
    dest=BASE/'audit/ent_textbook/error_taxonomies'
    selected={m:json.loads((dest/f'{m}_selection.json').read_text('utf8'))['selected'] for m in ['M05','M11','M12']}
    # All 15 missing joins were selected. Two wrong-link verdicts use a string
    # field, omitted by the first enumerator. Correct before taxonomy viewing:
    # all 17 are still selected, so no previously selected target is redrawn.
    all_links=json.loads((BASE/'evaluations/ent_textbook/continuity_reference/all_link_rows.json').read_text('utf8'))
    rows=list(selected['M11'])
    rows += [{**r,'page':r['from'][0],'pages':[r['from'][0],r['to'][0]],'error_kind':'wrong_link','target_id':f'all_link_rows:{i}'} for i,r in enumerate(all_links) if r['verdict']=='wrong']
    rows.sort(key=lambda r:(hashlib.sha256(f'{SEED}:ent_textbook:taxonomy:M11:{r["target_id"]}'.encode()).hexdigest(),r['target_id']))
    write_new(dest/'M11_population_correction.json',{'reason':'Initial enumerator missed two string verdict=wrong rows; 15 missing joins plus two wrong links, all selected before taxonomy viewing. Original selection retained. No target removed or redrawn.','population_size':17,'selected':rows})
    selected['M11']=rows
    # Superscript/subscript FN examples are complete (6/1). Link has zero
    # emitted aligned tokens, so every aligned reference link token is an FN.
    result=json.loads((BASE/'evaluations/ent_textbook/reference_styles/ent_textbook.json').read_text('utf8'))
    pop={}
    for kind in ['superscript','subscript']:
        xs=result['examples'][kind]['fn'];assert len(xs)==result['kinds'][kind]['reference_tokens']-result['kinds'][kind]['both']
        for p,o,t in xs:pop[f'{kind}:{p}:{o}']={'page':p,'ordinal':o,'token':t,'style_kind':kind,'error_kind':'reference_style_false_negative'}
    styles.XML={'ent_textbook':'ent_textbook_xml'}
    doc=styles.reference('ent_textbook')
    # reference() returns the frozen document; handle its documented tuple below.
    if isinstance(doc,tuple):doc=doc[0]
    kinds,_=styles.reference_kinds(doc)
    alignment=json.loads((EVIDENCE/'ent_textbook/alignment_evidence/scoped_alignment_payload.json').read_text('utf8'))
    for i,ks in enumerate(kinds):
        if 'link' not in ks or alignment['xml_page'][i]<0:continue
        p=alignment['pages'][alignment['xml_page'][i]];o=alignment['xml_ordinal'][i]
        pop[f'link:{i}:{p}:{o}']={'page':p,'ordinal':o,'reference_token_index':i,'style_kind':'link','error_kind':'reference_style_false_negative'}
    assert sum(r['style_kind']=='link' for r in pop.values())==108
    chosen=select('ent_textbook','taxonomy:M16',pop)
    write_new(dest/'M16_selection.json',chosen);selected['M16']=chosen['selected']
    needed=set()
    for rs in selected.values():
        for r in rs:
            needed.add(r['page']);needed.update(r.get('pages',[]))
    tokens={p:page_tokens(common.text_page('ent_textbook',p)) for p in needed}
    data=json.loads((EVIDENCE/'ent_textbook/book.json').read_text('utf8'))
    nodes=[n for top in data['content'] for n,*_ in frozen.walk(top)]
    def unit_text(uid):
        return [{'page':p,'first':f,'length':n,'text':' '.join(t.value for t in tokens[p].tokens[f:f+n])} for p,f,n in us[uid]['pdf'] if p in tokens]
    source=reference_path('ent_textbook_pdf');ext=PyMuPDFExtractor('cpu')
    for p in sorted(needed):
        path=BASE/f'audit/ent_textbook/context/page_{p:06d}.png'
        if not path.exists():path.write_bytes(ext.render_page(source,p,dpi=160).png)
    for m,rs in selected.items():
        out=[]
        for i,r in enumerate(rs):
            uids=r.get('reference_units',[]) or [r.get('unit') or (r.get('reference_unit') or {}).get('unit')]
            if r['error_kind']=='float_anchor':uids=[r[k] for k in ['expected_after_unit','predicted_after_unit','first_unit'] if r.get(k) is not None]
            uids=[u for u in uids if u is not None]
            p=r['page'];pages=r.get('pages') or [p]
            paths=[f'.cache/step18_part2/audit/ent_textbook/context/page_{q:06d}.png' for q in pages]
            out.append({**r,'index':i,'reference_source_text':{str(u):unit_text(u) for u in uids},
                'token_context': ' '.join(t.value for t in tokens[p].tokens[max(0,r.get('ordinal',0)-8):r.get('ordinal',0)+10]) if 'ordinal' in r else None,
                'crop_paths':paths,'context_paths':paths})
        write_new(dest/f'{m}_packets.json',out)
    write_new(dest/'presentation_receipt.json',{'no_scores_changed':True,'no_judgments_generated':True,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pages':sorted(needed)})
    print('Error-taxonomy presentation ready',flush=True)

if __name__=='__main__':main()
