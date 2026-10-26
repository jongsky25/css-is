import pytest
from scripts.avatar_baseline.analyze_navigation_timing import phase_interval, timing, compare


def gc(start=0,duration=100,pid=1):
    return {'name':'MajorGC','pid':pid,'ph':'X','ts':start,'dur':duration}


@pytest.mark.parametrize('before,after,phase',[(1000,2000,0),(1000099,1000101,None),(1000100,1000200,1),(3000099,3000101,None),(3000100,3000200,2)])
def test_phase_boundaries(before,after,phase):
    assert phase_interval([gc()],1,before,after)['phase']==phase


def test_unknown_and_wrong_renderer_not_matched():
    assert phase_interval([gc(pid=2)],1,1000,2000)['phase'] is None


@pytest.mark.parametrize('start,duration',[(500,1000),(1200,1),(1999,100)])
def test_gc_overlapping_window_excluded(start,duration):
    result=phase_interval([gc(),gc(start,duration)],1,1000,2000)
    assert result['gc_overlap'] and result['phase'] is None


def test_gc_ending_before_probe_age_uses_end():
    result=phase_interval([gc(100,900)],1,1100,1200)
    assert result['age_ms']==[.1,.2]


def test_unknown_phases_are_not_equal_match():
    a={'navigation':[{'mount':1,'phase':None,'documents':2,'nodes':100,'js_heap_bytes':1000}]}
    assert compare(a,a)[0]['phase_matched'] is False


def synthetic():
    events=[gc(),{'cat':'cppgc','name':'test','pid':1},
            {'name':'CommitLoad','pid':1,'args':{'data':{'url':'http://127.0.0.1:1/'}}}]
    rows=[]
    for m in range(1,21):
        for side,offset in [('before',0),('after',100)]:
            events.append({'name':'clock_sync','ts':m*1000+offset,'args':{'sync_id':f'nav-{m}-{side}'}})
        rows.append({'mount':m,'start_ns':m*1000000,'dom_start_ns':m*1000000+10,
            'dom_end_ns':m*1000000+20,'heap_end_ns':m*1000000+30,'finish_ns':m*1000000+40,
            'dom':{'documents':2,'nodes':100},'heap':{'usedSize':1000}})
    return events,rows


def test_complete_sequence():
    events,rows=synthetic();result=timing(events,rows)
    assert len(result['navigation'])==20 and result['app_pid']==1
    assert result['navigation'][-1]['phase']==0


@pytest.mark.parametrize('fault',['duplicate','missing','forced','pid','ordinal','negative','clock','host'])
def test_reject_invalid_evidence(fault):
    events,rows=synthetic()
    if fault=='duplicate':events.append(events[-1])
    if fault=='missing':events.pop()
    if fault=='forced':events.append({'args':{'forced':True}})
    if fault=='pid':events.append({'name':'CommitLoad','pid':2,'args':{'data':{'url':'http://127.0.0.1:1/'}}})
    if fault=='ordinal':rows[-1]['mount']=19
    if fault=='negative':rows[0]['heap']['usedSize']=-1
    if fault=='clock':events[-1]['ts']=0
    if fault=='host':rows[0]['finish_ns']=0
    with pytest.raises(ValueError):timing(events,rows)
