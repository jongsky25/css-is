"""Blank-page empty timer control for browser CPU emulation, diagnostic only."""
import json
import os
from pathlib import Path
import shutil
import time
import pytest
from tests.test_avatar_baseline_browser import baseline_server,reset,snapshot
from tests.test_avatar_native_control import PURE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_THROTTLE_DIAGNOSTIC')!='1',reason='Opt-in empty timer control')


def test_empty_callback_cpu_control(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,_,_=baseline_server
    out=Path(os.environ['CSS_AVATAR_OUT']).parent;out.mkdir(parents=True,exist_ok=True);rows=[]
    with sync_playwright() as pw:
        for run in range(3):
            for cpu in ([1,4] if run%2==0 else [4,1]):
                browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
                context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,timezone_id='UTC')
                def route(request):
                    if request.request.url.endswith('/empty.js'):
                        request.fulfill(content_type='text/javascript',body='setInterval(function emptyTick(){},80);')
                    else:request.fulfill(content_type='text/html',body='<html><body><button style="width:130px;height:170px">Control</button><script src="/empty.js"></script></body></html>')
                context.route('**/*',route);context.add_init_script(PURE)
                page=context.new_page();cdp=context.new_cdp_session(page);cdp.send('Emulation.setCPUThrottlingRate',{'rate':cpu})
                page.goto(origin+'/empty-control');page.goto(origin+'/empty-control');page.wait_for_timeout(500)
                reset(page);start=page.evaluate('()=>{avatarLoafs=[];avatarLoafObserver.takeRecords();return performance.now()}')
                deadline=time.monotonic()+30;action=0
                while time.monotonic()<deadline:
                    box=page.locator('button').bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
                    page.mouse.move(x,y);page.mouse.down();page.wait_for_timeout(500 if action%3==0 else 50)
                    if action%3==0:page.mouse.move(x+15,y+10,steps=3)
                    page.mouse.up();page.wait_for_timeout(350);action+=1
                end=page.evaluate('performance.now()')
                loafs=page.evaluate('()=>{avatarLoafObserver.takeRecords().forEach(avatarLoafCapture);return avatarLoafs}')
                scripts=[s for l in loafs for s in l['scripts'] if s['sourceURL'].endswith('/empty.js') and s['executionStart']<end and s['executionStart']+s['duration']>=start]
                observed=snapshot(page,cdp)
                rows.append({'cpu':cpu,'run':run,'actions':action,'start_ms':start,'end_ms':end,'scenario':observed,'native_long_animation_frames':loafs,'empty_scripts':scripts,'max_empty_callback_ms':max((s['duration'] for s in scripts),default=0)})
                (out/'empty-control.json').write_text(json.dumps({'diagnostic_only':True,'source':'setInterval(function emptyTick(){},80);','method':'Blank page: no avatars or app JS/CSS, same mobile viewport, CPU1/4, Date/seed, native probes and30s input. No API wrappers or kernel sampler.','samples':rows},indent=2))
                print(run,cpu,'frame',observed['frame_p95_ms'],'empty',rows[-1]['max_empty_callback_ms'],flush=True)
                context.close();browser.close()
    assert len(rows)==6
