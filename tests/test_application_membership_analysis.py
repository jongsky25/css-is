from copy import deepcopy
import json
import pytest
from scripts.avatar_baseline.application_membership import validate_selection,proof,inspect_slot
from scripts.avatar_baseline.hosted_application_calibration import summary


def row(group):
    tag='path' if group=='avatar' else 'div';attrs=json.dumps([[tag,[['class','fixture']]]]*32)
    return {'count':32,'pool_count':64,'root_count':1,'values':[1]*32,'tags':[tag]*32,
            'geometry_counts':[],'ownership':[group=='avatar']*32,'namespaces':[('http://www.w3.org/2000/svg' if group=='avatar' else 'http://www.w3.org/1999/xhtml')]*32,
            'before_attributes':attrs,'after_attributes':attrs}


def test_application_selection_has_source_boundaries_and_unchanged_strings():
    validate_selection(row('avatar'),'avatar');validate_selection(row('other'),'other')


@pytest.mark.parametrize('bad',['count','pool','root','values','ownership','namespace','attributes','tags'])
def test_mutated_or_wrong_source_selection_is_rejected(bad):
    r=row('avatar')
    if bad=='count':r['count']=31
    if bad=='pool':r['pool_count']=31
    if bad=='root':r['root_count']=2
    if bad=='values':r['values'][0]=0
    if bad=='ownership':r['ownership'][0]=False
    if bad=='namespace':r['namespaces'][0]='HTML'
    if bad=='attributes':r['after_attributes']='changed'
    if bad=='tags':r['tags'][0]='div'
    with pytest.raises(ValueError):validate_selection(r,'avatar')


def specimen():
    p={'mode':'proof','queries':[],'native':{'history':{'events':[]}}};t=100
    for g,base in [('avatar',1000),('other',2000)]:
        for r in [0,1]:
            for kind in ['reference','census']:
                phase=f'{kind}:0:{g}:{r}';value=row(g);value['geometry_counts']=[0]*32 if kind=='reference' else [];p['queries'].append({'phase':phase,'begin_ns':t,'end_ns':t+40,'result':value})
                for i in range(32):p['native']['history']['events'].append({'kind':'reference' if kind=='reference' else 'receiver','phase':phase,'address':hex(base+i),'attribute_absent':True,'begin_ns':t+i,'returned_ns':t+i+1})
                t+=50
    return p


def test_app_native_geometry_and_getter_witness_match(monkeypatch):
    import scripts.avatar_baseline.application_membership as module
    monkeypatch.setattr(module,'validate_workload',lambda p,raw:p['native'])
    result=proof(specimen(),[])
    assert result['receivers']==128 and result['references']==128 and result['acceptance'] is False


@pytest.mark.parametrize('bad',['reference','null','repeat','overlap','query','count'])
def test_app_native_identity_proof_is_not_inferred_from_js_alone(monkeypatch,bad):
    import scripts.avatar_baseline.application_membership as module
    monkeypatch.setattr(module,'validate_workload',lambda p,raw:p['native']);p=specimen();es=p['native']['history']['events']
    if bad=='reference':es[0]['address']='0xdead'
    if bad=='null':es[32]['attribute_absent']=False
    if bad=='repeat':es[96]['address']='0xdead'
    if bad=='overlap':
        for e in es:
            if ':other:' in e['phase']:e['address']=hex(int(e['address'],16)-1000)
    if bad=='query':p['queries'][0]['end_ns']=p['queries'][0]['begin_ns']
    if bad=='count':es.pop()
    with pytest.raises(ValueError):proof(p,[])


def test_phone_summary_does_not_turn_observer_pass_into_memory_acceptance():
    text=summary({'status':'application_calibration_passed','observer_qualified_for_application_attribution':True,'audit':{'cohorts':[],'errors':[]}})
    assert 'not memory acceptance' in text and 'no automatic app comparison' in text.lower()
    assert 'avatar-application-calibration' in text


@pytest.mark.parametrize('counts',[[],[-1]*32,['1']*32])
def test_actual_client_rect_counts_are_required_for_reference(monkeypatch,counts):
    import scripts.avatar_baseline.application_membership as module
    monkeypatch.setattr(module,'validate_workload',lambda p,raw:p['native'])
    p=specimen();p['queries'][0]['result']['geometry_counts']=counts
    with pytest.raises(ValueError):proof(p,[])


def test_compact_census_retains_every_getter_and_repeat():
    from tests.avatar_application_membership import expand_groups
    groups=[]
    for name in ['avatar','other']:
        r=row(name);r.pop('values');groups.append({'group':name,**r,'repeats':[[1]*32,[1]*32]})
    rows=expand_groups(groups)
    assert [(r['group'],r['repeat']) for r in rows]==[('avatar',0),('avatar',1),('other',0),('other',1)]
    assert sum(len(r['values']) for r in rows)==128
    assert rows[0]['before_attributes']==rows[1]['before_attributes']
    groups[0]['repeats'].pop()
    with pytest.raises(ValueError):expand_groups(groups)


def test_stable_main_scope_rejects_append_only_body_chrome():
    r=row('other');r.update(selection_scope='main-card-html',scope_root_count=1,in_main=[True]*32)
    validate_selection(r,'other',require_scope=True)
    r['in_main'][-1]=False
    with pytest.raises(ValueError):validate_selection(r,'other',require_scope=True)
