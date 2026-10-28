"""Fixed synthetic capability check; no CSS-IS data or acceptance measurements."""
import argparse
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import time

from playwright.sync_api import sync_playwright

BUILD = '1c5dca8527a61d07372e489142bee26af1bcaf71'
BROWSER = Path('/workspace/scratch/chromium156-bin/chromium')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        mode = self.path.strip('/').split('?')[0]
        if mode == 'dom':
            body = '<main>' + ''.join(f'<div class="n{i}"><span>row {i}</span></div>' for i in range(3000)) + '</main>'
        elif mode == 'svg':
            body = '<svg width="400" height="400">' + ''.join(f'<path d="M{i%400} 0L200 300" stroke="blue"/>' for i in range(3000)) + '</svg>'
        elif mode == 'style':
            body = '<style>' + ''.join(f'.n{i}{{color:rgb({i%255},20,30);padding:{i%10}px}}' for i in range(3000)) + '</style>'
            body += ''.join(f'<div class="n{i}">row {i}</div>' for i in range(3000))
        else:
            body = '<p>Empty control</p>'
        data = ('<!doctype html><html><head><link rel="icon" href="data:,"></head><body>'+body+'</body></html>').encode()
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)


def main():
    import frida  # Optional: required only when explicitly running this diagnostic.
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--mode',choices=['control','probe'],default='probe');args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[2]
    hook=root/'scripts/avatar_baseline/native/page_history.js'
    result={'acceptance':False,'forced_gc':False,'kind':'synthetic capability only',
        'schedule':['dom','svg','style']*4,'frida_version':frida.__version__,
        'hook_sha256':hashlib.sha256(hook.read_bytes()).hexdigest(),
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        'stages':[],'agent_messages':[],'mode':args.mode}
    notes=subprocess.check_output(['readelf','-n',str(BROWSER)],text=True)
    if 'Build ID: '+BUILD not in notes: raise ValueError('Unexpected browser ELF')
    result['browser_build_id']=BUILD
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    session=None
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=str(BROWSER),args=['--no-sandbox'])
            if browser.version != '156.0.8078.47': raise ValueError('Unexpected browser version')
            result['browser_version']=browser.version
            page=browser.new_page();cdp=browser.new_browser_cdp_session();done=[]
            cdp.on('Tracing.tracingComplete',lambda e:done.append(e))
            cdp.send('Tracing.start',{'transferMode':'ReturnAsStream','traceConfig':{'excludedCategories':['*'],'includedCategories':['devtools.timeline'],'recordMode':'recordUntilFull'}})
            origin=f'http://127.0.0.1:{server.server_port}'
            page.goto(origin+'/empty');cdp.send('Tracing.end')
            deadline=time.monotonic()+15
            while not done:
                if time.monotonic()>deadline:raise TimeoutError('Identity trace')
                page.wait_for_timeout(10)
            chunks=[];handle=done[0]['stream']
            while True:
                chunk=cdp.send('IO.read',{'handle':handle});chunks.append(chunk['data'])
                if chunk.get('eof'):break
            cdp.send('IO.close',{'handle':handle})
            events=json.loads(''.join(chunks))['traceEvents']
            pids={e['pid'] for e in events if e.get('name')=='CommitLoad' and e.get('args',{}).get('data',{}).get('url')==origin+'/empty'}
            if len(pids)!=1 or done[0].get('dataLossOccurred'):raise ValueError('Renderer identity ambiguity')
            pid=pids.pop();result['renderer_pid']=pid
            result['identity_events']=[e for e in events if e.get('name')=='CommitLoad']
            script=None
            if args.mode=='probe':
                session=frida.attach(pid)
                script=session.create_script(hook.read_text());script.on('message',lambda m,d:result['agent_messages'].append(m));script.load()
                if not any(m.get('payload',{}).get('ready') for m in result['agent_messages']):raise ValueError('Hook did not become ready')
            for i,mode in enumerate(result['schedule']):
                label=f'{i:02d}-{mode}'
                if script: script.exports_sync.setphase(label)
                start=time.monotonic_ns();page.goto(origin+'/'+mode);page.wait_for_timeout(220)
                result['stages'].append({'index':i,'mode':mode,'phase':label,'begin_ns':start,'end_ns':time.monotonic_ns(),
                    'live_nodes':page.evaluate('document.querySelectorAll("*").length')})
            if script:
                result['history']=script.exports_sync.result();script.unload();session.detach();session=None
            result['status']='captured' if not result.get('history',{}).get('dropped',0) else 'overflow'
            browser.close()
    except Exception as exc:
        result['status']='capability_failed';result['error']=repr(exc)
    finally:
        if session:
            try:session.detach()
            except Exception:pass
        server.shutdown();server.server_close()
        with gzip.open(args.out/'capture.json.gz','wt') as f:json.dump(result,f)
    print(json.dumps({k:result.get(k) for k in ['status','error','renderer_pid']}),flush=True)
    return result['status']!='captured'


if __name__=='__main__':raise SystemExit(main())
