"""Full real-app baseline with bounded read-only native membership observation."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import time
import pytest
from playwright.sync_api import Page, BrowserContext
from starlette.responses import HTMLResponse
from starlette.routing import Route
from tests import test_avatar_baseline_browser as baseline
from tests.test_avatar_baseline_browser import baseline_server
from tests import avatar_page_history_probe as native_helper
from tests.avatar_application_membership import QUERY_JS, BATCH_JS

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_APP_MEMBERSHIP')!='1',reason='Opt-in application observer calibration')


def test_application_membership(baseline_server,app_mod,monkeypatch):
    out=Path(os.environ['CSS_AVATAR_OUT']);mode=os.environ['CSS_AVATAR_APP_MODE']
    state={'protocol':'application-membership-v1','acceptance':False,'forced_gc':False,'mode':mode,
           'harness_commit':os.environ['CSS_AVATAR_APP_HARNESS_REF'],'snapshots':0,'mount':0,
           'navigations':[],'checkpoints':[],'queries':[],'messages':[],
           'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'selection_sha256':hashlib.sha256(Path('tests/avatar_application_membership.py').read_bytes()).hexdigest()}
    create=BrowserContext.new_page;goto=Page.goto;snapshot=baseline.snapshot
    primary=None;probe=None;cdp=None;completed=[];trace_active=False
    origin=baseline_server[0];original_hook=native_helper.HOOK
    async def empty(request):return HTMLResponse('<!doctype html><title>Observer identity</title>')
    route=Route('/_avatar_native_identity',empty);app_mod.app.router.routes.insert(0,route)
    def mark(name):
        begin=time.monotonic_ns();cdp.send('Tracing.recordClockSyncMarker',{'syncId':name})
        return {'name':name,'begin_ns':begin,'end_ns':time.monotonic_ns()}
    def new_page(context,*args,**kwargs):
        nonlocal primary,probe,cdp
        page=create(context,*args,**kwargs)
        if primary is None:
            primary=page;start=time.monotonic_ns()
            assert goto(page,origin+'/_avatar_native_identity').status==200
            native_helper.HOOK=Path('scripts/avatar_baseline/native/callback_buffer.js').resolve()
            probe=native_helper.PageHistory(page,mode!='control')
            if mode=='proof':probe.script.exports_sync.enablereference()
            cdp=context.browser.new_browser_cdp_session()
            cdp.on('Tracing.tracingComplete',lambda e:completed.append(e))
            pids=[p['id'] for p in cdp.send('SystemInfo.getProcessInfo')['processInfo'] if p['type']=='browser']
            assert len(pids)==1
            state['back_forward_cache_disabled']=b'--disable-back-forward-cache' in Path(f'/proc/{pids[0]}/cmdline').read_bytes().split(b'\0')
            state['bootstrap_interval_ns']=[start,time.monotonic_ns()]
        return page
    def navigate(page,*args,**kwargs):
        if page is not primary or not 8<=state['snapshots']<13:return goto(page,*args,**kwargs)
        state['mount']+=1;index=state['mount'];start=time.monotonic_ns()
        if mode=='probe':probe.phase(f'navigation:{index}')
        armed=time.monotonic_ns();result=goto(page,*args,**kwargs);loaded=time.monotonic_ns()
        row={'mount':index,'begin_ns':start,'arm_end_ns':armed,'goto_end_ns':loaded}
        state['navigations'].append(row)
        if mode!='proof':
            begin=time.monotonic_ns();rows=page.evaluate(BATCH_JS);end=time.monotonic_ns()
            row['census_interval_ns']=[begin,end];row['censuses']=rows
        row['end_ns']=time.monotonic_ns();return result
    def capture(page,session):
        nonlocal probe,trace_active
        begin=time.monotonic_ns();result=snapshot(page,session);end=time.monotonic_ns();state['snapshots']+=1
        if state['snapshots']==8:
            if mode=='proof':
                for group in ['avatar','other']:
                    for repeat in [0,1]:
                        for kind in ['reference','census']:
                            phase=f'{kind}:0:{group}:{repeat}';probe.phase(phase)
                            lo=time.monotonic_ns();value=page.evaluate(QUERY_JS,{'group':group,'kind':kind});hi=time.monotonic_ns()
                            state['queries'].append({'phase':phase,'begin_ns':lo,'end_ns':hi,'result':value})
                probe.phase('idle')
            state['begin_ns']=time.monotonic_ns()
            if mode=='probe':
                lo=time.monotonic_ns()
                cdp.send('Tracing.start',{'transferMode':'ReturnAsStream','traceConfig':{
                    'excludedCategories':['*'],'includedCategories':['devtools.timeline','blink','cppgc',
                    'disabled-by-default-cppgc','disabled-by-default-v8.gc'],
                    'traceBufferSizeInKb':65536,'recordMode':'recordUntilFull','memoryDumpConfig':{}}})
                trace_active=True;state['before']=mark('application-before');state['trace_setup_ns']=time.monotonic_ns()-lo
        elif state['snapshots']>8:
            state['checkpoints'].append({'mount':state['mount'],'interval_ns':[begin,end],'snapshot':result})
            if state['mount']==20:
                state['end_ns']=time.monotonic_ns()
                if trace_active:
                    state['after']=mark('application-after');count=len(completed);cdp.send('Tracing.end');trace_active=False
                    deadline=time.monotonic()+20
                    while len(completed)==count:
                        if time.monotonic()>deadline:raise TimeoutError('Application trace completion')
                        page.wait_for_timeout(10)
                    state['trace_completion']=completed[-1];handle=completed[-1]['stream'];parts=[]
                    state['transfer_begin_ns']=time.monotonic_ns()
                    while True:
                        chunk=cdp.send('IO.read',{'handle':handle});parts.append(chunk['data'])
                        if chunk.get('eof'):break
                    cdp.send('IO.close',{'handle':handle});state['transfer_end_ns']=time.monotonic_ns()
                    with gzip.open(out/'application-trace.json.gz','wt') as stream:stream.write(''.join(parts))
                lo=time.monotonic_ns();state['native']=probe.finish();probe=None;state['native_export_interval_ns']=[lo,time.monotonic_ns()]
        return result
    monkeypatch.setattr(BrowserContext,'new_page',new_page)
    monkeypatch.setattr(Page,'goto',navigate);monkeypatch.setattr(baseline,'snapshot',capture)
    try:
        state['workload_begin_ns']=time.monotonic_ns()
        baseline.test_real_application_baseline(baseline_server,app_mod,False,'warm')
        state['workload_end_ns']=time.monotonic_ns();state['status']='captured'
    except Exception as error:
        state.update(status='capture_failed',error=repr(error));raise
    finally:
        if probe:
            try:state['partial_native']=probe.finish()
            except Exception as error:state['finish_error']=repr(error)
        if cdp:
            try:cdp.detach()
            except Exception:pass
        native_helper.HOOK=original_hook;app_mod.app.router.routes.remove(route)
        with gzip.open(out/'application-membership.json.gz','wt') as stream:json.dump(state,stream)
    assert state['snapshots']==13 and state['mount']==20 and state['back_forward_cache_disabled']
