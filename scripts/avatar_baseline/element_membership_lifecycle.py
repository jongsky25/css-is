"""Synthetic DOM receiver/page-generation capability; never acceptance RSS."""
import argparse
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import time
import frida
from playwright.sync_api import sync_playwright

BUILD = '1c5dca8527a61d07372e489142bee26af1bcaf71'
COUNT = 512  # Retained v1 census profile.
CENSUS = 128
FIXTURE_COUNT = 4096
PROTOCOL = 'native-membership-lifecycle-v3'
STAGES = 12
BROWSER = Path('/workspace/scratch/avatar-runtime/root/usr/lib/chromium/chromium')
HOOK = Path(__file__).resolve().parent / 'native/element_membership_lifecycle.js'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path == '/empty':
            body = '<p>Identity fixture</p>'
        else:
            # Fixed separated blocks permit mixed-page observations without assuming segregation.
            body = '<svg width="64" height="64">'
            body += ''.join(f'<path data-group="avatar" d="M0 0L{i%64} 64"/>' for i in range(FIXTURE_COUNT)) + '</svg>'
            body += '<svg width="64" height="64">' + ''.join(f'<path data-group="other" d="M0 0L{i%64} 64"/>' for i in range(FIXTURE_COUNT)) + '</svg>'
        raw = ('<!doctype html><html><head><link rel="icon" href="data:,"></head><body>' + body + '</body></html>').encode()
        self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(out, mode):
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    result = {'protocol': PROTOCOL, 'acceptance': False, 'forced_gc': False,
              'mode': mode, 'count_per_group': CENSUS, 'fixture_count_per_group': FIXTURE_COUNT, 'stage_count': STAGES, 'stages': [], 'messages': [],
              'harness_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
              'runner_sha256': digest(Path(__file__)), 'hook_sha256': digest(HOOK), 'frida_version': frida.__version__, 'lifecycle_events': []}
    notes = subprocess.check_output(['readelf', '-n', str(BROWSER)], text=True)
    if 'Build ID: ' + BUILD not in notes:
        raise ValueError('Wrong browser build')
    result['build_id'] = BUILD
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    attached = None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=str(BROWSER), args=['--no-sandbox'])
            if browser.version != '156.0.8078.47':
                raise ValueError('Wrong browser version')
            result['browser_version'] = browser.version
            context = browser.new_context()
            context.add_init_script(r'''(() => {
                addEventListener('pagehide', event => {
                    const match = location.pathname.match(/^\/fixture\/(\d+)$/);
                    if (!match) return;
                    const data = {index: Number(match[1]), persisted: event.persisted};
                    console.timeStamp('membership-pagehide:' + data.index + ':' + data.persisted);
                    globalThis.membershipLifecycle(JSON.stringify(data));
                });
            })();''')
            page = context.new_page(); cdp = browser.new_browser_cdp_session(); completed = []
            processes = cdp.send('SystemInfo.getProcessInfo')['processInfo']
            browser_pids = [p['id'] for p in processes if p['type'] == 'browser']
            if len(browser_pids) != 1: raise ValueError('Ambiguous launched browser PID')
            arguments = Path(f'/proc/{browser_pids[0]}/cmdline').read_bytes().split(b'\0')
            result['back_forward_cache_disabled'] = b'--disable-back-forward-cache' in arguments
            result['launch_flag_verification'] = 'proc-cmdline-known-browser-pid'
            # Persist only the boolean, never unrelated argument or credential values.
            del arguments
            result['playwright_version'] = __import__('importlib.metadata', fromlist=['version']).version('playwright')
            page_cdp = context.new_cdp_session(page)
            def binding_event(event):
                if event['name'] == 'membershipLifecycle':
                    data = json.loads(event['payload'])
                    result['lifecycle_events'].append({**data, 'received_ns': time.monotonic_ns()})
            page_cdp.on('Runtime.bindingCalled', binding_event)
            page_cdp.send('Runtime.enable')
            page_cdp.send('Runtime.addBinding', {'name': 'membershipLifecycle'})
            result['lifecycle_transport'] = 'cdp-runtime-binding'
            cdp.on('Tracing.tracingComplete', lambda e: completed.append(e))
            cdp.send('Tracing.start', {'transferMode': 'ReturnAsStream', 'traceConfig': {
                'excludedCategories': ['*'], 'includedCategories': ['devtools.timeline'], 'recordMode': 'recordUntilFull'}})
            origin = f'http://127.0.0.1:{server.server_port}'
            page.goto(origin + '/empty'); cdp.send('Tracing.end')
            deadline = time.monotonic() + 15
            while not completed:
                if time.monotonic() > deadline: raise TimeoutError('Identity trace')
                page.wait_for_timeout(10)
            chunks = []; handle = completed[0]['stream']
            while True:
                chunk = cdp.send('IO.read', {'handle': handle}); chunks.append(chunk['data'])
                if chunk.get('eof'): break
            cdp.send('IO.close', {'handle': handle})
            trace = json.loads(''.join(chunks))
            pids = {e['pid'] for e in trace['traceEvents'] if e.get('name') == 'CommitLoad'
                    and e.get('args', {}).get('data', {}).get('url') == origin + '/empty'}
            if len(pids) != 1 or completed[0].get('dataLossOccurred'):
                raise ValueError('Ambiguous renderer identity')
            pid = pids.pop(); result['pid'] = pid
            if 'Build ID: ' + BUILD not in subprocess.check_output(['readelf', '-n', f'/proc/{pid}/exe'], text=True):
                raise ValueError('Wrong renderer build')
            (out / 'identity.json').write_text(json.dumps(trace) + '\n')
            script = None
            if mode == 'probe':
                attached = frida.attach(pid)
                script = attached.create_script(HOOK.read_text())
                script.on('message', lambda m, d: result['messages'].append(m)); script.load()
                if not any(m.get('payload', {}).get('ready') for m in result['messages']):
                    raise ValueError('Hooks not ready')
            def marker(name):
                start = time.monotonic_ns()
                cdp.send('Tracing.recordClockSyncMarker', {'syncId': name})
                return {'name': name, 'begin_ns': start, 'end_ns': time.monotonic_ns()}
            result['begin_ns'] = time.monotonic_ns()
            if mode == 'probe':
                start = time.monotonic_ns()
                cdp.send('Tracing.start', {'transferMode': 'ReturnAsStream', 'traceConfig': {
                    'excludedCategories': ['*'], 'includedCategories': ['devtools.timeline', 'blink', 'cppgc',
                        'disabled-by-default-cppgc', 'disabled-by-default-v8.gc'],
                    'traceBufferSizeInKb': 65536, 'recordMode': 'recordUntilFull', 'memoryDumpConfig': {}}})
                result['before'] = marker('membership-before')
                result['trace_setup_ns'] = time.monotonic_ns() - start
            for index in range(STAGES):
                stage = {'index': index, 'begin_ns': time.monotonic_ns(), 'censuses': []}
                result['stages'].append(stage)
                if script: script.exports_sync.setphase(f'navigation:{index}')
                page.goto(origin + f'/fixture/{index}'); page.wait_for_timeout(220)
                before = page.evaluate('document.documentElement.outerHTML')
                for group in ['avatar', 'other']:
                    for repeat in [0, 1]:
                        label = f'census:{index}:{group}:{repeat}'
                        census = {'phase': label, 'begin_ns': time.monotonic_ns()}
                        stage['censuses'].append(census)
                        if script: script.exports_sync.setphase(label)
                        census['result'] = page.evaluate('''({group, count}) => {
                            let nodes = [...document.querySelectorAll('[data-group="'+group+'"]')];
                            const fixture_count = nodes.length;
                            nodes = group === 'avatar' ? nodes.slice(-count) : nodes.slice(0, count);
                            let counts = nodes.map(node => node.getClientRects().length);
                            return {count: nodes.length, fixture_count, counts};
                        }''', {'group': group, 'count': CENSUS})
                        if script: script.exports_sync.setphase('between-censuses')
                        census['end_ns'] = time.monotonic_ns()
                after = page.evaluate('document.documentElement.outerHTML')
                stage['dom_before_sha256'] = hashlib.sha256(before.encode()).hexdigest()
                stage['dom_after_sha256'] = hashlib.sha256(after.encode()).hexdigest()
                start = time.monotonic_ns()
                stage['heap'] = {'value': page_cdp.send('Runtime.getHeapUsage'),
                                 'interval_ns': [start, time.monotonic_ns()]}
                start = time.monotonic_ns()
                stage['dom'] = {'value': page_cdp.send('Memory.getDOMCounters'),
                                'interval_ns': [start, time.monotonic_ns()]}
                stage['end_ns'] = time.monotonic_ns()
            result['end_ns'] = time.monotonic_ns()
            if mode == 'probe':
                result['after'] = marker('membership-after')
                count = len(completed); cdp.send('Tracing.end')
                deadline = time.monotonic() + 15
                while len(completed) == count:
                    if time.monotonic() > deadline: raise TimeoutError('Lifecycle trace completion')
                    page.wait_for_timeout(10)
                result['trace_completion'] = completed[-1]
                handle = completed[-1]['stream']; parts = []
                result['transfer_begin_ns'] = time.monotonic_ns()
                while True:
                    chunk = cdp.send('IO.read', {'handle': handle}); parts.append(chunk['data'])
                    if chunk.get('eof'): break
                cdp.send('IO.close', {'handle': handle})
                result['transfer_end_ns'] = time.monotonic_ns()
                (out / 'trace.json').write_text(''.join(parts))
            if script:
                result['history'] = script.exports_sync.result()
                script.unload(); attached.detach(); attached = None
            cdp.detach(); page_cdp.detach(); browser.close()
            result['status'] = 'captured'
    except Exception as error:
        result.update(status='capability_failed', error=repr(error))
    finally:
        if attached:
            try: attached.detach()
            except Exception: pass
        server.shutdown(); server.server_close()
        path = out / 'trace.json'
        if path.exists():
            with gzip.open(out / 'trace.json.gz', 'wb') as stream: stream.write(path.read_bytes())
            path.unlink()
        with gzip.open(out / 'capture.json.gz', 'wt') as stream:
            json.dump(result, stream)
    print(json.dumps({k: result.get(k) for k in ['status', 'error', 'pid']}), flush=True)
    return result['status'] != 'captured'


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', required=True, type=Path)
    p.add_argument('--mode', choices=['control', 'probe'], required=True); a = p.parse_args()
    raise SystemExit(run(a.out, a.mode))
