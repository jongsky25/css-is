from copy import deepcopy
from scripts.avatar_baseline.visual_state import compare


def state():
    return [{'index':0,'tag':'path','attributes':[['d','M0 0L1 1']],
             'style':{'stroke-width':'1px','transform':'none'},
             'rect':[0,0,1,1],'bbox':[0,0,1,1],'matrix':[1,0,0,1,0,0]}]


def test_subpixel_geometry_difference_is_not_rounded_away():
    before=state();after=deepcopy(before);after[0]['matrix'][4]=0.000001
    result=compare(before,after)
    assert not result['identical'] and result['differences'][0]['field']=='matrix'


def test_paint_property_difference_is_named():
    before=state();after=deepcopy(before);after[0]['style']['stroke-width']='2px'
    assert compare(before,after)['differences'][0]['field']=='style.stroke-width'


def test_missing_svg_node_is_not_ignored():
    assert compare(state(),[])['differences']==[{'index':0,'field':'missing_node'}]


def test_attribute_difference_is_not_hidden_by_equal_geometry():
    before=state();after=deepcopy(before);after[0]['attributes'][0][1]='M0 0L2 2'
    assert not compare(before,after)['identical']
