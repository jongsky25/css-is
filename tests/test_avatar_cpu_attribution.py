"""Diagnostic wall/thread-CPU attribution; never substitutes acceptance runs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import pytest
from tests.test_avatar_baseline_browser import baseline_server
from tests.test_avatar_native_control import PURE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_CPU_DIAGNOSTIC')!='1',reason='Opt-in CPU diagnostic')

@pytest.mark.parametrize('kind',['fern','mushroom','succulent'])
def test_cpu_attribution(baseline_server,app_mod,tmp_path,kind):
    import storage as st
    from jinja2 import ChoiceLoader,FileSystemLoader
    from playwright.sync_api import sync_playwright
    origin,cookie,uid=baseline_server
    conn=st.connect(app_mod.DB);st.set_user_avatar(conn,uid,kind,'CPU attribution');conn.close()
    env=app_mod.templates.env;original=env.loader
    folder=tmp_path/'old';folder.mkdir()
    for name in ['_avatars.html','_avatars_art.html']:
        (folder/name).write_bytes(subprocess.check_output(['git','show','5b580d9:templates/'+name]))
    out=Path(os.environ['CSS_AVATAR_OUT']).parent/kind;out.mkdir(parents=True,exist_ok=True)
    rows=[]
    try:
        with sync_playwright() as pw:
            for version in ['before','after']:
                env.loader=ChoiceLoader([FileSystemLoader(folder),original]) if version=='before' else original
                env.cache.clear()
                browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
                context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,timezone_id='UTC')
                context.add_cookies([cookie]);context.add_init_script(PURE)
                page=context.new_page();cdp=context.new_cdp_session(page)
                cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
                page.goto(origin+'/?view=me');page.goto(origin+'/?view=me');page.wait_for_timeout(500)
                done=[];cdp.on('Tracing.tracingComplete',lambda e:done.append(e))
                cdp.send('Tracing.start',{'categories':'toplevel,devtools.timeline,v8.execute','transferMode':'ReturnAsStream'})
                deadline=time.monotonic()+30;actions=0
                while time.monotonic()<deadline:
                    box=page.locator('.av-play-btn').bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
                    page.mouse.move(x,y);page.mouse.down();page.wait_for_timeout(500 if actions%3==0 else 50)
                    if actions%3==0:page.mouse.move(x+15,y+10,steps=3)
                    page.mouse.up();page.wait_for_timeout(350);actions+=1
                cdp.send('Tracing.end')
                while not done:page.wait_for_timeout(100)
                stream=done[0]['stream'];chunks=[]
                while True:
                    part=cdp.send('IO.read',{'handle':stream});chunks.append(part['data'])
                    if part.get('eof'):break
                cdp.send('IO.close',{'handle':stream})
                events=json.loads(''.join(chunks))['traceEvents']
                (out/f'{version}-trace.json').write_text(json.dumps({'traceEvents':events},separators=(',',':')))
                calls=[e for e in events if e.get('ph')=='X' and e['name']=='FunctionCall' and '/static/js/avatars.js' in e.get('args',{}).get('data',{}).get('url','')]
                rows.append({'version':version,'actions':actions,'calls':[{'wall_ms':e['dur']/1000,'thread_cpu_ms':e.get('tdur',0)/1000,'data':e.get('args',{}).get('data',{})} for e in calls if e.get('dur',0)>50000],
                             'total_avatar_wall_ms':sum(e.get('dur',0)/1000 for e in calls),'total_avatar_thread_ms':sum(e.get('tdur',0)/1000 for e in calls)})
                (out/'summary.json').write_text(json.dumps({'diagnostic_only':True,'same_runtime_both_arms':True,'old_art':'5b580d9','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'samples':rows},indent=2))
                print(kind,version,'slow',rows[-1]['calls'],flush=True)
                context.close();browser.close()
    finally:env.loader=original;env.cache.clear()
