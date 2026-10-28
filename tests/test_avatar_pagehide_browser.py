"""Functional probe for real navigation teardown and persisted-page behavior."""
import json
import os
from pathlib import Path
import shutil
import pytest
from tests.avatar_integration_support import baseline_server, PROBE


pytestmark=pytest.mark.skipif(os.getenv("CSS_AVATAR_BASELINE") != "1", reason="Opt-in real navigation lifecycle check")

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
        before=page.evaluate("""()=>{const w=document.querySelector('.avwrap[data-interactive]');
          window.cachedAvatarAnimations=w.getAnimations({subtree:true}).filter(a=>a.playState==='running');
          return cachedAvatarAnimations.length;}""")
        assert before>0
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
        preserved=page.evaluate("""()=>{const w=document.querySelector('.avwrap[data-interactive]');
          const animations=w.getAnimations({subtree:true});
          return {paused:w.dataset.motionPaused==='1',running:animations.filter(a=>a.playState==='running').length,
            retained:cachedAvatarAnimations.every(a=>animations.includes(a)&&a.playState==='paused')};}""")
        assert preserved=={'paused':True,'running':0,'retained':True}, preserved
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
        page.wait_for_function("document.querySelector('.avwrap[data-interactive]').dataset.motionPaused==='0'")
        assert page.evaluate("cachedAvatarAnimations.every(a=>a.playState==='running')"), 'Cached-page animations must resume'
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
