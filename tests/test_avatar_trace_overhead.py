"""Opt-in counterbalanced recorder-overhead study, with direct source timings."""
import json
import os
from pathlib import Path
import shutil
import time

import pytest
from tests.test_avatar_baseline_browser import baseline_server, PROBE, snapshot, reset

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in overhead study')

DURATIONS=r'''(()=>{
window.avatarCallbackDurations=[];
const source=()=>new Error().stack.split('\n').find(s=>/avatars\.js|avatar-audio\.js/.test(s));
const timed=(fn,src,type)=>function(...args){const start=performance.now();try{return fn.apply(this,args)}finally{avatarCallbackDurations.push({source:src,type,start,duration:performance.now()-start})}};
for(const name of ['setTimeout','setInterval','requestAnimationFrame']){
 const native=window[name];window[name]=function(fn,...args){const src=source();return native.call(window,src&&typeof fn==='function'?timed(fn,src,name):fn,...args)};
}
const add=EventTarget.prototype.addEventListener;
EventTarget.prototype.addEventListener=function(type,fn,options){const src=source();return add.call(this,type,src&&typeof fn==='function'?timed(fn,src,'event:'+type):fn,options)};
})();'''


def test_trace_recorder_overhead(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    out=Path(os.environ['CSS_AVATAR_OUT']).parent;rows=[]
    with sync_playwright() as pw:
        for run in range(5):
            for traced in ([False,True] if run%2==0 else [True,False]):
                # Match the existing focused protocol: a fresh browser per version.
                browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
                context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,timezone_id='UTC',service_workers='block')
                context.add_cookies([cookie]);context.add_init_script(PROBE+'\n'+DURATIONS)
                page=context.new_page();cdp=context.new_cdp_session(page)
                cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
                page.goto(origin+'/?view=me');page.goto(origin+'/?view=me');page.wait_for_timeout(500)
                done=[]
                if traced:
                    cdp.on('Tracing.tracingComplete',lambda e:done.append(e))
                    cdp.send('Tracing.start',{'categories':'toplevel,devtools.timeline,disabled-by-default-devtools.timeline.stack,v8.execute,blink.user_timing','transferMode':'ReturnAsStream'})
                reset(page);page.evaluate('avatarCallbackDurations=[]');deadline=time.monotonic()+30;action=0
                while time.monotonic()<deadline:
                    box=page.locator('.av-play-btn').bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
                    page.mouse.move(x,y);page.mouse.down();page.wait_for_timeout(500 if action%3==0 else 50)
                    if action%3==0:page.mouse.move(x+15,y+10,steps=3)
                    page.mouse.up();page.wait_for_timeout(350);action+=1
                observed=snapshot(page,cdp)
                durations=page.evaluate('avatarCallbackDurations')
                if traced:
                    cdp.send('Tracing.end')
                    while not done:page.wait_for_timeout(50)
                    stream=done[0]['stream'];chunks=[]
                    while True:
                        part=cdp.send('IO.read',{'handle':stream});chunks.append(part['data'])
                        if part.get('eof'):break
                    cdp.send('IO.close',{'handle':stream})
                    events=json.loads(''.join(chunks))['traceEvents']
                    calls=[]
                    for e in events:
                        d=e.get('args',{}).get('data',{})
                        if e.get('name')=='FunctionCall' and '/static/js/avatars.js' in d.get('url','') and e.get('dur',0)>50000:
                            calls.append({'duration_ms':e['dur']/1000,'cpu_ms':e.get('tdur',-1000)/1000,'line':d.get('lineNumber'),'function':d.get('functionName')})
                else:calls=[]
                rows.append({'run':run,'traced':traced,'seconds':30,'cpu':4,'kind':os.getenv('CSS_AVATAR_KIND','cat'),'mature':os.getenv('CSS_AVATAR_MATURE')=='1','actions':action,'scenario':observed,'callbacks':durations,'over_50ms_trace_calls':calls})
                (out/'recorder-overhead.json').write_text(json.dumps({'diagnostic_only':True,'method':'Five counterbalanced traced/untraced pairs, same final source and mature species, CPU4, original input sequence30s, same direct callback timer/RAF/event instrumentation both arms. No product or threshold changes.','samples':rows},indent=2))
                print('traced',traced,'run',run,'frame',observed['frame_p95_ms'],'max_callback',max((d['duration'] for d in durations),default=0),flush=True)
                context.close();browser.close()
