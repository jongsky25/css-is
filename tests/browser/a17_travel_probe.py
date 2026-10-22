"""Pinned local A17 travel accessibility evidence; outside ordinary test collection."""
import hashlib
import json
import os
from pathlib import Path

import storage as st
import travel
import travel_rules as rules
from tests.conftest import join_admin_section
from tests.test_travel_guidance_browser import browser, conn, travel_page, relay, mk, complete


def test_probe(travel_page,viewer,relay):
    page,state,c,context=travel_page
    engine=Path(os.environ['A17_AXE_PATH'])
    uid=st.get_admin_user(c,'viewer@test.local')['id'];join_admin_section(c,uid)
    results=[]

    def scan(surface,width,theme):
        page.evaluate('(t)=>document.documentElement.dataset.theme=t',theme)
        page.add_script_tag(path=str(engine))
        assert page.evaluate('axe.version')=='4.14.0'
        result=page.evaluate('''async () => {
          const r=await axe.run(document,{runOnly:{type:'tag',values:[
            'wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}});
          const items=vs=>vs.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));
          return {violations:items(r.violations),incomplete:items(r.incomplete),
            overflow:document.documentElement.scrollWidth>innerWidth};
        }''')
        result.update(surface=surface,width=width,theme=theme);results.append(result)

    for theme in ('light','dark'):
        for width in (1440,390):
            page.set_viewport_size({'width':width,'height':1000 if width>400 else 844})
            ref=mk(viewer);url=f'/travel/f/{ref}'
            page.goto('/travel');scan('My filings',width,theme)
            page.goto(url);scan('Missing checklist',width,theme)
            if width==390 and theme=='light':page.screenshot(path='/tmp/a17-travel-detail-mobile.png',full_page=False)
            page.goto(url+'#travel-answers')
            page.locator('#dpo_no').fill('Retained draft DPO')
            page.locator('#advance_amount').fill('bad amount')
            page.get_by_role('button',name='Save answers',exact=True).click();scan('Answer recovery',width,theme)
            f=complete(c,travel.get_by_ref(c,ref))
            rev=travel.start_generation(c,f,['appendix_a'])['appendix_a']
            page.goto(url);scan('Pending replacement with earlier copy',width,theme)
            travel.finish_item(c,f['id'],'appendix_a',rev,error='Example form attempt failed')
            travel.finish_generation(c,f['id'])
            page.goto(url);scan('Failed replacement with earlier copy',width,theme)
            page.goto(url+'/prepare');page.wait_for_selector('.tv-docs li');scan('Prepare forms with failed attempt',width,theme)
            pattern=f'**/travel/f/{ref}/status';failure=lambda route:route.fulfill(status=503,body='Unavailable')
            page.route(pattern,failure);page.reload();page.get_by_role('button',name='Check form progress',exact=True).wait_for()
            scan('Form progress read recovery',width,theme);page.unroute(pattern,failure)
            # A successful manual copy clears the attempt failure for subsequent filing stages.
            f=complete(c,travel.get_by_ref(c,ref))
            c.execute("UPDATE travel_filing SET gen_state='done' WHERE id=?",(f['id'],));c.commit()
            travel.sync_flags(c,f,[rules.FlagSpec('participant_only','example-role','Participant-only travel')])
            flag=travel.flags_of(c,f['id'])[0]
            page.goto(url);scan('Waiting for flag review',width,theme)
            page.goto('/travel/verify')
            row=page.locator(f"#flag-{flag['id']}")
            row.get_by_role('textbox',name='Note (needed to reject)').fill('Retained reviewer note')
            row.get_by_role('button',name='Verified',exact=True).click();scan('Supervisor confirmation recovery',width,theme)
            travel.decide_flag(c,flag,'example-reviewer','rejected','Please correct the details')
            page.goto(url);scan('Rejected flag and reason',width,theme)
            travel.decide_flag(c,flag,'example-reviewer','verified',supervisor_confirmed=True)
            f=travel.mark_ready(c,travel.get_filing(c,f['id']))
            page.goto(url+'/ready');scan('Ready to print and sign',width,theme)
            travel.mark_submitted(c,f)
            page.goto(url+'/ready');scan('Paper submission recorded',width,theme)
            closed=travel.get_by_ref(c,mk(viewer));travel.withdraw(c,closed)
            page.goto('/travel/f/'+closed['ref_code']);scan('Withdrawn filing',width,theme)
    report={'scope':'Synthetic local travel workflows; manual screen-reader/zoom/forced-color/staff review pending',
        'engine':{'version':'4.14.0','sha256':hashlib.sha256(engine.read_bytes()).hexdigest()},
        'browser':context.browser.version,'results':results,
        'totals':{'states':len(results),'violations':sum(len(r['violations']) for r in results),
            'incomplete':sum(len(r['incomplete']) for r in results),'overflows':sum(r['overflow'] for r in results)}}
    Path(os.environ['A17_REPORT']).write_text(json.dumps(report,indent=2)+'\n')
    assert report['totals']['violations']==0,report['totals']
    assert report['totals']['overflows']==0,report['totals']
