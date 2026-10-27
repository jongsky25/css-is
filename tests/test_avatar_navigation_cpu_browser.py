"""Bounded natural-GC trace; allocator dump only AFTER navigation measurements."""
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
from tests.avatar_scheduler_probe import read_scheduler, scheduler_environment
from tests.avatar_cpu_probe import CpuProfiles
from tests.test_avatar_baseline_browser import baseline_server

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_NAVIGATION_LIGHT') != '1', reason='Opt-in diagnostic')
GC_CATEGORIES = ['devtools.timeline', 'cppgc', 'disabled-by-default-cppgc', 'disabled-by-default-v8.gc', 'disabled-by-default-v8.cpu_profiler']


def test_navigation_cpu(baseline_server, app_mod, monkeypatch):
    out = Path(os.environ['CSS_AVATAR_OUT'])
    traced = os.environ['CSS_AVATAR_TRACE_MODE'] == 'trace'
    state = {'protocol': 'navigation-cpu-v2', 'mode': 'trace' if traced else 'control',
             'acceptance': False, 'forced_gc': False, 'snapshots': 0, 'mount': 0,
             'segments': [], 'rotations': [], 'checkpoints': [], 'samples': [], 'pids': [],
             'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    cpu = None
    profile_data = None
    state['cpu_probe_sha256'] = hashlib.sha256(Path(__file__).with_name('avatar_cpu_probe.py').read_bytes()).hexdigest()
    state['cpu_profile_enabled'] = traced
    state['scheduler_environment'] = scheduler_environment()
    state['navigation_intervals'] = []
    state['scheduler_edges'] = []
    state['scheduler_probe_sha256'] = hashlib.sha256(Path(__file__).with_name('avatar_scheduler_probe.py').read_bytes()).hexdigest()
    stop = threading.Event()
    worker = None
    attach_original = BrowserContext.new_cdp_session
    goto_original = Page.goto
    wait_original = Page.wait_for_timeout
    snapshot_original = baseline.snapshot
    completions = []
    session = None
    active = None

    def sample_status():
        while not stop.is_set():
            row = {'begin_ns': time.monotonic_ns(), 'renderers': [], 'missing_pids': []}
            for pid in tuple(state['pids']):
                try:
                    fields = {}
                    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
                        key, _, value = line.partition(':')
                        if key in ('VmRSS', 'RssAnon', 'RssFile', 'RssShmem', 'VmSwap'):
                            fields[key] = int(value.split()[0]) * 1024
                    row['renderers'].append({'pid': pid, 'status': fields})
                except FileNotFoundError:
                    row['missing_pids'].append(pid)
            row['scheduler'] = read_scheduler(state['pids'], os.getpid(), threading.get_native_id())
            row['end_ns'] = time.monotonic_ns()
            state['samples'].append(row)
            stop.wait(.1)

    def attach(context, page):
        nonlocal session, cpu
        cdp = attach_original(context, page)
        session = context.browser.new_browser_cdp_session()
        session.on('Tracing.tracingComplete', lambda event: completions.append(event))
        state['page'] = page
        if traced:
            cpu = CpuProfiles(cdp)
        return cdp

    def marker(name):
        start = time.monotonic_ns()
        session.send('Tracing.recordClockSyncMarker', {'syncId': name})
        return {'begin_ns': start, 'end_ns': time.monotonic_ns(), 'name': name}

    def start_trace(number, categories):
        nonlocal active
        begin = time.monotonic_ns()
        session.send('Tracing.start', {'transferMode': 'ReturnAsStream', 'traceConfig': {
            'recordMode': 'recordUntilFull', 'traceBufferSizeInKb': 65536,
            'excludedCategories': ['*'], 'includedCategories': categories, 'memoryDumpConfig': {}}})
        active = {'number': number, 'start_ns': begin, 'categories': categories,
                  'before': marker(f'segment-{number}-before')}

    def finish_trace():
        nonlocal active
        active['after'] = marker(f"segment-{active['number']}-after")
        count = len(completions)
        session.send('Tracing.end')
        deadline = time.monotonic() + 60
        while len(completions) == count:
            assert time.monotonic() < deadline, 'Trace completion timeout'
            wait_original(state['page'], 10)
        completion = completions[-1]
        active.update(completion=completion, end_ns=time.monotonic_ns(),
                      trace_file=f"trace-{active['number']}.json.gz")
        state['segments'].append(active)
        active = None

    def drain_traces():
        state['transfers'] = []
        for segment in state['segments']:
            begin = time.monotonic_ns()
            path = out / segment['trace_file'].removesuffix('.gz')
            handle = segment['completion']['stream']
            with path.open('w') as stream:
                while True:
                    chunk = session.send('IO.read', {'handle': handle})
                    assert not chunk.get('base64Encoded')
                    stream.write(chunk['data'])
                    if chunk.get('eof'):
                        break
            session.send('IO.close', {'handle': handle})
            state['transfers'].append({'number': segment['number'], 'begin_ns': begin,
                                       'end_ns': time.monotonic_ns(), 'bytes': path.stat().st_size})

    def goto(page, *args, **kwargs):
        if page is state.get('page') and 8 <= state['snapshots'] < 13:
            begin = time.monotonic_ns()
            result = goto_original(page, *args, **kwargs)
            state['navigation_intervals'].append({'mount': len(state['navigation_intervals']) + 1,
                                                  'begin_ns': begin, 'goto_end_ns': time.monotonic_ns()})
            return result
        return goto_original(page, *args, **kwargs)

    def wait(page, timeout):
        result = wait_original(page, timeout)
        if page is state.get('page') and 8 <= state['snapshots'] < 13 and timeout == 220:
            state['mount'] += 1
            state['navigation_intervals'][-1]['wait_end_ns'] = time.monotonic_ns()
        return result

    def snapshot(page, cdp):
        nonlocal worker, profile_data
        begin = time.monotonic_ns()
        observed = snapshot_original(page, cdp)
        end = time.monotonic_ns()
        state['snapshots'] += 1
        state['pids'] = [d['pid'] for d in observed['renderer_memory_detail']]
        if state['snapshots'] == 8:
            state['scheduler_edges'].append(read_scheduler(state['pids'], os.getpid(), threading.get_native_id()))
            state['navigation_begin_ns'] = time.monotonic_ns()
            worker = threading.Thread(target=sample_status, daemon=True)
            worker.start()
            start = time.monotonic_ns()
            if traced:
                start_trace(0, GC_CATEGORIES)
                cpu.start()
            state['rotations'].append({'mount': 0, 'begin_ns': start, 'end_ns': time.monotonic_ns()})
        elif state['snapshots'] > 8:
            mount = state['mount']
            state['checkpoints'].append({'mount': mount, 'snapshot': observed,
                                         'interval_ns': [begin, end]})
            if mount == 10:
                start = time.monotonic_ns()
                if traced:
                    finish_trace()
                    start_trace(1, GC_CATEGORIES)
                state['rotations'].append({'mount': mount, 'begin_ns': start, 'end_ns': time.monotonic_ns()})
            if mount == 20:
                # Everything below is outside the measured navigation window.
                state['navigation_end_ns'] = time.monotonic_ns()
                stop.set()
                worker.join(timeout=5)
                assert not worker.is_alive()
                state['scheduler_edges'].append(read_scheduler(state['pids'], os.getpid(), threading.get_native_id()))
                if cpu:
                    profile_data = cpu.stop()
                if traced:
                    finish_trace()
                    start_trace(2, ['disabled-by-default-memory-infra'])
                    state['endpoint_before'] = marker('endpoint-before')
                    state['endpoint_request'] = session.send('Tracing.requestMemoryDump', {
                        'levelOfDetail': 'detailed', 'determinism': 'none'})
                    state['endpoint_after'] = marker('endpoint-after')
                    finish_trace()
                    drain_traces()
                session.detach()
        return observed

    monkeypatch.setattr(BrowserContext, 'new_cdp_session', attach)
    monkeypatch.setattr(Page, 'wait_for_timeout', wait)
    monkeypatch.setattr(Page, 'goto', goto)
    monkeypatch.setattr(baseline, 'snapshot', snapshot)
    try:
        baseline.test_real_application_baseline(baseline_server, app_mod, False, 'warm')
    finally:
        if cpu and cpu.started:
            profile_data = cpu.stop()
        if profile_data is not None:
            with gzip.open(out / 'cpu-profiles.json.gz', 'wt') as target:
                json.dump(profile_data, target)
        stop.set()
        if worker:
            worker.join(timeout=5)
        state.pop('page', None)
        (out / 'light-provenance.json').write_text(json.dumps(state, indent=2) + '\n')
        # Compression happens after browser teardown, never between navigations.
        for path in out.glob('trace-*.json'):
            with path.open('rb') as src, gzip.open(str(path) + '.gz', 'wb') as dest:
                import shutil
                shutil.copyfileobj(src, dest)
            path.unlink()
    assert state['snapshots'] == 13 and state['mount'] == 20
    assert [c['mount'] for c in state['checkpoints']] == [1, 5, 10, 15, 20]
    assert len(state['segments']) == (3 if traced else 0)
    assert not any(s['completion'].get('dataLossOccurred') for s in state['segments']), 'Trace loss (all traces retained)'
    if traced:
        assert state['endpoint_request']['success']
