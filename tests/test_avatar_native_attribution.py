"""Opt-in mature-plant checks using native LoAF attribution, no trace recorder."""
import json
import os
from pathlib import Path
import shutil
import time

import pytest
from tests.test_avatar_baseline_browser import baseline_server, PROBE, snapshot, reset

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in native attribution')

# Reuse the original timer source capture; do not capture stacks on every rAF.
CALL="if(typeof callback==='function')callback(...passed);else (0,eval)(callback);"
TIMED="""const began=performance.now();try { if(typeof callback==='function')callback(...passed);else (0,eval)(callback); }
finally { if(/avatars\\.js|avatar-audio\\.js/.test(source))avatarTimerDurations.push({source,start:began,duration:performance.now()-began}); }"""
assert PROBE.count(CALL)==1
NATIVE_PROBE='window.avatarTimerDurations=[];\n'+PROBE.replace(CALL,TIMED)+r'''
window.avatarLoafs=[];
window.avatarLoafCapture=e=>avatarLoafs.push({start:e.startTime,duration:e.duration,blocking:e.blockingDuration,
 renderStart:e.renderStart,styleAndLayoutStart:e.styleAndLayoutStart,
 scripts:e.scripts.map(s=>({duration:s.duration,executionStart:s.executionStart,forcedStyleAndLayoutDuration:s.forcedStyleAndLayoutDuration,
 sourceURL:s.sourceURL,sourceFunctionName:s.sourceFunctionName,sourceCharPosition:s.sourceCharPosition,
 invoker:s.invoker,invokerType:s.invokerType,pauseDuration:s.pauseDuration}))});
window.avatarLoafSupported=PerformanceObserver.supportedEntryTypes.includes('long-animation-frame');
if(avatarLoafSupported){window.avatarLoafObserver=new PerformanceObserver(l=>l.getEntries().forEach(avatarLoafCapture));avatarLoafObserver.observe({type:'long-animation-frame',buffered:true})}
'''


def test_native_mature_plant_budget(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    kind=os.environ['CSS_AVATAR_KIND'];out=Path(os.environ['CSS_AVATAR_OUT']).parent;rows=[]
    with sync_playwright() as pw:
        for run in range(5):
            browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
            assert browser.version=='154.0.8037.57'
            context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,timezone_id='UTC',service_workers='block')
            context.add_cookies([cookie]);context.add_init_script(NATIVE_PROBE)
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            cdp=context.new_cdp_session(page);cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
            assert page.goto(origin+'/?view=me').status==200
            assert page.goto(origin+'/?view=me').status==200
            page.wait_for_timeout(500)
            assert page.locator(f'.avwrap[data-interactive] svg[data-avatar-kind="{kind}"][data-avatar-stage="6"]').count()==1
            assert page.evaluate('avatarLoafSupported')
            reset(page)
            start=page.evaluate('''()=>{avatarTimerDurations=[];avatarLoafs=[];avatarLoafObserver.takeRecords();return performance.now()}''')
            deadline=time.monotonic()+30;action=0
            while time.monotonic()<deadline:
                box=page.locator('.av-play-btn').bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
                page.mouse.move(x,y);page.mouse.down();page.wait_for_timeout(500 if action%3==0 else 50)
                if action%3==0:page.mouse.move(x+15,y+10,steps=3)
                page.mouse.up();page.wait_for_timeout(350);action+=1
            end=page.evaluate('performance.now()')
            native=page.evaluate('''()=>{avatarLoafObserver.takeRecords().forEach(avatarLoafCapture);return {timers:avatarTimerDurations,loafs:avatarLoafs}}''')
            observed=snapshot(page,cdp)
            timers=[t for t in native['timers'] if start<=t['start']<end]
            loafs=[l for l in native['loafs'] if l['start']<end and l['start']+l['duration']>=start]
            scripts=[dict(s,sourceURL=s['sourceURL'].replace(origin,'')) for l in loafs for s in l['scripts'] if '/static/js/avatars.js' in s['sourceURL'] or '/static/js/avatar-audio.js' in s['sourceURL']]
            assert timers, 'Existing timer-source attribution produced no records'
            maximum=max([t['duration'] for t in timers]+[s['duration'] for s in scripts],default=0)
            rows.append({'run':run,'kind':kind,'mature':True,'cpu':4,'seconds':30,'actions':action,'scenario':observed,
                         'timer_callbacks':timers,'native_long_animation_frames':loafs,'avatar_native_scripts':scripts,
                         'max_avatar_callback_ms':maximum,'callback_gate_passed':maximum<=50,'frame_gate_passed':observed['frame_p95_ms']<=33,'errors':errors})
            (out/'native-attribution.json').write_text(json.dumps({'source_commit':'00d76bc','kind':kind,'browser':browser.version,'method':'Five fresh warm CPU4 mobile runs, mature6, original30s input. OriginalPROBE plus two clock reads in existing avatar timer wrappers and native long-animation-frame attribution. No tracing recorder, per-rAF stack capture or event/RAF wrappers.','samples':rows},indent=2))
            print(kind,run,'frame',observed['frame_p95_ms'],'max_callback',maximum,flush=True)
            context.close();browser.close()
    assert all(not r['errors'] and r['callback_gate_passed'] and r['frame_gate_passed'] for r in rows),'Native mature-plant budget failed; every sample preserved'
