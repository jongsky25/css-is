import pytest
from scripts.avatar_baseline.analyze_stylesheet_screen import decision
from scripts.avatar_baseline.memory_audit import SCENARIOS,MOUNTS


def cohort(value):
    return {p:{'renderer_counts':[3,3],**{m:{'samples':[value,value],'median':value} for m in ['renderer_rss_sum_bytes','js_heap_bytes']}} for p in [*SCENARIOS,*('navigation_'+str(n) for n in MOUNTS)]}


def test_qualifies_only_with_both_orders_and_controls():
    assert decision([cohort(100*2**20),cohort(94*2**20),cohort(94*2**20),cohort(100*2**20)])['status']=='qualified_for_five_sample_validation'


def test_reverse_failure_is_not_hidden():
    assert decision([cohort(100*2**20),cohort(94*2**20),cohort(99*2**20),cohort(100*2**20)])['status']=='screen_failed'


def test_negative_control_decrease_also_fails_stability():
    result=decision([cohort(100*2**20),cohort(80*2**20),cohort(60*2**20),cohort(100*2**20)])
    assert result['status']=='screen_failed' and not result['controls_stable']


def test_unmatched_counts_invalid():
    cohorts=[cohort(100*2**20) for _ in range(4)];cohorts[1]['home_idle']['renderer_counts']=[2,2]
    assert decision(cohorts)['status']=='inconclusive'


def test_exact_improvement_boundary():
    assert decision([cohort(100*2**20),cohort(95*2**20),cohort(95*2**20),cohort(100*2**20)])['effect_qualified_both_orders']


def test_non_target_worsening_blocks_effect():
    cohorts=[cohort(100*2**20),cohort(94*2**20),cohort(94*2**20),cohort(100*2**20)]
    cohorts[1]['background']['js_heap_bytes']={'samples':[111*2**20]*2,'median':111*2**20}
    assert not decision(cohorts)['effect_qualified_both_orders']


def test_missing_cohort_rejected():
    with pytest.raises(ValueError):decision([cohort(100*2**20)])


def test_visual_failure_blocks_collection():
    from scripts.avatar_baseline.stylesheet_screen import validate_visual
    with pytest.raises(ValueError, match='collection blocked'):
        validate_visual({'all_pixels_identical':False})


def test_unchanged_source_visual_control_cannot_qualify_candidate():
    from scripts.avatar_baseline.stylesheet_screen import validate_visual
    with pytest.raises(ValueError, match='collection blocked'):
        validate_visual({'all_pixels_identical':True,'same_source_control':True})
