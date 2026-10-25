"""Opt-in real HTTP baseline. CSS_AVATAR_BASELINE=1; never uses production data."""
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE') != '1', reason='Opt-in performance baseline')


@pytest.fixture
def baseline_server(app_mod):
    import auth
    import hashlib
    import importlib.metadata
    import platform
    import subprocess
    import storage as st
    import uvicorn
    output = Path(os.getenv('CSS_AVATAR_OUT', 'docs/avatars/application'))
    output.mkdir(parents=True, exist_ok=True)
    sources = ['templates/_avatars.html', 'templates/_avatars_art.html',
               'static/js/avatars.js', 'static/js/avatar-audio.js', __file__]
    (output / 'environment.json').write_text(json.dumps({
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'platform': platform.platform(), 'python': platform.python_version(),
        'chromium': os.getenv('CSS_AVATAR_CHROMIUM', '154.0.8037.57'),
        'playwright': importlib.metadata.version('playwright'),
        'fixture_date_local': os.getenv('CSS_TEST_NOW', '2026-10-20T06:00:00') + ' Asia/Manila',
        'browser_date': '2026-07-15T12:00:00Z + performance.now()', 'random_seed': 12345,
        'source_sha256': {str(Path(name).relative_to(Path.cwd())) if Path(name).is_absolute() else name:
                          hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sources},
        'proxy_compression': 'test-local Starlette GZipMiddleware minimum_size=500',
    }, indent=2))
    from starlette.middleware.gzip import GZipMiddleware
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'admin@test.local')
    st.set_user_avatar(conn, user['id'], 'cat', 'Baseline Cat')
    conn.close()
    token = app_mod._issue_session(dict(user))
    sock = socket.socket(); sock.bind(('127.0.0.1', 0))
    origin = f'http://127.0.0.1:{sock.getsockname()[1]}'
    # Explicit controlled proxy compression; not a production configuration change.
    server = uvicorn.Server(uvicorn.Config(GZipMiddleware(app_mod.app, minimum_size=500),
                            log_level='error', lifespan='off'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        assert time.monotonic() < deadline, 'Local fixture server did not start'
        time.sleep(.02)
    yield origin, {'name': auth.COOKIE_NAME, 'value': token, 'url': origin}, user['id']
    server.should_exit = True; thread.join(timeout=10); sock.close()


PROBE = r'''(() => {
const NativeDate=Date, epoch=NativeDate.parse('2026-07-15T12:00:00Z');
window.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:[epoch+performance.now()]))} static now(){return epoch+performance.now()}};
let seed=12345; Math.random=()=>((seed=(1664525*seed+1013904223)>>>0)/4294967296);
localStorage.setItem('css_tour_optout','1');
const probe=window.avatarProbe={frames:[],long:[],events:[],lcp:0,timers:{},ticks:{}};
for(const name of ['setTimeout','setInterval']){
 const native=window[name], repeat=name==='setInterval';
 window[name]=function(callback,delay,...args){
 const source=(new Error()).stack.split('\n').find(s=>/avatars\.js|avatar-audio\.js/.test(s))||'other';
 let id=native(function(...passed){probe.ticks[source]=(probe.ticks[source]||0)+1;
 if(!repeat)delete probe.timers[id];
 if(typeof callback==='function')callback(...passed);else (0,eval)(callback);
 },delay,...args);probe.timers[id]={source,repeat,delay};return id;
 };
}
for(const name of ['clearTimeout','clearInterval']){const native=window[name];window[name]=id=>{delete probe.timers[id];native(id)}}
new PerformanceObserver(list=>list.getEntries().forEach(e=>probe.long.push({start:e.startTime,duration:e.duration,name:e.name}))).observe({type:'longtask',buffered:true});
new PerformanceObserver(list=>list.getEntries().forEach(e=>probe.lcp=e.startTime)).observe({type:'largest-contentful-paint',buffered:true});
new PerformanceObserver(list=>list.getEntries().forEach(e=>probe.events.push({name:e.name,duration:e.duration,processing:e.processingStart-e.startTime,interaction:e.interactionId}))).observe({type:'event',buffered:true,durationThreshold:16});
let last;function frame(t){if(last)probe.frames.push(t-last);last=t;requestAnimationFrame(frame)}requestAnimationFrame(frame);
})();'''


def snapshot(page, cdp):
    result = page.evaluate(r'''()=>({lcp_ms:avatarProbe.lcp,frames:avatarProbe.frames,
long_tasks:avatarProbe.long,events:avatarProbe.events,hidden:document.hidden,
animations:document.getAnimations().filter(a=>a.playState==='running').length,
avatar_animations:document.getAnimations().filter(a=>a.playState==='running' && a.effect.target.closest('.avwrap')).length,
timers:Object.values(avatarProbe.timers).filter(t=>/avatars\.js|avatar-audio\.js/.test(t.source)),
ticks:avatarProbe.ticks,nodes:document.querySelectorAll('*').length,
resources:performance.getEntriesByType('resource').map(r=>({name:r.name.split(location.origin).pop(),transfer:r.transferSize,encoded:r.encodedBodySize,decoded:r.decodedBodySize}))})''')
    browser_session = page.context.browser.new_browser_cdp_session()
    processes = browser_session.send('SystemInfo.getProcessInfo')['processInfo']
    browser_session.detach()
    rss = []
    for process in processes:
        if process['type'] != 'renderer': continue
        status = Path(f"/proc/{process['id']}/status")
        if status.exists():
            fields = status.read_text().splitlines()
            rss.extend(int(line.split()[1])*1024 for line in fields if line.startswith('VmRSS:'))
    result['renderer_rss_sum_bytes'] = sum(rss)
    result['renderer_process_count'] = len(rss)
    result['js_heap_bytes'] = cdp.send('Runtime.getHeapUsage')['usedSize']
    result['dom_counters'] = cdp.send('Memory.getDOMCounters')
    listeners = cdp.send('Runtime.evaluate', {'expression': "Object.fromEntries(Object.entries(getEventListeners(document)).map(([k,v])=>[k,v.length]))", 'includeCommandLineAPI': True, 'returnByValue': True})
    result['document_listeners'] = listeners['result']['value']
    frames = result.pop('frames')
    result['frame_count'] = len(frames)
    result['frame_p95_ms'] = sorted(frames)[int(.95*(len(frames)-1))] if frames else None
    return result


def reset(page):
    page.evaluate('avatarProbe.frames=[];avatarProbe.long=[];avatarProbe.events=[]')


@pytest.mark.parametrize('mobile', [False, True], ids=['desktop', 'mobile'])
@pytest.mark.parametrize('cache', ['cold', 'warm'])
def test_real_application_baseline(baseline_server, app_mod, mobile, cache):
    from playwright.sync_api import sync_playwright
    import storage as st
    origin, cookie, uid = baseline_server
    out = Path(os.getenv('CSS_AVATAR_OUT', 'docs/avatars/application'))
    out.mkdir(parents=True, exist_ok=True)
    seconds = int(os.getenv('CSS_AVATAR_SECONDS', '30'))
    runs = int(os.getenv('CSS_AVATAR_RUNS', '5'))
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
        expected = os.getenv('CSS_AVATAR_CHROMIUM', '154.0.8037.57')
        assert browser.version == expected, f'Pin explicit CSS_AVATAR_CHROMIUM after checking version: {browser.version}'
        for run in range(runs):
            context = browser.new_context(viewport={'width':390,'height':844} if mobile else {'width':1440,'height':1000},
                                          timezone_id='UTC', service_workers='block', has_touch=mobile)
            context.add_cookies([cookie]); context.add_init_script(PROBE)
            page = context.new_page()
            errors=[]; external=[]; responses=[]
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('request', lambda r: external.append(r.url) if not r.url.startswith(origin) else None)
            page.on('response', lambda r: responses.append({'url':r.url.replace(origin,''),'status':r.status,'encoding':r.headers.get('content-encoding','identity')}))
            # Block external requests, record attempts; app does not need network access.
            # CDP blocking leaves HTTP cache enabled (Playwright routing disables it).
            cdp = context.new_cdp_session(page); cdp.send('Network.enable')
            cdp.send('Network.setBlockedURLs', {'urls':['https://*']})
            cdp.send('Emulation.setCPUThrottlingRate', {'rate':4 if mobile else 1})
            if cache == 'cold': cdp.send('Network.clearBrowserCache')
            else: page.goto(origin+'/?view=me'); page.wait_for_timeout(300)
            assert page.goto(origin+'/?view=me').status == 200
            page.locator('.avwrap[data-kind="cat"]').wait_for()
            row={'run':run,'mobile':mobile,'cache':cache,'cpu_rate':4 if mobile else 1,'chromium':browser.version,
                 'seconds':seconds,'scenarios':{}}
            reset(page); page.wait_for_timeout(seconds*1000)
            row['scenarios']['home_idle']=snapshot(page,cdp)
            row['home_document']=page.evaluate('''()=>{let n=performance.getEntriesByType('navigation')[0];return {encoded:n.encodedBodySize,decoded:n.decodedBodySize,transfer:n.transferSize}}''')
            reset(page)
            # Trusted pointer input at fixed intervals, no CSS stability auto-waits.
            deadline=time.monotonic()+seconds; action=0
            while time.monotonic()<deadline:
                box=page.locator('.av-play-btn').bounding_box()
                x,y=box['x']+box['width']/2,box['y']+box['height']/2
                page.mouse.move(x,y); page.mouse.down(); page.wait_for_timeout(500 if action%3==0 else 50)
                
                if action%3==0: page.mouse.move(x+15,y+10,steps=3)
                page.mouse.up()
                page.wait_for_timeout(350);action+=1
            row['scenarios']['home_interaction']=snapshot(page,cdp)
            assert page.goto(origin+'/wellness').status==200
            # Care uses the existing production handler and registered session.
            with page.expect_response(lambda r: r.url.endswith('/avatar/care')) as care:
                page.locator('.av-care-btn').click(force=True)
            assert care.value.status==200 and care.value.json()['ok']
            page.wait_for_timeout(4000)
            row['care_response']=care.value.json()
            conn=st.connect(app_mod.DB); profile=st.get_user_profile(conn,uid);conn.close()
            assert profile['avatar_last_care_at']; row['care_persisted']=True
            row['scenarios']['wellness_care']=snapshot(page,cdp)
            assert page.goto(origin+'/me').status==200
            reset(page)
            selected=[]
            for key in [a['key'] for a in st.AVATAR_CATALOG]:
                radio=page.locator(f'input[name="avatar_kind"][value="{key}"]')
                radio.check(force=True); assert radio.is_checked();selected.append(key)
                radio.scroll_into_view_if_needed();page.wait_for_timeout(50)
            page.locator('#companion-growth-title').scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            row['picker_selected']=selected; row['scenarios']['picker_growth']=snapshot(page,cdp)
            row['picker_document']=page.evaluate('''()=>{let n=performance.getEntriesByType('navigation')[0];return {encoded:n.encodedBodySize,decoded:n.decodedBodySize,transfer:n.transferSize}}''')
            if run==0:page.screenshot(path=str(out/f'profile-{mobile}-{cache}.png'),full_page=True)
            page.goto(origin+'/admin/appearance');reset(page)
            for outfit in ['halloween','halloween_vampire','halloween_pumpkin','christmas']:
                page.locator('#editor-outfit').select_option(outfit)
                page.locator('#appearance-preview-button').click(force=True)
                page.frame_locator('#appearance-preview').locator(f'svg[data-avatar-outfit="{outfit}"]').first.wait_for()
            row['scenarios']['seasonal_preview']=snapshot(page,cdp)
            page.goto(origin+'/?view=me'); page.wait_for_timeout(300)
            # Offscreen without changing production animation policy.
            page.evaluate("document.querySelector('.avwrap').closest('.av-play').style.marginTop='2000px'")
            reset(page);page.wait_for_timeout(1500);row['scenarios']['offscreen']=snapshot(page,cdp)
            page.emulate_media(reduced_motion='reduce');page.wait_for_timeout(500)
            row['scenarios']['reduced_motion']=snapshot(page,cdp)
            # Probe actual background visibility; record unsupported automation honestly.
            page.emulate_media(reduced_motion='no-preference')
            cdp.send('Emulation.setIdleOverride',{'isUserActive':False,'isScreenUnlocked':False})
            other=context.new_page();other.goto('about:blank');other.bring_to_front()
            page.wait_for_timeout(1500);row['scenarios']['background']=snapshot(page,cdp)
            row['hidden_verified']=row['scenarios']['background']['hidden']
            other.close();cdp.send('Emulation.clearIdleOverride')
            page.bring_to_front();page.emulate_media(reduced_motion='no-preference')
            navigation=[]
            for index in range(20):
                page.goto(origin+'/?view=me');page.wait_for_timeout(220)
                if index in [0,4,9,14,19]:navigation.append({'mount':index+1,**snapshot(page,cdp)})
            row['navigation_trend']=navigation
            row['errors']=errors;row['external_attempts']=external;row['responses']=responses
            rows.append(row);context.close()
            (out/f'{mobile}-{cache}.json').write_text(json.dumps(rows,indent=2))
            print(f'BASELINE {mobile=} {cache=} {run+1}/{runs}',flush=True)
        browser.close()
    assert not any(r['errors'] for r in rows)


def test_native_visibility_and_touch(baseline_server, tmp_path):
    """Use a native tab without Playwright's forced-active-page override."""
    import subprocess
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    out=Path(os.getenv('CSS_AVATAR_OUT','docs/avatars/application'));out.mkdir(parents=True,exist_ok=True)
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    process=subprocess.Popen([shutil.which('chromium'),'--headless','--no-sandbox',f'--remote-debugging-port={port}',
                              f'--user-data-dir={tmp_path / "native-profile"}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        import urllib.request
        for attempt in range(100):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version',timeout=1):break
            except OSError:time.sleep(.1)
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp(f'http://127.0.0.1:{port}',no_defaults=True)
            context=browser.contexts[0];context.add_cookies([cookie]);context.add_init_script(PROBE)
            page=context.pages[0];page.set_viewport_size({'width':390,'height':844});page.goto(origin+'/?view=me')
            cdp=context.new_cdp_session(page);page.wait_for_timeout(500)
            visible=snapshot(page,cdp)
            page.evaluate("document.querySelector('.avwrap').closest('.av-play').style.marginTop='2000px'")
            reset(page);page.wait_for_timeout(int(os.getenv('CSS_AVATAR_SECONDS','30'))*1000)
            offscreen=snapshot(page,cdp)
            page.evaluate("document.querySelector('.avwrap').closest('.av-play').style.marginTop=''")
            other=context.new_page();other.goto('about:blank');other.bring_to_front()
            page.wait_for_function('document.hidden')
            reset(page);before=snapshot(page,cdp)
            other.wait_for_timeout(int(os.getenv('CSS_AVATAR_SECONDS','30'))*1000)
            hidden=snapshot(page,cdp)
            assert hidden['hidden']
            other.close();page.bring_to_front();page.wait_for_function('!document.hidden')
            # Touch uses trusted browser input on the real drag surface.
            cdp.send('Emulation.setTouchEmulationEnabled',{'enabled':True,'maxTouchPoints':1})
            box=page.locator('.avwrap').bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
            before_drag=page.locator('.avwrap').get_attribute('style')
            cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
            cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x+25,'y':y+10}]})
            cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
            after_drag=page.locator('.avwrap').get_attribute('style')
            assert before_drag!=after_drag, 'Touch drag did not move the real Home companion'
            before_nudge=page.locator('.avwrap').get_attribute('style')
            page.locator('.av-play-btn').focus();page.keyboard.press('ArrowLeft')
            assert before_nudge!=page.locator('.avwrap').get_attribute('style'), 'Keyboard nudge did not move companion'
            page.goto(origin+'/me');page.wait_for_timeout(300)
            picker_animations=page.evaluate('''()=>document.getAnimations().filter(a=>a.effect.target.closest('.avcard')).map(a=>({name:a.animationName,state:a.playState,kind:a.effect.target.closest('.avcard').querySelector('svg').dataset.avatarKind}))''')
            page.emulate_media(reduced_motion='reduce')
            for theme in ['light','dark','contrast']:
                page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
                page.screenshot(path=str(out/f'profile-native-{theme}.png'),full_page=True)
            (out/'native-visibility-touch.json').write_text(json.dumps({'picker_animations':picker_animations,'visible':visible,'offscreen':offscreen,'hidden_start':before,'hidden_end':hidden,
                 'touch_drag_changed_style':before_drag!=after_drag,'keyboard_nudge_style':page.locator('.avwrap').get_attribute('style'),
                 'method':'Native Chromium tabs; connect_over_cdp(no_defaults=True), no visibility getter override'},indent=2))
            browser.close()
    finally:
        process.terminate();process.wait(timeout=10)
