"""One navigation GC trace, component brackets, no polling or allocator dumps."""
import gzip
import json
import os
from pathlib import Path
import time
import pytest
from playwright.sync_api import Page, CDPSession, BrowserContext
from tests import test_avatar_baseline_browser as baseline
from tests.test_avatar_baseline_browser import baseline_server
from tests.avatar_snapshot_timing import SnapshotTiming

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_SNAPSHOT_ORDER') != '1', reason='Opt-in diagnostic')
CATEGORIES = ['devtools.timeline', 'cppgc', 'disabled-by-default-cppgc', 'disabled-by-default-v8.gc']


def test_snapshot_order(baseline_server, app_mod, monkeypatch):
    out = Path(os.environ['CSS_AVATAR_OUT'])
    probe = os.environ['CSS_AVATAR_ORDER_MODE'] == 'probe'
    state = {'protocol': 'snapshot-order-v1', 'acceptance': False, 'forced_gc': False,
             'mode': 'probe' if probe else 'control', 'snapshots': [], 'navigations': []}
    completions = []
    session = None
    page_ref = None
    capture_original = baseline.snapshot
    attach_original = BrowserContext.new_cdp_session
    goto_original = Page.goto
    timing = SnapshotTiming(monkeypatch, Page, CDPSession) if probe else None

    def attach(context, page):
        nonlocal session, page_ref
        cdp = attach_original(context, page)
        page_ref = page
        session = context.browser.new_browser_cdp_session()
        session.on('Tracing.tracingComplete', lambda e: completions.append(e))
        return cdp

    def marker(name):
        begin = time.monotonic_ns()
        session.send('Tracing.recordClockSyncMarker', {'syncId': name})
        return {'name': name, 'begin_ns': begin, 'end_ns': time.monotonic_ns()}

    def navigate(page, *args, **kwargs):
        if page is page_ref and 8 <= len(state['snapshots']) < 13:
            row = {'mount': len(state['navigations']) + 1, 'begin_ns': time.monotonic_ns()}
            state['navigations'].append(row)
            try:
                return goto_original(page, *args, **kwargs)
            finally:
                row['goto_end_ns'] = time.monotonic_ns()
        return goto_original(page, *args, **kwargs)

    def capture(page, cdp):
        begin = time.monotonic_ns()
        if probe:
            result, bracket = timing.capture(capture_original, page, cdp)
        else:
            result = capture_original(page, cdp)
            bracket = {'interval_ns': [begin, time.monotonic_ns()], 'calls': []}
        index = len(state['snapshots'])
        state['snapshots'].append({'index': index, 'mount': len(state['navigations']),
                                   'snapshot': result, **bracket})
        if index == 7:
            state['navigation_begin_ns'] = time.monotonic_ns()
            if probe:
                start = time.monotonic_ns()
                session.send('Tracing.start', {'transferMode': 'ReturnAsStream', 'traceConfig': {
                    'recordMode': 'recordUntilFull', 'traceBufferSizeInKb': 65536,
                    'excludedCategories': ['*'], 'includedCategories': CATEGORIES, 'memoryDumpConfig': {}}})
                state['before'] = marker('order-before')
                state['trace_setup_ns'] = time.monotonic_ns() - start
        if index == 12:
            state['navigation_end_ns'] = time.monotonic_ns()
            if probe:
                state['after'] = marker('order-after')
                session.send('Tracing.end')
                deadline = time.monotonic() + 60
                while not completions:
                    assert time.monotonic() < deadline, 'Trace completion timeout'
                    page.wait_for_timeout(10)
                state['completion'] = completions[-1]
                state['transfer_begin_ns'] = time.monotonic_ns()
                handle = completions[-1]['stream']
                with (out / 'trace.json').open('w') as stream:
                    while True:
                        chunk = session.send('IO.read', {'handle': handle})
                        assert not chunk.get('base64Encoded')
                        stream.write(chunk['data'])
                        if chunk.get('eof'):
                            break
                session.send('IO.close', {'handle': handle})
                state['transfer_end_ns'] = time.monotonic_ns()
            session.detach()
        return result

    monkeypatch.setattr(BrowserContext, 'new_cdp_session', attach)
    monkeypatch.setattr(Page, 'goto', navigate)
    monkeypatch.setattr(baseline, 'snapshot', capture)
    try:
        baseline.test_real_application_baseline(baseline_server, app_mod, False, 'warm')
    finally:
        (out / 'order-provenance.json').write_text(json.dumps(state, indent=2) + '\n')
        path = out / 'trace.json'
        if path.exists():
            with gzip.open(out / 'trace.json.gz', 'wb') as stream:
                stream.write(path.read_bytes())
            path.unlink()
    assert len(state['snapshots']) == 13 and len(state['navigations']) == 20
    assert not probe or not state['completion'].get('dataLossOccurred')
