"""Explicit local A17 calendar axe evidence, outside ordinary test discovery."""
import hashlib
import json
import os
from pathlib import Path

import storage as st
from tests.test_calendar_guidance_browser import browser, conn, calendar_page, make, DAY


def test_probe(calendar_page):
    page,state,c,context=calendar_page
    engine=Path(os.environ['A17_AXE_PATH'])
    eid=make(c)
    cancelled=make(c,title='CALEP Cancelled')
    st.cal_cancel(c,cancelled)
    expired=make(c,title='CALEP Restore period ended')
    st.cal_cancel(c,expired)
    c.execute("UPDATE calendar_entry SET cancelled_at='2020-01-01T00:00:00' WHERE id=?",(expired,));c.commit()
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

    uid=st.get_admin_user(c,'viewer@test.local')['id']
    for theme in ('light','dark'):
        for width in (1440,390):
            page.set_viewport_size({'width':width,'height':1000 if width>400 else 844})
            st.cal_update(c,eid,status='confirmed',venue='Example room')
            page.goto('/calendar?day='+DAY);scan('Agenda',width,theme)
            page.locator(f'.cal-tt[href="/calendar/entries/{eid}"]').first.click()
            page.wait_for_selector('#cal-sheet .cal-guidance')
            scan('Item preview',width,theme)
            page.keyboard.press('Escape')
            page.locator('.cal-dayadd').first.click();scan('Quick add',width,theme)
            page.keyboard.press('Escape')
            for status in ('confirmed','tentative','postponed'):
                st.cal_update(c,eid,status=status)
                page.goto(f'/calendar/entries/{eid}');scan(status.capitalize()+' detail',width,theme)
                if width==390 and theme=='light' and status=='tentative':page.screenshot(path='/tmp/a17-calendar-detail-mobile.png',full_page=False)
            page.goto(f'/calendar/entries/{cancelled}');scan('Cancelled detail',width,theme)
            page.goto(f'/calendar/entries/{expired}');scan('Expired restore detail',width,theme)
            page.goto(f'/calendar/entries/{eid}/cancel');scan('Cancellation review',width,theme)
            page.goto(f'/calendar/entries/{eid}/edit')
            page.locator('input[name=venue]').fill('Draft venue')
            c.execute("UPDATE calendar_entry SET updated_at='2099-01-01T00:00:00' WHERE id=?",(eid,));c.commit()
            page.get_by_role('button',name='Save changes',exact=True).click();scan('Edit conflict',width,theme)
            if width==390 and theme=='light':page.screenshot(path='/tmp/a17-calendar-conflict-mobile.png',full_page=False)
            page.goto('/calendar/new?day='+DAY)
            page.locator('input[name=title]').fill('CALEP Invalid date range')
            page.locator('select[name=audience]').select_option('bureau')
            page.locator('input[name=end_date]').fill('2026-10-01')
            page.get_by_role('button',name='Add to the calendar',exact=True).click();scan('Validation recovery',width,theme)
            st.feed_off(c,uid)
            page.goto('/me#calendar-feed');page.locator('.feed-help summary').click();scan('Subscription off and help',width,theme)
            page.get_by_role('button',name='Create my calendar link').click()
            page.locator('.feed-help summary').click();scan('Subscription active and help',width,theme)
    report={'scope':'Synthetic local calendar journeys; manual screen-reader/zoom/forced-color/staff review pending',
        'engine':{'version':'4.14.0','sha256':hashlib.sha256(engine.read_bytes()).hexdigest()},
        'browser':context.browser.version,'results':results,
        'totals':{'states':len(results),'violations':sum(len(r['violations']) for r in results),
            'incomplete':sum(len(r['incomplete']) for r in results),'overflows':sum(r['overflow'] for r in results)}}
    # Keep only selectors/diagnostics; never retain the private feed URL or token.
    raw=json.dumps(report,indent=2)
    import re
    raw=re.sub(r'(/calendar/feed/)[A-Za-z0-9_-]+',r'\1[REDACTED]',raw)
    Path(os.environ['A17_REPORT']).write_text(raw+'\n')
    assert report['totals']['violations']==0,report['totals']
    assert report['totals']['overflows']==0,report['totals']
