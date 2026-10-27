from copy import deepcopy
import pytest
from tests.test_absent_attribute_capability import specimen as svg_specimen
from scripts.avatar_baseline.mixed_getter_capability import validate
from scripts.avatar_baseline.mixed_membership_fixture import MODES, tag


def specimen():
    native=deepcopy(svg_specimen()['native']);native['history']['events']=[];docs=[]
    for index,mode in enumerate(MODES):
        base=svg_specimen();queries=base['queries'];events=base['native']['history']['events']
        for q in queries:
            q['phase']=q['phase'].replace(':0:',f':{index}:');q['begin_ns']+=index*10000;q['end_ns']+=index*10000
            q['result'].update(fixture_count=3000,selector_queries=1,tags=[tag(mode,q['phase'].split(':')[2])]*32)
        for e in events:
            e['phase']=e['phase'].replace(':0:',f':{index}:')
            for key in ['begin_ns','callback_ready_ns','returned_ns']:e[key]+=index*10000
        native['history']['events']+=events
        docs.append({'index':index,'mode':mode,'queries':queries,'dom_before_sha256':'same'+mode,'dom_after_sha256':'same'+mode})
    return {'native':native,'documents':docs,'selection_policy':'per-evaluate-selector-cache'}


def test_all_three_types_are_checked_against_reference():
    r=validate(specimen());assert r['receiver_records']==384 and r['reference_records']==384
    assert [d['mode'] for d in r['documents']]==MODES


@pytest.mark.parametrize('bad',['mode','tags','queries','extra_phase','order','selector_count'])
def test_mixed_type_capability_fails_closed(bad):
    p=specimen()
    if bad=='mode':p['documents'][0]['mode']='svg'
    if bad=='tags':p['documents'][0]['queries'][0]['result']['tags'][0]='path'
    if bad=='queries':p['documents'][0]['queries'][0]['phase']=p['documents'][0]['queries'][1]['phase']
    if bad=='extra_phase':p['native']['history']['events'][0]['phase']='reference:999:avatar:0'
    if bad=='order':p['documents'][1]['queries'][0]['begin_ns']=1
    if bad=='selector_count':p['documents'][0]['queries'][0]['result']['selector_queries']=4
    with pytest.raises(ValueError):validate(p)
