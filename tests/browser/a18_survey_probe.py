"""Explicit synthetic A18 browser/axe evidence; excluded from ordinary collection."""
import hashlib
import json
import os
from pathlib import Path

import i18n
import storage as st
import tzutil as tz
from tests.test_survey_guidance_browser import browser, survey_page, walkin, speaker_form, fill_csm


def test_probe(survey_page):
    page,context,c,token,state=survey_page
    engine=Path(os.environ['A18_AXE_PATH']);results=[]
    speaker=speaker_form(c)
    fid=st.create_form_instance(c,2,'F2',tz.today_local().isoformat(),topic='A18 activity feedback')
    activity=c.execute('SELECT qr_token FROM form_instance WHERE id=?',(fid,)).fetchone()[0]
    def scan(surface,lang,theme,width):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        page.add_script_tag(path=str(engine))
        assert page.evaluate('axe.version')=='4.14.0'
        data=page.evaluate('''async()=>{
          const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}});
          const items=vs=>vs.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));
          return {violations:items(r.violations),incomplete:items(r.incomplete),overflow:document.documentElement.scrollWidth>innerWidth};
        }''')
        data.update(surface=surface,language=lang,theme=theme,width=width);results.append(data)
    for language in ('en','fil'):
        context.set_extra_http_headers({'Accept-Language':language})
        submit=str(i18n.t('submit',language))
        for theme in ('light','dark'):
            for width in (390,1440):
                page.set_viewport_size({'width':width,'height':900})
                page.goto(f'/r/{token}');scan('CSM form',language,theme,width)
                page.get_by_role('button',name=submit,exact=True).click();scan('Correction summary',language,theme,width)
                page.locator('#conv-toggle').click();scan('One step at a time',language,theme,width)
                page.goto(f'/r/{activity}');scan('Activity form',language,theme,width)
                page.goto(f'/r/{speaker}');scan('Speaker form',language,theme,width)
                page.goto('/seq?tokens='+speaker);scan('Combined form',language,theme,width)
                page.goto(f'/r/{token}');fill_csm(page)
                page.get_by_role('button',name=submit,exact=True).click();scan('Server confirmation',language,theme,width)
                page.goto(f'/r/{token}');fill_csm(page);page.evaluate('window.testOffline=true')
                page.get_by_role('button',name=submit,exact=True).click();page.wait_for_selector('.offline-saved')
                scan('Device queue pending',language,theme,width)
                if width==390 and language=='fil' and theme=='light':page.screenshot(path='/tmp/a18-survey-mobile.png')
                page.evaluate('''async()=>{await new Promise((resolve,reject)=>{
                  const r=indexedDB.open('css_offline',1);r.onerror=reject;r.onsuccess=()=>{
                    const t=r.result.transaction('queue','readwrite');t.objectStore('queue').clear();t.oncomplete=()=>{r.result.close();resolve()};t.onerror=reject;
                  };});}''')
    report={'scope':'Synthetic local survey states; staff/screen-reader/real-device/provider review pending',
      'engine':{'version':'4.14.0','sha256':hashlib.sha256(engine.read_bytes()).hexdigest()},'browser':context.browser.version,'results':results,
      'totals':{'states':len(results),'violations':sum(len(r['violations']) for r in results),'incomplete':sum(len(r['incomplete']) for r in results),'overflows':sum(r['overflow'] for r in results)}}
    Path(os.environ['A18_REPORT']).write_text(json.dumps(report,indent=2)+'\n')
    assert report['totals']['violations']==0,report['totals']
    assert report['totals']['overflows']==0,report['totals']
