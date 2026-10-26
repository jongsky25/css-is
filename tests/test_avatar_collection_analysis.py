import pytest
from scripts.avatar_baseline.analyze_collection import summarize


def fixture():
    events=[{'name':'CommitLoad','pid':2,'ts':1,'args':{'data':{'url':'http://127.0.0.1:80/me'}}},
        {'name':'clock_sync','pid':1,'ts':10,'args':{'sync_id':'one'}},
        {'name':'MajorGC','pid':2,'ts':8,'args':{}},
        {'name':'MajorGC','pid':3,'ts':9,'args':{}},
        {'name':'CppGC.SweepPages','pid':2,'ts':9,'cat':'disabled-by-default-cppgc'},
        {'name':'clock_sync','pid':1,'ts':20,'args':{'sync_id':'two'}}]
    snap={'renderer_rss_sum_bytes':100,'renderer_memory_detail':[{'pid':2,'status':{'VmRSS':70}}],
          'js_heap_bytes':20,'dom_counters':{'documents':2,'nodes':100}}
    return events,[{'checkpoint':k,'snapshot':snap} for k in ['one','two']]


def test_gc_is_scoped_to_app_and_checkpoint_interval():
    events,records=fixture();result=summarize(events,records)
    assert len(result['points'][0]['major_gc_since_previous'])==1
    assert result['points'][1]['major_gc_since_previous']==[]
    assert result['points'][0]['cpp_gc_events_since_previous']=={'CppGC.SweepPages':1}
    assert result['points'][0]['rss_bytes']==100
    assert result['points'][0]['other_renderer_rss_bytes']==30


def test_duplicate_clock_is_rejected():
    events,records=fixture();events.append(events[1].copy())
    with pytest.raises(ValueError,match='duplicate'):summarize(events,records)


def test_multiple_app_renderers_require_review():
    events,records=fixture();events.append({**events[0],'pid':4})
    with pytest.raises(ValueError,match='role mapping'):summarize(events,records)


def test_forced_collection_invalidates_diagnosis():
    events,records=fixture();events[2]['args']['forced']=True
    with pytest.raises(ValueError,match='Forced collection'):summarize(events,records)
