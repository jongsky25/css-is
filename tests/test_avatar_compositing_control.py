"""Matched current-art CSS hint trial; test-only until all gates pass."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import pytest
from tests.test_avatar_baseline_browser import baseline_server,reset,snapshot
from tests.test_avatar_native_control import PURE
pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_COMPOSITING_DIAGNOSTIC')!='1',reason='Opt-in compositing trial')

@pytest.mark.parametrize('kind',os.getenv('CSS_AVATAR_COMPOSITING_KINDS','mushroom').split(','))
def test_compositing_control(baseline_server,app_mod,kind):
    import storage as st
    from playwright.sync_api import sync_playwright
    origin,cookie,uid=baseline_server
    conn=st.connect(app_mod.DB);st.set_user_avatar(conn,uid,kind,'Native Control');conn.close()
    out=Path(os.environ['CSS_AVATAR_OUT']).parent/kind;out.mkdir(parents=True,exist_ok=True);rows=[]
    css='.avwrap[data-interactive] svg[data-avatar-art="v2"],.avwrap[data-interactive] .avstage{will-change:transform}'
    with sync_playwright() as pw:
        for run in range(5):
            for variant in (['current','promoted'] if run%2==0 else ['promoted','current']):
                browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
                assert browser.version=='154.0.8037.57'
                context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,timezone_id='UTC',service_workers='block')
                context.add_cookies([cookie]);context.add_init_script(PURE)
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                cdp=context.new_cdp_session(page);cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
                page.goto(origin+'/?view=me');page.goto(origin+'/?view=me')
                page.add_style_tag(content=css if variant=='promoted' else '/* current */');page.wait_for_timeout(500)
                assert page.locator(f'.avwrap[data-interactive] svg[data-avatar-kind="{kind}"][data-avatar-stage="6"]').count()==1
                computed=page.evaluate('''()=>{const w=document.querySelector('.avwrap[data-interactive]');return {root:getComputedStyle(w.querySelector('svg')).willChange,stage:getComputedStyle(w.querySelector('.avstage')).willChange}}''')
                reset(page);start=page.evaluate('()=>{avatarLoafs=[];avatarLoafObserver.takeRecords();return performance.now()}')
                deadline=time.monotonic()+30;action=0
                while time.monotonic()<deadline:
                    box=page.locator('.av-play-btn').bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
                    page.mouse.move(x,y);page.mouse.down();page.wait_for_timeout(500 if action%3==0 else 50)
                    if action%3==0:page.mouse.move(x+15,y+10,steps=3)
                    page.mouse.up();page.wait_for_timeout(350);action+=1
                end=page.evaluate('performance.now()')
                loafs=page.evaluate('()=>{avatarLoafObserver.takeRecords().forEach(avatarLoafCapture);return avatarLoafs}')
                scripts=[s for l in loafs for s in l['scripts'] if ('/static/js/avatars.js' in s['sourceURL'] or '/static/js/avatar-audio.js' in s['sourceURL']) and s['executionStart']<end and s['executionStart']+s['duration']>=start]
                observed=snapshot(page,cdp)
                rows.append({'kind':kind,'run':run,'variant':variant,'computed_will_change':computed,'cpu':4,'mature':True,'seconds':30,'actions':action,'start_ms':start,'end_ms':end,'scenario':observed,'native_long_animation_frames':loafs,'owned_scripts':scripts,'max_owned_script_ms':max((s['duration'] for s in scripts),default=0),'errors':errors})
                (out/'compositing-control.json').write_text(json.dumps({'diagnostic_only':True,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'runtime_sha256':hashlib.sha256(Path('static/js/avatars.js').read_bytes()).hexdigest(),'css_candidate':css,'same_current_art_and_runtime':True,'samples':rows},indent=2))
                print(kind,variant,run,'frame',observed['frame_p95_ms'],'owned',rows[-1]['max_owned_script_ms'],flush=True)
                if run==0:page.screenshot(path=str(out/f'{variant}.png'))
                context.close();browser.close()
    promoted=[r for r in rows if r['variant']=='promoted']
    result={'passed':len(promoted)==5 and all(r['scenario']['frame_p95_ms']<=33 and r['max_owned_script_ms']<=50 and not r['errors'] for r in promoted),'current_frame_values':[r['scenario']['frame_p95_ms'] for r in rows if r['variant']=='current'],'promoted_frame_values':[r['scenario']['frame_p95_ms'] for r in promoted],'promoted_owned_values':[r['max_owned_script_ms'] for r in promoted]}
    (out/'assessment.json').write_text(json.dumps(result,indent=2))
    assert len(rows)==10 and not any(r['errors'] for r in rows)
