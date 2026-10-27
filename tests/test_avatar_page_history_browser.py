"""Full baseline with bounded native history on its twenty navigation mounts."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import time
import pytest
from playwright.sync_api import Page
from tests import test_avatar_baseline_browser as baseline
from tests.test_avatar_baseline_browser import baseline_server
from tests.avatar_page_history_probe import PageHistory

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_PAGE_HISTORY')!='1',reason='Opt-in native history')


def test_page_history(baseline_server, app_mod, monkeypatch):
    out=Path(os.environ['CSS_AVATAR_OUT'])
    state={'acceptance':False,'forced_gc':False,'protocol':'native-page-history-v1',
           'mode':os.environ['CSS_AVATAR_HISTORY_MODE'],'snapshots':0,'mount':0,
           'checkpoints':[],'navigations':[],
           'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    snapshot=baseline.snapshot;goto=Page.goto;probe=None
    def navigate(page,*args,**kwargs):
        if 8<=state['snapshots']<13:
            state['mount']+=1
            if probe: probe.phase('navigation-'+str(state['mount']))
            start=time.monotonic_ns();result=goto(page,*args,**kwargs)
            state['navigations'].append({'mount':state['mount'],'begin_ns':start,'goto_end_ns':time.monotonic_ns()})
            return result
        return goto(page,*args,**kwargs)
    def capture(page,cdp):
        nonlocal probe
        start=time.monotonic_ns();result=snapshot(page,cdp);end=time.monotonic_ns()
        state['snapshots']+=1
        if state['snapshots']==8:
            probe=PageHistory(page,state['mode']=='probe')
            state['navigation_begin_ns']=time.monotonic_ns()
        elif state['snapshots']>8:
            state['checkpoints'].append({'mount':state['mount'],'interval_ns':[start,end],'snapshot':result})
            if state['mount']==20:
                state['navigation_end_ns']=time.monotonic_ns()
                state['native']=probe.finish();probe=None
        return result
    monkeypatch.setattr(Page,'goto',navigate)
    monkeypatch.setattr(baseline,'snapshot',capture)
    try:
        baseline.test_real_application_baseline(baseline_server,app_mod,False,'warm')
    finally:
        if probe:
            state['partial_native']=probe.finish()
        with gzip.open(out/'page-history.json.gz','wt') as f:json.dump(state,f)
    assert state['snapshots']==13 and state['mount']==20
    assert [c['mount'] for c in state['checkpoints']]==[1,5,10,15,20]
    assert not any(m['type']=='error' for m in state['native']['agent_messages'])
    assert state['native'].get('history',{}).get('dropped',0)==0
