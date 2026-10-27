import pytest
from scripts.avatar_baseline.analyze_navigation_residency import join_dump, observation


def fixture():
    events=[{'name':'CommitLoad','pid':42,'args':{'data':{'url':'http://127.0.0.1:123/?view=me'}}}];records=[];status=[]
    for m in range(1,21):
        b=m*1000;a=b+50
        events += [{'name':'clock_sync','ts':t,'args':{'sync_id':f'nav-{m}-{side}'}} for side,t in [('before',b),('after',a)]]
        events.append({'name':'cppgc.Sweep','cat':'cppgc','pid':42,'ts':b-10,'ph':'X','dur':20,'args':{'forced':False}})
        events.append({'name':'periodic_interval','ph':'v','pid':42,'ts':b+20,'id':hex(m+500),'args':{'dumps':{'allocators':{'blink_gc/main':{'attrs':{'size':{'units':'bytes','value':'1000'}}}}}}})
        snapshot={'renderer_rss_sum_bytes':100,'renderer_memory_detail':[{'pid':42,'status':{'VmRSS':100}}],'js_heap_bytes':10,'dom_counters':{'documents':2},'lcp_ms':20,'long_tasks':[]}
        records.append({'mount':m,'snapshot':snapshot,'after_dump_snapshot':snapshot,'snapshot_interval_ns':[(b-10)*1000,(b-5)*1000],
            'before_marker':{'begin_ns':(b-1)*1000,'end_ns':(b+1)*1000},'after_marker':{'begin_ns':(a-1)*1000,'end_ns':(a+1)*1000},
            'after_snapshot_interval_ns':[(a+2)*1000,(a+3)*1000],'dump_request':{'success':True,'dumpGuid':hex(m)}})
        value=(100 if m%2 else 90)*2**20
        status.append({'begin_ns':(a+4)*1000,'end_ns':(a+5)*1000,'renderers':[{'pid':42,'status':{'VmRSS':value,'RssAnon':value,'RssFile':0,'RssShmem':0,'VmSwap':0}}]})
    return events,records,status


def test_exported_id_is_not_assumed_to_equal_request_guid():
    result=observation(*fixture())
    assert len(result['navigation'])==20 and result['navigation'][0]['allocators']['blink_gc/main']['size']==4096
    assert len(result['rss_drops_at_least_5_mib'])==10
    assert result['rss_drops_at_least_5_mib'][0]['overlapping_dump_mounts']==[2]


def test_disjoint_fragments_join_without_summing_families():
    e,r,s=fixture();dump=next(x for x in e if x.get('ph')=='v')
    e.append({**dump,'args':{'dumps':{'allocators':{'v8':{'attrs':{'size':{'units':'bytes','value':'20'}}}}}}})
    assert join_dump(e,42,1000,1050)['allocators']=={'blink_gc/main':{'size':4096},'v8':{'size':32}}


def test_duplicate_allocator_rejected():
    e,r,s=fixture();e.append(next(x for x in e if x.get('ph')=='v'))
    with pytest.raises(ValueError,match='Overlapping'):observation(e,r,s)


def test_dump_outside_interval_rejected():
    e,r,s=fixture();next(x for x in e if x.get('ph')=='v')['ts']=1060
    with pytest.raises(ValueError,match='Missing or ambiguous'):observation(e,r,s)


def test_forced_collection_rejected():
    e,r,s=fixture();e.append({'args':{'forced':True}})
    with pytest.raises(ValueError,match='Forced'):observation(e,r,s)


def test_duplicate_clock_rejected():
    e,r,s=fixture();e.append(next(x for x in e if x.get('name')=='clock_sync'))
    with pytest.raises(ValueError,match='clock'):observation(e,r,s)


def test_missing_sampled_app_rejected():
    e,r,s=fixture()
    for x in s:x['renderers'][0]['pid']=99
    with pytest.raises(ValueError,match='Insufficient'):observation(e,r,s)


def test_nonchronological_host_probe_rejected():
    e,r,s=fixture();r[0]['before_marker']['begin_ns']=999999999
    with pytest.raises(ValueError,match='host'):observation(e,r,s)


def test_no_gc_events_is_retained_as_no_observed_collection():
    e,r,s=fixture();e=[x for x in e if x.get('cat')!='cppgc']
    assert observation(e,r,s)['cpp_gc_event_count']==0


def test_trace_loss_is_invalid_even_if_workload_exit_was_zero():
    from scripts.avatar_baseline.analyze_navigation_residency import capture_issue
    assert 'Trace data loss' in capture_issue({'exit_code':0},{'trace_completion':{'dataLossOccurred':True}})


def test_invalid_slot_stays_in_all_affected_pairs():
    from scripts.avatar_baseline.analyze_navigation_residency import pair_comparisons
    cohorts=[{'index':i,'status':'valid_capture','navigation':[]} for i in range(8)]
    cohorts[4]['status']='invalid_capture'
    rows=pair_comparisons(cohorts)
    assert len(rows)==8
    assert [r['name'] for r in rows if r['status']=='unavailable_invalid_capture']==['block1-source-reverse','block1-current-control']
