import copy
import pytest
from scripts.avatar_baseline.native_root_retention import graph


def fixture():
    # root -> GC roots -> global handles -> NativeContext -> Window;
    # a second Window has only weak/shortcut incoming references.
    strings = ['', '(GC roots)', '(Global handles)', 'system / NativeContext',
               'Window / fixture', 'Window / shortcut-only', 'retainer']
    node_fields = ['name','type','id','edge_count']
    edge_fields = ['to_node','name_or_index','type']
    nodes = [0,0,1,3, 1,0,3,1, 2,0,5,1, 3,1,7,1, 4,2,9,1, 5,2,11,0]
    edges = [4,0,0, 20,6,1, 20,6,2, 8,0,0, 12,6,3, 16,6,3, 12,6,3]
    return {'snapshot':{'node_count':6,'edge_count':7,'meta':{
        'node_fields':node_fields,'edge_fields':edge_fields,
        'node_types':['string',['synthetic','hidden','object'],'number','number'],
        'edge_types':['node','string_or_number',['element','weak','shortcut','internal']]}},
        'nodes':nodes,'edges':edges,'strings':strings}


def test_strong_root_path_uses_metadata_and_handles_cycles():
    result = graph(fixture())
    window = next(t for t in result['targets'] if t['node']['name']=='Window / fixture')
    assert window['reachable_without_weak_or_shortcut']
    assert [p['from']['name'] for p in window['path']]==['','(GC roots)','(Global handles)','system / NativeContext']
    assert window['path'][-1]['edge_name']=='retainer'
    assert window['root_category']=='(Global handles)'
    assert result['nodes']==6 and result['edges']==7


def test_weak_and_display_shortcut_are_not_retaining_paths():
    target = next(t for t in graph(fixture())['targets'] if t['node']['name']=='Window / shortcut-only')
    assert target['reachable_without_weak_or_shortcut'] is False
    assert target['path']==[] and target['root_category']=='(unreachable)'


@pytest.mark.parametrize('change', ['unaligned','out_of_range','totals','name','kind','truncated'])
def test_reject_malformed_graph(change):
    value = copy.deepcopy(fixture())
    if change=='unaligned':value['edges'][0]=5
    if change=='out_of_range':value['edges'][0]=24
    if change=='totals':value['snapshot']['edge_count']=8
    if change=='name':value['edges'][4]=999
    if change=='kind':value['edges'][2]=99
    if change=='truncated':value['nodes'].pop()
    with pytest.raises(ValueError):graph(value)
