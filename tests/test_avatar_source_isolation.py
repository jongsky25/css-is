import copy
import pytest
from scripts.avatar_baseline.analyze_source_isolation import points,qualifies
from scripts.avatar_baseline.lifecycle_candidate import compare
from scripts.avatar_baseline.memory_audit import BUDGET
from tests.test_avatar_targeted_memory import cohort


def test_screen_requires_both_navigation_improvements_and_every_other_gate(tmp_path):
    _,_,rows=cohort(tmp_path);old=points(rows[:2]);new=copy.deepcopy(old)
    for checkpoint in ['navigation_10','navigation_20']:
        p=new[checkpoint]['renderer_rss_sum_bytes'];p['median']-=5*1024*1024;p['samples']=[v-5*1024*1024 for v in p['samples']]
    assert qualifies(compare(old,new))
    new['background']['js_heap_bytes']['median']+=BUDGET+1
    assert not qualifies(compare(old,new))


def test_improvement_at_only_one_checkpoint_does_not_qualify(tmp_path):
    _,_,rows=cohort(tmp_path);old=points(rows[:2]);new=copy.deepcopy(old)
    new['navigation_10']['renderer_rss_sum_bytes']['median']-=20*1024*1024
    assert not qualifies(compare(old,new))


@pytest.mark.parametrize('fault',['missing_sample','duplicate','missing_navigation','errors','invalid_count'])
def test_invalid_screen_is_rejected(tmp_path,fault):
    _,_,rows=cohort(tmp_path);rows=rows[:2]
    if fault=='missing_sample':rows.pop()
    elif fault=='duplicate':rows[1]['run']=0
    elif fault=='missing_navigation':rows[0]['navigation_trend'].pop()
    elif fault=='errors':rows[0]['errors']=['application failure']
    else:rows[0]['scenarios']['background']['renderer_process_count']=0
    with pytest.raises(ValueError):points(rows)


def test_five_sample_validation_requires_all_five(tmp_path):
    _,_,rows=cohort(tmp_path)
    assert points(rows,5)
    with pytest.raises(ValueError):points(rows[:2],5)
    with pytest.raises(ValueError):points(rows)


@pytest.mark.parametrize('fault',['none','missing','exit','order','index','samples','base'])
def test_observer_plan_identity(fault):
    from scripts.avatar_baseline.analyze_source_isolation import validate_plan
    order=['current','geometry','geometry','current']
    plan={'observer_validation':True,'base':'f700187','acceptance':False,
          'order':order,'samples_per_arm':5,
          'cohorts':[{'index':i,'arm':a,'exit_code':0} for i,a in enumerate(order)]}
    if fault=='missing':plan['cohorts'].pop()
    elif fault=='exit':plan['cohorts'][1]['exit_code']=1
    elif fault=='order':plan['cohorts'][1]['arm']='current'
    elif fault=='index':plan['cohorts'][1]['index']=0
    elif fault=='samples':plan['samples_per_arm']=2
    elif fault=='base':plan['base']='1c964dc'
    if fault=='none':assert validate_plan(plan)==(True,tuple(order),5)
    else:
        with pytest.raises(ValueError):validate_plan(plan)
