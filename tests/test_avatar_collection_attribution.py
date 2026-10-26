"""Opt-in natural collection attribution, never acceptance evidence."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import time

import pytest
from playwright.sync_api import BrowserContext
from tests import test_avatar_baseline_browser as baseline
from tests.test_avatar_baseline_browser import baseline_server

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_COLLECTION_DIAGNOSTIC') != '1', reason='Opt-in collection attribution')


def test_collection_attribution(baseline_server, app_mod, monkeypatch):
    out = Path(os.environ['CSS_AVATAR_OUT']); out.mkdir(parents=True, exist_ok=True)
    labels = ['home_idle','home_interaction','wellness_care','picker_growth','seasonal_preview','offscreen','reduced_motion','background','navigation_1','navigation_5','navigation_10','navigation_15','navigation_20']
    native_dumps = os.getenv('CSS_AVATAR_RESIDENCY_DIAGNOSTIC') == '1'
    state = {'records':[], 'navigation':[], 'done':[]}
    new_session = BrowserContext.new_cdp_session
    snapshot = baseline.snapshot

    def attach(context, page):
        cdp = new_session(context, page)
        session = context.browser.new_browser_cdp_session()
        state['session'] = session
        session.on('Tracing.tracingComplete', lambda e: state['done'].append(e))
        config = {'recordMode':'recordUntilFull', 'includedCategories': ['v8','blink','blink_gc','v8.gc','cppgc','disabled-by-default-cppgc','disabled-by-default-v8.gc','disabled-by-default-blink_gc','devtools.timeline','blink.user_timing','loading']}
        if native_dumps:
            config['includedCategories'].append('disabled-by-default-memory-infra')
            config['memoryDumpConfig'] = {}
        session.send('Tracing.start', {'transferMode':'ReturnAsStream', 'traceConfig':config})
        cdp.send('Page.enable')
        cdp.on('Page.frameNavigated', lambda e: state['navigation'].append({'monotonic_ns':time.monotonic_ns(),'event':e}))
        cdp.send('Memory.startSampling', {'samplingInterval':32768})
        return cdp

    def capture(page, cdp):
        observed = snapshot(page, cdp)
        index = len(state['records']); label = labels[index]
        session = state['session']
        session.send('Tracing.recordClockSyncMarker', {'syncId':label})
        profile = cdp.send('Memory.getSamplingProfile')
        with gzip.open(out/f'{label}-native.json.gz','wt') as f: json.dump(profile,f)
        record = {'checkpoint':label,'monotonic_ns':time.monotonic_ns(),'snapshot':observed,
            'targets':session.send('Target.getTargets')['targetInfos'],
            'processes':session.send('SystemInfo.getProcessInfo')['processInfo'],
            'frame_tree':cdp.send('Page.getFrameTree')}
        if native_dumps:
            record['dump_request'] = session.send('Tracing.requestMemoryDump', {'levelOfDetail':'detailed'})
            assert record['dump_request']['success'], record['dump_request']
            record['after_dump_snapshot'] = snapshot(page, cdp)
        state['records'].append(record)
        (out/'checkpoints.json').write_text(json.dumps(state['records'],indent=2))
        (out/'navigation.json').write_text(json.dumps(state['navigation'],indent=2))
        if len(state['records']) == len(labels):
            cdp.send('Memory.stopSampling'); session.send('Tracing.end')
            deadline=time.monotonic()+60
            while not state['done']:
                assert time.monotonic()<deadline
                page.wait_for_timeout(100)
            assert not state['done'][0].get('dataLossOccurred')
            handle=state['done'][0]['stream']
            with gzip.open(out/'collection-trace.json.gz','wt') as f:
                while True:
                    chunk=session.send('IO.read',{'handle':handle}); f.write(chunk['data'])
                    if chunk.get('eof'):break
            session.send('IO.close',{'handle':handle}); session.detach()
        return observed

    monkeypatch.setattr(BrowserContext,'new_cdp_session',attach)
    monkeypatch.setattr(baseline,'snapshot',capture)
    baseline.test_real_application_baseline(baseline_server,app_mod,False,'warm')
    assert len(state['records'])==13
    (out/'provenance.json').write_text(json.dumps({'acceptance':False,'instrumented':True,
        'protocol':'Full unchanged warm desktop sequence; natural collection only; no extra cache flush or forced GC. Native sampling covers target session, trace covers browser processes.',
        'native_allocator_dumps':native_dumps, 'trace_completion':state['done'][0],
        'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2))
