"""Matched art controls with external kernel thread-CPU bounds, no JS wrappers.

Diagnostic only. Native wall durations remain unchanged in raw control records.
"""
import json
import gzip
import os
from pathlib import Path
import threading
import time
import pytest
from tests.test_avatar_baseline_browser import baseline_server
from tests import test_avatar_native_control as native

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_SCHEDULER_DIAGNOSTIC')!='1',reason='Opt-in scheduler attribution')


def test_matched_scheduler_attribution(baseline_server,app_mod,tmp_path,monkeypatch):
    runs=[];active={}
    original_reset=native.reset;original_snapshot=native.snapshot

    def mapping(page):
        before=time.monotonic_ns()/1e6;client=page.evaluate('performance.now()');after=time.monotonic_ns()/1e6
        return {'offset_low_ms':before-client,'offset_high_ms':after-client,'roundtrip_ms':after-before}

    def reset(page):
        original_reset(page)
        session=page.context.browser.new_browser_cdp_session()
        pids=[p['id'] for p in session.send('SystemInfo.getProcessInfo')['processInfo'] if p['type']=='renderer'];session.detach()
        assert pids
        active.clear();active.update({'pids':pids,'initial_mapping':mapping(page),'samples':[],'stop':threading.Event()})
        def sample():
            while not active['stop'].is_set():
                before=time.monotonic_ns()/1e6;values={}
                for pid in pids:
                    try:
                        cpu,wait,slices=map(int,Path(f'/proc/{pid}/schedstat').read_text().split())
                        values[str(pid)]={'cpu_ns':cpu,'runqueue_wait_ns':wait,'timeslices':slices}
                    except FileNotFoundError:pass
                active['samples'].append({'before_ms':before,'after_ms':time.monotonic_ns()/1e6,'threads':values})
                active['stop'].wait(float(os.getenv('CSS_AVATAR_SCHEDULER_SAMPLE_MS','5'))/1000)
        active['thread']=threading.Thread(target=sample,daemon=True);active['thread'].start()

    def snapshot(page,cdp):
        active['final_mapping']=mapping(page)
        # Include a sample after the full scripted interval and mapping bracket.
        time.sleep(.01)
        active['stop'].set();active['thread'].join(timeout=5)
        runs.append({k:v for k,v in active.items() if k not in ['thread','stop']})
        return original_snapshot(page,cdp)

    monkeypatch.setattr(native,'reset',reset);monkeypatch.setattr(native,'snapshot',snapshot)
    after_only=os.getenv('CSS_AVATAR_SCHEDULER_AFTER_ONLY')=='1'
    if after_only:monkeypatch.setenv('CSS_AVATAR_NATIVE_AFTER_ONLY','1')
    else:monkeypatch.delenv('CSS_AVATAR_NATIVE_AFTER_ONLY',raising=False)
    try:
        try:
            native.test_native_art_control(baseline_server,app_mod,tmp_path,'fern')
        except AssertionError as error:
            if not after_only or 'Final native budget failed' not in str(error):raise
    finally:
        if active.get('stop'):
            active['stop'].set();active['thread'].join(timeout=5)
    out=Path(os.environ['CSS_AVATAR_OUT']).parent
    raw=json.loads((out/'fern/native-control.json').read_text())
    assert len(runs)==len(raw['samples'])==(5 if after_only else 10)
    assessments=[]
    for row,run in zip(raw['samples'],runs):
        bounds=[];samples=run['samples'];mapping_start=run['initial_mapping'];mapping_end=run['final_mapping']
        offset_low=min(mapping_start['offset_low_ms'],mapping_end['offset_low_ms'])
        offset_high=max(mapping_start['offset_high_ms'],mapping_end['offset_high_ms'])
        for script in row['avatar_native_scripts']:
            if script['duration']<=50:continue
            start=script['executionStart']+offset_low;end=script['executionStart']+script['duration']+offset_high
            before=[s for s in samples if s['after_ms']<=start];after=[s for s in samples if s['before_ms']>=end]
            bound=None;wait=None
            if before and after and set(before[-1]['threads'])==set(after[0]['threads'])==set(map(str,run['pids'])):
                bound=sum(after[0]['threads'][pid]['cpu_ns']-before[-1]['threads'][pid]['cpu_ns'] for pid in before[-1]['threads'])/1e6
                wait=sum(after[0]['threads'][pid]['runqueue_wait_ns']-before[-1]['threads'][pid]['runqueue_wait_ns'] for pid in before[-1]['threads'])/1e6
            bounds.append({'script':script,'renderer_main_thread_cpu_upper_bound_ms':bound,'renderer_main_thread_runqueue_wait_ms':wait,'cpu_bound_le50':bound is not None and bound<=50})
        assessments.append({'version':row['version'],'run':row['run'],'frame_p95_ms':row['scenario']['frame_p95_ms'],'over50_wall_scripts':bounds,'all_bounded_cpu_le50':all(b['cpu_bound_le50'] for b in bounds)})
    with gzip.open(out/'scheduler-samples.json.gz','wt') as stream:json.dump(runs,stream,separators=(',',':'))
    (out/'assessment.json').write_text(json.dumps({'diagnostic_only':True,'after_only':after_only,'sample_period_ms':float(os.getenv('CSS_AVATAR_SCHEDULER_SAMPLE_MS','5')),'method':('Five final-art runs' if after_only else 'Five counterbalanced old/new-art pairs')+', same frozen runtime. External Linux schedstat sampling of all renderer main threads. Clock brackets map native script wall intervals to a conservative CPU upper bound over a larger sampled interval. No JS API wrappers, tracing or per-callback instrumentation.','samples':assessments},indent=2))
    print(json.dumps(assessments,indent=2),flush=True)
