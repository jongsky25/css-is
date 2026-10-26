"""Functional probe for real navigation teardown and persisted-page behavior."""
import json
import os
from pathlib import Path
import shutil
import pytest
from tests.test_avatar_baseline_browser import baseline_server, PROBE


pytestmark=pytest.mark.skipif(os.getenv("CSS_AVATAR_LIFECYCLE") != "1", reason="Opt-in real navigation lifecycle check")

def test_pagehide_cleanup(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    observations=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='UTC',service_workers='block')
        context.add_cookies([cookie]);context.add_init_script(PROBE)
        page=context.new_page()
        page.goto(origin+'/?view=me');page.wait_for_timeout(500)
        before=page.evaluate("document.querySelector('.avwrap[data-interactive]').getAnimations({subtree:true}).filter(a=>a.playState==='running').length")
        assert before>0
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
        preserved=page.evaluate("document.querySelector('.avwrap[data-interactive]').getAnimations({subtree:true}).filter(a=>a.playState==='running').length")
        assert preserved==before, 'Cached-page animations must survive'
        page.evaluate('''()=>{const element=document.createElement('div');element.id='outside-avatar-animation';document.body.append(element);
          element.animate([{opacity:0},{opacity:1}],{duration:1000,iterations:Infinity});
          window.addEventListener('pagehide',event=>sessionStorage.setItem('avatar-cleanup-probe',JSON.stringify({persisted:event.persisted,
            avatar:document.querySelector('.avwrap[data-interactive]').getAnimations({subtree:true}).filter(a=>a.playState==='running').length,
            outside:element.getAnimations().filter(a=>a.playState==='running').length})));}''')
        page.goto(origin+'/me')
        value=page.evaluate("sessionStorage.getItem('avatar-cleanup-probe')")
        if value:observations.append(json.loads(value))
        context.close();browser.close()
    out=Path(os.environ['CSS_AVATAR_OUT']);out.mkdir(parents=True,exist_ok=True)
    (out/'pagehide-behavior.json').write_text(json.dumps({'before':before,'preserved':preserved,'observations':observations},indent=2))
    assert len(observations)==1 and observations[0]=={'persisted':False,'avatar':0,'outside':1}
