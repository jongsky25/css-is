import pytest
from scripts.avatar_baseline.analyze_residency import summarize
from tests.test_avatar_collection_analysis import fixture


def data():
    events,records=fixture()
    for i,record in enumerate(records):
        record['dump_request']={'success':True,'dumpGuid':str(i+10)}
        record['after_dump_snapshot']={'renderer_rss_sum_bytes':101+i}
        events.insert(0,{'ph':'v','pid':2,'id':'0x'+str(i+10),'ts':11+i*10,'args':{'dumps':{'allocators':{
            'malloc':{'attrs':{'size':{'units':'bytes','value':hex(40+i)[2:]},'count':{'units':'objects','value':'99'}}}}}}})
    return events,records


def test_clock_join_not_event_order_or_exported_ids_and_no_rss_subtraction():
    events,records=data();records[0]['dump_request']['dumpGuid']='0xff';result=summarize(events,records)
    assert [r['app_allocator_bytes']['malloc'] for r in result['records']]==[{'size':40},{'size':41}]
    assert [r['rss_bytes'] for r in result['records']]==[100,100]
    assert [r['after_dump_rss_bytes'] for r in result['records']]==[101,102]
    assert result['acceptance'] is False


def test_missing_dump_is_rejected():
    events,records=data();events.pop(0)
    with pytest.raises(ValueError,match='Missing or ambiguous'):summarize(events,records)


def test_duplicate_pid_dump_is_rejected():
    events,records=data();events.append(events[0].copy())
    with pytest.raises(ValueError,match='Duplicate allocator'):summarize(events,records)


def test_failed_request_is_rejected():
    events,records=data();records[0]['dump_request']['success']=False
    with pytest.raises(ValueError,match='Unsuccessful'):summarize(events,records)


def test_disjoint_fragments_of_one_dump_are_merged():
    events,records=data();fragment={**events[0],'args':{'dumps':{'allocators':{
        'partition_alloc':{'attrs':{'size':{'units':'bytes','value':'f'}}}}}}}
    events.append(fragment);result=summarize(events,records)
    assert result['records'][1]['app_allocator_bytes']['partition_alloc']=={'size':15}
    assert result['records'][1]['app_allocator_bytes']['malloc']=={'size':41}


def test_multiple_dumps_in_one_interval_are_rejected():
    events,records=data();events.append({**events[0],'id':'0xff','ts':22})
    with pytest.raises(ValueError,match='ambiguous'):summarize(events,records)


def test_summary_retains_totals_not_per_object_children():
    from scripts.avatar_baseline.analyze_residency import allocator_family
    assert allocator_family('blink_gc/main/allocated_objects')
    assert allocator_family('partition_alloc/partitions/buffer')
    assert not allocator_family('blink_gc/main/allocated_objects/__deadbeef')
    assert not allocator_family('global/deadbeef')
