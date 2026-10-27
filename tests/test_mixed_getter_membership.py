from copy import deepcopy
import pytest
from scripts.avatar_baseline.analyze_element_membership import inspect, OFFSETS
from scripts.avatar_baseline.mixed_membership_fixture import SCHEDULE,tag


def specimen():
    p={'protocol':'native-element-membership-v5','status':'captured','acceptance':False,'forced_gc':False,
       'build_id':'1c5dca8527a61d07372e489142bee26af1bcaf71','browser_version':'156.0.8078.47',
       'frida_version':'17.5.1','count_per_group':32,'stage_count':12,'fixture_count_per_group':3000,
       'fixture_profile':'legacy-dom-svg-style-3000-v1','fixture_schedule':SCHEDULE,
       'observable':'absent-attribute-node-ns','attribute_namespace':'urn:css-is:membership:absent',
       'attribute_local_name':'absent','mode':'probe','begin_ns':1,'end_ns':1300000,'messages':[],
       'stages':[],'history':{'offsets':{**OFFSETS,'receiver':0x100cce80},'page_size':131072,'dropped':0,'events':[]}}
    def event(kind,address,start,phase,backend='0x10'):
        return {'kind':kind,'address':hex(address),'backend':backend,'phase':phase,
                'begin_ns':start,'callback_ready_ns':start+1,'returned_ns':start+2,'attribute_absent':True}
    for i,mode in enumerate(SCHEDULE):
        start=i*100000+1000;page=(i+1)*131072;phase=f'navigation:{i}'
        stage={'index':i,'fixture_mode':mode,'dom_before_sha256':'same','dom_after_sha256':'same',
               'begin_ns':start,'end_ns':start+99000,'censuses':[]}
        p['stages'].append(stage);p['history']['events'].append(event('allocate',page,start+10,phase))
        for q,(group,repeat) in enumerate((g,r) for g in ['avatar','other'] for r in [0,1]):
            label=f'census:{i}:{group}:{repeat}'
            stage['censuses'].append({'phase':label,'begin_ns':start+2000,'end_ns':start+90000,
                'result':{'count':32,'fixture_count':3000,'counts':[1]*32,'tags':[tag(mode,group)]*32}})
            for n in range(32):
                address=page+16+n*16+(1024 if group=='other' else 0)
                p['history']['events'].append(event('receiver',address,start+3000+q*1000+n*3,label,None))
        p['history']['events'].append(event('pool',page,start+95000,phase))
    return p


def test_every_mixed_mode_has_known_receiver_and_returned_generation():
    result=inspect(specimen())
    assert result['status']=='capability_passed'
    assert result['receiver_records']==1536 and result['matched_fraction']==1
    assert result['labelled_returned_generations']==12


@pytest.mark.parametrize('mode',['dom','svg','style'])
def test_global_returns_cannot_cover_a_missing_fixture_mode(mode):
    p=specimen()
    p['history']['events']=[e for e in p['history']['events'] if not
      (e['kind']=='pool' and SCHEDULE[int(e['phase'].split(':')[1])]==mode)]
    result=inspect(p)
    assert result['status']=='capability_failed'
    assert 'No labelled page return for mixed mode: '+mode in result['errors']


@pytest.mark.parametrize('bad',['schedule','tags','size','null'])
def test_mixed_identity_and_shape_contract_fails_closed(bad):
    p=specimen()
    if bad=='schedule':p['stages'][0]['fixture_mode']='svg'
    if bad=='tags':p['stages'][0]['censuses'][0]['result']['tags'][0]='path'
    if bad=='size':p['fixture_count_per_group']=4096
    if bad=='null':next(e for e in p['history']['events'] if e['kind']=='receiver')['attribute_absent']=False
    with pytest.raises(ValueError):inspect(p)


def test_navigation_armed_overflow_and_outside_query_cannot_be_silently_ignored():
    p=specimen();extra=deepcopy(next(e for e in p['history']['events'] if e['kind']=='receiver'))
    extra['phase']='census:0:overflow';p['history']['events'].append(extra)
    with pytest.raises(ValueError,match='phase'):inspect(p)
    p=specimen();entry=next(e for e in p['history']['events'] if e['kind']=='receiver')
    entry.update(begin_ns=2000,callback_ready_ns=2001,returned_ns=2002)
    with pytest.raises(ValueError,match='outside'):inspect(p)
