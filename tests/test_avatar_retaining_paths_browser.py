"""Prepared forensic-only snapshot. Requires explicit forced-GC authorization."""
import gzip
import hashlib
import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import BrowserContext
from tests.test_avatar_baseline_browser import baseline_server
from tests.test_avatar_navigation_timing_browser import test_navigation_timing as run_natural_timing

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_FORENSIC_GC')!='authorized',
    reason='Pending explicit permission for forensic snapshot forced GC')


def capture_snapshot(cdp, out):
    natural_hashes={name:hashlib.sha256((out/name).read_bytes()).hexdigest()
        for name in ['False-warm.json','navigation-timing.json','navigation-trace.json.gz','timing-provenance.json']}
    before={'dom':cdp.send('Memory.getDOMCounters'),'heap':cdp.send('Runtime.getHeapUsage')}
    path=out/'post-workload.heapsnapshot.json.gz'
    with gzip.open(path,'wt') as stream:
        def chunk(event):stream.write(event['chunk'])
        cdp.on('HeapProfiler.addHeapSnapshotChunk',chunk)
        try:
            # Chromium forces GC internally. Never use this in natural/acceptance capture.
            cdp.send('HeapProfiler.takeHeapSnapshot',{'reportProgress':False,'exposeInternals':True})
        finally:
            cdp.remove_listener('HeapProfiler.addHeapSnapshotChunk',chunk)
    after={'dom':cdp.send('Memory.getDOMCounters'),'heap':cdp.send('Runtime.getHeapUsage')}
    (out/'forensic-provenance.json').write_text(json.dumps({
        'acceptance':False,'intentional_forced_gc':True,'natural_trace_closed_before_snapshot':True,
        'natural_evidence_sha256':natural_hashes,'before':before,'after':after,'snapshot_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limits':'Post-forced-GC retaining paths only. Transient garbage can disappear. Cannot establish ownership of earlier natural-GC observations or pass a memory gate.'},indent=2))


def test_retaining_paths(baseline_server, app_mod, monkeypatch):
    out=Path(os.environ['CSS_AVATAR_OUT']);state={}
    attach_original=BrowserContext.new_cdp_session
    close_original=BrowserContext.close

    def attach(context,page):
        cdp=attach_original(context,page);state.update(cdp=cdp,context=context)
        return cdp

    def close(context,*args,**kwargs):
        if context is state.get('context') and not state.get('captured'):
            # The nested natural timing probe closes its trace before context teardown.
            provenance=json.loads((out/'timing-provenance.json').read_text())
            assert provenance['navigation_observations']==20
            assert not provenance['trace_completion'].get('dataLossOccurred')
            assert (out/'navigation-trace.json.gz').exists()
            rows=json.loads((out/'False-warm.json').read_text())
            assert len(rows)==1 and rows[0]['navigation_trend'][-1]['mount']==20
            capture_snapshot(state['cdp'],out);state['captured']=True
        return close_original(context,*args,**kwargs)

    monkeypatch.setattr(BrowserContext,'new_cdp_session',attach)
    monkeypatch.setattr(BrowserContext,'close',close)
    run_natural_timing(baseline_server,app_mod,monkeypatch)
    assert state.get('captured')
