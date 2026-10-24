"""Complete all-fewer rare-kind diagnostics; no new metrics or rescoring."""
import datetime,json
from evaluation_routes import BASE
from fixed_sampling import select,append_judgment

def main():
    rows=[json.loads(s) for s in (BASE/'audit/judgments.jsonl').read_text('utf8').splitlines()]
    math=[r for r in rows if r['book_id']=='ent_textbook' and r['family']=='style:math' and r['agent_verdict']=='wrong']
    assert len(math)==6
    chosen=select('ent_textbook','taxonomy:M16:visible_math',{r['target_id']:r for r in math})
    for r in chosen['selected']:
        append_judgment({'judgment_id':'ent_textbook:taxonomy:M16:visible_math:'+r['target_id'],'book_id':'ent_textbook','family':'taxonomy:M16:visible_math','target_id':r['target_id'],'crop_paths':r['crop_paths'],'context_paths':r['context_paths'],'agent_verdict':'anatomical_label_misclassified_as_math','notes':'All six visually wrong emitted math spans in the fixed all-nine math sample are anatomical nerve labels, sometimes including a closing parenthesis. General later rule: distinguish anatomical subscript identifiers from equations using context and evidence. Existing mathematical subscript representation and styling reference recall are separate; no change made.','selected_evidence':r,'viewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    census=next(r for r in rows if r['judgment_id']=='ent_textbook:page_census:17')
    chosen=select('ent_textbook','taxonomy:M13',{'17:folio':census})
    for r in chosen['selected']:
        append_judgment({'judgment_id':'ent_textbook:taxonomy:M13:17:folio','book_id':'ent_textbook','family':'taxonomy:M13','target_id':'17:folio','crop_paths':r['crop_paths'],'context_paths':r['context_paths'],'agent_verdict':'printed_folio_retained_as_body_text','notes':'Visible xvii retained inside a body/reviewer paragraph; published page label is inferred rather than folio furniture. Numeric label identity and node typing are different metrics. General rule needed: retain and identify folio furniture without merging it into column text. All one observed source-census folio error inspected.','selected_evidence':r['comparison']['folio'],'viewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    print('All-six visible math causes and all-one folio cause recorded')

if __name__=='__main__':main()
