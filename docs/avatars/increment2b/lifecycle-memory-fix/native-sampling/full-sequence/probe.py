"""Temporary native allocator sampling through the unchanged lifecycle workload."""
import gzip,json,os
from pathlib import Path
from tests import test_avatar_baseline_browser as baseline
from tests.test_avatar_baseline_browser import baseline_server

def test_native_lifecycle_sampling(baseline_server,app_mod,monkeypatch):
    original=baseline.snapshot;state={'index':0}
    def capture(page,cdp):
        if state['index']==0:cdp.send('Memory.startSampling',{'samplingInterval':32768})
        result=original(page,cdp);state['index']+=1
        if state['index']==13:
            profile=cdp.send('Memory.getSamplingProfile')
            out=Path(os.environ['CSS_AVATAR_OUT']);out.mkdir(parents=True,exist_ok=True)
            with gzip.open(out/'native-profile.json.gz','wt') as f:json.dump(profile,f)
            cdp.send('Memory.stopSampling')
        return result
    monkeypatch.setattr(baseline,'snapshot',capture)
    baseline.test_real_application_baseline(baseline_server,app_mod,False,'warm')
    assert state['index']==13
