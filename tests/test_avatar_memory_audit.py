"""Regression coverage for omitted lifecycle memory and invalid measurements."""
import copy
import json

import pytest
from scripts.avatar_baseline.memory_audit import audit_memory, SCENARIOS, MOUNTS, BUDGET


def cohorts(tmp_path):
    before=tmp_path/'before';after=tmp_path/'after';before.mkdir();after.mkdir()
    for mobile in (False,True):
        for cache in ('cold','warm'):
            rows=[]
            for run in range(5):
                point={'renderer_rss_sum_bytes':100*1024*1024,'js_heap_bytes':5*1024*1024,'renderer_process_count':3}
                rows.append({'run':run,'seconds':30,'mobile':mobile,'cache':cache,'chromium':'156.0.8078.47',
                    'scenarios':{s:copy.deepcopy(point) for s in SCENARIOS},
                    'navigation_trend':[dict(point,mount=m) for m in MOUNTS]})
            for folder in (before,after):(folder/f'{mobile}-{cache}.json').write_text(json.dumps(rows))
    return before,after


def change(after, callback):
    path=after/'False-warm.json';rows=json.loads(path.read_text());callback(rows);path.write_text(json.dumps(rows))


def test_complete_equal_memory_passes(tmp_path):
    verdict=audit_memory(*cohorts(tmp_path))
    assert verdict['status']=='passed' and len(verdict['records'])==104


@pytest.mark.parametrize('scenario',['offscreen','reduced_motion','background'])
def test_inactive_scenario_cannot_escape_memory_budget(tmp_path,scenario):
    before,after=cohorts(tmp_path)
    def increase(rows):
        for r in rows:r['scenarios'][scenario]['renderer_rss_sum_bytes']+=BUDGET+1
    change(after,increase)
    result=audit_memory(before,after)
    assert result['status']=='application_regression'
    assert len(result['failures'])==1 and result['failures'][0]['scenario']==scenario


def test_navigation_endpoint_cannot_escape_memory_budget(tmp_path):
    before,after=cohorts(tmp_path)
    def increase(rows):
        for r in rows:r['navigation_trend'][-1]['renderer_rss_sum_bytes']+=BUDGET+1
    change(after,increase)
    result=audit_memory(before,after)
    assert result['status']=='application_regression'
    assert result['failures'][0]['scenario']=='navigation_20'


def test_mismatched_process_counts_are_inconclusive(tmp_path):
    before,after=cohorts(tmp_path)
    change(after,lambda rows:rows[0]['scenarios']['background'].update(renderer_process_count=4))
    assert audit_memory(before,after)['status']=='inconclusive'


@pytest.mark.parametrize('fault',['duplicate_run','missing_scenario','zero_memory','browser'])
def test_invalid_evidence_never_passes(tmp_path,fault):
    before,after=cohorts(tmp_path)
    def corrupt(rows):
        if fault=='duplicate_run':rows[-1]['run']=0
        elif fault=='missing_scenario':del rows[0]['scenarios']['offscreen']
        elif fault=='zero_memory':rows[0]['scenarios']['offscreen']['renderer_rss_sum_bytes']=0
        else:rows[0]['chromium']='other-version'
    change(after,corrupt)
    assert audit_memory(before,after)['status']=='inconclusive'
