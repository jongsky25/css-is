"""Supplemental lifecycle/picker observations; records existing failures, never patches them."""
import json, shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

out=Path('docs/avatars/baseline'); out.mkdir(parents=True,exist_ok=True)
rows=[]
with sync_playwright() as pw:
    b=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
    for scene in ['home','picker']:
        c=b.new_context(viewport={'width':1440,'height':1000}); p=c.new_page()
        p.goto('http://127.0.0.1:8765/?scene='+scene)
        p.wait_for_timeout(500)
        def state(label):
            rows.append({'scene':scene,'state':label,**p.evaluate('''()=>({hidden:document.hidden,
animations:document.getAnimations().map(a=>({state:a.playState,target:a.effect.target.getAttribute('class')})),
nodes:document.querySelectorAll('*').length})''')})
        state('visible')
        p.evaluate("document.querySelector('main').style.marginTop='2000px'"); p.wait_for_timeout(1000); state('offscreen')
        p.emulate_media(reduced_motion='reduce'); p.wait_for_timeout(500); state('reduced-motion')
        # Actual same-document detach/mount cycles expose retained document listeners.
        session=c.new_cdp_session(p)
        def counts():
            return session.send('Runtime.evaluate',{'expression':"Object.fromEntries(Object.entries(getEventListeners(document)).map(([k,v])=>[k,v.length]))",'includeCommandLineAPI':True,'returnByValue':True})['result']['value']
        before=counts()
        p.evaluate("window.fixture=document.querySelector('main').innerHTML")
        for i in range(20):
            p.evaluate("document.querySelector('main').innerHTML=window.fixture")
            p.wait_for_timeout(250)
        rows.append({'scene':scene,'state':'20-mounts','document_listeners_before':before,'document_listeners_after':counts()})
        c.close()
    b.close()
(out/'lifecycle.json').write_text(json.dumps(rows,indent=2))
