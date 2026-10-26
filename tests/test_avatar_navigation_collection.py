import pytest
from scripts.avatar_baseline.analyze_navigation_collection import completed_major


def event(ts=10, dur=20, pid=1):
    return {'name':'MajorGC','ph':'X','pid':pid,'ts':ts,'dur':dur}


def test_completion_not_start_controls_interval():
    assert completed_major([event()],1,0,20) == []
    assert completed_major([event()],1,20,30)[0]['end_timestamp_us'] == 30
    assert completed_major([event()],1,30,40) == []


def test_filters_process_and_orders_completion():
    result = completed_major([event(10,50),event(20,10),event(pid=2)],1,0,100)
    assert [e['end_timestamp_us'] for e in result] == [30,60]


@pytest.mark.parametrize('change',[{'ph':'B'},{'dur':-1}])
def test_unknown_duration_rejected(change):
    with pytest.raises(ValueError):
        completed_major([{**event(),**change}],1,0,100)


def test_snapshot_and_dump_gc_are_separate(monkeypatch):
    from scripts.avatar_baseline import analyze_navigation_collection as module
    prior = {'checkpoint':'background','trace_timestamp_us':10,'documents':8,'rss_bytes':100}
    point = {'checkpoint':'navigation_1','trace_timestamp_us':30,'documents':2,
             'nodes':20,'rss_bytes':120,'app_renderer_rss_bytes':110,'js_heap_bytes':30,
             'dump_timestamp_us':40,'after_dump_rss_bytes':125,
             'app_allocator_bytes':{'blink_gc/main/heap':{'size':80,'allocated_objects_size':10}}}
    monkeypatch.setattr(module,'summarize',lambda es,rs:{'app_pid':1,'records':[prior,point]})
    rows = [{}, {'after_dump_snapshot':{'dom_counters':{'documents':1}}}]
    result = module.analyze([event(15,10),event(29,6)], rows)['navigation'][0]
    assert result['document_delta'] == -6
    assert result['rss_delta_bytes'] == 20
    assert len(result['completed_major_gc']) == 1
    assert result['ms_since_last_completed_major_gc'] == .005
    assert len(result['major_gc_completing_between_marker_and_dump']) == 1
    assert result['post_dump_documents'] == 1
    assert result['blink_heap_attributes_bytes']['allocated_objects_size'] == 10
