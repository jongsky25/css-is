import pytest
from scripts.avatar_baseline.audit_original_gc import pair_statistics,relation


@pytest.mark.parametrize('bounds,point,expected',[
    ([1,2],3,'definitely_before'),([4,5],3,'definitely_after'),
    ([2,4],3,'overlap_or_uncertain'),([1,3],3,'overlap_or_uncertain'),
    ([3,5],3,'overlap_or_uncertain')])
def test_uncertain_boundary_is_not_forced_into_an_order(bounds,point,expected):
    assert relation(bounds,point)==expected


def test_invalid_bounds_are_rejected():
    with pytest.raises(ValueError):relation([4,2],3)


def test_statistics_pair_by_thread_and_containing_gc_not_heap_size():
    major=[dict(ts=100,dur=20,tid=1),dict(ts=200,dur=20,tid=1)]
    stats=[dict(ts=110,tid=1,values={'end_object_size':756936}),dict(ts=210,tid=1,values={'end_object_size':756936})]
    assert [row['major_index'] for row in pair_statistics(major,stats)]==[0,1]


@pytest.mark.parametrize('stats',[
    [dict(ts=150,tid=1)], [dict(ts=110,tid=2)], [],
    [dict(ts=110,tid=1),dict(ts=111,tid=1)]])
def test_missing_wrong_thread_or_duplicate_statistics_fail_closed(stats):
    with pytest.raises(ValueError):pair_statistics([dict(ts=100,dur=20,tid=1)],stats)
