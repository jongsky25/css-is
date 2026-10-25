"""Opt-in startup trace: compare original/current art+avatar runtime, same app."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from tests.test_avatar_baseline_browser import baseline_server, PROBE

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE') != '1', reason='Opt-in startup diagnostic')


def test_cold_startup_trace(baseline_server, app_mod, tmp_path):
    from jinja2 import ChoiceLoader, FileSystemLoader
    from playwright.sync_api import sync_playwright
    import storage as st
    origin,cookie,uid=baseline_server
    conn=st.connect(app_mod.DB);st.record_avatar_care(conn,uid);conn.close()
    env=app_mod.templates.env;loader=env.loader
    folder=tmp_path/'original';folder.mkdir()
    for file in ['_avatars.html','_avatars_art.html']:
        (folder/file).write_bytes(subprocess.check_output(['git','show','1c964dc:templates/'+file]))
    placeholder = os.getenv('CSS_AVATAR_STARTUP_PLACEHOLDER') == '1'
    if placeholder:
        for p in folder.iterdir():p.unlink()
        (folder/'office_connect.html').write_bytes(subprocess.check_output(['git','show','41c8e01:templates/office_connect.html']))
    loaders={'current':loader,('before-placeholder' if placeholder else 'original'):ChoiceLoader([FileSystemLoader(folder),loader])}
    runtime={version:{file:(subprocess.check_output(['git','show','1c964dc:static/js/'+file]) if version=='original' else Path('static/js',file).read_bytes()) for file in ['avatars.js','avatar-audio.js','search.js']} for version in loaders}
    if placeholder:
        runtime['before-placeholder']['search.js']=subprocess.check_output(['git','show','41c8e01:static/js/search.js'])
    out=Path(os.environ['CSS_AVATAR_OUT']).parent;rows=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
            for run in range(5):
                for version in (list(loaders) if run%2==0 else list(reversed(loaders))):
                    env.loader=loaders[version]
                    context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='UTC',service_workers='block')
                    context.add_cookies([cookie]);context.add_init_script(PROBE)
                    def script_handler(file):
                        def serve(route):
                            route.fulfill(body=runtime[version][file],content_type='text/javascript')
                        return serve
                    for file in ['avatars.js','avatar-audio.js','search.js']:
                        context.route('**/static/js/'+file+'*',script_handler(file))
                    page=context.new_page();cdp=context.new_cdp_session(page)
                    cdp.send('Network.enable');cdp.send('Network.setBlockedURLs',{'urls':['https://*']});cdp.send('Network.clearBrowserCache')
                    cdp.send('Emulation.setCPUThrottlingRate',{'rate':1})
                    done=[];cdp.on('Tracing.tracingComplete',lambda e:done.append(e))
                    cdp.send('Tracing.start',{'categories':'toplevel,devtools.timeline,v8.execute,v8,blink,blink.user_timing,loading,disabled-by-default-devtools.timeline.stack','transferMode':'ReturnAsStream'})
                    cdp.send('Profiler.enable');cdp.send('Profiler.start')
                    assert page.goto(origin+'/?view=me').status==200
                    page.wait_for_timeout(2000)
                    profile=cdp.send('Profiler.stop')['profile']
                    observed=page.evaluate('''()=>({lcp:avatarProbe.lcp,candidate:avatarProbe.lcp_detail,navigation:performance.getEntriesByType('navigation')[0].toJSON(),resources:performance.getEntriesByType('resource').map(e=>e.toJSON())})''')
                    cdp.send('Tracing.end')
                    while not done:page.wait_for_timeout(50)
                    stream=done[0]['stream'];chunks=[]
                    while True:
                        part=cdp.send('IO.read',{'handle':stream});chunks.append(part['data'])
                        if part.get('eof'):break
                    cdp.send('IO.close',{'handle':stream})
                    events=json.loads(''.join(chunks))['traceEvents']
                    # Start at navigationStart; traces use the same monotonic clock.
                    nav=next((e['ts'] for e in events if e.get('name')=='navigationStart'), min(e['ts'] for e in events if 'ts' in e))
                    spans=[]
                    for e in events:
                        if e.get('ph')!='X' or e.get('dur',0)<1000 or e.get('ts',0)<nav:continue
                        data=e.get('args',{}).get('data',{})
                        spans.append({'name':e['name'],'pid':e['pid'],'tid':e['tid'],'start_ms':(e['ts']-nav)/1000,'duration_ms':e['dur']/1000,'cpu_ms':e.get('tdur',-1000)/1000,
                                      'url':str(data.get('url','')).replace(origin,''),'function':data.get('functionName'),'line':data.get('lineNumber')})
                    nodes={n['id']:n['callFrame'] for n in profile['nodes']};costs={}
                    for node,delta in zip(profile.get('samples',[]),profile.get('timeDeltas',[])):
                        f=nodes[node];key=(f['url'].replace(origin,''),f['functionName'],f['lineNumber']);costs[key]=costs.get(key,0)+delta/1000
                    top=sorted([{'url':k[0],'function':k[1],'line':k[2],'sampled_ms':v} for k,v in costs.items()],key=lambda v:v['sampled_ms'],reverse=True)[:35]
                    rows.append({'version':version,'run':run,'observed':observed,'trace_spans':spans,'cpu_profile_top':top,'runtime_sha256':{f:hashlib.sha256(b).hexdigest() for f,b in runtime[version].items()}})
                    (out/'startup-trace.json').write_text(json.dumps({'diagnostic_only':True,'method':'Five counterbalanced CPU1 cold desktop contexts per art/runtime version; same current application/storage/auth; happy mood; 2s observation; tracing+CPU profiling+matching routing overhead, not full-scenario acceptance. Loader-specific template caches retained.','placeholder_comparison':placeholder,'samples':rows},indent=2))
                    print(version,run,observed['lcp'],flush=True)
                    context.close()
            browser.close()
    finally:
        env.loader=loader;env.cache.clear()
