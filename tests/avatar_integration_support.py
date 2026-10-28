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



@pytest.fixture
def baseline_server(app_mod):
    import auth
    import hashlib
    import importlib.metadata
    import platform
    import subprocess
    import storage as st
    import uvicorn
    output = Path(os.getenv('CSS_AVATAR_OUT', '/tmp/avatar-integration/application'))
    output.mkdir(parents=True, exist_ok=True)
    sources = ['templates/_avatars.html', 'templates/_avatars_art.html',
               'templates/me.html', 'templates/_growth.html',
               'static/js/avatars.js', 'static/js/avatar-audio.js', 'static/js/search.js',
               'templates/office_connect.html', 'templates/dash_layout.html', __file__]
    sources += [str(p) for p in sorted(Path('templates').glob('_avatar_species/*.html'))]
    if Path('tests/avatar_browser_fixture.py').exists():
        sources.append('tests/avatar_browser_fixture.py')
    if Path('templates/_avatars_shared.html').exists():
        sources.append('templates/_avatars_shared.html')
    (output / 'environment.json').write_text(json.dumps({
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'platform': platform.platform(), 'python': platform.python_version(),
        'chromium': os.getenv('CSS_AVATAR_CHROMIUM', '154.0.8037.57'),
        'playwright': importlib.metadata.version('playwright'),
        'fixture_date_local': os.getenv('CSS_TEST_NOW', '2026-10-20T06:00:00') + ' Asia/Manila',
        'browser_date': '2026-07-15T12:00:00Z + performance.now()', 'random_seed': 12345,
        'source_sha256': {str(Path(name).relative_to(Path.cwd())) if Path(name).is_absolute() else name:
                          hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sources},
        'process_tree_cpu_affinity': sorted(os.sched_getaffinity(0)),
        'requested_renderer_pin_cpu': 1 if os.getenv('CSS_AVATAR_PIN_RENDERER')=='1' else None,
        'proxy_compression': 'test-local Starlette GZipMiddleware minimum_size=500',
    }, indent=2))
    from starlette.middleware.gzip import GZipMiddleware
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'admin@test.local')
    st.set_user_avatar(conn, user['id'], os.getenv('CSS_AVATAR_KIND', 'cat'), 'Baseline Cat')
    if os.getenv('CSS_AVATAR_MATURE') == '1':
        from datetime import date, timedelta
        for week in range(40):
            day = (date(2026, 7, 13) - timedelta(weeks=week)).isoformat()
            conn.execute("INSERT INTO wellness_claim(user_id,week_start,break_date,start_time,hours,activity,status) "
                         "VALUES(?,?,?,'10:00',1,'exercise','completed')", (user['id'], day, day))
        conn.commit()
        assert st.wellness_stats(conn, user['id'])['stage'] == 6
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
new PerformanceObserver(list=>list.getEntries().forEach(e=>{probe.lcp=e.startTime;probe.lcp_detail={tag:e.element?.tagName,id:e.element?.id,text:e.element?.textContent?.slice(0,120),size:e.size,url:e.url}})).observe({type:'largest-contentful-paint',buffered:true});
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
resources:performance.getEntriesByType('resource').map(r=>({name:r.name.split(location.origin).pop(),transfer:r.transferSize,encoded:r.encodedBodySize,decoded:r.decodedBodySize,start:r.startTime,duration:r.duration,responseStart:r.responseStart,responseEnd:r.responseEnd,initiator:r.initiatorType}))})''')
    frames = result.pop('frames')
    result['frame_count'] = len(frames)
    result['frame_p95_ms'] = sorted(frames)[int(.95*(len(frames)-1))] if frames else None
    return result


def reset(page):
    page.evaluate('avatarProbe.frames=[];avatarProbe.long=[];avatarProbe.events=[]')


