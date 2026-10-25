"""Native invoker diagnostics and strict frame gate; owned work needs a trace."""
from tests.avatar_browser_fixture import pin_renderer_threads
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest
from tests.test_avatar_baseline_browser import baseline_server, snapshot, reset

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in native control')

PURE=r'''(()=>{
const D=Date,epoch=D.parse('2026-07-15T12:00:00Z');window.Date=class extends D{constructor(...a){super(...(a.length?a:[epoch+performance.now()]))}static now(){return epoch+performance.now()}};
let seed=12345;Math.random=()=>((seed=(1664525*seed+1013904223)>>>0)/4294967296);localStorage.setItem('css_tour_optout','1');
window.avatarProbe={frames:[],long:[],events:[],lcp:0,timers:{},ticks:{}};window.avatarLoafs=[];
new PerformanceObserver(l=>l.getEntries().forEach(e=>avatarProbe.long.push({start:e.startTime,duration:e.duration,name:e.name}))).observe({type:'longtask',buffered:true});
new PerformanceObserver(l=>l.getEntries().forEach(e=>avatarProbe.lcp=e.startTime)).observe({type:'largest-contentful-paint',buffered:true});
new PerformanceObserver(l=>l.getEntries().forEach(e=>avatarProbe.events.push({name:e.name,duration:e.duration,processing:e.processingStart-e.startTime,interaction:e.interactionId}))).observe({type:'event',buffered:true,durationThreshold:16});
let last;function frame(t){if(last)avatarProbe.frames.push(t-last);last=t;requestAnimationFrame(frame)}requestAnimationFrame(frame);
window.avatarLoafCapture=e=>avatarLoafs.push({start:e.startTime,duration:e.duration,blocking:e.blockingDuration,renderStart:e.renderStart,styleAndLayoutStart:e.styleAndLayoutStart,
 scripts:e.scripts.map(s=>({duration:s.duration,executionStart:s.executionStart,forcedStyleAndLayoutDuration:s.forcedStyleAndLayoutDuration,sourceURL:s.sourceURL,sourceFunctionName:s.sourceFunctionName,sourceCharPosition:s.sourceCharPosition,invoker:s.invoker,invokerType:s.invokerType,pauseDuration:s.pauseDuration}))});
window.avatarLoafSupported=PerformanceObserver.supportedEntryTypes.includes('long-animation-frame');
if(avatarLoafSupported){window.avatarLoafObserver=new PerformanceObserver(l=>l.getEntries().forEach(avatarLoafCapture));avatarLoafObserver.observe({type:'long-animation-frame',buffered:true})}
})();'''


@pytest.mark.parametrize('kind',['fern','mushroom','succulent'])
def test_native_art_control(baseline_server,app_mod,tmp_path,kind):
    import storage as st
    from jinja2 import ChoiceLoader,FileSystemLoader
    from playwright.sync_api import sync_playwright
    origin,cookie,uid=baseline_server
    conn=st.connect(app_mod.DB);st.set_user_avatar(conn,uid,kind,'Native Control');conn.close()
    env=app_mod.templates.env;loader=env.loader
    folder=tmp_path/'old';folder.mkdir()
    for name in ['_avatars.html','_avatars_art.html']:(folder/name).write_bytes(subprocess.check_output(['git','show','5b580d9:templates/'+name]))
    loaders={'before':ChoiceLoader([FileSystemLoader(folder),loader]),'after':loader}
    after_only=os.getenv('CSS_AVATAR_NATIVE_AFTER_ONLY')=='1'
    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    out=Path(os.environ['CSS_AVATAR_OUT']).parent/kind;out.mkdir(parents=True,exist_ok=True);rows=[]
    try:
        with sync_playwright() as pw:
            for run in range(5):
                for version in (['after'] if after_only else (['before','after'] if run%2==0 else ['after','before'])):
                    env.loader=loaders[version]
                    browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
                    assert browser.version=='154.0.8037.57'
                    context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,timezone_id='UTC',service_workers='block')
                    context.add_cookies([cookie]);context.add_init_script(PURE)
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    cdp=context.new_cdp_session(page);cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
                    pins=pin_renderer_threads(browser)
                    assert os.getenv('CSS_AVATAR_PIN_RENDERER')!='1' or any(p['name'].startswith('CPUThrottling') for p in pins)
                    page.goto(origin+'/?view=me');page.goto(origin+'/?view=me');page.wait_for_timeout(500)
                    assert page.locator(f'.avwrap[data-interactive] svg[data-avatar-kind="{kind}"][data-avatar-stage="6"]').count()==1
                    assert page.evaluate('avatarLoafSupported')
                    reset(page);start=page.evaluate('''()=>{avatarLoafs=[];avatarLoafObserver.takeRecords();return performance.now()}''')
                    deadline=time.monotonic()+30;action=0
                    while time.monotonic()<deadline:
                        box=page.locator('.av-play-btn').bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
                        page.mouse.move(x,y);page.mouse.down();page.wait_for_timeout(500 if action%3==0 else 50)
                        if action%3==0:page.mouse.move(x+15,y+10,steps=3)
                        page.mouse.up();page.wait_for_timeout(350);action+=1
                    end=page.evaluate('performance.now()')
                    loafs=page.evaluate('''()=>{avatarLoafObserver.takeRecords().forEach(avatarLoafCapture);return avatarLoafs}''')
                    loafs=[l for l in loafs if l['start']<end and l['start']+l['duration']>=start]
                    scripts=[dict(s,sourceURL=s['sourceURL'].replace(origin,'')) for l in loafs for s in l['scripts'] if '/static/js/avatars.js' in s['sourceURL'] or '/static/js/avatar-audio.js' in s['sourceURL']]
                    observed=snapshot(page,cdp)
                    rows.append({'run':run,'version':version,'kind':kind,'mature':True,'cpu':4,'seconds':30,'thread_pins':pins,'actions':action,'start_ms':start,'end_ms':end,
                                 'scenario':observed,'native_long_animation_frames':loafs,'avatar_native_scripts':scripts,
                                 'max_avatar_callback_ms':max((s['duration'] for s in scripts),default=0),'errors':errors})
                    (out/'native-control.json').write_text(json.dumps({'source_commit':source_commit,'before_art':None if after_only else '5b580d9','after_only':after_only,'same_current_runtime_both_arms':not after_only,'kind':kind,'method':('Five final-source warm CPU4 mobile runs; mature6; original30s input; native LoAF/LongTask/EventTiming/rAF only; no API wrappers, tracing, callback clocks or stacks.' if after_only else 'Five counterbalanced warm CPU4 mobile pairs; mature6; original30s input; native LoAF/LongTask/EventTiming/rAF only. No timer/event/rAF wrappers, tracing recorder, callback clocks or stacks. Same current Home/search/runtime with old/new art/frame macros.'),'samples':rows},indent=2))
                    print(kind,version,run,'frame',observed['frame_p95_ms'],'max_callback',max((s['duration'] for s in scripts),default=0),flush=True)
                    context.close();browser.close()
    finally:env.loader=loader;env.cache.clear()
    assert len(rows)==(5 if after_only else 10) and all(not r['errors'] for r in rows)
    if after_only:
        assert all(r['scenario']['frame_p95_ms']<=33 for r in rows), 'Final native frame budget failed; all samples retained. Invoker wall duration is diagnostic; use direct FunctionCall tracing for owned50ms work.'
