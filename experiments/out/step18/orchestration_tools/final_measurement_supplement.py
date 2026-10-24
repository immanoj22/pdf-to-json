"""Describe retained OCR records and registered missing components; no new run."""
import json
from collections import Counter
from pathlib import Path
from book_core.cache_store import read_json
from book_core.ocr.tokens import OcrPage
from evaluation_routes import BASE,EVIDENCE,write_new,sha

def main():
    inputs=json.loads((BASE/'audit/mideast/ocr_diagnostic_inputs.json').read_text('utf8'))
    rows=[]
    for row in inputs['rows']:
        p=Path(row['stored_ocr_cache_path'])
        model=OcrPage.model_validate_json(read_json(p)['payload'])
        rows.append({'page':row['page'],'usage':row['usage'],'cache_sha256':sha(p),
            'reader':model.page.extractor.model_dump(mode='json'),
            'evidence_records':len(model.words),
            'granularity':dict(Counter(w.granularity for w in model.words)),
            'engines':dict(Counter(w.engine for w in model.words)),
            'line_ids':len({s.line_id for s in model.page.store.spans.values()}),
            'region_indices':sorted({w.region_index for w in model.words}),
            'stored_warnings':len(model.warnings)})
    out={'no_ocr_rerun':True,'rows':rows,'production_only':{'pages':1,'regions_with_words':1,'word_records':5,'line_ids':3,
        'review_items':3,'review_items_per_page':3.0,'review_items_per_word_record':0.6,'review_items_per_line':1.0,
        'note':'Three review items target the same cover page. These rates are workload ratios, not word/line error rates. Eight stored OCR warnings are separate from three published review items.'}}
    write_new(EVIDENCE/'measurement_evidence/ocr_record_supplement.json',out)
    result=json.loads((EVIDENCE/'results.json').read_text('utf8'))
    result['books']['mideast']['M14']['retained_record_supplement']=out
    for book in ['ent_textbook','mideast']:
        m=result['books'][book]
        m['M14']['character_multiset_F1']={'status':'unmeasured','reason':'No independent transcript registered.'}
        m['M15']['eligible_RTL_units']=0
        m['M15']['eligible_RTL_pages']=0
        m['M15']['RTL_visual_diagnostic']={'status':'not_applicable','reason':'No emitted eligible RTL unit; unknown direction is not recoded as LTR.'}
        m['M10']['credit_accuracy']={'status':'unmeasured','reason':'No independent supported credit denominator from frozen reader.'}
        m['M10']['linked_name_accuracy']={'status':'unmeasured','reason':'No independent parsed printed-label/name denominator from frozen reader.'}
        m['M10']['ambiguous_figure_accuracy']={'status':'unmeasured','reason':'No independent whole-book figure truth; sample observations retained by warning kind.'}
    # This is the assembled report, not a frozen evaluator output. Retain v1
    # verbatim and write v2 with additional registered component disclosures.
    write_new(EVIDENCE/'results_v2.json',result)
    print('Supplement saved; original results.json retained, final report is results_v2.json',flush=True)

if __name__=='__main__':main()
