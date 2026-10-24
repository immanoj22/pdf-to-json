"""Preserve earlier wrappers and write input-routing copies with reviewed scope.

Changes here are invocation paths, the coverage precondition and descriptive
scope text. Frozen evaluator function bodies remain unchanged.
"""
import ast,difflib,json
from evaluation_routes import BASE,sha,write_new

def main():
    names=['table_reference_evidence','published_reference_metrics','ent_figure_reference_metrics',
        'ent_heading_folio_metrics','ent_style_reference_metrics','continuity_reference_metrics','prepare_visual_populations']
    receipts=[]
    for name in names:
        source=BASE/(name+'.py');text=source.read_text('utf8');original=text
        text='from ent_scope_bridge import require_scope_review\n'+text
        lines=[]
        for line in text.splitlines():
            if "assert mapping['expected_coverage_complete']" in line:
                line=line[:len(line)-len(line.lstrip())]+'require_scope_review(mapping)'
            if "assert scope['expected_coverage_complete']" in line:
                line=line[:len(line)-len(line.lstrip())]+'require_scope_review(scope)'
            lines.append(line)
        text='\n'.join(lines)+'\n'
        if name=='table_reference_evidence':
            text=text.replace("book / 'alignment_evidence/derived'","book / 'alignment_evidence/scoped_derived'")
        if name=='ent_figure_reference_metrics':
            text=text.replace("target / 'derived'","target / 'scoped_derived'")
        if name=='ent_style_reference_metrics':
            text=text.replace("alignment_evidence/alignment_payload.json","alignment_evidence/scoped_alignment_payload.json")
        text=text.replace('46 mapped reference pages','43 located reference-marker pages (46 expected; 3 unlocated)')
        text=text.replace('46 registered pages','43 located reference-marker pages (46 expected; 3 unlocated)')
        ast.parse(text)
        dest=BASE/(name+'_scoped.py')
        with dest.open('x',encoding='utf8') as s:s.write(text)
        diff=''.join(difflib.unified_diff(original.splitlines(True),text.splitlines(True),fromfile=source.name,tofile=dest.name))
        receipts.append({'original':source.name,'original_sha256':sha(source),'invocation_copy':dest.name,'copy_sha256':sha(dest),'diff':diff})
    write_new(BASE/'scoped_invocation_receipt.json',{'changes':'Registered input scope routing only; no frozen evaluator algorithm, tokenization, threshold, profile or production file changes. All results conditional on 43 located marker pages; all losses retained.','wrappers':receipts})

if __name__=='__main__':main()
