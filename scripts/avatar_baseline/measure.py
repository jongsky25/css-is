"""Run against gallery.py; raw metrics deliberately retain outliers and baseline failures."""
import argparse, gzip, json, platform, shutil, statistics, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
from gallery import ROOT, render

p = argparse.ArgumentParser(); p.add_argument('--out', default='docs/avatars/baseline'); p.add_argument('--seconds', type=int, default=30); p.add_argument('--runs', type=int, default=5)
a = p.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
results = {'platform': platform.platform(), 'commit': subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
           'seconds_per_scenario': a.seconds, 'runs': [], 'sizes_gzip': {}}
for scene in ['home','picker','gallery']:
    html = render(scene).encode(); results['sizes_gzip'][scene] = len(gzip.compress(html, mtime=0))
results['sizes_gzip']['js'] = sum(len(gzip.compress((ROOT / 'static/js' / f).read_bytes(), mtime=0)) for f in ['avatars.js','avatar-audio.js'])
results['sizes_gzip']['css'] = len(gzip.compress(render('home').split('<style>')[2].split('</style>')[0].encode(), mtime=0))
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
    results['chromium'] = browser.version
    for theme in ['light','dark']:
        for outfit, month in [('default',0),('default',7),('halloween',10),('halloween_vampire',10),('halloween_pumpkin',10),('christmas',12)]:
            ctx = browser.new_context(viewport={'width':1440,'height':1000}, reduced_motion='reduce', timezone_id='UTC')
            page = ctx.new_page(); page.clock.set_fixed_time('2026-07-15T12:00:00Z'); page.goto(f'http://127.0.0.1:8765/?theme={theme}&outfit={outfit}&month={month}')
            page.screenshot(path=str(out / f'{theme}-{outfit}-{month}.png'), full_page=True); ctx.close()
    for mobile in [False, True]:
        for cache in ['cold','warm']:
            for run in range(a.runs):
                ctx = browser.new_context(timezone_id='UTC', viewport={'width':390,'height':844} if mobile else {'width':1440,'height':1000})
                page = ctx.new_page(); errors=[]; external=[]
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('request', lambda r: external.append(r.url) if not r.url.startswith('http://127.0.0.1:8765/') else None)
                cdp = ctx.new_cdp_session(page); cdp.send('Emulation.setCPUThrottlingRate', {'rate':4 if mobile else 1})
                page.clock.set_fixed_time('2026-07-15T12:00:00Z')
                page.add_init_script('''window.probe={frames:[],long:[],lcp:0};
new PerformanceObserver(l=>l.getEntries().forEach(e=>probe.long.push(e.duration))).observe({type:'longtask',buffered:true});
new PerformanceObserver(l=>l.getEntries().forEach(e=>probe.lcp=e.startTime)).observe({type:'largest-contentful-paint',buffered:true});
let last;function tick(t){if(last)probe.frames.push(t-last);last=t;requestAnimationFrame(tick)}requestAnimationFrame(tick);''')
                if cache == 'warm': page.goto('http://127.0.0.1:8765/?scene=home')
                page.goto('http://127.0.0.1:8765/?scene=home'); page.wait_for_timeout(500)
                start = cdp.send('Runtime.getHeapUsage')['usedSize']
                scenarios={}
                for scenario in ['idle','interaction']:
                    page.evaluate('probe.frames=[];probe.long=[]'); latencies=[]
                    for second in range(a.seconds):
                        if scenario == 'interaction':
                            page.mouse.move(100 + second % 8 * 20, 220)
                            page.locator('.av-play-btn').click()
                            if second % 6 == 0: page.locator('.av-care-btn').click()
                            page.mouse.move(140,220); page.mouse.down(); page.mouse.move(170,240,steps=4); page.mouse.up()
                            latencies.append(page.evaluate('''()=>new Promise(r=>{let t=performance.now();requestAnimationFrame(()=>r(performance.now()-t))})'''))
                        page.wait_for_timeout(1000)
                    data=page.evaluate('probe'); frames=sorted(data['frames'])
                    scenarios[scenario]={'lcp_ms':data['lcp'],'frame_p95_ms':frames[int(.95*(len(frames)-1))],
                        'long_tasks_ms':data['long'],'latency_ms':latencies}
                for i in range(20): page.goto('http://127.0.0.1:8765/?scene=home')
                end = cdp.send('Runtime.getHeapUsage')['usedSize']
                results['runs'].append({'mobile':mobile,'cpu_rate':4 if mobile else 1,'cache':cache,'run':run,
                    'scenarios':scenarios,'heap_after_navigation_delta_bytes':end-start,'nodes':page.locator('*').count(),
                    'errors':errors,'external_requests':external})
                ctx.close(); (out / 'raw.json').write_text(json.dumps(results, indent=2)); print(mobile,cache,run,flush=True)
    browser.close()
summary=[]
for mobile in [False,True]:
    for cache in ['cold','warm']:
        rows=[r for r in results['runs'] if r['mobile']==mobile and r['cache']==cache]
        for scenario in ['idle','interaction']:
            for metric in ['lcp_ms','frame_p95_ms']:
                values=[r['scenarios'][scenario][metric] for r in rows]
                summary.append({'mobile':mobile,'cache':cache,'scenario':scenario,'metric':metric,'median':statistics.median(values),'worst':max(values)})
(out/'summary.json').write_text(json.dumps(summary,indent=2))
