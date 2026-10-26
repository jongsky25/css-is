"""Opt-in native allocation attribution; never acceptance evidence."""
import gzip
import json
import os
from pathlib import Path
import time

import pytest
from tests import test_avatar_baseline_browser as baseline
from tests.test_avatar_baseline_browser import baseline_server

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_ALLOCATION_DIAGNOSTIC') != '1', reason='Opt-in native allocation diagnosis')


def test_lifecycle_allocations(baseline_server, app_mod, monkeypatch):
    out = Path(os.environ['CSS_AVATAR_OUT'])
    checkpoints = ['home_idle','home_interaction','wellness_care','picker_growth',
                   'seasonal_preview','offscreen','reduced_motion','background',
                   'navigation_1','navigation_5','navigation_10','navigation_15','navigation_20']
    original = baseline.snapshot
    state = {'index': 0, 'requests': []}

    def capture(page, cdp):
        observed = original(page, cdp)
        label = checkpoints[state['index'] % len(checkpoints)]
        if 'session' not in state:
            session = page.context.browser.new_browser_cdp_session()
            state['session'] = session
            state['done'] = []
            session.on('Tracing.tracingComplete', lambda event: state['done'].append(event))
            session.send('Tracing.start', {'traceConfig': {
                'recordMode': 'recordUntilFull',
                'includedCategories': ['disabled-by-default-memory-infra'],
                'memoryDumpConfig': {}}, 'transferMode': 'ReturnAsStream'})
        session = state['session']
        dump = session.send('Tracing.requestMemoryDump', {'levelOfDetail':'detailed'})
        assert dump['success'], dump
        state['requests'].append({'checkpoint':label, 'run':state['index']//len(checkpoints),
                                  'request':dump, 'snapshot':observed,
                                  'targets':session.send('Target.getTargets')['targetInfos']})
        (out/'allocation-requests.json').write_text(json.dumps(state['requests'],indent=2))
        state['index'] += 1
        if state['index'] == int(os.environ.get('CSS_AVATAR_RUNS','1'))*len(checkpoints):
            session.send('Tracing.end')
            deadline = time.monotonic()+60
            while not state['done']:
                assert time.monotonic()<deadline, 'Trace completion timed out'
                page.wait_for_timeout(100)
            assert not state['done'][0].get('dataLossOccurred'), 'Trace lost data'
            handle=state['done'][0]['stream']
            with gzip.open(out/'memory-trace.json.gz','wt') as target:
                while True:
                    chunk=session.send('IO.read',{'handle':handle})
                    target.write(chunk['data'])
                    if chunk.get('eof'):break
            session.send('IO.close',{'handle':handle})
            session.detach()
        return observed

    monkeypatch.setattr(baseline, 'snapshot', capture)
    baseline.test_real_application_baseline(baseline_server, app_mod, False, 'warm')
    assert state['index'] == int(os.environ.get('CSS_AVATAR_RUNS','1'))*len(checkpoints)
