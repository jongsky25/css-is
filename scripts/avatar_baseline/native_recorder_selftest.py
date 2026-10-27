"""Bounded CModule ABI/clock/concurrency/overflow preflight; no workload measurements."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
import frida
from playwright.sync_api import sync_playwright
from tests import avatar_page_history_probe as helper
from scripts.avatar_baseline.mixed_membership_fixture import Handler

BROWSER=Path('/workspace/scratch/avatar-runtime/root/usr/lib/chromium/chromium')
HOOK=Path(__file__).resolve().parent/'native/callback_buffer.js'
PREFIX='globalThis.RECORDER_SELF_TEST_ONLY=true;\n'
SOURCES=['scripts/avatar_baseline/native_recorder_selftest.py','scripts/avatar_baseline/native/callback_buffer.js',
         'tests/avatar_page_history_probe.py','scripts/avatar_baseline/mixed_membership_fixture.py']


def validate(p):
    if p.get('error'):raise ValueError(p['error'])
    if len(p['clock_samples'])!=20:raise ValueError('Incomplete clock proof')
    for c in p['clock_samples']:
        if not 0<c['begin_ns']<=c['native_ns']<=c['end_ns']:raise ValueError('Wrong native clock domain')
    for label,expected_count,expected_dropped,expected_limit in [('concurrency',1024,0,50000),('overflow',32,36,32)]:
        q=p[label];history=q['history']
        if (history.get('recorder_backend')!='cmodule-buffer-v1' or history.get('clock_domain')!='CLOCK_MONOTONIC'
            or history.get('abi')!='linux-x64-gum-invocation-v1' or history.get('toolchain')!='internal'
            or not q['begin_ns']<=history['snapshot_end_ns']<=q['end_ns']
            or 'w' not in history['storage']['first_protection'] or 'w' not in history['storage']['last_protection']
            or history['storage']['state_bytes']>history['storage']['allocated_bytes']
            or history['record_size']!=72 or history['record_capacity']!=50000 or history['record_limit']!=expected_limit
            or history['pending_at_snapshot']!=0 or history['dropped']!=expected_dropped or len(history['events'])!=expected_count):
            raise ValueError('Native buffer/overflow proof failed')
        addresses=set();threads=set();workers=set()
        for e in history['events']:
            address=int(e['address'],16);worker=address>>32;seq=address&0xffffffff
            if (e['kind']!='__selftest' or not 1<=worker<=4 or not 1<=seq<=(256 if label=='concurrency' else 17)
                or int(e['backend'],16)!=(address^0x5a5a) or address in addresses
                or e['phase_id']!=e['phase_document'] or e['phase_type']!=1
                or not q['begin_ns']<=e['begin_ns']<=e['callback_ready_ns']<=e['returned_ns']<=q['end_ns']):
                raise ValueError('Native immutable value/thread/phase/clock proof failed')
            addresses.add(address);threads.add(e['thread']);workers.add(worker)
        if label=='concurrency' and (len(threads)!=4 or workers!={1,2,3,4}):raise ValueError('Concurrency thread coverage failed')
    return {'status':'selftest_passed','acceptance':False,'clock_samples':20,'native_threads':4,
            'immutable_records':1024,'overflow_stored':32,'overflow_dropped':36,'record_size':72}


def audit(root,repo,ref):
    p=json.load(gzip.open(root/'capture.json.gz','rt'))
    if p['harness_commit']!=ref or set(p['source_sha256'])!=set(SOURCES):raise ValueError('Wrong self-test source inventory')
    for name,digest in p['source_sha256'].items():
        if hashlib.sha256(subprocess.check_output(['git','show',ref+':'+name],cwd=repo)).hexdigest()!=digest:raise ValueError('Self-test source changed')
    if p['identity']['build_id']!='1c5dca8527a61d07372e489142bee26af1bcaf71' or p['frida_version']!='17.5.1':raise ValueError('Wrong native environment')
    if any(m.get('type')=='error' for m in p['messages']):raise ValueError('Native agent error')
    return {**validate(p),'harness_commit':ref,'source_hashes_verified':len(SOURCES),
            'capture_sha256':hashlib.sha256((root/'capture.json.gz').read_bytes()).hexdigest()}


def run(out):
    out.mkdir(parents=True,exist_ok=False);repo=Path(__file__).resolve().parents[2]
    ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip();hashes={}
    for name in SOURCES:
        data=(repo/name).read_bytes()
        if data!=subprocess.check_output(['git','show',ref+':'+name],cwd=repo):raise ValueError('Uncommitted self-test')
        hashes[name]=hashlib.sha256(data).hexdigest()
    p={'harness_commit':ref,'source_sha256':hashes,'prefix_sha256':hashlib.sha256(PREFIX.encode()).hexdigest(),
       'acceptance':False,'frida_version':frida.__version__,'messages':[],'clock_samples':[]}
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.lifecycle_events=[]
    threading.Thread(target=server.serve_forever,daemon=True).start();session=None
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=str(BROWSER),args=['--no-sandbox'])
            if browser.version!='156.0.8078.47':raise ValueError('Wrong browser version')
            page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/empty')
            identity=helper.PageHistory(page,False);p['identity']=identity.finish()
            session=frida.attach(p['identity']['pid']);script=session.create_script(PREFIX+HOOK.read_text())
            script.on('message',lambda m,d:p['messages'].append(m));script.load()
            if not any(m.get('payload',{}).get('selftest_ready') for m in p['messages']):raise ValueError('CModule did not initialize')
            for _ in range(20):
                begin=time.monotonic_ns();value=script.exports_sync.clock()
                p['clock_samples'].append({'begin_ns':begin,'native_ns':value,'end_ns':time.monotonic_ns()})
            for name,iterations,limit in [('concurrency',256,50000),('overflow',17,32)]:
                begin=time.monotonic_ns();history=script.exports_sync.selftest(4,iterations,limit)
                p[name]={'begin_ns':begin,'end_ns':time.monotonic_ns(),'history':history}
            script.unload();session.detach();session=None;browser.close()
    except Exception as e:p['error']=repr(e)
    finally:
        if session:
            try:session.detach()
            except Exception:pass
        server.shutdown();server.server_close()
        with gzip.open(out/'capture.json.gz','wt') as f:json.dump(p,f)
    try:a=audit(out,repo,ref)
    except (ValueError,KeyError,TypeError,OSError) as e:a={'status':'selftest_failed','acceptance':False,'harness_commit':ref,'error':repr(e)}
    (out/'assessment.json').write_text(json.dumps(a,indent=2)+'\n');print(json.dumps(a));return a['status']!='selftest_passed'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();raise SystemExit(run(a.out))
