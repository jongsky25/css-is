"""Targeted diagnostics must not conceal an invalid or reverse-order cohort."""
import copy
import json
import pytest
from scripts.avatar_baseline.lifecycle_candidate import read_cohort, compare
from scripts.avatar_baseline.memory_audit import BUDGET
from tests.test_avatar_memory_audit import cohorts


def cohort(tmp_path):
    before,_=cohorts(tmp_path)
    folder=tmp_path/'cohort';(folder/'application').mkdir(parents=True)
    rows=json.loads((before/'False-warm.json').read_text())
    for row in rows:row['errors']=[]
    path=folder/'application/False-warm.json';path.write_text(json.dumps(rows))
    return folder,path,rows


def test_targeted_reverse_order_failure_remains_visible(tmp_path):
    folder,_,_=cohort(tmp_path);original=read_cohort(folder);candidate=copy.deepcopy(original)
    point=candidate['seasonal_preview']['renderer_rss_sum_bytes']
    point['samples']=[v+BUDGET+1 for v in point['samples']];point['median']+=BUDGET+1
    verdict=compare(original,candidate)
    assert verdict['status']=='application_regression' and len(verdict['records'])==26
    assert len(verdict['failures'])==1 and not verdict['acceptance']


def test_targeted_cross_source_renderer_mismatch_is_inconclusive(tmp_path):
    folder,_,_=cohort(tmp_path);original=read_cohort(folder);candidate=copy.deepcopy(original)
    candidate['background']['renderer_counts']=[4]*5
    assert compare(original,candidate)['status']=='inconclusive'


@pytest.mark.parametrize('fault',['duplicate','missing_navigation','browser','javascript_error','zero_memory'])
def test_targeted_cohort_rejects_invalid_evidence(tmp_path,fault):
    folder,path,rows=cohort(tmp_path)
    if fault=='duplicate':rows[-1]['run']=0
    elif fault=='missing_navigation':rows[0]['navigation_trend'].pop()
    elif fault=='browser':rows[0]['chromium']='154.0.8037.57'
    elif fault=='javascript_error':rows[0]['errors']=['broken handler']
    else:rows[0]['scenarios']['offscreen']['renderer_rss_sum_bytes']=0
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError):read_cohort(folder)
