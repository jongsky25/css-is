"""Opt-in per-navigation allocator/GC/residency diagnostic; no forced GC."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import pytest
from playwright.sync_api import BrowserContext, Page
from tests import test_avatar_baseline_browser as baseline
from tests.test_avatar_baseline_browser import baseline_server

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_NAVIGATION_RESIDENCY')!='1',reason='Opt-in allocator diagnostic')


def test_navigation_residency(baseline_server,app_mod,monkeypatch):
    out=Path(os.environ['CSS_AVATAR_OUT']);state={'snapshots':0,'records':[],'complete':[],'pids':[],'samples':[]}
    stop=threading.Event();thread=None
    attach_original=BrowserContext.new_cdp_session;wait_original=Page.wait_for_timeout;snapshot_original=baseline.snapshot

    def sample_status():
        while not stop.is_set():
            entry={'begin_ns':time.monotonic_ns(),'renderers':[],'missing_pids':[]}
            for pid in tuple(state['pids']):
                try:
                    data={}
                    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
                        k,_,value=line.partition(':')
                        if k in ['VmRSS','RssAnon','RssFile','RssShmem','VmSwap']:data[k]=int(value.split()[0])*1024
                    entry['renderers'].append({'pid':pid,'status':data})
                except FileNotFoundError:entry['missing_pids'].append(pid)
            entry['end_ns']=time.monotonic_ns();state['samples'].append(entry);stop.wait(.1)

    def attach(context,page):
        cdp=attach_original(context,page);session=context.browser.new_browser_cdp_session()
        state.update(cdp=cdp,session=session,page=page)
        session.on('Tracing.tracingComplete',lambda e:state['complete'].append(e))
        return cdp

    def marker(name):
        start=time.monotonic_ns();state['session'].send('Tracing.recordClockSyncMarker',{'syncId':name})
        return {'begin_ns':start,'end_ns':time.monotonic_ns()}

    def wait(page,timeout):
        nonlocal thread
        result=wait_original(page,timeout)
        if page is state.get('page') and state['snapshots']>=8 and timeout==220:
            mount=len(state['records'])+1;assert mount<=20
            start=time.monotonic_ns();observed=snapshot_original(page,state['cdp']);observed_end=time.monotonic_ns()
            state['pids']=[d['pid'] for d in observed['renderer_memory_detail']]
            if thread is None:thread=threading.Thread(target=sample_status,daemon=True);thread.start()
            before=marker(f'nav-{mount}-before')
            request=state['session'].send('Tracing.requestMemoryDump',{'levelOfDetail':'detailed','determinism':'none'})
            after=marker(f'nav-{mount}-after')
            assert request['success'],request
            post_start=time.monotonic_ns();post=snapshot_original(page,state['cdp']);post_end=time.monotonic_ns()
            state['records'].append({'mount':mount,'snapshot':observed,'snapshot_interval_ns':[start,observed_end],
                'before_marker':before,'dump_request':request,'after_marker':after,
                'after_dump_snapshot':post,'after_snapshot_interval_ns':[post_start,post_end]})
            (out/'navigation-residency.json').write_text(json.dumps(state['records'],indent=2)+'\n')
        return result

    def snapshot(page,cdp):
        observed=snapshot_original(page,cdp);state['snapshots']+=1
        if state['snapshots']==8:
            state['session'].send('Tracing.start',{'transferMode':'ReturnAsStream','traceConfig':{
                'recordMode':'recordUntilFull','traceBufferSizeInKb':262144,
                'includedCategories':['v8','devtools.timeline','cppgc','disabled-by-default-cppgc',
                                      'disabled-by-default-v8.gc','disabled-by-default-memory-infra'],
                'memoryDumpConfig':{}}})
        if state['snapshots']==13:
            assert len(state['records'])==20
            stop.set()
            if thread:thread.join(timeout=5);assert not thread.is_alive()
            (out/'renderer-status.json').write_text(json.dumps(state['samples'],indent=2)+'\n')
            session=state['session'];session.send('Tracing.end');deadline=time.monotonic()+60
            while not state['complete']:
                assert time.monotonic()<deadline,'Trace completion timeout'
                wait_original(page,100)
            completion=state['complete'][0]
            handle=completion['stream']
            with gzip.open(out/'navigation-residency-trace.json.gz','wt') as f:
                while True:
                    chunk=session.send('IO.read',{'handle':handle});assert not chunk.get('base64Encoded')
                    f.write(chunk['data'])
                    if chunk.get('eof'):break
            session.send('IO.close',{'handle':handle});session.detach()
            (out/'residency-provenance.json').write_text(json.dumps({'acceptance':False,'forced_gc':False,
                'trace_scope':'navigation-only-v2','snapshots':13,'navigation_observations':20,'native_sampling':False,'allocator_dumps':20,'dump_determinism':'none','status_interval_seconds':.1,
                'trace_completion':completion,'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')
            assert not completion.get('dataLossOccurred'),'Trace data loss (raw trace retained)'
        return observed

    monkeypatch.setattr(BrowserContext,'new_cdp_session',attach);monkeypatch.setattr(Page,'wait_for_timeout',wait)
    monkeypatch.setattr(baseline,'snapshot',snapshot)
    try:baseline.test_real_application_baseline(baseline_server,app_mod,False,'warm')
    finally:
        stop.set()
        if thread:thread.join(timeout=5)
        (out/'renderer-status.json').write_text(json.dumps(state['samples'],indent=2)+'\n')
    assert state['snapshots']==13 and len(state['records'])==20
