"""Opt-in shared geometry observation and actual discarded-page teardown."""
import json
import os
from pathlib import Path
import shutil
import pytest
from tests.test_avatar_baseline_browser import baseline_server,PROBE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in browser verification')


def test_shared_geometry_observer_and_navigation_teardown(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='UTC')
        context.add_cookies([cookie]);context.add_init_script(PROBE)
        context.add_init_script('''(()=>{const Native=ResizeObserver;window.geometryObserverRecords=[];
          window.ResizeObserver=class extends Native{constructor(cb){super(cb);this.targets=new Set();geometryObserverRecords.push(this)}
            observe(el,options){this.targets.add(el);return super.observe(el,options)}
            unobserve(el){this.targets.delete(el);return super.unobserve(el)}
            disconnect(){this.targets.clear();return super.disconnect()}};})()''')
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(origin+'/?view=me');page.wait_for_timeout(500)
        page.evaluate('''()=>{const wrap=document.querySelector('.avwrap[data-interactive]');const copy=wrap.cloneNode(true);
          copy.id='geometry-extra-wrap';wrap.parentNode.appendChild(copy)}''')
        page.wait_for_timeout(400)
        before=page.evaluate('''()=>{const wraps=[...document.querySelectorAll('.avwrap[data-interactive]')],o=__cssAvatarGeometry.bodyObserver;
          return {wraps:wraps.length,observed:wraps.every(w=>o.targets.has(w)),body:o.targets.has(document.body),
            owners:geometryObserverRecords.filter(r=>wraps.some(w=>r.targets.has(w))).length}}''')
        assert before=={'wraps':2,'observed':True,'body':True,'owners':1}
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
        assert page.evaluate('__cssAvatarGeometry.bodyObserver.targets.size')>=3
        page.evaluate('''()=>{window.addEventListener('pagehide',e=>sessionStorage.setItem('geometry-pagehide',JSON.stringify({
          persisted:e.persisted,observerReleased:__cssAvatarGeometry.bodyObserver===null,rafReleased:__cssAvatarGeometry.raf===null,
          observedAvatarTargets:geometryObserverRecords.reduce((n,r)=>n+[...r.targets].filter(t=>t.matches?.('.avwrap[data-interactive]')).length,0)})))}''')
        page.goto(origin+'/me')
        after=json.loads(page.evaluate("sessionStorage.getItem('geometry-pagehide')"))
        assert after=={'persisted':False,'observerReleased':True,'rafReleased':True,'observedAvatarTargets':0}
        assert not errors
        context.close();browser.close()
    out=Path(os.environ['CSS_AVATAR_OUT']);out.mkdir(parents=True,exist_ok=True)
    (out/'geometry-lifecycle.json').write_text(json.dumps({'before':before,'after':after,'errors':errors},indent=2)+'\n')
