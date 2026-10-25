"""Direct owned FunctionCall attribution, without JS API wrappers or stacks."""
from tests.avatar_browser_fixture import pin_renderer_threads, accepted_frame
import gzip
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

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_CPU_DIAGNOSTIC')!='1',reason='Opt-in CPU attribution')

@pytest.mark.parametrize('kind',['fern','mushroom','succulent'])
def test_cpu_attribution(baseline_server,app_mod,tmp_path,kind):
    import storage as st
    from jinja2 import ChoiceLoader,FileSystemLoader
    from playwright.sync_api import sync_playwright
    origin,cookie,uid=baseline_server
    conn=st.connect(app_mod.DB);st.set_user_avatar(conn,uid,kind,'Native Control');conn.close()
    env=app_mod.templates.env;original=env.loader
    folder=tmp_path/'old';folder.mkdir()
    for name in ['_avatars.html','_avatars_art.html']:
        (folder/name).write_bytes(subprocess.check_output(['git','show','5b580d9:templates/'+name]))
    out=Path(os.environ['CSS_AVATAR_OUT']).parent/kind;out.mkdir(parents=True,exist_ok=True)
    rows=[];runs=int(os.getenv('CSS_AVATAR_CPU_RUNS','1'));after_only=os.getenv('CSS_AVATAR_CPU_AFTER_ONLY')=='1'
    try:
        with sync_playwright() as pw:
            for run in range(runs):
                for version in (['after'] if after_only else (['before','after'] if run%2==0 else ['after','before'])):
                    env.loader=ChoiceLoader([FileSystemLoader(folder),original]) if version=='before' else original
                    env.cache.clear()
                    browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
                    assert browser.version==os.getenv('CSS_AVATAR_CHROMIUM','154.0.8037.57')
                    context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,timezone_id='UTC',service_workers='block')
                    context.add_cookies([cookie]);context.add_init_script(PURE)
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    cdp=context.new_cdp_session(page);cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
                    pins=pin_renderer_threads(browser)
                    assert os.getenv('CSS_AVATAR_PIN_RENDERER')!='1' or any(p['name'].startswith('CPUThrottling') for p in pins)
                    page.goto(origin+'/?view=me');page.goto(origin+'/?view=me');page.wait_for_timeout(500)
                    assert page.locator(f'.avwrap[data-interactive] svg[data-avatar-kind="{kind}"][data-avatar-stage="6"]').count()==1
                    done=[];cdp.on('Tracing.tracingComplete',lambda e:done.append(e))
                    cdp.send('Tracing.start',{'traceConfig':{'recordMode':'recordUntilFull','includedCategories':['toplevel','devtools.timeline','v8.execute','blink.user_timing'],'traceBufferSizeInKb':131072},'transferMode':'ReturnAsStream'})
                    reset(page);page.evaluate("performance.mark('avatar-input-start')")
                    deadline=time.monotonic()+30;actions=0
                    while time.monotonic()<deadline:
                        box=page.locator('.av-play-btn').bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
                        page.mouse.move(x,y);page.mouse.down();page.wait_for_timeout(500 if actions%3==0 else 50)
                        if actions%3==0:page.mouse.move(x+15,y+10,steps=3)
                        page.mouse.up();page.wait_for_timeout(350);actions+=1
                    page.evaluate("performance.mark('avatar-input-end')")
                    observed=snapshot(page,cdp)
                    cdp.send('Tracing.end')
                    while not done:page.wait_for_timeout(100)
                    stream=done[0]['stream'];chunks=[]
                    while True:
                        part=cdp.send('IO.read',{'handle':stream});chunks.append(part['data'])
                        if part.get('eof'):break
                    cdp.send('IO.close',{'handle':stream})
                    events=json.loads(''.join(chunks))['traceEvents']
                    raw_file=f'{version}-{run}-trace.json.gz'
                    with gzip.open(out/raw_file,'wt') as target:json.dump({'traceEvents':events},target,separators=(',',':'))
                    start=next(e['ts'] for e in events if e.get('name')=='avatar-input-start')
                    end=next(e['ts'] for e in events if e.get('name')=='avatar-input-end')
                    calls=[e for e in events if e.get('ph')=='X' and e['name']=='FunctionCall' and ('/static/js/avatars.js' in e.get('args',{}).get('data',{}).get('url','') or '/static/js/avatar-audio.js' in e.get('args',{}).get('data',{}).get('url','')) and e['ts']<end and e['ts']+e.get('dur',0)>=start]
                    assert calls, 'Trace did not record owned callbacks'
                    details=[{'wall_ms':e['dur']/1000,'thread_cpu_ms':e.get('tdur',0)/1000,'data':dict(e.get('args',{}).get('data',{}),url=e.get('args',{}).get('data',{}).get('url','').replace(origin,''))} for e in calls]
                    maximum=max(c['wall_ms'] for c in details)
                    rows.append({'kind':kind,'version':version,'run':run,'mature':True,'cpu':4,'seconds':30,'thread_pins':pins,'actions':actions,'scenario':observed,'trace_file':raw_file,'trace_data_loss':bool(done[0].get('dataLossOccurred',False)),'start_trace_us':start,'end_trace_us':end,'owned_call_count':len(calls),'max_owned_call_wall_ms':maximum,'over50_owned_calls':[c for c in details if c['wall_ms']>50],'total_owned_wall_ms':sum(c['wall_ms'] for c in details),'total_owned_thread_cpu_ms':sum(c['thread_cpu_ms'] for c in details),'errors':errors})
                    (out/'summary.json').write_text(json.dumps({'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'runtime_sha256':hashlib.sha256(Path('static/js/avatars.js').read_bytes()).hexdigest(),'kind':kind,'before_art':None if after_only else '5b580d9','after_only':after_only,'same_runtime_both_arms':not after_only,'method':'Counterbalanced current-runtime old/new-art controls; native timeline FunctionCall wall spans for avatars/audio within explicit performance marks. CPU4, mature6, 30s input; PURE probes, no timer/event/rAF wrappers or stack capture. No CPU or GC subtraction. All native invoker diagnostics retained separately.','samples':rows},indent=2))
                    print(kind,version,run,'frame',observed['frame_p95_ms'],'owned_call_wall',round(maximum,3),flush=True)
                    context.close();browser.close()
    finally:env.loader=original;env.cache.clear()
    assert len(rows)==(runs if after_only else 2*runs) and not any(r['errors'] or r['trace_data_loss'] for r in rows)
    if runs==5:
        assert all(r['max_owned_call_wall_ms']<=50 and accepted_frame(r['scenario']['frame_p95_ms']) for r in rows if r['version']=='after'), 'Owned callback or frame budget failed; all records retained'
