"""Opt-in CPU4 interaction traces; test-only CSS variants never imply acceptance."""
import json
import hashlib
import subprocess
import os
from pathlib import Path
import shutil
import time

import pytest
from tests.test_avatar_baseline_browser import baseline_server, PROBE, snapshot, reset

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE') != '1', reason='Opt-in interaction diagnostic')


def test_interaction_trace(baseline_server):
    from playwright.sync_api import sync_playwright
    origin, cookie, _ = baseline_server
    out = Path(os.environ['CSS_AVATAR_OUT']).parent
    results = []
    variant = os.getenv('CSS_AVATAR_DIAG_VARIANT', 'promoted')
    assert variant in ['promoted', 'contain', 'batched']
    idle = int(os.getenv('CSS_AVATAR_DIAG_IDLE_SECONDS', '30'))
    css = '.avwrap[data-interactive] .av-play-btn{contain:layout}' if variant == 'contain' else '.avwrap[data-interactive] svg[data-avatar-art="v2"]{will-change:transform}'
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
        for run in range(int(os.getenv('CSS_AVATAR_DIAG_RUNS', '3'))):
            for version in (['current'] if os.getenv('CSS_AVATAR_DIAG_CURRENT_ONLY') == '1' else (['current', variant] if run % 2 == 0 else [variant, 'current'])):
                context = browser.new_context(viewport={'width':390,'height':844}, has_touch=True, timezone_id='UTC', service_workers='block')
                context.add_cookies([cookie]); context.add_init_script(PROBE)
                runtime = None
                if variant == 'batched':
                    runtime = subprocess.check_output(['git','show','853c93d:static/js/avatars.js']) if version == 'current' else Path('static/js/avatars.js').read_bytes()
                    context.route('**/static/js/avatars.js*', lambda route: route.fulfill(body=runtime, content_type='text/javascript'))
                page = context.new_page(); cdp = context.new_cdp_session(page)
                cdp.send('Network.enable'); cdp.send('Network.setBlockedURLs', {'urls':['https://*']})
                cdp.send('Emulation.setCPUThrottlingRate', {'rate':4}); cdp.send('Network.clearBrowserCache')
                assert page.goto(origin+'/?view=me').status == 200
                if version != 'current' and variant != 'batched':
                    page.add_style_tag(content=css)
                page.wait_for_timeout(idle*1000)
                cdp.send('Performance.enable', {'timeDomain':'threadTicks'})
                cpu_before = cdp.send('Performance.getMetrics')
                done = []
                cdp.on('Tracing.tracingComplete', lambda e: done.append(e))
                cdp.send('Tracing.start', {'categories':'toplevel,devtools.timeline,disabled-by-default-devtools.timeline.stack,v8.execute,blink.user_timing', 'transferMode':'ReturnAsStream'})
                states = []
                reset(page); deadline = time.monotonic()+30; action=0
                while time.monotonic() < deadline:
                    box = page.locator('.av-play-btn').bounding_box(); x=box['x']+box['width']/2; y=box['y']+box['height']/2
                    page.mouse.move(x,y); page.mouse.down(); page.wait_for_timeout(500 if action%3==0 else 50)
                    if action%3==0: page.mouse.move(x+15,y+10,steps=3)
                    page.mouse.up(); page.wait_for_timeout(350); action+=1
                    states.append(page.evaluate('''()=>({t:performance.now(),classes:document.querySelector('.avwrap').className,
                        animations:document.getAnimations().map(a=>({name:a.animationName,target:a.effect.target.getAttribute('class')})),
                        svg_filter:getComputedStyle(document.querySelector('.avwrap svg')).filter,
                        svg_will_change:getComputedStyle(document.querySelector('.avwrap svg')).willChange})'''))
                cpu_after = cdp.send('Performance.getMetrics')
                observed = snapshot(page,cdp)
                cdp.send('Tracing.end')
                while not done: page.wait_for_timeout(100)
                stream=done[0]['stream']; chunks=[]
                while True:
                    part=cdp.send('IO.read',{'handle':stream});chunks.append(part['data'])
                    if part.get('eof'):break
                cdp.send('IO.close',{'handle':stream})
                events=json.loads(''.join(chunks))['traceEvents']
                tasks=[e for e in events if e.get('ph')=='X' and e.get('dur',0)>50000 and e['name'] in ['RunTask','ThreadControllerImpl::RunTask']]
                details=[]
                for task in tasks:
                    nested=[e for e in events if e.get('ph')=='X' and e.get('pid')==task['pid'] and e.get('tid')==task['tid'] and task['ts']<=e.get('ts',-1)<task['ts']+task['dur']]
                    spans=[]
                    for e in nested:
                        if e['name'] in ['FunctionCall','UpdateLayoutTree','Paint','Layout','PrePaint','Layerize','Animation','AnimationFrame::Render','CompositeLayers','EvaluateScript']:
                            data=e.get('args',{}).get('data',{})
                            spans.append({'name':e['name'],'duration_ms':e.get('dur',0)/1000,'thread_cpu_ms':e.get('tdur', -1000)/1000,'function':data.get('functionName'),'url':data.get('url','').replace(origin,''),'line':data.get('lineNumber')})
                    details.append({'duration_ms':task['dur']/1000,'thread_cpu_ms':task.get('tdur',-1000)/1000,'spans':spans})
                page.screenshot(path=str(out/f'{version}-{run}.png'))
                results.append({'version':version,'run':run,'runtime_sha256':hashlib.sha256(runtime).hexdigest() if runtime else None,'actions':action,'scenario':observed,'states':states,'tasks':details,'thread_metrics_before':cpu_before,'thread_metrics_after':cpu_after,
                    'timed_event_totals_ms':{name:sum(e.get('dur',0)/1000 for e in events if e.get('ph')=='X' and e.get('name')==name) for name in ['FunctionCall','UpdateLayoutTree','Paint','Layout','PrePaint','Layerize']}})
                (out/'interaction-trace.json').write_text(json.dumps({'diagnostic_only':True,'browser':browser.version,'cpu':4,'idle_seconds':idle,'input_seconds':30,'test_only_css':css if variant != 'batched' else None,'runtime_comparison':variant == 'batched','samples':results},indent=2))
                print(version,run,observed['frame_p95_ms'],flush=True)
                context.close()
        browser.close()
