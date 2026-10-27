import pytest
from scripts.avatar_baseline.analyze_stylesheet_residency import point, analyze, SMAPS


def record(mount=1):
    def renderer(pid,rss):
        return {'pid':pid,'status':{'VmRSS':rss,'RssAnon':rss-20,'RssFile':15,'RssShmem':5,'VmSwap':0},'smaps_rollup':{k:0 for k in SMAPS}}
    return {'mount':mount,'renderer_memory_detail':[renderer(10,100),renderer(20,50)],'renderer_process_count':2,
            'renderer_rss_sum_bytes':151,'js_heap_bytes':10,'dom_counters':{'documents':2},'lcp_ms':100,'long_tasks':[]}


def test_sequential_read_residual_is_preserved():
    assert point(record(),10)['status_vs_measured_residual']==-1


def test_changed_renderer_rank_does_not_change_tracked_identity():
    rows=[]
    for _ in range(4):
        cohort=[]
        for run in range(2):
            nav=[record(m) for m in [1,5,10,15,20]]
            nav[-1]['renderer_memory_detail'][1]['status'].update(VmRSS=200,RssAnon=180)
            cohort.append({'run':run,'navigation_trend':nav})
        rows.append(cohort)
    result=analyze(rows)
    assert all(s['tracked_pid']==10 and s['points'][-1]['tracked_status']['VmRSS']==100 for s in result['samples'])


def test_missing_tracked_pid_is_not_silently_reassigned():
    r=record();r['renderer_memory_detail'][0]['pid']=30
    with pytest.raises(ValueError,match='disappeared'):point(r,10)


def test_duplicate_pid_rejected():
    r=record();r['renderer_memory_detail'][1]['pid']=10
    with pytest.raises(ValueError,match='Duplicate'):point(r,10)


def test_inconsistent_status_components_rejected():
    r=record();r['renderer_memory_detail'][0]['status']['RssAnon']+=1
    with pytest.raises(ValueError,match='components'):point(r,10)


def test_renderer_count_mismatch_rejected():
    r=record();r['renderer_process_count']=3
    with pytest.raises(ValueError,match='count'):point(r,10)
