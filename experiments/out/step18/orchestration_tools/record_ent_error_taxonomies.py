"""Explicit manual classifications after actual source/context views."""
import datetime,json
from evaluation_routes import BASE
from fixed_sampling import append_judgment

def main():
    dest=BASE/'audit/ent_textbook/error_taxonomies'
    order_notes={
      0:'Reviewer Jagdeep in left column precedes Kiran in right; output reversed column sequence.',
      1:'Answer 15 and answer 33 are in a multicolumn answer grid; logical question-number sequence is disturbed by output traversal.',
      2:'Left-column resonance item precedes right-column flowchart caption in reference. Caption promoted into main flow also makes this a role/float problem.',
      3:'Recess is in left-column EAC list before superior relation in right column; output ranks the latter first.',
      4:'Left-column reviewer attribution precedes right-column attribution; output reversed columns.',
      5:'Santosh in left reviewer column precedes Sunil in right; output reversed column sequence.',
      6:'Question options in left column precede later options in right column; output reordered question groups.',
      7:'Left-bottom cranial nerve detail precedes right-column Floor subitem; output begins right column prematurely.',
      8:'Left reviewer attribution precedes later right-column Chapter 35 review; output reversed column order.',
      9:'Left-bottom cranial nerve detail precedes right-column Middle Ear Mucosa; output starts right column early.',
      10:'Rosenthal canal in lower left precedes Round window at right-column top; output reverses them.',
      11:'Figure 7 is printed above right-column Structure prose that references it. Reference semantic anchor is after Structure, while output starts the float before main text. Both layout and reference anchor convention matter; raster alone does not prove the preferred semantic attachment.',
      12:'Helicotrema at bottom left precedes Saccule in right column; output reverses columns.',
      13:'Left-column attribution precedes continuation review prose in right column; output reverses columns.',
      14:'Left Absorption text precedes right-column case-study prose. Callout text mixed into main sequence is also a role/float problem.',
      15:'Left-column question option precedes question 16 in right column; output reverses logical question sequence.',
      16:'Left-column Floor relation precedes right-column Middle Ear Mucosa; output reverses columns.',
      17:'Left-column reviewer name precedes right-column affiliation; output reverses columns.',
      18:'Shreeya in left reviewer column precedes Sunil in right; output reverses column sequence.',
      19:'KS Gangadhara in left reviewer column precedes Man Prakash in right; output reverses columns.'}
    for metric in ['M05','M11','M12','M16']:
        rows=json.loads((dest/f'{metric}_packets.json').read_text('utf8'))
        for r in rows:
            i=r['index'];kind=r['error_kind']
            if metric=='M05':
                verdict='float_anchor_convention_and_layout' if i==11 else 'layout_column_or_group_order'
                note=order_notes[i]
            elif metric=='M12':
                verdict='heading_hierarchy_role' if kind=='heading_level' else 'heading_merged_or_not_recognized'
                note=('Visible standalone heading is detected but assigned a different reference nesting level. Absolute DocBook depth includes parent structure; preserve this convention discrepancy separately from missing visual heading.' if kind=='heading_level' else 'Visible standalone blue/section heading was not matched as a heading by frozen structure-stage evidence. Source context confirms the title, with callouts/figures/columns nearby.')
                if i==11:note+=' Chapter title is also classified front_section_title on a body page.'
            elif metric=='M16':
                verdict='reference_link_markup_not_preserved_visual_interactivity_unclear'
                note='Rendered original contains the figure/table/chapter reference recorded in token context. XML marks it as a link, while aligned output emits no link span. This is a reference-markup recall failure; a raster cannot establish whether the PDF itself provides an interactive link. Do not equate it with a visible-font failure.'
            elif kind=='wrong_link':
                verdict='continuation_wrong_endpoint'
                note=('Source stapes option b and next-page option c are distinct items, not one continued item.' if r['page']==50 else 'Macula sentence continues in next-page left column; link instead jumps to right-column arterial-supply text. Real continuation bypassed.')
            elif kind=='all_reference_cross_page_rows':
                verdict='role_and_boundary_prevent_continuation'
                note='Frozen archive-stage reference paragraph is split across the two pages without its expected join. Source shows a sentence continuation. Intervening float, wrong role or fragmented ownership prevents the join.'
                if r['unit']==1061:note+=' Published JSON does join the aligned body endpoints, but its leading next-page fragment is classified caption. Archive-stage miss and published link identity are separate measures.'
            else:
                verdict='within_page_fragmentation_or_reference_boundary'
                note='Source reference unit is fragmented in the frozen archive ownership/column-join view. These rows are called column splits by the evaluator; they do not all cross a physical column. Several fragments are parts of one printed line/list item.'
                if r['unit']==107:note+=' Metadata Email label and address are separate source fragments on one line; reference paragraph grouping is a convention, not missing text.'
            append_judgment({'judgment_id':f'ent_textbook:taxonomy:{metric}:'+r['target_id'],'book_id':'ent_textbook','family':'taxonomy:'+metric,'target_id':r['target_id'],'crop_paths':r['crop_paths'],'context_paths':r['context_paths'],'selected_evidence':r,'agent_verdict':verdict,'notes':note+' General causes only; no scorer, converter, threshold or profile change made.','viewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    print('77 explicit taxonomy judgments recorded',flush=True)

if __name__=='__main__':main()
