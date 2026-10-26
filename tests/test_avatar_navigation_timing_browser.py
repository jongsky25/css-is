"""Opt-in per-navigation natural-GC timing; never acceptance evidence."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import time

import pytest
from playwright.sync_api import BrowserContext, Page
from tests import test_avatar_baseline_browser as baseline
from tests.test_avatar_baseline_browser import baseline_server

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_NAVIGATION_TIMING') != '1', reason='Opt-in timing diagnostic')


def test_navigation_timing(baseline_server, app_mod, monkeypatch):
    out = Path(os.environ['CSS_AVATAR_OUT'])
    state = {'snapshots':0, 'records':[], 'complete':[]}
    attach_original = BrowserContext.new_cdp_session
    wait_original = Page.wait_for_timeout
    snapshot_original = baseline.snapshot

    def attach(context, page):
        cdp = attach_original(context, page)
        session = context.browser.new_browser_cdp_session()
        state.update(cdp=cdp, session=session, page=page)
        session.on('Tracing.tracingComplete', lambda e: state['complete'].append(e))
        session.send('Tracing.start', {'transferMode':'ReturnAsStream', 'traceConfig':{
            'recordMode':'recordUntilFull', 'includedCategories':[
                'v8','devtools.timeline','cppgc','disabled-by-default-cppgc']}})
        return cdp

    def wait(page, timeout):
        result = wait_original(page, timeout)
        if page is state.get('page') and state['snapshots'] >= 8 and timeout == 220:
            mount = len(state['records'])+1
            assert mount <= 20
            session, cdp = state['session'], state['cdp']
            start = time.monotonic_ns()
            session.send('Tracing.recordClockSyncMarker', {'syncId':f'nav-{mount}-before'})
            dom_start = time.monotonic_ns()
            dom = cdp.send('Memory.getDOMCounters')
            dom_end = time.monotonic_ns()
            heap = cdp.send('Runtime.getHeapUsage')
            heap_end = time.monotonic_ns()
            session.send('Tracing.recordClockSyncMarker', {'syncId':f'nav-{mount}-after'})
            finish = time.monotonic_ns()
            state['records'].append({'mount':mount,'dom':dom,'heap':heap,
                'start_ns':start,'dom_start_ns':dom_start,'dom_end_ns':dom_end,
                'heap_end_ns':heap_end,'finish_ns':finish})
            (out/'navigation-timing.json').write_text(json.dumps(state['records'],indent=2))
        return result

    def snapshot(page, cdp):
        result = snapshot_original(page, cdp)
        state['snapshots'] += 1
        if state['snapshots'] == 13:
            assert len(state['records']) == 20
            session = state['session']; session.send('Tracing.end')
            deadline = time.monotonic()+60
            while not state['complete']:
                assert time.monotonic() < deadline, 'Trace completion timeout'
                wait_original(page,100)
            completion = state['complete'][0]
            assert not completion.get('dataLossOccurred'), 'Trace data loss'
            handle = completion['stream']
            with gzip.open(out/'navigation-trace.json.gz','wt') as stream:
                while True:
                    chunk = session.send('IO.read',{'handle':handle})
                    assert not chunk.get('base64Encoded'), 'Unexpected trace encoding'
                    stream.write(chunk['data'])
                    if chunk.get('eof'):break
            session.send('IO.close',{'handle':handle}); session.detach()
            (out/'timing-provenance.json').write_text(json.dumps({
                'acceptance':False,'native_sampling':False,'allocator_dumps':False,
                'trace_completion':completion,'snapshots':13,'navigation_observations':20,
                'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2))
        return result

    monkeypatch.setattr(BrowserContext,'new_cdp_session',attach)
    monkeypatch.setattr(Page,'wait_for_timeout',wait)
    monkeypatch.setattr(baseline,'snapshot',snapshot)
    baseline.test_real_application_baseline(baseline_server,app_mod,False,'warm')
    assert state['snapshots']==13 and len(state['records'])==20
