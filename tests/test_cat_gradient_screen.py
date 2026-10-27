"""Fail closed on visual prerequisites and memory/control regression gates."""
from copy import deepcopy
import pytest
from scripts.avatar_baseline.run_cat_gradients import validate_visual, REFS
from scripts.avatar_baseline.analyze_cat_gradients import decision
from scripts.avatar_baseline.memory_audit import SCENARIOS, MOUNTS


def visual():
    sheets=[{'case':f'{theme}-{outfit}-{mode}','cells':96,'pixel_identical':True,
             'state_comparison':{'identical':True},
             'checks':[{'ids_unique':True,'missing':[],'avatars':96,'cat_v2':6}]*2}
            for theme in ['light','dark','contrast']
            for outfit in ['default','halloween','halloween_vampire','halloween_pumpkin','christmas']
            for mode in ['live','preview']]
    return {'refs':{'original':'1c964dcba2fa19de1eab077b00e0e5748d742554',**REFS},
            'browser':'156.0.8078.47','cells':2880,'sheets':sheets,
            'all_pixels_identical':True,'all_states_identical':True}


def test_visual_complete_matrix():
    validate_visual(visual())


@pytest.mark.parametrize('problem',['source','missing','duplicate','pixels','geometry','id','reference'])
def test_visual_rejects_incomplete_or_changed_evidence(problem):
    v=deepcopy(visual())
    if problem=='source':v['refs']['candidate']='other'
    if problem=='missing':v['sheets'].pop()
    if problem=='duplicate':v['sheets'][-1]=v['sheets'][0]
    if problem=='pixels':v['sheets'][0]['pixel_identical']=False
    if problem=='geometry':v['sheets'][0]['state_comparison']['identical']=False
    if problem=='id':v['sheets'][0]['checks'][0]['ids_unique']=False
    if problem=='reference':v['sheets'][0]['checks'][0]['missing']=['missing']
    with pytest.raises(ValueError):validate_visual(v)


def cohort(mib):
    return {k:{'renderer_counts':[1,1],
               **{m:{'samples':[mib*1048576]*2,'median':mib*1048576}
                  for m in ['renderer_rss_sum_bytes','js_heap_bytes']}}
            for k in [*SCENARIOS,*('navigation_'+str(m) for m in MOUNTS)]}


def test_both_orders_improve_with_stable_controls():
    result=decision([cohort(100),cohort(94),cohort(94),cohort(100)])
    assert result['status']=='qualified_for_five_sample_validation'
    assert result['acceptance'] is False


def test_favorable_source_pair_cannot_hide_unstable_control():
    result=decision([cohort(100),cohort(94),cohort(114),cohort(120)])
    assert result['effect_qualified_both_orders'] is True
    assert result['controls_stable'] is False
    assert result['status']=='screen_failed'


def test_every_checkpoint_is_gated():
    rows=[cohort(100),cohort(94),cohort(94),cohort(100)]
    rows[2]['background']['renderer_rss_sum_bytes']={'samples':[111*1048576]*2,'median':111*1048576}
    assert decision(rows)['status']=='screen_failed'
