import copy
import pytest
from scripts.avatar_baseline.analyze_blink_types import extract, compare, bounded_allocators


def attr(value, units='bytes'):
    return {'type': 'scalar','units':units,'value':hex(value)[2:]}


def fixture():
    def types(n, count):
        return {'attrs': {'allocated_objects_size':attr(n),'object_count':attr(count,'objects')}}
    return {
        'blink_gc/main/heap': {'attrs': {'allocated_objects_size':attr(96),
            'committed_size':attr(4096),'size':attr(4096),'pooled_size':attr(2048)}},
        'blink_objects/blink_gc/main/Text (0x1)': types(64,2),
        'blink_objects/blink_gc/main/Text (0x2)': types(32,1),
        'blink_objects/blink_gc/main/HTMLDocument (0x3)': types(0,0),
        'blink_gc/main/heap/Normal/pages/page_0/types/Text (0x1)': types(32,1),
        'blink_gc/main/heap/Normal/pages/page_1/types/Text (0x1)': types(32,1),
        'blink_gc/main/heap/Normal/pages/page_1/types/Text (0x2)': types(32,1),
    }


def test_global_page_views_not_double_counted_and_names_merged():
    result = extract(fixture())
    assert result['allocated_objects_bytes'] == 96
    assert result['raw_type_count'] == 3
    assert result['named_type_count'] == 2
    assert result['types']['Text']['object_count'] == 3
    assert result['types']['Text']['allocated_bytes'] == 96
    assert result['pooled_bytes'] == 2048


@pytest.mark.parametrize('change,match', [
    (lambda a: a['blink_objects/blink_gc/main/Text (0x1)']['attrs'].update(object_count=attr(4,'objects')), 'Page/global'),
    (lambda a: a['blink_gc/main/heap']['attrs'].update(allocated_objects_size=attr(95)), 'reconcile'),
    (lambda a: a['blink_objects/blink_gc/main/Text (0x1)']['attrs'].update(object_count=attr(2)), 'scalar'),
    (lambda a: a.pop('blink_objects/blink_gc/main/Text (0x1)'), 'absent'),
])
def test_accounting_failure_is_rejected(change,match):
    a = fixture(); change(a)
    with pytest.raises(ValueError,match=match): extract(a)


def test_invalid_type_and_hex_rejected():
    a = fixture(); a['blink_objects/blink_gc/main/Text'] = a.pop('blink_objects/blink_gc/main/Text (0x1)')
    with pytest.raises(ValueError,match='identity'): extract(a)
    a = fixture(); a['blink_gc/main/heap']['attrs']['size']['value']='-1'
    with pytest.raises(ValueError,match='hexadecimal'): extract(a)


def test_cross_process_type_ids_do_not_create_false_difference():
    a = fixture(); b = {k.replace('(0x1)','(0x99)'):v for k,v in copy.deepcopy(a).items()}
    left,right = extract(a),extract(b); left['index']=0; right['index']=1
    result = compare(left,right)
    assert result['allocated_objects_delta_bytes'] == 0
    assert all(x['allocated_bytes_delta']==0 and x['object_count_delta']==0 for x in result['type_differences'])


def test_dump_identity_and_duplicate_fragment_guard():
    def event(pid=7, ident='a', ts=10, alloc=None):
        return {'pid':pid,'id':ident,'ts':ts,'ph':'v','args':{'dumps':{'allocators':alloc or fixture()}}}
    events = [event(),event(pid=9),event(ident='b'),event(ts=20)]
    assert bounded_allocators(events,7,'a',10) == fixture()
    with pytest.raises(ValueError,match='Overlapping'): bounded_allocators([event(),event()],7,'a',10)
    with pytest.raises(ValueError,match='Missing'): bounded_allocators(events,1,'a',10)
